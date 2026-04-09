import pytest
from core.engine.models import EngineState, InstrumentPipeline
from core.instrument_config import InstrumentSpec
from strategy.base import BaseStrategy

def test_engine_state_enum():
    """確保 EngineState 定義完整"""
    assert EngineState.INITIALIZING.value == "initializing"
    assert EngineState.RUNNING.value == "running"
    assert EngineState.PAUSED.value == "paused"
    assert EngineState.STOPPED.value == "stopped"
    assert EngineState.ERROR.value == "error"

def test_instrument_pipeline_defaults():
    """確保 InstrumentPipeline 自動建立子系統(Aggregator, IndicatorEngine, 快照等)的預設行為"""
    from core.instrument_config import get_spec
    spec = get_spec("TMF")
    pipeline = InstrumentPipeline(code="TMF", spec=spec)
    
    assert pipeline.code == "TMF"
    assert pipeline.spec.code == "TMF"
    # 確認 Aggregator 自動建立
    assert pipeline.aggregator is not None
    assert pipeline.aggregator.intervals == [1, 5, 15]
    
    # 確認 IndicatorEngine 自動建立
    assert pipeline.indicator_engine is not None
    assert pipeline.indicator_engine_5m is not None
    assert pipeline.indicator_engine_15m is not None
    
    # 確認 Orderbook 機制自動建立
    assert pipeline.orderbook_engine is not None
    
    # 確認 Snapshot 自動建立
    assert pipeline.snapshot is not None
    assert pipeline.snapshot_5m is not None
    assert pipeline.snapshot_15m is not None

def test_instrument_pipeline_with_strategy():
    """確保 InstrumentPipeline 支援注入自訂 strategy"""
    from core.instrument_config import get_spec
    from strategy.momentum import AdaptiveMomentumStrategy
    spec = get_spec("TMF")
    strategy = AdaptiveMomentumStrategy()
    pipeline = InstrumentPipeline(code="TMF", spec=spec, strategy=strategy)
    
    assert pipeline.strategy is strategy
