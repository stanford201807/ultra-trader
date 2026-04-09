import pytest
from unittest.mock import MagicMock
from core.engine.executor import OrderExecutor
from strategy.base import Signal, SignalDirection

def test_executor_cooldown():
    """測試冷卻機制：冷卻中應攔截下單"""
    engine = MagicMock()
    executor = OrderExecutor(engine)
                             
    assert executor._is_order_cooled_down("TMF") == False
    executor._set_order_cooldown("TMF", 60)
    assert executor._is_order_cooled_down("TMF") == True

def test_executor_entry_paper_mode():
    """測試 Paper 模式進場：不呼叫 broker 但更新持倉"""
    engine = MagicMock()
    mock_pm = MagicMock()
    mock_broker = MagicMock()
    
    engine.broker = mock_broker
    engine.position_manager = mock_pm
    engine.risk_manager = MagicMock()
    engine.trading_mode = "paper"
    engine.performance = None
    
    executor = OrderExecutor(engine)
                             
    pipeline = MagicMock()
    pipeline.snapshot.price = 20000
    
    signal = Signal(direction=SignalDirection.BUY, strength=1.0, stop_loss=19900, take_profit=20200, reason="Test")
    
    executor.execute_entry("TMF", signal, pipeline)
    
    mock_broker.place_order.assert_not_called()
    mock_pm.open_position.assert_called_once()
