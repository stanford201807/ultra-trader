from enum import Enum
from dataclasses import dataclass, field
from core.market_data import TickAggregator, IndicatorEngine, MarketSnapshot
from strategy.base import BaseStrategy
from strategy.orderbook_features import OrderbookFeatureEngine, OrderbookFeatures
from core.instrument_config import InstrumentSpec

class EngineState(Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"

@dataclass
class InstrumentPipeline:
    """每個商品的獨立處理管線（升級版：含多時框指標引擎）"""
    code: str
    spec: InstrumentSpec
    aggregator: TickAggregator = field(default=None)
    indicator_engine: IndicatorEngine = field(default=None)
    strategy: BaseStrategy = field(default=None)
    snapshot: MarketSnapshot = field(default_factory=MarketSnapshot)
    orderbook_engine: OrderbookFeatureEngine = field(default=None)
    orderbook_features: OrderbookFeatures = field(default_factory=OrderbookFeatures)
    # 多時框指標引擎
    indicator_engine_5m: IndicatorEngine = field(default=None)
    indicator_engine_15m: IndicatorEngine = field(default=None)
    snapshot_5m: MarketSnapshot = field(default_factory=MarketSnapshot)
    snapshot_15m: MarketSnapshot = field(default_factory=MarketSnapshot)

    def __post_init__(self):
        if self.aggregator is None:
            self.aggregator = TickAggregator(intervals=[1, 5, 15])
        if self.indicator_engine is None:
            self.indicator_engine = IndicatorEngine(lookback_period=200)
        if self.orderbook_engine is None:
            self.orderbook_engine = OrderbookFeatureEngine()
        if self.indicator_engine_5m is None:
            self.indicator_engine_5m = IndicatorEngine(lookback_period=200)
        if self.indicator_engine_15m is None:
            self.indicator_engine_15m = IndicatorEngine(lookback_period=200)
