"""Add AI review queue.

Revision ID: 0003_ai_review_queue
Revises: 0002_ingestion_framework
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_ai_review_queue"
down_revision = "0002_ingestion_framework"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_review_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("raw_response", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["news_analyses.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
    )


def downgrade() -> None:
    op.drop_table("ai_review_queue")

