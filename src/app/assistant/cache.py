import hashlib
import logging
from typing import ClassVar

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .contracts import AssistantChatResponse, AssistantIntent

logger = logging.getLogger(__name__)


class AssistantCache:
    PUBLIC_INTENTS: ClassVar[frozenset[AssistantIntent]] = frozenset({
        AssistantIntent.NEWS,
        AssistantIntent.MARKET,
        AssistantIntent.NEWS_MARKET,
        AssistantIntent.MARKET_EVENT,
    })

    def __init__(self, redis: Redis, ttl_seconds: int = 60) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def key(self, intent: AssistantIntent, message: str) -> str:
        normalized = "".join(message.casefold().split())
        digest = hashlib.sha256(f"m13-v1:{intent}:{normalized}".encode()).hexdigest()
        return f"ai:assistant:{digest}"

    async def get(
        self, intent: AssistantIntent, message: str
    ) -> AssistantChatResponse | None:
        if intent not in self.PUBLIC_INTENTS:
            return None
        try:
            value = await self.redis.get(self.key(intent, message))
            if not value:
                return None
            result = AssistantChatResponse.model_validate_json(value)
            return result.model_copy(update={"cached": True})
        except (RedisError, ValidationError) as exc:
            logger.warning("assistant_cache_read_failed error_type=%s", type(exc).__name__)
            return None

    async def set(
        self, intent: AssistantIntent, message: str, value: AssistantChatResponse
    ) -> None:
        if intent not in self.PUBLIC_INTENTS:
            return
        try:
            await self.redis.set(
                self.key(intent, message),
                value.model_dump_json(),
                ex=self.ttl_seconds,
            )
        except RedisError as exc:
            logger.warning("assistant_cache_write_failed error_type=%s", type(exc).__name__)
