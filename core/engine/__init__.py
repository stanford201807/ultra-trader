"""
UltraTrader 交易引擎（多商品 Facade 架構版）
將龐大的引擎邏輯拆分為：
- EventProcessor：事件分派、Tick/KBar 處理、策略決策
- OrderExecutor：進出場邏輯、冷卻機制
- HealthMonitor：心跳、異常偵測、持倉核對
- EngineQueries：狀態查詢
"""

import os
import threading
from datetime import datetime
from typing import Optional, Callable, Dict, Any, List

from loguru import logger
from dotenv import load_dotenv

from core.engine.models import EngineState, InstrumentPipeline
from core.engine.health import HealthMonitor
from core.engine.executor import OrderExecutor
from core.engine.queries import EngineQueries
from core.engine.events import EventProcessor

import math
def _safe_round(val, decimals=1, default=0):
    """安全 round — NaN/Inf 返回 default"""
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return default
    return round(val, decimals)

from core.broker import BaseBroker, MockBroker, ShioajiBroker, OrderResult
from core.market_data import TickAggregator, IndicatorEngine, MarketSnapshot
from core.position import PositionManager
from core.logger import setup_logger, log_trade
from core.instrument_config import get_spec
from strategy.base import BaseStrategy
from strategy.momentum import AdaptiveMomentumStrategy
from strategy.gold_trend import GoldTrendStrategy
from strategy.orderbook_features import OrderbookFeatureEngine
from strategy.orderbook_profiles import ORDERBOOK_PROFILES
from risk.manager import RiskManager
from risk.profile_config import normalize_risk_profile, get_orderbook_profile_for_risk
from core.performance import PerformanceTracker


def _create_strategy(strategy_type: str) -> BaseStrategy:
    """根據類型建立策略"""
    if strategy_type == "gold_trend":
        return GoldTrendStrategy()
    return AdaptiveMomentumStrategy()


