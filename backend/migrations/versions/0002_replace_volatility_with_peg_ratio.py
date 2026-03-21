"""Replace volatility with peg_ratio in stock_data

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stock_data", sa.Column("peg_ratio", sa.Numeric(), nullable=True))
    op.drop_column("stock_data", "volatility")


def downgrade() -> None:
    op.add_column("stock_data", sa.Column("volatility", sa.Numeric(), nullable=True))
    op.drop_column("stock_data", "peg_ratio")
