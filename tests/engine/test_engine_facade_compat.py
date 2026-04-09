from datetime import datetime
from unittest.mock import MagicMock


def test_trading_engine_has_optional_intelligence_attrs():
    from core.engine import TradingEngine

    engine = TradingEngine()
    assert hasattr(engine, "data_collector")
    assert hasattr(engine, "left_side_engine")


def test_trading_engine_initialize_uses_env_trading_mode_when_not_provided(monkeypatch):
    from core.engine import TradingEngine

    monkeypatch.setenv("TRADING_MODE", "paper")
    engine = TradingEngine()

    assert engine.initialize({"instruments": ["TMF"]}) in (True, False)
    assert engine.trading_mode == "paper"


def test_trading_engine_initialize_passes_instrument_codes_to_shioaji(monkeypatch):
    import core.engine as engine_module

    captured = {}

    class FakeShioajiBroker:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("SHIOAJI_API_KEY", "key")
    monkeypatch.setenv("SHIOAJI_SECRET_KEY", "secret")
    monkeypatch.setattr(engine_module, "ShioajiBroker", FakeShioajiBroker)

    engine = engine_module.TradingEngine()

    assert engine.initialize({"trading_mode": "paper", "instruments": ["TMF", "TGF"]}) is True
    assert captured["contract_codes"] == ["TMF", "TGF"]


def test_trading_engine_get_kbars_delegates_to_queries():
    from core.engine import TradingEngine

    engine = TradingEngine()
    engine.queries = MagicMock()
    engine.queries.get_kbars.return_value = [{"time": "t"}]

    result = engine.get_kbars(timeframe=5, count=10, instrument="TMF")

    assert result == [{"time": "t"}]
    engine.queries.get_kbars.assert_called_once_with(timeframe=5, count=10, instrument="TMF")


def test_health_monitor_start_stop_controls_tick_heartbeat():
    from core.engine.health import HealthMonitor

    engine = MagicMock()
    engine.pipelines = {}
    engine.instruments = []
    engine.position_manager = MagicMock()
    engine.broker = MagicMock()
    engine.risk_manager = MagicMock()
    engine.trading_mode = "simulation"

    monitor = HealthMonitor(engine)

    monitor.tick_heartbeat()
    assert monitor._heartbeat_count == 0

    monitor.start()
    monitor.tick_heartbeat()
    assert monitor._heartbeat_count == 1

    monitor.stop()
    monitor.tick_heartbeat()
    assert monitor._heartbeat_count == 1


def test_trading_engine_aggregate_historical_bars():
    from core.engine import TradingEngine
    from core.market_data import KBar

    engine = TradingEngine()
    bars = [
        KBar(datetime=datetime(2026, 4, 8, 9, 0), open=100, high=101, low=99, close=100.5, volume=10, interval=1),
        KBar(datetime=datetime(2026, 4, 8, 9, 1), open=100.5, high=102, low=100, close=101.5, volume=20, interval=1),
        KBar(datetime=datetime(2026, 4, 8, 9, 2), open=101.5, high=103, low=101, close=102.5, volume=30, interval=1),
        KBar(datetime=datetime(2026, 4, 8, 9, 3), open=102.5, high=104, low=102, close=103.5, volume=40, interval=1),
    ]

    aggregated = engine._aggregate_historical_bars(bars, 2)

    assert len(aggregated) == 2
    assert aggregated[0].datetime == datetime(2026, 4, 8, 9, 0)
    assert aggregated[0].open == 100
    assert aggregated[0].high == 102
    assert aggregated[0].low == 99
    assert aggregated[0].close == 101.5
    assert aggregated[0].volume == 30
