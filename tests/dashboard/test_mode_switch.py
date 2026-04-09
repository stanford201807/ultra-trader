from types import SimpleNamespace

from dashboard.app import _build_mode_switch_config, _build_pm_account_snapshot, _resolve_close_targets


class DummyBroker:
    def __init__(self):
        self.account_calls = 0
        self.position_calls = 0

    def get_account_info(self):
        self.account_calls += 1
        return SimpleNamespace(
            equity=0,
            balance=0,
            margin_used=0,
            margin_available=0,
            unrealized_pnl=0,
        )

    def get_real_positions(self):
        self.position_calls += 1
        return [{"code": "TMF", "quantity": 0}]

    def resolve_instrument_from_code(self, code):
        return {"TMFR1": "TMF"}.get(code, "")


class DummyPositionManager:
    balance = 300000

    def get_total_unrealized_pnl(self, prices):
        return 1200

    def get_total_margin_used(self):
        return 30000


class DummyEngine:
    def __init__(self):
        self.trading_mode = "simulation"
        self.risk_profile = "balanced"
        self.timeframe = 5
        self.instruments = ["TMF"]
        self.auto_trade = True
        self.state = SimpleNamespace(value="running")
        self.broker = DummyBroker()
        self.position_manager = DummyPositionManager()
        self.pipelines = {"TMF": SimpleNamespace(aggregator=SimpleNamespace(current_price=22100))}


def test_switch_mode_preserves_runtime_config():
    engine = DummyEngine()
    assert _build_mode_switch_config(engine, "paper") == {
        "trading_mode": "paper",
        "risk_profile": "balanced",
        "timeframe": 5,
        "instruments": ["TMF"],
        "auto_trade": True,
    }


def test_real_account_skips_margin_query_in_paper_mode():
    engine = DummyEngine()
    data = _build_pm_account_snapshot(engine, engine.broker.get_real_positions())
    assert data["account"]["equity"] == 301200
    assert engine.broker.account_calls == 0
    assert engine.broker.position_calls == 1


def test_real_account_paper_mode_should_not_expose_real_positions():
    engine = DummyEngine()
    data = _build_pm_account_snapshot(engine, [])

    assert data["positions"] == []


def test_resolve_close_targets_prefers_broker_mapping():
    engine = DummyEngine()
    order_target, sync_instrument = _resolve_close_targets(engine, "TMFR1")

    assert order_target == "TMF"
    assert sync_instrument == "TMF"


def test_resolve_close_targets_falls_back_to_raw_code_for_legacy_position():
    engine = DummyEngine()
    order_target, sync_instrument = _resolve_close_targets(engine, "MXFD6")

    assert order_target == "MXFD6"
    assert sync_instrument == ""
