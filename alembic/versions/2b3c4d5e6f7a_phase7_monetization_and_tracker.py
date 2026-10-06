"""phase7_monetization_and_tracker

Revision ID: 2b3c4d5e6f7a
Revises: 1f2a3b4c5d6e
Create Date: 2026-10-06 22:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b3c4d5e6f7a'
down_revision: Union[str, Sequence[str], None] = '1f2a3b4c5d6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with subscriptions, entitlements, and application tracker."""
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('plan', sa.String(length=50), server_default='free', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=True)

    op.create_table(
        'entitlements',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('feature', sa.String(length=100), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entitlements_user_id'), 'entitlements', ['user_id'], unique=False)
    op.create_index(op.f('ix_entitlements_feature'), 'entitlements', ['feature'], unique=False)

    op.create_table(
        'job_application_tracker',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('vacancy_id', sa.String(length=255), nullable=True),
        sa.Column('vacancy_canonical_id', sa.String(length=255), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('company', sa.String(length=255), nullable=False),
        sa.Column('url', sa.String(length=1024), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='applied', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('salary_offered', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_application_tracker_user_id'), 'job_application_tracker', ['user_id'], unique=False)
    op.create_index(op.f('ix_job_application_tracker_canonical_id'), 'job_application_tracker', ['vacancy_canonical_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('job_application_tracker')
    op.drop_table('entitlements')
    op.drop_table('subscriptions')
