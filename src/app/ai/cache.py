import hashlib
import json
from typing import Any

from redis.asyncio import Redis


class AICache:
    def __init__(self, redis: Redis, ttl_seconds: int = 86400) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def key(self, prompt_version: str, content_hash: str) -> str:
        material = f"{prompt_version}:{content_hash}".encode()
        return f"ai:cache:{hashlib.sha256(material).hexdigest()}"

    async def get(self, prompt_version: str, content_hash: str) -> dict[str, Any] | None:
        value = await self.redis.get(self.key(prompt_version, content_hash))
        return json.loads(value) if value else None

    async def set(self, prompt_version: str, content_hash: str, value: dict[str, Any]) -> None:
        await self.redis.set(self.key(prompt_version, content_hash), json.dumps(value, ensure_ascii=True), ex=self.ttl_seconds)

