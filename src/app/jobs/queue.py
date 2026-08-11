from typing import Any

from redis.asyncio import Redis

from .task import Task


class TaskQueue:
    def __init__(self, redis: Redis, queue_name: str = "tasks") -> None:
        self.redis: Any = redis
        self.queue_name = queue_name

    async def enqueue(self, task: Task) -> None:
        await self.redis.rpush(self.queue_name, task.serialize())

    async def dequeue(self, timeout: int = 0) -> Task | None:
        item = await self.redis.blpop(self.queue_name, timeout=timeout)
        return Task.deserialize(item[1]) if item else None
