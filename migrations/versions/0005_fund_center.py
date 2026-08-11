"""Add fund watchlists and positions.

Revision ID: 0005_fund_center
Revises: 0004_notification_framework
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_fund_center"
down_revision = "0004_notification_framework"
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
        "fund_watchlists",
        *common_columns(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fund_code", sa.String(16), nullable=False),
        sa.UniqueConstraint("user_id", "fund_code", name="uq_fund_watchlist_user_code"),
    )
    op.create_index(
        "ix_fund_watchlists_user_created",
        "fund_watchlists",
        ["user_id", "created_at"],
    )
    op.create_table(
        "fund_positions",
        *common_columns(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fund_code", sa.String(16), nullable=False),
        sa.Column("shares", sa.Numeric(20, 6), nullable=False),
        sa.Column("average_cost", sa.Numeric(20, 6), nullable=False),
        sa.UniqueConstraint("user_id", "fund_code", name="uq_fund_position_user_code"),
        sa.CheckConstraint("shares > 0", name="ck_fund_position_shares_positive"),
        sa.CheckConstraint(
            "average_cost >= 0",
            name="ck_fund_position_average_cost_nonnegative",
        ),
    )


def downgrade() -> None:
    op.drop_table("fund_positions")
    op.drop_index("ix_fund_watchlists_user_created", table_name="fund_watchlists")
    op.drop_table("fund_watchlists")
