"""Dashboard 回測服務。"""

from __future__ import annotations

from typing import Any

from backtest.data_loader import DataLoader
from backtest.engine import BacktestEngine
from backtest.report import BacktestReport
from dashboard.schemas.backtest import BacktestRunRequest
from risk.profile_config import normalize_risk_profile
from scripts.backtest_runner import (
    _build_strategy_factory,
    _filter_data_by_date,
    _resolve_orderbook_profile,
    _summarize_result,
)


def _load_backtest_data(request: BacktestRunRequest):
    if request.data_path:
        return DataLoader.load_csv(request.data_path)
    return DataLoader.generate_synthetic(
        days=request.days,
        timeframe_minutes=request.timeframe_minutes,
        seed=request.seed,
    )


def run_backtest(request: BacktestRunRequest | dict[str, Any]) -> dict[str, Any]:
    """執行回測並回傳可供 API 使用的 payload。"""
    parsed = request if isinstance(request, BacktestRunRequest) else BacktestRunRequest.model_validate(request)

    risk_profile = normalize_risk_profile(parsed.risk_profile)
    selected_orderbook_profile = _resolve_orderbook_profile(risk_profile, parsed.orderbook_profile)
    strategy_factory = _build_strategy_factory(parsed.strategy, selected_orderbook_profile)

    data = _load_backtest_data(parsed)
    start_date = parsed.start_date.isoformat() if parsed.start_date else None
    end_date = parsed.end_date.isoformat() if parsed.end_date else None
    filtered_data = _filter_data_by_date(data, start_date, end_date)
    if filtered_data.empty:
        raise ValueError("日期區間內無可用 K 棒資料")

    if len(filtered_data) > parsed.max_bars:
        filtered_data = filtered_data.tail(parsed.max_bars).reset_index(drop=True)

    engine = BacktestEngine(
        initial_balance=parsed.initial_balance,
        slippage=parsed.slippage,
        commission=parsed.commission,
        instrument=parsed.instrument,
    )
    result = engine.run(
        data=filtered_data,
        strategy=strategy_factory(),
        risk_profile=risk_profile,
        use_orderbook_filter=parsed.use_orderbook_filter,
    )
    report = BacktestReport(result).to_dict()
    summary = _summarize_result(result)

    return {
        "request": {
            "strategy": parsed.strategy,
            "risk_profile": risk_profile,
            "instrument": parsed.instrument,
            "initial_balance": parsed.initial_balance,
            "slippage": parsed.slippage,
            "commission": parsed.commission,
            "use_orderbook_filter": parsed.use_orderbook_filter,
            "orderbook_profile": selected_orderbook_profile,
            "start_date": start_date,
            "end_date": end_date,
            "bars": len(filtered_data),
        },
        "summary": summary,
        "report": report,
    }

