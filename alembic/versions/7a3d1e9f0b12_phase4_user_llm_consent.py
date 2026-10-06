"""phase4_user_llm_consent

Revision ID: 7a3d1e9f0b12
Revises: de3c2da402e4
Create Date: 2026-10-06 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a3d1e9f0b12'
down_revision: Union[str, Sequence[str], None] = 'de3c2da402e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('llm_consent', sa.Boolean(), server_default=sa.text('0'), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'llm_consent')
