"""Extend AI usage records for finance assistant requests.

Revision ID: 0007_ai_assistant_usage
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_ai_assistant_usage"
down_revision = "0006_jin10_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("ai_usages", "analysis_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column(
        "ai_usages",
        sa.Column("purpose", sa.String(32), nullable=False, server_default="news_analysis"),
    )
    op.add_column("ai_usages", sa.Column("intent", sa.String(32), nullable=True))
    op.add_column(
        "ai_usages",
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("ai_usages", sa.Column("error_type", sa.String(64), nullable=True))
    op.alter_column("ai_usages", "purpose", server_default=None)
    op.alter_column("ai_usages", "success", server_default=None)


def downgrade() -> None:
    op.drop_column("ai_usages", "error_type")
    op.drop_column("ai_usages", "success")
    op.drop_column("ai_usages", "intent")
    op.drop_column("ai_usages", "purpose")
    op.execute("DELETE FROM ai_usages WHERE analysis_id IS NULL")
    op.alter_column("ai_usages", "analysis_id", existing_type=sa.Uuid(), nullable=False)
