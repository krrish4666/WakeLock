"""add_missing_enum_values

Revision ID: 2cde6a0e4eb5
Revises: 004a88078d1c
Create Date: 2026-08-18 13:29:07.822075

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2cde6a0e4eb5'
down_revision: Union[str, None] = '004a88078d1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get the current database connection
    bind = op.get_bind()
    
    # Check if the dialect is PostgreSQL
    if bind.dialect.name == 'postgresql':
        # Add new enum values to the existing PostgreSQL transactiontype enum
        # Note: IF NOT EXISTS is supported in PostgreSQL 9.3+
        op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'PLAN_LOCK'")
        op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'REFUND'")
        op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'WITHDRAWAL'")

def downgrade() -> None:
    # PostgreSQL does not easily support removing enum values.
    # We leave the enum values in place as this is a non-destructive schema update.
    # Therefore, downgrade is intentionally a no-op.
    pass
