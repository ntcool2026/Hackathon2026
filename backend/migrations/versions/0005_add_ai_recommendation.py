"""add ai_recommendation to stock_scores

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_scores", sa.Column("ai_recommendation", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("stock_scores", "ai_recommendation")
