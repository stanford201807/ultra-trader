from fastapi.responses import JSONResponse

from dashboard.app import _execute_backtest_run, create_app
from dashboard.schemas.backtest import BacktestRunRequest


def test_backtest_route_registered() -> None:
    app = create_app(engine=None)
    routes = {
        (route.path, tuple(sorted(route.methods)))
        for route in app.routes
        if hasattr(route, "methods") and route.methods
    }

    assert ("/api/backtest/run", ("POST",)) in routes


def test_execute_backtest_run_returns_service_result(monkeypatch) -> None:
    def fake_run_backtest_service(body):
        return {
            "request": {"strategy": "momentum"},
            "summary": {"pnl": 123.0},
            "report": {"metrics": {"總交易次數": 1}},
        }

    monkeypatch.setattr("dashboard.app.run_backtest_service", fake_run_backtest_service)

    response = _execute_backtest_run(BacktestRunRequest())

    assert isinstance(response, dict)
    assert response["summary"]["pnl"] == 123.0


def test_execute_backtest_run_returns_400_for_bad_value(monkeypatch) -> None:
    def fake_run_backtest_service(body):
        raise ValueError("bad request")

    monkeypatch.setattr("dashboard.app.run_backtest_service", fake_run_backtest_service)

    response = _execute_backtest_run(BacktestRunRequest())

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
