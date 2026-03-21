"""add price_change_pct to stock_data

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_data", sa.Column("price_change_pct", sa.Numeric(), nullable=True))


def downgrade() -> None:
    op.drop_column("stock_data", "price_change_pct")
