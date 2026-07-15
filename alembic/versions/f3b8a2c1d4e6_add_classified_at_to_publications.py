"""add_classified_at_to_publications

Revision ID: f3b8a2c1d4e6
Revises: 17a128e4d3a5
Create Date: 2026-07-14 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3b8a2c1d4e6'
down_revision: Union[str, Sequence[str], None] = '17a128e4d3a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE publications
        ADD COLUMN classified_at TIMESTAMPTZ
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE publications
        DROP COLUMN classified_at
    """)