class TradingEngine:
    """
    交易引擎 Facade
    整合：Broker, PositionManager, RiskManager, Strategy 以及四個核心子模組
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.state = EngineState.INITIALIZING

        # 核心設定
        self.trading_mode: str = "simulation"
        self.risk_profile: str = "balanced"
        self.timeframe: int = 1
        self.auto_trade: bool = False

        # 商品管線
        self.instruments: List[str] = []
        self.pipelines: Dict[str, InstrumentPipeline] = {}

        # 基礎元件
        self.broker: Optional[BaseBroker] = None
        self.risk_manager: Optional[RiskManager] = None
        self.position_manager: Optional[PositionManager] = None
        self.performance: Optional[PerformanceTracker] = None
        self._ws_broadcast: Optional[Callable] = None

        # 向後相容單商品屬性
        self.aggregator: Optional[TickAggregator] = None
        self.indicator_engine: Optional[IndicatorEngine] = None
        self.strategy: Optional[BaseStrategy] = None
        self.snapshot: MarketSnapshot = MarketSnapshot()

        # Dashboard/情報模組（可選）— 預設關閉但需存在屬性避免 AttributeError
        self.data_collector = None
        self.left_side_engine = None

        # 子系統注入
        self.health_monitor = HealthMonitor(self)
        self.executor = OrderExecutor(self)
        self.queries = EngineQueries(self)
        self.events = EventProcessor(self)

    def _reset_runtime_components(self) -> None:
        """重建可在模式切換時污染的執行期元件。"""
        self.broker = None
        self.risk_manager = None
        self.position_manager = None
        self.performance = None
        self.pipelines = {}
        self.aggregator = None
        self.indicator_engine = None
        self.strategy = None
        self.snapshot = MarketSnapshot()
        self.health_monitor = HealthMonitor(self)
        self.executor = OrderExecutor(self)
        self.queries = EngineQueries(self)
        self.events = EventProcessor(self)

    # ━━━━━━━━━━━━━━━━ 生命週期 ━━━━━━━━━━━━━━━━

    def initialize(self, config: Optional[dict] = None) -> bool:
        """初始化引擎及所有相依元件"""
        with self._lock:
            try:
                config = config or {}
                load_dotenv()
                setup_logger()
                logger.info("Initializing Trading Engine...")
                self._reset_runtime_components()

                # 讀取設定
                default_trading_mode = os.getenv("TRADING_MODE", "simulation")
                self.trading_mode = config.get("trading_mode", default_trading_mode)
                self.risk_profile = normalize_risk_profile(config.get("risk_profile", "balanced"))
                self.timeframe = config.get("timeframe", 1)
                default_instruments = [
                    code.strip()
                    for code in os.getenv("INSTRUMENTS", "TMF").split(",")
                    if code.strip()
                ] or ["TMF"]
                self.instruments = config.get("instruments", default_instruments)
                strategy_type = config.get("strategy_type", "momentum")
                self.auto_trade = config.get("auto_trade", False)

                # 初始化部位追蹤
                instrument_specs = {code: get_spec(code) for code in self.instruments}
                self.position_manager = PositionManager(
                    instruments=self.instruments,
                    configs=instrument_specs,
                    initial_balance=300000,
                )

                # 初始化 Broker
                if self.trading_mode in ["live", "paper"]:
                    api_key = os.getenv("SHIOAJI_API_KEY")
                    secret_key = os.getenv("SHIOAJI_SECRET_KEY")
                    if not api_key or not secret_key:
                        raise ValueError("缺少 Shioaji API 或 Secret Key")
                    is_live = (self.trading_mode == "live")
                    self.broker = ShioajiBroker(
                        api_key=api_key,
                        secret_key=secret_key,
                        simulation=not is_live,
                        contract_codes=self.instruments,
                    )
                else:
                    self.broker = MockBroker()

                # 初始化風控
                self.risk_manager = RiskManager(self.risk_profile)
                self.risk_manager.set_profile(self.risk_profile)

                # 建立商品處理管線
                for code in self.instruments:
                    spec = instrument_specs[code]
                    if spec.strategy_type == "gold_trend":
                        strat = GoldTrendStrategy()
                    else:
                        strat = _create_strategy(strategy_type)

                    pipeline = InstrumentPipeline(
                        code=code,
                        spec=spec,
                        aggregator=TickAggregator(intervals=[self.timeframe, 5, 15]),
                        indicator_engine=IndicatorEngine(lookback_period=200),
                        indicator_engine_5m=IndicatorEngine(lookback_period=200),
                        indicator_engine_15m=IndicatorEngine(lookback_period=200),
                        orderbook_engine=OrderbookFeatureEngine(),
                        strategy=strat
                    )
                    # 設置 K 棒完成回調
                    pipeline.aggregator.on_kbar_complete(
                        self.timeframe,
                        lambda kbar, c=code, cb=self.events.on_kbar_complete: cb(c, kbar),
                    )
                    pipeline.aggregator.on_kbar_complete(
                        5, lambda kbar, c=code: self.events._on_kbar_5m_complete(c, kbar)
                    )
                    pipeline.aggregator.on_kbar_complete(
                        15, lambda kbar, c=code: self.events._on_kbar_15m_complete(c, kbar)
                    )

                    self.pipelines[code] = pipeline

                # 向後相容單商品指標
                p0 = self.pipelines[self.instruments[0]]
                self.aggregator = p0.aggregator
                self.indicator_engine = p0.indicator_engine
                self.strategy = p0.strategy

                # 初始化績效追蹤
                self.performance = PerformanceTracker(trading_mode=self.trading_mode)
                self.performance.starting_balance = self.position_manager.balance
                self._apply_risk_profile_to_strategies(self.risk_profile)

                self.state = EngineState.INITIALIZING
                logger.info("Engine successfully initialized.")
                return True

            except Exception as e:
                logger.error(f"引擎初始化失敗: {e}")
                self.state = EngineState.ERROR
                return False

    def start(self):
        """啟動交易引擎"""
        with self._lock:
            if self.state in [EngineState.RUNNING, EngineState.PAUSED]:
                return

            try:
                # 連線與訂閱
                if not self.broker.connect():
                    raise RuntimeError("Broker connect failed.")

                # 真實行情模式先暖機歷史 K 棒，讓 Dashboard 立即有可視資料
                if self.trading_mode in ["live", "paper"]:
                    self._warmup_historical_bars()

                self.broker.subscribe_tick(self.events.on_tick)

                # 啟動子系統執行緒
                self.events.start()
                self.health_monitor.start()

                self.state = EngineState.RUNNING
                self._broadcast_state()
                logger.info("Trading engine started. Subsystems running.")

            except Exception as e:
                logger.error(f"引擎啟動失敗: {e}")
                self.state = EngineState.ERROR

    def _warmup_historical_bars(self) -> None:
        """從券商載入歷史 1 分 K，預熱聚合器與指標。"""
        if not self.broker or not hasattr(self.broker, "get_historical_kbars"):
            return

        for instrument in self.instruments:
            pipeline = self.pipelines.get(instrument)
            if not pipeline:
                continue

            try:
                historical_bars = self.broker.get_historical_kbars(instrument=instrument, count=200)
                if not historical_bars:
                    continue

                pipeline.aggregator.seed_bars(1, historical_bars)

                for interval in sorted(set([self.timeframe, 5, 15])):
                    if interval == 1:
                        continue
                    timeframe_bars = self._aggregate_historical_bars(historical_bars, interval)
                    pipeline.aggregator.seed_bars(interval, timeframe_bars)

                if len(historical_bars) >= 5:
                    history_df = pipeline.aggregator.get_bars_dataframe(1, count=200)
                    if not history_df.empty:
                        pipeline.snapshot = pipeline.indicator_engine.update(history_df)

                logger.info(f"[Warmup] {instrument}: 載入 {len(historical_bars)} 根歷史 K 棒")
            except Exception as exc:
                logger.warning(f"[Warmup] {instrument} 歷史 K 棒暖機失敗: {exc}")

    def _aggregate_historical_bars(self, bars: list[Any], interval: int) -> list[Any]:
        """將 1 分 K 聚合成指定分鐘週期。"""
        if interval <= 1 or not bars:
            return list(bars)

        aggregated = []
        current_group = []
        current_bucket = None

        for bar in sorted(bars, key=lambda item: item.datetime):
            bucket_minute = (bar.datetime.hour * 60 + bar.datetime.minute) // interval
            bucket_key = (bar.datetime.date(), bucket_minute)

            if current_bucket is None or bucket_key == current_bucket:
                current_group.append(bar)
                current_bucket = bucket_key
                continue

            aggregated.append(self._merge_bar_group(current_group, interval))
            current_group = [bar]
            current_bucket = bucket_key

        if current_group:
            aggregated.append(self._merge_bar_group(current_group, interval))

        return aggregated

    @staticmethod
    def _merge_bar_group(bars: list[Any], interval: int) -> Any:
        from core.market_data import KBar

        first_bar = bars[0]
        last_bar = bars[-1]
        return KBar(
            datetime=first_bar.datetime,
            open=first_bar.open,
            high=max(bar.high for bar in bars),
            low=min(bar.low for bar in bars),
            close=last_bar.close,
            volume=sum(bar.volume for bar in bars),
            interval=interval,
        )

    def stop(self):
        """停止引擎"""
        with self._lock:
            if self.state == EngineState.STOPPED:
                return

            self.state = EngineState.STOPPED
            self._broadcast_state()

            # 停止子系統
            self.events.stop()
            self.health_monitor.stop()

            # 平倉保護
            if self.position_manager:
                for inst, pos in self.position_manager.positions.items():
                    if pos and not pos.is_flat:
                        price = self.pipelines[inst].snapshot.price
                        self.executor.force_close(inst, "engine stop/exit", price)

            if self.broker:
                self.broker.disconnect()

            logger.info("Trading engine cleanly stopped.")

    def pause(self):
        """暫停策略決策（僅更新資料）"""
        with self._lock:
            if self.state == EngineState.RUNNING:
                self.state = EngineState.PAUSED
                self._broadcast_state()
                logger.info("Engine paused.")

    def resume(self):
        """恢復策略決策"""
        with self._lock:
            if self.state == EngineState.PAUSED:
                self.state = EngineState.RUNNING
                self._broadcast_state()
                logger.info("Engine resumed.")

    # ━━━━━━━━━━━━━━━━ WebSocket 與命令 ━━━━━━━━━━━━━━━━

    def set_ws_broadcast(self, callback: Callable):
        """註冊廣播回調"""
        self._ws_broadcast = callback

    def _broadcast(self, type_: str, data: Any):
        """執行廣播"""
        if self._ws_broadcast:
            message = {"type": type_, "data": data}
            try:
                self._ws_broadcast(message)
            except TypeError:
                self._ws_broadcast(type_, data)

    def _broadcast_state(self):
        self._broadcast("state", self.get_state())

    def toggle_auto_trade(self, enabled: Optional[bool] = None) -> bool:
        """切換或設定自動交易開關"""
        self.auto_trade = (not self.auto_trade) if enabled is None else bool(enabled)
        self._broadcast_state()
        self._broadcast("settings", {"auto_trade": self.auto_trade})
        logger.info(f"自動交易已切換為：{'ON' if self.auto_trade else 'OFF'}")
        return self.auto_trade

    def set_risk_profile(self, profile: str) -> bool:
        """切換風控設定檔"""
        profile = normalize_risk_profile(profile)
        if self.risk_manager:
            self.risk_manager.set_profile(profile)
            self.risk_profile = profile
            self._apply_risk_profile_to_strategies(profile)
            self._broadcast_state()
            return True
        return False

    def _apply_risk_profile_to_strategies(self, profile: str):
        """同步 canonical 風險等級到各商品策略與 orderbook filter。"""
        orderbook_profile_name = get_orderbook_profile_for_risk(profile)
        orderbook_profile = ORDERBOOK_PROFILES.get(orderbook_profile_name, {})

        for pipeline in self.pipelines.values():
            strategy = getattr(pipeline, "strategy", None)
            if not strategy:
                continue

            signal_generator = getattr(strategy, "signal_generator", None)
            if signal_generator and hasattr(signal_generator, "risk_profile"):
                signal_generator.risk_profile = profile

            orderbook_filter = getattr(strategy, "orderbook_filter", None)
            if orderbook_filter and hasattr(orderbook_filter, "configure"):
                orderbook_filter.configure(**orderbook_profile)

    def manual_open(self, instrument: str, side: str, quantity: int = 1,
                    stop_loss: float = 0, take_profit: float = 0) -> dict:
        """手動市價進場（委派 executor.manual_open）"""
        return self.executor.manual_open(
            instrument=instrument, side=side, quantity=quantity,
            stop_loss=stop_loss, take_profit=take_profit,
        )

    def manual_close(self, instrument: str, is_simulation: bool = None) -> dict:
        """手動市價平倉（委派 executor.manual_close）"""
        return self.executor.manual_close(instrument, is_simulation)

    # ━━━━━━━━━━━━━━━━ 向後相容委派 ━━━━━━━━━━━━━━━━

    def _process_tick(self, tick: Any):
        self.events._process_tick(tick)

    def _process_kbar(self, instrument: str, kbar: Any):
        self.events._process_kbar(instrument, kbar)

    def _execute_entry(self, instrument: str, signal: Any, pipeline: Any):
        self.executor.execute_entry(instrument, signal, pipeline)

    def _execute_exit(self, instrument: str, signal: Any, price: float):
        self.executor.execute_exit(instrument, signal, price)

    # ━━━━━━━━━━━━━━━━ 資源委派 (EngineQueries) ━━━━━━━━━━━━━━━━

    def get_state(self) -> dict:
        return self.queries.get_state()

    def get_positions(self) -> dict:
        return self.queries.get_positions()

    def get_trade_history(self) -> list:
        return self.queries.get_trade_history()

    def get_kbars(self, timeframe: int = 1, count: int = 200, instrument: str = "") -> list[dict]:
        return self.queries.get_kbars(timeframe=timeframe, count=count, instrument=instrument)

    def get_stats(self) -> dict:
        if not self.position_manager:
            return {}
        return self.position_manager.get_stats()

    def delete_trade(self, trade_id: str) -> bool:
        return self.queries.delete_trade(trade_id)

    def update_trade(self, trade_id: str, updates: dict) -> bool:
        return self.queries.update_trade(trade_id, updates)
