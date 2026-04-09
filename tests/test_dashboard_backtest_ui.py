from pathlib import Path


def test_dashboard_has_backtest_page_route() -> None:
    app_py = Path("dashboard/app.py").read_text(encoding="utf-8")
    assert '@app.get("/backtest")' in app_py
    assert '"backtest" / "index.html"' in app_py


def test_strategy_panel_has_backtest_new_tab_button() -> None:
    template = Path("dashboard/static/templates/app-dom.part1.html").read_text(
        encoding="utf-8"
    )
    assert 'href="/backtest"' in template
    assert 'target="_blank"' in template
    assert "backtest-link-btn" in template


def test_backtest_page_wires_frontend_module() -> None:
    page = Path("dashboard/static/backtest/index.html").read_text(encoding="utf-8")
    assert "/static/app/backtestPage.js" in page
    assert 'id="equity-chart"' in page
    assert 'id="zoom-recent-20"' in page
    assert 'id="zoom-all"' in page
    assert 'id="export-json"' in page
    assert 'id="export-csv"' in page
    assert 'data-preset="conservative"' in page
    assert 'data-preset="balanced"' in page
    assert 'data-preset="aggressive"' in page

    module_code = Path("dashboard/static/app/modules/backtest.js").read_text(
        encoding="utf-8"
    )
    assert 'fetch("/api/backtest/run"' in module_code
    assert 'method: "POST"' in module_code
    assert "runBacktest" in module_code
    assert "renderEquityChart" in module_code
    assert "applyPreset" in module_code
    assert "applyChartZoom" in module_code
    assert "exportBacktestJson" in module_code
    assert "exportBacktestCsv" in module_code
