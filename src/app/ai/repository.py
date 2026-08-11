from uuid import UUID

from app.db.models import AIUsage, MarketImpact, NewsAnalysis
from app.db.repositories import AnalysisRepository

from .providers.base import ProviderResult
from .schemas import AnalysisOutput


class AnalysisResultRepository(AnalysisRepository):
    async def save(self, event_id: UUID, news_id: UUID, prompt_version_id: UUID, prompt_text: str, result: AnalysisOutput, provider_result: ProviderResult, duration_ms: int) -> NewsAnalysis:
        analysis = NewsAnalysis(event_id=event_id, news_id=news_id, prompt_version_id=prompt_version_id, provider=provider_result.provider, model=provider_result.model, category=result.category, markets={"assets": [impact.asset for impact in result.market_impacts]}, importance=result.importance, summary=result.summary, confidence=result.confidence, raw_response=provider_result.raw_response, prompt_text_snapshot=prompt_text, duration_ms=duration_ms)
        await self.add(analysis)
        for impact in result.market_impacts:
            self.session.add(MarketImpact(analysis_id=analysis.id, asset=impact.asset, direction=impact.direction, confidence=impact.confidence, reason=impact.reason))
        self.session.add(AIUsage(analysis_id=analysis.id, provider=provider_result.provider, model=provider_result.model, prompt_tokens=provider_result.prompt_tokens, completion_tokens=provider_result.completion_tokens, total_tokens=provider_result.total_tokens, duration_ms=duration_ms))
        await self.session.flush()
        return analysis

