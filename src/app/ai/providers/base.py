from dataclasses import dataclass
from typing import Any, Protocol

from app.ai.prompts import BuiltPrompt


@dataclass(slots=True)
class ProviderResult:
    provider: str
    model: str
    output: dict[str, Any]
    raw_response: dict[str, Any]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "output": self.output,
            "raw_response": self.raw_response,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProviderResult":
        return cls(**value)


class AIProvider(Protocol):
    name: str

    async def analyze(self, prompt: BuiltPrompt) -> ProviderResult: ...
