from typing import Any

import httpx

from app.ai.prompts import BuiltPrompt

from .base import ProviderResult


class OpenAICompatibleAdapter:
    name = "openai-compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.AsyncClient(timeout=60.0)
        self.max_tokens = max_tokens

    async def analyze(self, prompt: BuiltPrompt) -> ProviderResult:
        request_body: dict[str, Any] = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.task},
            ],
        }
        if self.max_tokens is not None:
            request_body["max_tokens"] = self.max_tokens
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=request_body,
        )
        response.raise_for_status()
        response_body: dict[str, Any] = response.json()
        output = response_body["choices"][0]["message"]["content"]
        import json
        usage = response_body.get("usage", {})
        return ProviderResult(
            self.name,
            self.model,
            json.loads(output),
            response_body,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
        )
