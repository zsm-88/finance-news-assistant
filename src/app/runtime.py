import logging
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cache import AICache
from app.ai.pipeline import AIPipeline
from app.ai.providers.openai_compatible import OpenAICompatibleAdapter
from app.ai.providers.registry import ProviderRegistry
from app.ai.providers.router import ProviderRouter
from app.config import Settings
from app.db.models import PromptVersion, UserPreference
from app.db.repositories import EventRepository, PromptVersionRepository, UserPreferenceRepository
from app.ingestion.contracts import SourceAdapter
from app.ingestion.jin10 import Jin10Adapter
from app.ingestion.matcher import DeterministicEventMatcher
from app.ingestion.normalizer import DefaultNormalizer
from app.ingestion.rss import RssSourceAdapter
from app.ingestion.service import IngestionService
from app.notifications.channels.registry import PushChannelRegistry
from app.notifications.channels.telegram import TelegramChannel
from app.notifications.channels.wecom import WeComChannel
from app.notifications.service import NotificationService
from app.report.service import ReportService

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_VERSION = "m10-zh-v1"
DEFAULT_PROMPT = """你是一名严谨的财经新闻分析师。仅分析输入的事件上下文，不负责把英文新闻逐句翻译。所有面向用户的文本字段必须使用简体中文，包括 summary、category 和每项 market_impacts.reason。summary 应概括事件及其关键信息；importance 必须为 1 到 5 的整数；市场影响只能使用输出 Schema 允许的资产和方向，并用简体中文简洁说明原因。严格返回一个符合 output_schema 的 JSON 对象，不要输出 Markdown 或 JSON 以外的说明。"""


async def ensure_runtime_records(session: AsyncSession, settings: Settings) -> tuple[PromptVersion, UserPreference]:
    prompts = PromptVersionRepository(session)
    prompt = await prompts.by_name_version("event-analysis", DEFAULT_PROMPT_VERSION)
    if prompt is None:
        prompt = PromptVersion(prompt_name="event-analysis", version=DEFAULT_PROMPT_VERSION, prompt_content=DEFAULT_PROMPT, enabled=True)
        await prompts.add(prompt)
    await prompts.enable_exclusively(prompt)
    user_id = UUID(settings.notification_user_id)
    preferences = UserPreferenceRepository(session)
    preference = await preferences.for_user(user_id)
    if preference is None:
        preference = UserPreference(user_id=user_id, markets=[], assets=[], categories=[], minimum_importance=settings.push_min_importance, quiet_hours_start=settings.quiet_hours_start, quiet_hours_end=settings.quiet_hours_end)
        await preferences.add(preference)
    await session.commit()
    return prompt, preference


def validate_runtime_settings(settings: Settings) -> None:
    if settings.enable_ai and not all((settings.ai_base_url, settings.ai_api_key, settings.ai_model)):
        raise RuntimeError("ENABLE_AI requires AI_BASE_URL, AI_API_KEY and AI_MODEL")
    if settings.enable_push and not settings.wecom_webhook_url:
        raise RuntimeError("ENABLE_PUSH requires WECOM_WEBHOOK_URL")


