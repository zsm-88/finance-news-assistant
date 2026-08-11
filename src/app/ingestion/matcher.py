import hashlib
import re
from datetime import timedelta
from difflib import SequenceMatcher

from app.db.repositories import EventRepository

from .contracts import NormalizedNews

SOURCE_PREFIX = re.compile(r"^(?:金十数据|财联社|证券时报|东方财富|快讯)[：:\s]+")
NON_WORD = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
ENTITY_PATTERN = re.compile(
    r"(?:[A-Z]{2,8}|\d{6}|中国|美国|欧元区|日本|英国|美联储|央行|证监会|"
    r"国务院|CPI|PPI|GDP|非农|黄金|原油|美元|人民币|比特币)",
    re.IGNORECASE,
)


def normalize_title(value: str) -> str:
    value = SOURCE_PREFIX.sub("", value.strip())
    return NON_WORD.sub("", value).lower()


def title_tokens(value: str) -> set[str]:
    normalized = normalize_title(value)
    latin = set(re.findall(r"[a-z]+|\d+(?:\.\d+)?", normalized))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    return latin | {chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))}


def entities(value: str) -> set[str]:
    return {match.group(0).lower() for match in ENTITY_PATTERN.finditer(value)}


class DeterministicEventMatcher:
    def __init__(self, events: EventRepository | None = None, window_hours: int = 3) -> None:
        self.events = events
        self.window = timedelta(hours=window_hours)

    async def match(self, news: NormalizedNews) -> str:
        normalized = normalize_title(news.title)
        fallback = hashlib.sha256(normalized.encode()).hexdigest()
        if self.events is None or not normalized:
            return fallback

        incoming_tokens = title_tokens(news.title)
        incoming_entities = entities(news.title)
        candidates = await self.events.in_window(
            news.published_at - self.window,
            news.published_at + self.window,
        )
        best_key: str | None = None
        best_score = 0.0
        for event in candidates:
            candidate = normalize_title(event.title)
            if candidate == normalized:
                return event.event_key
            candidate_tokens = title_tokens(event.title)
            union = incoming_tokens | candidate_tokens
            token_score = len(incoming_tokens & candidate_tokens) / len(union) if union else 0.0
            sequence_score = SequenceMatcher(None, normalized, candidate).ratio()
            shared_entities = incoming_entities & entities(event.title)
            entity_bonus = min(0.25, len(shared_entities) * 0.1)
            score = max(token_score, sequence_score) + entity_bonus
            if score > best_score:
                best_key, best_score = event.event_key, score
        if best_key is not None and best_score >= 0.72:
            return best_key
        return fallback
