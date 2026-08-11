import logging
from collections.abc import Iterable, Mapping
from time import perf_counter

from pydantic import ValidationError

from app.ai.providers.router import ProviderRouter

from .cache import AssistantCache
from .context import AssistantContextBuilder
from .contracts import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantModelOutput,
    AssistantReference,
)
from .intent import IntentClassifier
from .prompts import AssistantPromptBuilder
from .repository import AssistantUsageRepository

logger = logging.getLogger(__name__)


class AssistantUnavailableError(RuntimeError):
    pass


class AssistantProviderError(RuntimeError):
    pass


class FinanceAssistantService:
    def __init__(
        self,
        router: ProviderRouter | None,
        context_builder: AssistantContextBuilder,
        usage: AssistantUsageRepository,
        cache: AssistantCache,
        classifier: IntentClassifier | None = None,
        prompt_builder: AssistantPromptBuilder | None = None,
    ) -> None:
        self.router = router
        self.context_builder = context_builder
        self.usage = usage
        self.cache = cache
        self.classifier = classifier or IntentClassifier()
        self.prompt_builder = prompt_builder or AssistantPromptBuilder()

    async def chat(self, request: AssistantChatRequest) -> AssistantChatResponse:
        intent = self.classifier.classify(request.message)
        started = perf_counter()
        cached = await self.cache.get(intent, request.message)
        if cached is not None:
            await self.usage.record(
                provider="cache",
                model="m13-public-cache",
                intent=intent.value,
                success=True,
                duration_ms=self._duration(started),
            )
            return cached
        if self.router is None:
            await self.usage.record(
                provider="unconfigured",
                model="unconfigured",
                intent=intent.value,
                success=False,
                error_type="not_configured",
                duration_ms=self._duration(started),
            )
            raise AssistantUnavailableError("AI 财经助手暂未配置")

        provider = self.router.route()
        provider_name = getattr(provider, "name", "unknown")
        model_name = getattr(provider, "model", "unknown")
        try:
            context = await self.context_builder.build(intent, request.message)
            prompt = self.prompt_builder.build(request, intent, context)
            provider_result = await provider.analyze(prompt)
            output = AssistantModelOutput.model_validate(provider_result.output)
            response = AssistantChatResponse(
                intent=intent,
                answer=output.answer,
                summary=output.summary,
                key_points=output.key_points,
                market_impacts=output.market_impacts,
                references=self._references(output.reference_ids, context.references),
                data_time=context.data_time,
                data_status=context.data_status,
                disclaimer=output.disclaimer,
            )
        except Exception as exc:
            error_type = "invalid_response" if isinstance(exc, (ValidationError, ValueError, KeyError)) else type(exc).__name__
            logger.warning(
                "assistant_provider_failed intent=%s error_type=%s",
                intent.value,
                error_type,
            )
            await self.usage.record(
                provider=provider_name,
                model=model_name,
                intent=intent.value,
                success=False,
                error_type=error_type[:64],
                duration_ms=self._duration(started),
            )
            raise AssistantProviderError("AI 财经助手暂时不可用") from exc

        await self.usage.record(
            provider=provider_result.provider,
            model=provider_result.model,
            intent=intent.value,
            success=True,
            prompt_tokens=provider_result.prompt_tokens,
            completion_tokens=provider_result.completion_tokens,
            total_tokens=provider_result.total_tokens,
            duration_ms=self._duration(started),
        )
        await self.cache.set(intent, request.message, response)
        return response

    @staticmethod
    def _references(
        reference_ids: Iterable[str],
        available: Mapping[str, AssistantReference],
    ) -> list[AssistantReference]:
        selected: list[AssistantReference] = []
        seen: set[str] = set()
        for reference_id in reference_ids:
            if reference_id in available and reference_id not in seen:
                selected.append(available[reference_id])
                seen.add(reference_id)
        if not selected:
            for reference_id, reference in available.items():
                if reference.type in {"news", "market", "fund"}:
                    selected.append(reference)
                    seen.add(reference_id)
                if len(selected) >= 5:
                    break
        return selected[:8]

    @staticmethod
    def _duration(started: float) -> int:
        return max(0, round((perf_counter() - started) * 1000))
