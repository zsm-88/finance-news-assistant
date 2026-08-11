from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AssistantIntent(StrEnum):
    GENERAL_FINANCE = "GENERAL_FINANCE"
    NEWS = "NEWS"
    MARKET = "MARKET"
    FUND = "FUND"
    NEWS_MARKET = "NEWS_MARKET"
    MARKET_EVENT = "MARKET_EVENT"
    FUND_ANALYSIS = "FUND_ANALYSIS"
    UNKNOWN = "UNKNOWN"


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1500)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        return value.strip()


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation: list[ConversationMessage] = Field(default_factory=list, max_length=5)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class AssistantReference(BaseModel):
    type: Literal["news", "event", "market", "fund"]
    id: str
    title: str
    source: str
    published_at: datetime | None = None


class AssistantModelOutput(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    summary: str = Field(min_length=1, max_length=500)
    key_points: list[str] = Field(default_factory=list, max_length=8)
    market_impacts: list[str] = Field(default_factory=list, max_length=8)
    reference_ids: list[str] = Field(default_factory=list, max_length=12)
    disclaimer: str = Field(default="", max_length=500)


class AssistantChatResponse(BaseModel):
    intent: AssistantIntent
    answer: str
    summary: str
    key_points: list[str]
    market_impacts: list[str]
    references: list[AssistantReference]
    data_time: datetime
    data_status: str
    disclaimer: str
    cached: bool = False
