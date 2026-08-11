from datetime import UTC, datetime

from app.ingestion.contracts import RawNewsPayload
from app.ingestion.normalizer import DefaultNormalizer
from app.jobs.task import Task


def test_task_round_trip() -> None:
    task = Task(type="collect", payload={"source": "jin10"})
    restored = Task.deserialize(task.serialize())
    assert restored.type == "collect"
    assert restored.payload == {"source": "jin10"}
    assert restored.created_at.tzinfo == UTC


def test_normalizer_preserves_source_identity() -> None:
    raw = RawNewsPayload(
        source="jin10",
        source_item_id="42",
        raw_json={"title": "Title", "content": "Body", "published_at": "2026-08-08T00:00:00+00:00"},
        headers={"etag": "abc"},
        received_at=datetime.now(UTC),
        content_hash="x",
        fetch_version="v1",
    )
    result = DefaultNormalizer().normalize(raw)
    assert result.source == "jin10"
    assert result.source_item_id == "42"
    assert result.title == "Title"
