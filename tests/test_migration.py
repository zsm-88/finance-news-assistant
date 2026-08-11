from pathlib import Path


def test_initial_migration_is_single_head_and_reversible() -> None:
    migration = Path("migrations/versions/0001_initial_schema.py").read_text(encoding="utf-8")
    assert 'revision = "0001_initial_schema"' in migration
    assert "down_revision = None" in migration
    assert "def downgrade()" in migration


def test_m10_revision_migration_is_reversible() -> None:
    migration = Path("migrations/versions/0006_jin10_revisions.py").read_text(encoding="utf-8")
    assert 'revision = "0006_jin10_revisions"' in migration
    assert 'down_revision = "0005_fund_center"' in migration
    assert "source_revision" in migration
    assert "source_action" in migration
    assert "def downgrade()" in migration


def test_m13_ai_usage_migration_is_minimal_and_reversible() -> None:
    migration = Path("migrations/versions/0007_ai_assistant_usage.py").read_text(
        encoding="utf-8"
    )
    assert 'revision = "0007_ai_assistant_usage"' in migration
    assert 'down_revision = "0006_jin10_revisions"' in migration
    assert '"analysis_id"' in migration
    assert '"purpose"' in migration
    assert '"intent"' in migration
    assert '"success"' in migration
    assert "create_table" not in migration
    assert "def downgrade()" in migration
