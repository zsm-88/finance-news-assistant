"""Report service: uses AI to generate daily/weekly financial briefings."""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import ProviderResult
from app.ai.providers.router import ProviderRouter
from app.db.models import Event
from app.db.repositories import EventRepository
from app.ingestion.contracts import SourceAdapter
from app.notifications.channels.base import NotificationMessage

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = """你是一名专业的财经简报分析师。根据给定的时间范围内的新闻事件列表，生成一份结构化简报。

规则：
1. 全部输出必须使用简体中文
2. 按重要性降序排列事件（重要性5最高，1最低）
3. 每个事件附带一句话点评
4. 最后给出整体市场情绪判断
5. 严格返回符合 output_schema 的 JSON 对象

输出格式：
{
  "report_title": "今日财经简报",
  "period": "2025-01-01 ~ 2025-01-01",
  "overall_sentiment": "谨慎乐观",
  "key_events": [
    {
      "title": "事件标题",
      "importance": 5,
      "category": "宏观",
      "summary": "一句话要点",
      "brief_comment": "一句话点评",
      "market_impact": ["A股:利好", "黄金:中性"]
    }
  ],
  "summary": "当日市场整体回顾和建议"
}"""


class ReportService:
    """Generates daily/weekly financial reports using the AI pipeline."""

    def __init__(
        self,
        session: AsyncSession,
        router: ProviderRouter,
    ) -> None:
        self.session = session
        self.router = router

    async def generate(
        self,
        period: Literal["daily", "weekly"],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Generate a report for the given period.

        Args:
            period: 'daily' for past 24h, 'weekly' for past 7 days
            now: Reference timestamp (defaults to UTC now)

        Returns:
            Parsed report dict from the AI provider
        """
        current = now or datetime.now(UTC)
        if period == "daily":
            start = current - timedelta(hours=24)
            report_type = "今日"
        else:
            start = current - timedelta(days=7)
            report_type = "本周"

        events_repo = EventRepository(self.session)
        events = await events_repo.in_window(start, current, limit=50)

        if not events:
            logger.info("No events found for %s report period", period)
            return {
                "report_title": f"{report_type}财经简报",
                "period": f"{start.strftime('%Y-%m-%d')} ~ {current.strftime('%Y-%m-%d')}",
                "overall_sentiment": "无数据",
                "key_events": [],
                "summary": f"{report_type}没有重要财经事件。",
            }

        prompt = self._build_report_prompt(events, report_type, start, current)
        provider_result = await self.router.route().analyze(prompt)
        return provider_result.output

    def _build_report_prompt(
        self,
        events: list[Event],
        report_type: str,
        start: datetime,
        end: datetime,
    ) -> Any:
        """Build a BuiltPrompt-like dict for the report task."""

        class _BuiltPrompt:
            def __init__(self, system: str, task: str):
                self.system = system
                self.task = task

        event_list = []
        for e in events:
            event_list.append({
                "title": e.title,
                "importance": e.importance,
                "category": e.event_type,
                "summary": e.summary or "",
                "occurred_at": e.occurred_at.isoformat() if e.occurred_at else "",
                "markets": e.markets or {},
            })

        task = json.dumps(
            {
                "report_type": report_type,
                "period": f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}",
                "events": event_list,
            },
            ensure_ascii=False,
        )
        return _BuiltPrompt(REPORT_SYSTEM_PROMPT, task)

    async def generate_and_push_text(
        self,
        period: Literal["daily", "weekly"],
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Generate a report and format it as markdown text for push channels.

        Returns:
            (raw_report, markdown_text)
        """
        report = await self.generate(period, now)
        lines: list[str] = []
        lines.append(f"# {report.get('report_title', '财经简报')}")
        lines.append("")
        lines.append(f"**时期**: {report.get('period', '')}")
        lines.append(f"**市场情绪**: {report.get('overall_sentiment', '未知')}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for ev in report.get("key_events", []):
            stars = "★" * ev.get("importance", 0)
            lines.append(f"### {stars} {ev.get('title', '')}")
            lines.append(f"*分类*: {ev.get('category', '')}")
            lines.append(f"*要点*: {ev.get('summary', '')}")
            lines.append(f"*点评*: {ev.get('brief_comment', '')}")
            impacts = ev.get("market_impact", [])
            if impacts:
                lines.append("*影响*: " + ", ".join(impacts))
            lines.append("")

        lines.append("---")
        lines.append(report.get("summary", ""))
        return report, "\n".join(lines)

    async def push_report(
        self,
        period: Literal["daily", "weekly"],
        push_channel: Any,
        destination: str = "personal-report",
        now: datetime | None = None,
    ) -> None:
        """Generate a report and push it through a channel."""
        report, markdown = await self.generate_and_push_text(period, now)
        title = report.get("report_title", "财经简报")
        await push_channel.send(
            NotificationMessage(title=title, body=markdown, destination=destination)
        )
        logger.info(
            "Report pushed",
            extra={"period": period, "title": title, "events": len(report.get("key_events", []))},
        )