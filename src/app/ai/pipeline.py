from time import monotonic

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIReviewQueue, Event, NewsItem, PromptVersion
from app.db.repositories import AIReviewQueueRepository

from .cache import AICache
from .context import ContextBuilder
from .prompts import PromptBuilder
from .providers.router import ProviderRouter
from .repository import AnalysisResultRepository
from .validator import ResponseValidator


class AIPipeline:
    def __init__(self, session: AsyncSession, router: ProviderRouter, cache: AICache | None = None) -> None:
        self.session = session
        self.router = router
        self.cache = cache
        self.contexts = ContextBuilder()
        self.prompts = PromptBuilder()
        self.validator = ResponseValidator()
        self.reviews = AIReviewQueueRepository(session)
        self.analyses = AnalysisResultRepository(session)

    async def analyze(self, event: Event, news: NewsItem, prompt_version: PromptVersion, provider: str | None = None):
        context = await self.contexts.build(event, news)
        prompt = self.prompts.build(prompt_version, context)
        if self.cache:
            cached = await self.cache.get(prompt.prompt_version, news.content_hash)
            if cached:
                output = self.validator.validate(cached["output"])
                from .providers.base import ProviderResult
                event.importance = output.importance
                event.summary = output.summary
                event.event_type = output.category
                event.markets = {"assets": [impact.asset for impact in output.market_impacts]}
                event.status = "succeeded"
                analysis = await self.analyses.save(event.id, news.id, prompt_version.id, prompt.cache_material, output, ProviderResult.from_dict(cached["provider_result"]), 0)
                await self.session.commit()
                return analysis
        started = monotonic()
        try:
            provider_result = await self.router.route(provider).analyze(prompt)
        except Exception as exc:
            event.status = "failed"
            await self.reviews.add(AIReviewQueue(event_id=event.id, reason=f"provider error: {exc}", raw_response={}))
            await self.session.commit()
            raise
        try:
            output = self.validator.validate(provider_result.output)
        except ValueError as exc:
            event.status = "failed"
            await self.reviews.add(AIReviewQueue(event_id=event.id, reason=str(exc), raw_response=provider_result.raw_response))
            await self.session.commit()
            raise
        duration_ms = int((monotonic() - started) * 1000)
        analysis = await self.analyses.save(event.id, news.id, prompt_version.id, prompt.cache_material, output, provider_result, duration_ms)
        event.importance = output.importance
        event.summary = output.summary
        event.event_type = output.category
        event.markets = {"assets": [impact.asset for impact in output.market_impacts]}
        event.status = "succeeded"
        await self.session.commit()
        if self.cache:
            await self.cache.set(prompt.prompt_version, news.content_hash, {"output": output.model_dump(), "provider_result": provider_result.to_dict()})
        return analysis