async def run_cycle(session: AsyncSession, redis, settings: Settings) -> int:
    validate_runtime_settings(settings)
    prompt, preference = await ensure_runtime_records(session, settings)
    news_items = []
    if settings.enable_crawler:
        async with (
            httpx.AsyncClient(timeout=settings.jin10_request_timeout_seconds) as jin10_client,
            httpx.AsyncClient(
                timeout=settings.rss_request_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; FinanceAssistant/1.0)"},
            ) as rss_client,
        ):
            adapters: list[SourceAdapter] = []
            if settings.enable_chinanews:
                adapters.append(
                    RssSourceAdapter(
                        "chinanews",
                        settings.chinanews_rss_url,
                        rss_client,
                        fetch_version="chinanews-finance-rss-v1",
                    )
                )
            if settings.enable_tmtpost:
                adapters.append(
                    RssSourceAdapter(
                        "tmtpost",
                        settings.tmtpost_rss_url,
                        rss_client,
                        fetch_version="tmtpost-rss-v1",
                    )
                )
            if settings.enable_eastmoney:
                adapters.append(
                    RssSourceAdapter(
                        "eastmoney",
                        settings.eastmoney_rss_url,
                        rss_client,
                        fetch_version="eastmoney-finance-rss-v1",
                    )
                )
            if settings.enable_cls:
                adapters.append(
                    RssSourceAdapter(
                        "cls",
                        settings.cls_rss_url,
                        rss_client,
                        fetch_version="cls-telegraph-v1",
                    )
                )
            if settings.enable_stcn:
                adapters.append(
                    RssSourceAdapter(
                        "stcn",
                        settings.stcn_rss_url,
                        rss_client,
                        fetch_version="stcn-finance-rss-v1",
                    )
                )
            if settings.enable_wallstreetcn:
                adapters.append(
                    RssSourceAdapter(
                        "wallstreetcn",
                        settings.wallstreetcn_rss_url,
                        rss_client,
                        fetch_version="wallstreetcn-global-rss-v1",
                    )
                )
            if settings.enable_jin10 and settings.jin10_secret_key:
                adapters.append(
                    Jin10Adapter(
                        settings.jin10_secret_key,
                        settings.jin10_base_url,
                        settings.jin10_market_category,
                        jin10_client,
                    )
                )
            elif settings.enable_jin10:
                logger.warning("金十数据源未配置")
            if settings.enable_cnbc_fallback:
                adapters.append(
                    RssSourceAdapter(
                        settings.news_source_name,
                        settings.news_source_url,
                        rss_client,
                    )
                )
            for adapter in adapters:
                try:
                    ingestion = IngestionService(
                        session,
                        adapter,
                        DefaultNormalizer(),
                        DeterministicEventMatcher(EventRepository(session)),
                    )
                    source_news = await ingestion.ingest(settings.max_items_per_cycle)
                    await session.commit()
                    news_items.extend(source_news)
                except Exception:
                    await session.rollback()
                    logger.exception("news source collection failed", extra={"source": adapter.name})
    logger.info("collection completed", extra={"news_count": len(news_items)})
    if not settings.enable_ai:
        return len(news_items)

    providers = ProviderRegistry()
    providers.register(OpenAICompatibleAdapter(settings.ai_base_url or "", settings.ai_api_key or "", settings.ai_model or ""))
    pipeline = AIPipeline(session, ProviderRouter(providers, "openai-compatible"), AICache(redis))
    channels = PushChannelRegistry()
    if settings.enable_push:
        channels.register(WeComChannel(settings.wecom_webhook_url or ""))
        if settings.telegram_bot_token and settings.telegram_chat_id:
            channels.register(
                TelegramChannel(settings.telegram_bot_token, settings.telegram_chat_id)
            )
    notifier = NotificationService(session, channels)
    events = EventRepository(session)

    for news in news_items:
        event = await events.get(news.event_id)
        if event is None:
            continue
        try:
            await pipeline.analyze(event, news, prompt)
            if settings.enable_push:
                await notifier.process(event, preference, "wecom", settings.push_destination)
        except Exception:
            await session.rollback()
            logger.exception("news processing failed", extra={"news_id": str(news.id), "event_id": str(news.event_id)})
    return len(news_items)


async def run_report(
    session: AsyncSession,
    settings: Settings,
    period: str = "daily",
) -> dict[str, object]:
    """Generate and return a financial report for the given period."""
    if not settings.enable_ai:
        raise RuntimeError("ENABLE_AI is required for report generation")
    if not all((settings.ai_base_url, settings.ai_api_key, settings.ai_model)):
        raise RuntimeError("AI_BASE_URL, AI_API_KEY and AI_MODEL are required")

    providers = ProviderRegistry()
    providers.register(OpenAICompatibleAdapter(
        settings.ai_base_url or "",
        settings.ai_api_key or "",
        settings.ai_model or "",
    ))
    router = ProviderRouter(providers, "openai-compatible")
    service = ReportService(session, router)
    report = await service.generate(period)  # type: ignore[arg-type]
    return report
