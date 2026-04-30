from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.config import DEFAULT_ALPHA, DEFAULT_HORIZONS, DEFAULT_Z_SCORE


class ExpectedRangesRequest(BaseModel):
    asset: str = Field(..., description="Ativo (ex.: brl, gbp, idr, aud)")
    z_score: float = Field(default=DEFAULT_Z_SCORE)
    alpha: float = Field(default=DEFAULT_ALPHA, ge=0.0, le=1.0)
    horizons: list[int] = Field(default_factory=lambda: DEFAULT_HORIZONS.copy())
    source: Literal["auto", "polygon", "local"] = "auto"
    lookback_days: int = Field(default=730, ge=30, le=3650)


class RangeBand(BaseModel):
    lower: float
    upper: float


class HorizonResult(BaseModel):
    days: int
    price_reference: float
    range_percentage: float
    token_usdc: RangeBand
    usdc_token: RangeBand


class ExpectedRangesResponse(BaseModel):
    asset: str
    symbol: str
    date: str
    z_score: float
    alpha: float
    results: list[HorizonResult]
    summary_text: str
