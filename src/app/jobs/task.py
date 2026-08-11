import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class Task:
    type: str
    payload: dict[str, Any]
    retry_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def serialize(self) -> str:
        value = asdict(self)
        value["created_at"] = self.created_at.isoformat()
        return json.dumps(value, ensure_ascii=True)

    @classmethod
    def deserialize(cls, value: str) -> "Task":
        data = json.loads(value)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)
