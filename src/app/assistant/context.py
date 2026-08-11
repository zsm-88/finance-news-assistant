from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.db.models import Event, NewsItem
from app.db.repositories import AnalysisRepository, EventRepository, NewsRepository
from app.fund.service import FundService
from app.market.service import MarketService

from .contracts import AssistantIntent, AssistantReference

SOURCE_NAMES = {
    "chinanews": "中新网财经",
    "tmtpost": "钛媒体",
    "cnbc": "CNBC",
    "jin10": "金十数据",
}
SOURCE_PRIORITY = {"chinanews": 0, "tmtpost": 1, "cnbc": 2}


@dataclass(slots=True)
class AssistantContext:
    payload: dict[str, Any]
    references: dict[str, AssistantReference]
    data_time: datetime
    data_status: str


class AssistantContextBuilder:
    def __init__(
        self,
        events: EventRepository,
        news: NewsRepository,
        analyses: AnalysisRepository,
        market: MarketService,
        funds: FundService,
        max_events: int = 10,
    ) -> None:
        self.events = events
        self.news = news
        self.analyses = analyses
        self.market = market
        self.funds = funds
        self.max_events = max_events

    async def build(self, intent: AssistantIntent, message: str = "") -> AssistantContext:
        payload: dict[str, Any] = {}
        references: dict[str, AssistantReference] = {}
        times: list[datetime] = []
        statuses: list[str] = []
        market_cutoff: datetime | None = None

        if intent in {
            AssistantIntent.MARKET,
            AssistantIntent.NEWS_MARKET,
            AssistantIntent.MARKET_EVENT,
            AssistantIntent.GENERAL_FINANCE,
        }:
            market_data, market_refs, market_times, market_stale = await self._market(message)
            payload["market"] = market_data
            references.update(market_refs)
            times.extend(market_times)
            market_cutoff = max(market_times) if market_times else None
            if market_stale:
                statuses.append("行情为最近交易日数据，不是实时行情")

        if intent in {
            AssistantIntent.NEWS,
            AssistantIntent.NEWS_MARKET,
            AssistantIntent.MARKET_EVENT,
            AssistantIntent.GENERAL_FINANCE,
        }:
            cutoff = market_cutoff if intent is AssistantIntent.NEWS_MARKET else None
            relevant_asset = self._relevant_asset(message) if cutoff else None
            event_data, event_refs, event_times = await self._events(cutoff, relevant_asset)
            payload["events"] = event_data
            references.update(event_refs)
            times.extend(event_times)
            if intent is AssistantIntent.NEWS_MARKET and not event_data:
                statuses.append("缺少行情截止时间之前的事件，无法确认涨跌原因")

        if intent in {AssistantIntent.FUND, AssistantIntent.FUND_ANALYSIS}:
            fund_data, fund_refs, fund_times, fund_status = await self._funds(intent)
            payload["funds"] = fund_data
            references.update(fund_refs)
            times.extend(fund_times)
            statuses.extend(fund_status)

        if not payload:
            payload["available_data"] = "当前问题没有匹配到可检索的项目数据"
            statuses.append("数据不足")
        data_time = max(times) if times else datetime.now(UTC)
        return AssistantContext(
            payload=payload,
            references=references,
            data_time=data_time,
            data_status="；".join(dict.fromkeys(statuses)) or "数据正常",
        )

    async def _events(
        self,
        cutoff: datetime | None = None,
        relevant_asset: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, AssistantReference], list[datetime]]:
        result: list[dict[str, Any]] = []
        refs: dict[str, AssistantReference] = {}
        times: list[datetime] = []
        candidates = await self.events.latest(self.max_events * 5 if cutoff else self.max_events)
        events = [event for event in candidates if cutoff is None or event.occurred_at <= cutoff]
        for event in events[: self.max_events]:
            items = sorted(
                await self.news.for_event(event.id),
                key=lambda item: (SOURCE_PRIORITY.get(item.source, 9), -item.published_at.timestamp()),
            )
            representative = items[0] if items else None
            analysis = await self.analyses.latest_for_event(event.id)
            impacts = await self.analyses.impacts(analysis.id) if analysis else []
            if relevant_asset and not any(
                impact.asset.casefold() == relevant_asset.casefold() for impact in impacts
            ):
                continue
            reference_id = f"event:{event.id}"
            news_reference_id = None
            if representative is not None:
                news_reference_id = f"news:{representative.id}"
                reference_id = news_reference_id
                refs[reference_id] = self._news_reference(representative)
                times.append(representative.published_at)
            else:
                refs[reference_id] = self._event_reference(event)
            times.append(event.occurred_at)
            result.append(
                {
                    "reference_id": reference_id,
                    "news_reference_id": news_reference_id,
                    "title": event.title,
                    "occurred_at": event.occurred_at.isoformat(),
                    "importance": event.importance,
                    "event_type": event.event_type,
                    "summary": analysis.summary if analysis else event.summary,
                    "news_source": SOURCE_NAMES.get(representative.source, representative.source)
                    if representative
                    else None,
                    "market_impacts": [
                        {
                            "asset": impact.asset,
                            "direction": impact.direction,
                            "reason": impact.reason,
                            "confidence": impact.confidence,
                        }
                        for impact in impacts
                    ],
                }
            )
        return result, refs, times

    async def _market(
        self,
        message: str,
    ) -> tuple[list[dict[str, Any]], dict[str, AssistantReference], list[datetime], bool]:
        response = await self.market.list_quotes()
        rows: list[dict[str, Any]] = []
        refs: dict[str, AssistantReference] = {}
        times: list[datetime] = []
        stale = False
        selected = self._select_quotes(response.items, message)
        for quote in selected:
            if quote.price is None:
                continue
            reference_id = f"market:{quote.symbol}"
            refs[reference_id] = AssistantReference(
                type="market",
                id=quote.symbol,
                title=quote.name,
                source=quote.source,
                published_at=quote.timestamp,
            )
            rows.append({"reference_id": reference_id, **quote.model_dump(mode="json")})
            if quote.timestamp:
                times.append(quote.timestamp)
            stale = stale or quote.is_stale
        return rows, refs, times, stale

    @staticmethod
    def _select_quotes(quotes, message: str):  # type: ignore[no-untyped-def]
        symbol_keywords = {
            "上证": "sh000001",
            "深证": "sz399001",
            "创业板": "sz399006",
            "沪深300": "sh000300",
            "恒生": "hk_hsi",
            "纳斯达克": "us_ixic",
            "标普": "us_gspc",
            "道琼斯": "us_dji",
        }
        symbols = {symbol for keyword, symbol in symbol_keywords.items() if keyword in message}
        if symbols:
            return [quote for quote in quotes if quote.symbol in symbols]
        if "A股" in message or "a股" in message:
            return [quote for quote in quotes if quote.market == "CN"]
        if "港股" in message:
            return [quote for quote in quotes if quote.market == "HK"]
        if "美股" in message:
            return [quote for quote in quotes if quote.market == "US"]
        return quotes

    @staticmethod
    def _relevant_asset(message: str) -> str | None:
        if "港股" in message or "恒生" in message:
            return "港股"
        if any(value in message for value in ("美股", "纳斯达克", "标普", "道琼斯")):
            return "美股"
        if "黄金" in message or "金价" in message:
            return "黄金"
        if any(value in message for value in ("A股", "a股", "上证", "深证", "创业板", "沪深")):
            return "A股"
        return None

    async def _funds(
        self, intent: AssistantIntent
    ) -> tuple[list[dict[str, Any]], dict[str, AssistantReference], list[datetime], list[str]]:
        response = await self.funds.watchlist()
        rows: list[dict[str, Any]] = []
        refs: dict[str, AssistantReference] = {}
        times: list[datetime] = [response.generated_at]
        statuses: list[str] = []
        for item in response.items[:5]:
            reference_id = f"fund:{item.code}"
            refs[reference_id] = AssistantReference(
                type="fund",
                id=item.code,
                title=item.name,
                source=(
                    item.official_nav.source
                    if item.official_nav.value is not None
                    else "基金自选（正式净值暂缺）"
                ),
                published_at=None,
            )
            row = {"reference_id": reference_id, **item.model_dump(mode="json")}
            if intent is AssistantIntent.FUND_ANALYSIS and len(rows) < 3:
                history = await self.funds.nav_history(item.code, "1m")
                row["official_nav_history"] = history.model_dump(mode="json")
                if history.status != "available":
                    statuses.append(history.message or "当前暂无基金历史净值数据")
            rows.append(row)
        if not response.provider_configured:
            statuses.append(response.message or "基金正式数据源未配置")
        if not rows:
            statuses.append("当前没有自选基金数据")
        return rows, refs, times, statuses

    @staticmethod
    def _news_reference(news: NewsItem) -> AssistantReference:
        return AssistantReference(
            type="news",
            id=str(news.id),
            title=news.title,
            source=SOURCE_NAMES.get(news.source, news.source),
            published_at=news.published_at,
        )

    @staticmethod
    def _event_reference(event: Event) -> AssistantReference:
        return AssistantReference(
            type="event",
            id=str(event.id),
            title=event.title,
            source="财经事件",
            published_at=event.occurred_at,
        )
