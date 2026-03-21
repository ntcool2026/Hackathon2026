"""Add ai_risk_score to stock_scores

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stock_scores", sa.Column("ai_risk_score", sa.Numeric(), nullable=True))


def downgrade() -> None:
    op.drop_column("stock_scores", "ai_risk_score")
