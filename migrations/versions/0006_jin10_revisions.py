"""Preserve source revisions and actions for auditable news ingestion.

Revision ID: 0006_jin10_revisions
Revises: 0005_fund_center
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_jin10_revisions"
down_revision = "0005_fund_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_news",
        sa.Column("source_revision", sa.String(128), nullable=False, server_default="initial"),
    )
    op.add_column(
        "raw_news",
        sa.Column("source_action", sa.String(16), nullable=False, server_default="created"),
    )
    op.drop_constraint("uq_raw_news_fetch", "raw_news", type_="unique")
    op.create_unique_constraint(
        "uq_raw_news_fetch_revision",
        "raw_news",
        ["source", "source_item_id", "fetch_version", "source_revision"],
    )
    op.create_check_constraint(
        "ck_raw_news_source_action",
        "raw_news",
        "source_action IN ('created', 'updated', 'deleted')",
    )
    op.alter_column("raw_news", "source_revision", server_default=None)
    op.alter_column("raw_news", "source_action", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_raw_news_source_action", "raw_news", type_="check")
    op.drop_constraint("uq_raw_news_fetch_revision", "raw_news", type_="unique")
    op.create_unique_constraint(
        "uq_raw_news_fetch",
        "raw_news",
        ["source", "source_item_id", "fetch_version"],
    )
    op.drop_column("raw_news", "source_action")
    op.drop_column("raw_news", "source_revision")
