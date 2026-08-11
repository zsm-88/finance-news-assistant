from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIUsage


class AssistantUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        provider: str,
        model: str,
        intent: str,
        success: bool,
        duration_ms: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        error_type: str | None = None,
        analysis_id: UUID | None = None,
    ) -> AIUsage:
        usage = AIUsage(
            analysis_id=analysis_id,
            purpose="finance_assistant",
            intent=intent,
            success=success,
            error_type=error_type,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
        )
        self.session.add(usage)
        await self.session.commit()
        return usage
