"""
UltraTrader 回測測試
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from datetime import datetime, timedelta

import pandas as pd

from backtest.engine import BacktestEngine
from strategy.base import BaseStrategy, Signal, SignalDirection
from strategy.orderbook_features import OrderbookFeatures
from strategy.orderbook_filter import OrderbookFilter
from strategy.momentum import AdaptiveMomentumStrategy
from core.market_data import KBar, MarketSnapshot
from core.position import Position
import risk.manager as risk_manager_module
from scripts.backtest_runner import (
    ORDERBOOK_PROFILES,
    _build_strategy_factory,
    _filter_data_by_date,
    _resolve_orderbook_profile,
)


class OrderbookBacktestTestStrategy(BaseStrategy):
    """測試用簡化策略：固定做多，並支援 orderbook filter"""

    def __init__(self):
        self.orderbook_filter = OrderbookFilter(
            spread_threshold_normal=2.0,
            spread_threshold_open=4.0,
            spread_threshold_crisis=6.0,
            pressure_min_score=2,
        )
        self._latest_orderbook_features = OrderbookFeatures()
        self._last_orderbook_decision_reason = ""
        self._last_orderbook_blocked = False

    @property
    def name(self) -> str:
        return "OrderbookBacktestTest"

    def update_orderbook_features(self, features):
        self._latest_orderbook_features = features or OrderbookFeatures()

    def on_kbar(self, kbar: KBar, snapshot: MarketSnapshot):
        self._last_orderbook_decision_reason = ""
        self._last_orderbook_blocked = False
        decision = self.orderbook_filter.allow_entry(
            SignalDirection.BUY,
            self._latest_orderbook_features,
        )
        self._last_orderbook_decision_reason = decision.reason
        self._last_orderbook_blocked = not decision.allowed
        if not decision.allowed:
            return None
        return Signal(
            direction=SignalDirection.BUY,
            strength=0.8,
            stop_loss=snapshot.price - 50,
            take_profit=snapshot.price + 80,
            reason="test entry",
        )

    def check_exit(self, position: Position, snapshot: MarketSnapshot):
        if position.bars_since_entry >= 1:
            return Signal(
                direction=SignalDirection.CLOSE,
                strength=1.0,
                stop_loss=0,
                take_profit=0,
                reason="test exit",
            )
        return None


class TestBacktestEngineOrderbook(unittest.TestCase):
    """測試 orderbook 回測比較"""

    def _build_data(self, bars: int = 24) -> pd.DataFrame:
        start = datetime(2026, 4, 1, 9, 0)
        rows = []
        price = 22000.0
        for i in range(bars):
            dt = start + timedelta(minutes=i)
            open_price = price
            close_price = price + 8
            rows.append({
                "datetime": dt,
                "open": open_price,
                "high": close_price + 3,
                "low": open_price - 2,
                "close": close_price,
                "volume": 120,
            })
            price = close_price
        return pd.DataFrame(rows)

    def test_backtest_resets_persisted_risk_state(self):
        """回測應隔離持久化風控狀態，不受實盤殘留影響"""
        engine = BacktestEngine(initial_balance=100000, slippage=0, instrument="TMF")
        original_loader = risk_manager_module.load_risk_state
        risk_manager_module.load_risk_state = lambda: {
            "today": datetime.now().strftime("%Y-%m-%d"),
            "peak_equity": 100000,
            "daily_loss": 999999,
            "consecutive_losses": 99,
        }
        try:
            result = engine.run(
                data=self._build_data(),
                strategy=OrderbookBacktestTestStrategy(),
                risk_profile="balanced",
                use_orderbook_filter=False,
            )
        finally:
            risk_manager_module.load_risk_state = original_loader

        self.assertGreater(len(result.trades), 0)

    def test_run_orderbook_comparison_returns_two_results(self):
        """比較模式應回傳 baseline 與 filtered 兩組結果"""
        engine = BacktestEngine(initial_balance=100000, slippage=0, instrument="TMF")
        engine._build_orderbook_proxy_features = lambda *args, **kwargs: OrderbookFeatures(
            spread=3.0,
            orderbook_ready=True,
            pressure_score=-3,
            pressure_bias="bearish",
        )

        results = engine.run_orderbook_comparison(
            data=self._build_data(),
            strategy_factory=OrderbookBacktestTestStrategy,
            risk_profile="balanced",
        )

        self.assertIn("baseline", results)
        self.assertIn("orderbook_filtered", results)
        self.assertFalse(results["baseline"].orderbook_enabled)
        self.assertTrue(results["orderbook_filtered"].orderbook_enabled)

    def test_filtered_result_tracks_orderbook_rejections(self):
        """當 proxy orderbook 反向時，filtered 應留下拒單統計"""
        engine = BacktestEngine(initial_balance=100000, slippage=0, instrument="TMF")
        engine._build_orderbook_proxy_features = lambda *args, **kwargs: OrderbookFeatures(
            spread=3.0,
            orderbook_ready=True,
            pressure_score=-3,
            pressure_bias="bearish",
        )

        baseline = engine.run(
            data=self._build_data(),
            strategy=OrderbookBacktestTestStrategy(),
            risk_profile="balanced",
            use_orderbook_filter=False,
        )
        filtered = engine.run(
            data=self._build_data(),
            strategy=OrderbookBacktestTestStrategy(),
            risk_profile="balanced",
            use_orderbook_filter=True,
        )

        self.assertGreater(len(baseline.trades), 0)
        self.assertEqual(len(filtered.trades), 0)
        self.assertGreater(filtered.orderbook_metrics["entry_checks"], 0)
        self.assertGreater(filtered.orderbook_metrics["entry_rejected"], 0)
        self.assertGreater(filtered.orderbook_metrics["avg_spread_checked"], 0)


class TestBacktestRunnerHelpers(unittest.TestCase):
    """測試回測腳本的日期切分與參數工廠"""

    def test_filter_data_by_date_uses_inclusive_date_range(self):
        data = pd.DataFrame(
            {
                "datetime": pd.to_datetime(
                    [
                        "2026-03-02 23:59:00",
                        "2026-03-03 09:00:00",
                        "2026-03-21 13:45:00",
                        "2026-03-22 00:00:00",
                    ]
                ),
                "open": [1, 2, 3, 4],
                "high": [1, 2, 3, 4],
                "low": [1, 2, 3, 4],
                "close": [1, 2, 3, 4],
                "volume": [1, 1, 1, 1],
            }
        )

        filtered = _filter_data_by_date(data, "2026-03-03", "2026-03-21")

        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered.iloc[0]["datetime"], pd.Timestamp("2026-03-03 09:00:00"))
        self.assertEqual(filtered.iloc[-1]["datetime"], pd.Timestamp("2026-03-21 13:45:00"))

    def test_build_strategy_factory_applies_orderbook_profile(self):
        factory = _build_strategy_factory("momentum", "A5")

        strategy = factory()

        self.assertIsInstance(strategy, AdaptiveMomentumStrategy)
        self.assertEqual(
            strategy.orderbook_filter.spread_threshold_normal,
            ORDERBOOK_PROFILES["A5"]["spread_threshold_normal"],
        )
        self.assertEqual(
            strategy.orderbook_filter.spread_threshold_open,
            ORDERBOOK_PROFILES["A5"]["spread_threshold_open"],
        )
        self.assertEqual(
            strategy.orderbook_filter.spread_threshold_crisis,
            ORDERBOOK_PROFILES["A5"]["spread_threshold_crisis"],
        )
        self.assertEqual(
            strategy.orderbook_filter.pressure_min_score,
            ORDERBOOK_PROFILES["A5"]["pressure_min_score"],
        )

    def test_resolve_orderbook_profile_uses_fixed_mapping(self):
        self.assertEqual(_resolve_orderbook_profile("conservative", None), "A1")
        self.assertEqual(_resolve_orderbook_profile("balanced", None), "A3")
        self.assertEqual(_resolve_orderbook_profile("aggressive", None), "A4")
        self.assertEqual(_resolve_orderbook_profile("dangerous", None), "A5")

    def test_resolve_orderbook_profile_prefers_explicit_override(self):
        self.assertEqual(_resolve_orderbook_profile("conservative", "A4"), "A4")


if __name__ == "__main__":
    unittest.main()
