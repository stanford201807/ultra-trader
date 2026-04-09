"""
UltraTrader 策略測試
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from unittest.mock import MagicMock
from datetime import datetime

from core.market_data import KBar, MarketSnapshot, IndicatorEngine, Tick
from strategy.filters import MarketRegime, MarketRegimeClassifier, SessionPhase
from strategy.orderbook_features import OrderbookFeatureEngine, OrderbookFeatures
from strategy.orderbook_filter import OrderbookFilter
from strategy.signals import MultiFactorSignalGenerator
from strategy.momentum import AdaptiveMomentumStrategy
from strategy.base import Signal, SignalDirection
from core.engine import TradingEngine, InstrumentPipeline, EngineState
from core.instrument_config import get_spec
from core.position import PositionManager
from strategy.orderbook_profiles import ORDERBOOK_PROFILES


class TestMarketRegimeClassifier(unittest.TestCase):
    """測試市場狀態分類器"""

    def setUp(self):
        self.classifier = MarketRegimeClassifier()

    def test_strong_trend_up(self):
        """ADX 高 + 多頭排列 → 強勢上漲"""
        snap = MarketSnapshot(
            adx=40, plus_di=30, minus_di=15,
            ema5=22100, ema10=22050, ema20=22000, ema60=21900,
            atr_ratio=1.0,
        )
        # 需要連續 2 根確認（hysteresis）
        self.classifier.classify(snap)
        regime = self.classifier.classify(snap)
        self.assertEqual(regime, MarketRegime.STRONG_TREND_UP)

    def test_strong_trend_down(self):
        """ADX 高 + 空頭排列 → 強勢下跌"""
        snap = MarketSnapshot(
            adx=39, plus_di=12, minus_di=28,
            ema5=21800, ema10=21850, ema20=21900, ema60=22000,
            atr_ratio=1.0,
        )
        self.classifier.classify(snap)
        regime = self.classifier.classify(snap)
        self.assertEqual(regime, MarketRegime.STRONG_TREND_DOWN)

    def test_ranging(self):
        """ADX 低 → 盤整"""
        snap = MarketSnapshot(
            adx=15, plus_di=20, minus_di=18,
            ema5=22000, ema10=22010, ema20=22005, ema60=22008,
            atr_ratio=0.8,
        )
        # 初始狀態就是 RANGING，所以不需要遲滯
        regime = self.classifier.classify(snap)
        self.assertEqual(regime, MarketRegime.RANGING)

    def test_volatile(self):
        """ATR 比率過高 → 劇烈波動"""
        snap = MarketSnapshot(
            adx=30, atr_ratio=2.0,
            ema5=22000, ema20=22000, ema60=22000,
        )
        self.classifier.classify(snap)
        regime = self.classifier.classify(snap)
        self.assertEqual(regime, MarketRegime.VOLATILE)

    def test_hysteresis(self):
        """遲滯測試：需要連續 2 根 K 棒才切換"""
        snap_trend = MarketSnapshot(
            adx=35, plus_di=25, minus_di=12,
            ema5=22100, ema20=22000, ema60=21900,
            atr_ratio=1.0,
        )
        snap_range = MarketSnapshot(
            adx=15, plus_di=20, minus_di=18,
            ema5=22000, ema20=22000, ema60=22000,
            atr_ratio=0.8,
        )

        # 初始是 RANGING
        # 1 根趨勢 K 棒 → 還是 RANGING
        regime = self.classifier.classify(snap_trend)
        self.assertEqual(regime, MarketRegime.RANGING)

        # 第 2 根趨勢 → 切換
        regime = self.classifier.classify(snap_trend)
        self.assertNotEqual(regime, MarketRegime.RANGING)


class TestMultiFactorSignalGenerator(unittest.TestCase):
    """測試多因子訊號產生器"""

    def setUp(self):
        self.generator = MultiFactorSignalGenerator()

    def test_strong_buy_signal(self):
        """所有因子利多 → 產生強買入訊號"""
        snap = MarketSnapshot(
            price=22100,
            ema5=22080, ema10=22060, ema20=22000, ema60=21900,
            rsi=62, rsi_ma5=60, rsi_ma10=55,
            adx=35, plus_di=28, minus_di=15,
            atr=50, atr_ratio=1.0, atr_ma20=50,
            volume=100, volume_ma20=60, volume_ratio=1.67,
            recent_high=22090, recent_low=21950,
        )
        signal = self.generator.generate(snap, MarketRegime.STRONG_TREND_UP)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, SignalDirection.BUY)
        self.assertGreater(signal.strength, 0.5)

    def test_no_signal_in_ranging(self):
        """盤整市 → 不產生動量訊號"""
        snap = MarketSnapshot(price=22000, adx=15, atr_ratio=0.8)
        signal = self.generator.generate(snap, MarketRegime.RANGING)
        self.assertIsNone(signal)

    def test_no_signal_in_volatile(self):
        """劇烈波動 → 不交易"""
        snap = MarketSnapshot(price=22000, atr_ratio=2.5)
        signal = self.generator.generate(snap, MarketRegime.VOLATILE)
        self.assertIsNone(signal)


class TestAdaptiveMomentumStrategy(unittest.TestCase):
    """測試自適應動量策略"""

    def setUp(self):
        self.strategy = AdaptiveMomentumStrategy()

    def test_exit_stop_loss_long(self):
        """做多停損觸發"""
        from core.position import Position, Side

        position = Position(
            side=Side.LONG,
            entry_price=22000,
            quantity=1,
            stop_loss=21900,
            take_profit=22200,
            entry_time=datetime.now(),
        )

        snap = MarketSnapshot(price=21890, atr=50)
        signal = self.strategy.check_exit(position, snap)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, SignalDirection.CLOSE)
        self.assertIn("停損", signal.reason)

    def test_exit_take_profit_short(self):
        """做空停利觸發"""
        from core.position import Position, Side

        position = Position(
            side=Side.SHORT,
            entry_price=22000,
            quantity=1,
            stop_loss=22100,
            take_profit=21800,
            entry_time=datetime.now(),
        )

        snap = MarketSnapshot(price=21790, atr=50)
        signal = self.strategy.check_exit(position, snap)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, SignalDirection.CLOSE)
        self.assertIn("停利", signal.reason)

    def test_no_exit_when_flat(self):
        """空倉不觸發出場"""
        from core.position import Position
        position = Position()
        snap = MarketSnapshot(price=22000)
        signal = self.strategy.check_exit(position, snap)
        self.assertIsNone(signal)

    def test_on_kbar_rejects_when_orderbook_conflicts(self):
        """多因子成立但 orderbook 明顯反向時，應拒絕進場"""
        self.strategy.regime_classifier.classify = lambda snapshot: MarketRegime.STRONG_TREND_UP
        self.strategy.signal_generator.generate = lambda *args, **kwargs: Signal(
            direction=SignalDirection.BUY,
            strength=0.8,
            stop_loss=21900,
            take_profit=22200,
            reason="test buy",
        )
        self.strategy._session.get_phase = lambda now=None: SessionPhase.NORMAL
        self.strategy.update_orderbook_features(OrderbookFeatures(
            spread=1.0,
            orderbook_ready=True,
            pressure_score=-3,
            pressure_bias="bearish",
        ))

        snap = MarketSnapshot(price=22000, adx=30, atr=50, atr_ratio=1.0)
        signal = self.strategy.on_kbar(
            KBar(datetime=datetime.now(), open=22000, high=22010, low=21990, close=22000, volume=100),
            snap,
        )
        self.assertIsNone(signal)

    def test_on_kbar_falls_back_when_orderbook_not_ready(self):
        """orderbook 未就緒時，應安全退化為原本策略行為"""
        self.strategy.regime_classifier.classify = lambda snapshot: MarketRegime.STRONG_TREND_UP
        expected = Signal(
            direction=SignalDirection.BUY,
            strength=0.8,
            stop_loss=21900,
            take_profit=22200,
            reason="test buy",
        )
        self.strategy.signal_generator.generate = lambda *args, **kwargs: expected
        self.strategy._session.get_phase = lambda now=None: SessionPhase.NORMAL
        self.strategy.update_orderbook_features(OrderbookFeatures(orderbook_ready=False))

        snap = MarketSnapshot(price=22000, adx=30, atr=50, atr_ratio=1.0)
        signal = self.strategy.on_kbar(
            KBar(datetime=datetime.now(), open=22000, high=22010, low=21990, close=22000, volume=100),
            snap,
        )
        self.assertIs(signal, expected)


class TestOrderbookFeatures(unittest.TestCase):
    """測試 L1 orderbook 特徵引擎"""

    def test_market_snapshot_has_safe_orderbook_defaults(self):
        """MarketSnapshot 的 orderbook 欄位有安全預設值"""
        snap = MarketSnapshot()
        self.assertEqual(snap.spread, 0.0)
        self.assertEqual(snap.mid_price, 0.0)
        self.assertEqual(snap.pressure_bias, "neutral")
        self.assertFalse(snap.orderbook_ready)

    def test_feature_engine_builds_bullish_pressure(self):
        """連續 bid 上移 / ask 下移時，應形成 bullish pressure"""
        engine = OrderbookFeatureEngine(window_size=5, tick_size=1.0, bias_threshold=2)

        ticks = [
            Tick(datetime=datetime.now(), price=22000, volume=1, bid_price=21999, ask_price=22001),
            Tick(datetime=datetime.now(), price=22001, volume=1, bid_price=22000, ask_price=22001),
            Tick(datetime=datetime.now(), price=22001, volume=1, bid_price=22001, ask_price=22002),
            Tick(datetime=datetime.now(), price=22002, volume=1, bid_price=22002, ask_price=22002),
        ]

        features = OrderbookFeatures()
        for tick in ticks:
            features = engine.update(tick)

        self.assertTrue(features.orderbook_ready)
        self.assertGreater(features.pressure_score, 0)
        self.assertEqual(features.pressure_bias, "bullish")
        self.assertGreater(features.microprice_proxy, 0)
        self.assertAlmostEqual(features.spread, 0.0)

    def test_invalid_bid_ask_keeps_previous_features(self):
        """無效 bid/ask 不應污染已建立的特徵狀態"""
        engine = OrderbookFeatureEngine(window_size=5)
        valid_tick = Tick(datetime=datetime.now(), price=22000, volume=1, bid_price=21999, ask_price=22001)
        invalid_tick = Tick(datetime=datetime.now(), price=22000, volume=1, bid_price=22005, ask_price=22001)

        first = engine.update(valid_tick)
        second = engine.update(invalid_tick)

        self.assertEqual(first.last_bid_price, second.last_bid_price)
        self.assertEqual(first.last_ask_price, second.last_ask_price)
        self.assertEqual(first.ticks_seen, second.ticks_seen)


class TestOrderbookFilter(unittest.TestCase):
    """測試 orderbook 進場過濾器"""

    def setUp(self):
        self.filter = OrderbookFilter(
            spread_threshold_normal=2.0,
            spread_threshold_open=4.0,
            spread_threshold_crisis=6.0,
            pressure_min_score=2,
        )

    def test_filter_falls_back_when_not_ready(self):
        """特徵未就緒時安全退化為放行"""
        features = OrderbookFeatures(orderbook_ready=False)
        decision = self.filter.allow_entry(SignalDirection.BUY, features)
        self.assertTrue(decision.allowed)
        self.assertIn("fallback", decision.reason)

    def test_filter_rejects_wide_spread(self):
        """spread 過大時拒絕進場"""
        features = OrderbookFeatures(
            spread=3.0,
            orderbook_ready=True,
            pressure_score=0,
            pressure_bias="neutral",
        )
        decision = self.filter.allow_entry(SignalDirection.BUY, features)
        self.assertFalse(decision.allowed)
        self.assertIn("spread", decision.reason)

    def test_filter_allows_wider_spread_in_strong_trend(self):
        """強趨勢時應使用較寬的 spread 門檻"""
        features = OrderbookFeatures(
            spread=5.0,
            orderbook_ready=True,
            pressure_score=0,
            pressure_bias="neutral",
        )
        decision = self.filter.allow_entry(
            SignalDirection.BUY,
            features,
            regime=MarketRegime.STRONG_TREND_UP,
            now=datetime(2026, 3, 24, 10, 0),
        )
        self.assertTrue(decision.allowed)
        self.assertIn("aligned", decision.reason)

    def test_filter_uses_tighter_threshold_at_night_for_strong_trend(self):
        """強趨勢夜盤應保留較保守的 spread 門檻"""
        features = OrderbookFeatures(
            spread=5.0,
            orderbook_ready=True,
            pressure_score=0,
            pressure_bias="neutral",
        )
        decision = self.filter.allow_entry(
            SignalDirection.BUY,
            features,
            regime=MarketRegime.STRONG_TREND_UP,
            now=datetime(2026, 3, 24, 21, 0),
        )
        self.assertFalse(decision.allowed)
        self.assertIn("spread", decision.reason)

    def test_filter_expands_threshold_when_volatility_is_high(self):
        """高波動時應放寬 spread 門檻"""
        features = OrderbookFeatures(
            spread=2.3,
            orderbook_ready=True,
            pressure_score=0,
            pressure_bias="neutral",
        )
        decision = self.filter.allow_entry(
            SignalDirection.BUY,
            features,
            volatility_ratio=1.5,
        )
        self.assertTrue(decision.allowed)
        self.assertIn("aligned", decision.reason)

    def test_filter_tightens_threshold_when_volatility_is_low(self):
        """低波動時應收緊 spread 門檻"""
        features = OrderbookFeatures(
            spread=2.0,
            orderbook_ready=True,
            pressure_score=0,
            pressure_bias="neutral",
        )
        decision = self.filter.allow_entry(
            SignalDirection.BUY,
            features,
            volatility_ratio=0.5,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("spread", decision.reason)

    def test_filter_rejects_opposite_pressure_for_buy(self):
        """做多時遇到明顯賣壓應拒單"""
        features = OrderbookFeatures(
            spread=1.0,
            orderbook_ready=True,
            pressure_score=-3,
            pressure_bias="bearish",
        )
        decision = self.filter.allow_entry(SignalDirection.BUY, features)
        self.assertFalse(decision.allowed)
        self.assertIn("bearish", decision.reason)

    def test_filter_allows_aligned_pressure(self):
        """方向一致且 spread 正常時應放行"""
        features = OrderbookFeatures(
            spread=1.0,
            orderbook_ready=True,
            pressure_score=3,
            pressure_bias="bullish",
        )
        decision = self.filter.allow_entry(SignalDirection.BUY, features)
        self.assertTrue(decision.allowed)
        self.assertIn("aligned", decision.reason)


class TestEngineOrderbookIntegration(unittest.TestCase):
    """測試 engine 與 orderbook 特徵整合"""

    def test_process_tick_updates_pipeline_orderbook_features(self):
        """tick 流入後，pipeline 應更新 orderbook 特徵與 snapshot"""
        spec = get_spec("TMF")
        engine = TradingEngine()
        engine.instruments = ["TMF"]
        engine.pipelines = {"TMF": InstrumentPipeline(code="TMF", spec=spec, strategy=AdaptiveMomentumStrategy())}
        engine.position_manager = PositionManager(
            instruments=["TMF"],
            configs={"TMF": spec},
            initial_balance=100000,
        )
        engine.broker = None
        engine.state = EngineState.PAUSED
        engine._ws_broadcast = None
        engine._tick_count = 0

        ticks = [
            Tick(datetime=datetime.now(), price=22000, volume=1, bid_price=21999, ask_price=22001, instrument="TMF"),
            Tick(datetime=datetime.now(), price=22001, volume=1, bid_price=22000, ask_price=22001, instrument="TMF"),
        ]

        for tick in ticks:
            engine.events._process_tick(tick)

        pipeline = engine.pipelines["TMF"]
        self.assertTrue(pipeline.orderbook_features.orderbook_ready)
        self.assertEqual(pipeline.snapshot.spread, pipeline.orderbook_features.spread)
        self.assertEqual(pipeline.snapshot.pressure_bias, pipeline.orderbook_features.pressure_bias)
        self.assertTrue(pipeline.snapshot.orderbook_ready)

    def test_set_risk_profile_maps_dangerous_to_crisis_and_updates_orderbook_profile(self):
        """dangerous 應映射為 crisis，並套用對應 orderbook 參數"""
        spec = get_spec("TMF")
        engine = TradingEngine()
        engine.risk_manager = MagicMock()
        engine.instruments = ["TMF"]
        engine.pipelines = {"TMF": InstrumentPipeline(code="TMF", spec=spec, strategy=AdaptiveMomentumStrategy())}
        engine.position_manager = PositionManager(
            instruments=["TMF"],
            configs={"TMF": spec},
            initial_balance=100000,
        )

        engine.set_risk_profile("dangerous")

        strategy = engine.pipelines["TMF"].strategy
        self.assertEqual(engine.risk_profile, "crisis")
        self.assertEqual(strategy.signal_generator.risk_profile, "crisis")
        self.assertEqual(
            strategy.orderbook_filter.spread_threshold_normal,
            ORDERBOOK_PROFILES["A5"]["spread_threshold_normal"],
        )
        self.assertEqual(
            strategy.orderbook_filter.pressure_min_score,
            ORDERBOOK_PROFILES["A5"]["pressure_min_score"],
        )

    def test_set_risk_profile_rejects_invalid_value(self):
        """未知風險值應直接拒絕"""
        engine = TradingEngine()
        with self.assertRaises(ValueError):
            engine.set_risk_profile("all-in")


if __name__ == "__main__":
    unittest.main()
