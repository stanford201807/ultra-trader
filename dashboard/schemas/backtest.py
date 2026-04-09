"""Dashboard 回測 API 參數 schema。"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


RiskProfile = Literal["conservative", "balanced", "aggressive", "crisis", "dangerous"]
StrategyName = Literal["momentum", "mean_reversion"]
InstrumentName = Literal["TMF", "TGF"]
OrderbookProfile = Literal["A1", "A2", "A3", "A4", "A5"]


class BacktestRunRequest(BaseModel):
    """回測執行請求。"""

    strategy: StrategyName = "momentum"
    risk_profile: RiskProfile = "balanced"
    instrument: InstrumentName = "TMF"
    initial_balance: float = Field(default=43000.0, gt=0, le=100_000_000)
    slippage: int = Field(default=1, ge=0, le=20)
    commission: float = Field(default=18.0, ge=0, le=5_000)
    use_orderbook_filter: bool = False
    orderbook_profile: OrderbookProfile | None = None

    data_path: str | None = None
    days: int = Field(default=30, ge=1, le=3650)
    seed: int = 42
    timeframe_minutes: int = Field(default=1, ge=1, le=60)
    start_date: date | None = None
    end_date: date | None = None
    max_bars: int = Field(default=20_000, ge=100, le=500_000)

    @model_validator(mode="after")
    def validate_date_range(self) -> "BacktestRunRequest":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date 不可早於 start_date")
        return self

