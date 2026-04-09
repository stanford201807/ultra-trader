from datetime import date

import pytest
from pydantic import ValidationError

from dashboard.schemas.backtest import BacktestRunRequest


def test_backtest_schema_has_expected_defaults() -> None:
    request = BacktestRunRequest()

    assert request.strategy == "momentum"
    assert request.risk_profile == "balanced"
    assert request.instrument == "TMF"
    assert request.initial_balance == 43000.0
    assert request.use_orderbook_filter is False
    assert request.days == 30
    assert request.timeframe_minutes == 1


def test_backtest_schema_rejects_invalid_date_range() -> None:
    with pytest.raises(ValidationError):
        BacktestRunRequest(
            start_date=date(2026, 4, 8),
            end_date=date(2026, 4, 1),
        )


def test_backtest_schema_accepts_dangerous_risk_profile_alias() -> None:
    request = BacktestRunRequest(risk_profile="dangerous")
    assert request.risk_profile == "dangerous"
