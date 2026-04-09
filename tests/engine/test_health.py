import pytest
from unittest.mock import MagicMock
from core.engine.health import HealthMonitor
from core.engine.models import InstrumentPipeline
from core.instrument_config import get_spec
from core.position import PositionManager

def test_health_monitor_anomaly_trigger():
    """確保異常價差跳動能觸發斷路保護"""
    mock_risk_manager = MagicMock()
    mock_broker = MagicMock()
    # 建立 Pipeline 與虛假 current_price
    spec = get_spec("TMF")
    pipeline = InstrumentPipeline(code="TMF", spec=spec)
    pipeline.aggregator = MagicMock()
    pipeline.snapshot = MagicMock()
    
    # 初始價格 20000, ATR = 100
    pipeline.aggregator.current_price = 20000
    pipeline.snapshot.atr = 100
    
    pm = PositionManager(instruments=["TMF"], configs={"TMF": spec}, initial_balance=100000)
    
    engine = MagicMock()
    engine.pipelines = {"TMF": pipeline}
    engine.position_manager = pm
    engine.broker = mock_broker
    engine.risk_manager = mock_risk_manager
    engine.trading_mode = "live"
    engine.instruments = ["TMF"]
    
    monitor = HealthMonitor(engine)
                            
    # 第一次心跳建立基線
    monitor._check_price_anomaly()
    
    # 修改價格, 跳動 50 ( < 3x ATR )
    pipeline.aggregator.current_price = 20050
    monitor._check_price_anomaly()
    mock_risk_manager.circuit_breaker.on_connection_lost.assert_not_called()
    
    # 價格暴跌超出 5x ATR (100 * 5 = 500)
    pipeline.aggregator.current_price = 19500
    monitor._check_price_anomaly()
    
    # 應該要自動保護 (on_connection_lost 是斷路器的方法)
    mock_risk_manager.circuit_breaker.on_connection_lost.assert_called_once()
