from datetime import datetime, timedelta

import pandas as pd

from dashboard.schemas.backtest import BacktestRunRequest
from dashboard.services import backtest_service
from backtest.engine import BacktestResult


def _make_data(rows: int = 20) -> pd.DataFrame:
    start = datetime(2026, 4, 1, 9, 0)
    values = []
    price = 22000
    for i in range(rows):
        ts = start + timedelta(minutes=i)
        values.append(
            {
                "datetime": ts,
                "open": price,
                "high": price + 5,
                "low": price - 5,
                "close": price + 2,
                "volume": 100,
            }
        )
        price += 1
    return pd.DataFrame(values)


def test_run_backtest_returns_api_friendly_payload(monkeypatch) -> None:
    fake_data = _make_data()

    monkeypatch.setattr(
        backtest_service.DataLoader,
        "generate_synthetic",
        lambda **kwargs: fake_data,
    )

    class FakeEngine:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self, **kwargs):
            return BacktestResult(
                trades=[],
                equity_curve=[43000.0, 43100.0],
                daily_pnl={"2026-04-01": 100.0},
                total_bars=2,
                start_date="2026-04-01 09:00:00",
                end_date="2026-04-01 09:01:00",
                initial_balance=43000.0,
                final_balance=43100.0,
                orderbook_enabled=False,
                orderbook_metrics={},
            )

    monkeypatch.setattr(backtest_service, "BacktestEngine", FakeEngine)

    payload = backtest_service.run_backtest(BacktestRunRequest())

    assert payload["request"]["strategy"] == "momentum"
    assert payload["request"]["risk_profile"] == "balanced"
    assert payload["summary"]["pnl"] == 100.0
    assert "metrics" in payload["report"]
    assert "equity_curve" in payload["report"]


def test_run_backtest_uses_csv_loader_when_data_path_provided(monkeypatch) -> None:
    fake_data = _make_data()
    called = {"load_csv": False}

    def fake_load_csv(path: str):
        called["load_csv"] = True
        assert path == "data/historical/test.csv"
        return fake_data

    monkeypatch.setattr(backtest_service.DataLoader, "load_csv", fake_load_csv)

    class FakeEngine:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return BacktestResult(
                trades=[],
                equity_curve=[43000.0],
                daily_pnl={},
                total_bars=1,
                start_date="2026-04-01 09:00:00",
                end_date="2026-04-01 09:00:00",
                initial_balance=43000.0,
                final_balance=43000.0,
                orderbook_enabled=False,
                orderbook_metrics={},
            )

    monkeypatch.setattr(backtest_service, "BacktestEngine", FakeEngine)

    backtest_service.run_backtest(
        BacktestRunRequest(
            data_path="data/historical/test.csv",
            days=7,
        )
    )

    assert called["load_csv"] is True
