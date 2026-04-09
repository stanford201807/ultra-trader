import pytest
from unittest.mock import MagicMock
from core.engine.queries import EngineQueries
from core.engine.models import EngineState, InstrumentPipeline
from core.instrument_config import get_spec
from core.position import PositionManager

def test_engine_queries_get_state():
    """測試 get_state 能夠返回完整的狀態字典"""
    mock_broker = MagicMock()
    mock_broker.get_contract_name.return_value = "MockBroker"
    mock_risk_manager = MagicMock()
    mock_risk_manager.to_dict.return_value = {"test": 1}
    
    spec = get_spec("TMF")
    pipeline = InstrumentPipeline(code="TMF", spec=spec)
    pipeline.aggregator = MagicMock()
    pipeline.aggregator.current_price = 22000
    
    pm = MagicMock()
    pm.positions = {}
    pm.get_total_unrealized_pnl.return_value = 0
    pm.balance = 100000
    pm.get_total_margin_used.return_value = 0
    pm.get_daily_pnl.return_value = 0
    pm.get_daily_trade_count.return_value = 0
    
    engine = MagicMock()
    engine.state = EngineState.RUNNING
    engine.trading_mode = "simulation"
    engine.risk_profile = "balanced"
    engine.auto_trade = True
    engine.instruments = ["TMF"]
    engine.pipelines = {"TMF": pipeline}
    engine.broker = mock_broker
    engine.position_manager = pm
    engine.risk_manager = mock_risk_manager
    engine.performance = None
    engine.data_collector = None
    engine.left_side_engine = None
    
    queries = EngineQueries(engine)
    
    state = queries.get_state()
    assert state["engine_state"] == "running"
    assert state["trading_mode"] == "simulation"
    assert state["auto_trade"] == True
    assert state["account"]["balance"] == 100000
    assert "TMF" in state["instruments_data"]
    assert state["instruments_data"]["TMF"]["price"] == 22000
