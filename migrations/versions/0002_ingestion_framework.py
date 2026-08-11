"""Add raw ingestion, cursors, runtime config and audit log.

Revision ID: 0002_ingestion_framework
Revises: 0001_initial_schema
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_ingestion_framework"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def common_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "raw_news", *common_columns(),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_item_id", sa.String(128), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(), nullable=False),
        sa.Column("headers", postgresql.JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("fetch_version", sa.String(32), nullable=False),
        sa.UniqueConstraint("source", "source_item_id", "fetch_version", name="uq_raw_news_fetch"),
    )
    op.create_table(
        "source_cursors", *common_columns(),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("last_id", sa.String(128), nullable=True),
        sa.Column("last_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_data", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("source", name="uq_source_cursor_source"),
    )
    op.add_column("news_items", sa.Column("raw_news_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_news_items_raw_news_id", "news_items", "raw_news", ["raw_news_id"], ["id"])
    op.create_table(
        "system_configs", *common_columns(),
        sa.Column("config_key", sa.String(128), nullable=False),
        sa.Column("config_value", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.UniqueConstraint("config_key", name="uq_system_config_key"),
    )
    op.create_table(
        "audit_logs", *common_columns(),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before_data", postgresql.JSONB(), nullable=False),
        sa.Column("after_data", postgresql.JSONB(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_constraint("fk_news_items_raw_news_id", "news_items", type_="foreignkey")
    op.drop_column("news_items", "raw_news_id")
    for table in ("audit_logs", "system_configs", "source_cursors", "raw_news"):
        op.drop_table(table)
