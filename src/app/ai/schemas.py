from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MarketImpactOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset: Literal["A股", "港股", "美股", "黄金", "美元", "原油", "债券"]
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=1)
    importance: int = Field(ge=1, le=5)
    summary: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    market_impacts: list[MarketImpactOutput]
