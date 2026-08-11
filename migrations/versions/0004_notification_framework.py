"""Add notification decision and preference models.

Revision ID: 0004_notification_framework
Revises: 0003_ai_review_queue
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_notification_framework"
down_revision = "0003_ai_review_queue"
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
        "notifications", *common_columns(),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("merged_from", postgresql.JSONB(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.CheckConstraint("priority BETWEEN 1 AND 5", name="ck_notification_priority"),
    )
    op.create_index("ix_notifications_event_status", "notifications", ["event_id", "status"])
    op.create_table(
        "user_preferences", *common_columns(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("markets", postgresql.JSONB(), nullable=False),
        sa.Column("assets", postgresql.JSONB(), nullable=False),
        sa.Column("categories", postgresql.JSONB(), nullable=False),
        sa.Column("minimum_importance", sa.SmallInteger(), nullable=False),
        sa.Column("quiet_hours_start", sa.String(5), nullable=False),
        sa.Column("quiet_hours_end", sa.String(5), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_user_preference_user"),
        sa.CheckConstraint("minimum_importance BETWEEN 1 AND 5", name="ck_preference_importance"),
    )
    op.create_table(
        "notification_timelines", *common_columns(),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"]),
    )
    op.drop_constraint("uq_push_idempotency", "push_deliveries", type_="unique")
    op.add_column("push_deliveries", sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False))
    op.add_column("push_deliveries", sa.Column("provider_message_id", sa.String(255), nullable=True))
    op.add_column("push_deliveries", sa.Column("response_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("push_deliveries", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("push_deliveries", "analysis_id", nullable=True)
    op.create_foreign_key("fk_push_notification", "push_deliveries", "notifications", ["notification_id"], ["id"])
    op.create_unique_constraint("uq_push_idempotency", "push_deliveries", ["notification_id", "channel", "destination"])


def downgrade() -> None:
    op.drop_constraint("uq_push_idempotency", "push_deliveries", type_="unique")
    op.drop_constraint("fk_push_notification", "push_deliveries", type_="foreignkey")
    op.alter_column("push_deliveries", "analysis_id", nullable=False)
    for column in ("sent_at", "response_data", "provider_message_id", "notification_id"):
        op.drop_column("push_deliveries", column)
    op.create_unique_constraint("uq_push_idempotency", "push_deliveries", ["analysis_id", "channel", "destination"])
    op.drop_table("notification_timelines")
    op.drop_table("user_preferences")
    op.drop_index("ix_notifications_event_status", table_name="notifications")
    op.drop_table("notifications")

