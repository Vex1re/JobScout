"""phase5_user_interactions

Revision ID: 1f2a3b4c5d6e
Revises: 7a3d1e9f0b12
Create Date: 2026-10-06 21:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f2a3b4c5d6e'
down_revision: Union[str, Sequence[str], None] = '7a3d1e9f0b12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_interactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('vacancy_canonical_id', sa.String(length=255), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_user_interactions_user_id', 'user_interactions', ['user_id'], unique=False)
    op.create_index('ix_user_interactions_vacancy_canonical_id', 'user_interactions', ['vacancy_canonical_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_user_interactions_vacancy_canonical_id', table_name='user_interactions')
    op.drop_index('ix_user_interactions_user_id', table_name='user_interactions')
    op.drop_table('user_interactions')
