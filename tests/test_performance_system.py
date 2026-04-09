from datetime import datetime
from core.position import PositionManager, Side, Trade
from core.performance import PerformanceTracker

def test_trade_dataclass_fields():
    trade = Trade(
        entry_time=datetime.now(),
        exit_time=datetime.now(),
        side="long",
        entry_price=100.0,
        exit_price=110.0,
        quantity=1,
        pnl=10.0,
        pnl_points=10.0,
        commission=1.0,
        reason="take_profit",
        strategy="momentum",
        market_regime="TRENDING_UP",
        signal_strength=0.85,
        max_favorable=12.0,
        max_adverse=2.0
    )
    assert trade.strategy == "momentum"
    assert trade.market_regime == "TRENDING_UP"
    assert trade.signal_strength == 0.85

def test_position_manager_open_position_with_strategy_args():
    manager = PositionManager(initial_balance=10000.0)
    
    # 測試 open_position 應能接收新參數
    pos = manager.open_position(
        instrument="TMF",
        side=Side.LONG,
        price=100.0,
        quantity=1,
        stop_loss=90.0,
        take_profit=120.0,
        strategy="mean_reversion",
        market_regime="RANGING",
        signal_strength=0.75
    )
    
    assert pos.strategy == "mean_reversion"
    assert pos.market_regime == "RANGING"
    assert pos.signal_strength == 0.75
    
def test_position_manager_close_position_propagates_fields():
    manager = PositionManager(initial_balance=10000.0, configs={"TMF": None})
    manager.open_position(
        instrument="TMF",
        side=Side.LONG,
        price=100.0,
        quantity=1,
        stop_loss=90.0,
        take_profit=120.0,
        strategy="momentum",
        market_regime="TRENDING_UP",
        signal_strength=0.9
    )
    
    # 關閉部位，建立 Trade
    trade = manager.close_position(
        instrument="TMF",
        price=110.0,
        reason="take_profit"
    )
    
    assert trade is not None
    assert trade.strategy == "momentum"
    assert trade.market_regime == "TRENDING_UP"
    assert trade.signal_strength == 0.9
    
def test_performance_tracker_daily_summary():
    tracker = PerformanceTracker()
    
    trade1 = {
        "entry_time": "2026-04-08T10:00:00",
        "exit_time": "2026-04-08T11:00:00",
        "side": "long",
        "entry_price": 100.0,
        "exit_price": 110.0,
        "quantity": 1,
        "pnl": 10.0,
        "pnl_points": 10.0,
        "net_pnl": 9.0,
        "commission": 1.0,
        "reason": "take_profit",
        "strategy": "momentum",
        "market_regime": "TRENDING_UP",
        "signal_strength": 0.8
    }
    
    trade2 = {
        "entry_time": "2026-04-08T12:00:00",
        "exit_time": "2026-04-08T13:00:00",
        "side": "short",
        "entry_price": 110.0,
        "exit_price": 115.0, # Loss
        "quantity": 1,
        "pnl": -5.0,
        "pnl_points": -5.0,
        "net_pnl": -6.0,
        "commission": 1.0,
        "reason": "stop_loss",
        "strategy": "momentum",
        "market_regime": "TRENDING_UP",
        "signal_strength": 0.6
    }
    
    tracker.today_trades = [trade1, trade2]
    
    summary = tracker._build_daily_summary("2026-04-08", ending_balance=10000.0)
    assert summary.total_trades == 2
    assert summary.winning_trades == 1
    assert summary.losing_trades == 1
    assert summary.daily_pnl == 3.0 # 9 + (-6) = 3
    assert "momentum" in summary.strategy_performance
