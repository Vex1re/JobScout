"""phase2_vacancies_ingestion

Revision ID: de3c2da402e4
Revises: d98b492d0c53
Create Date: 2026-10-06 21:17:42.147381

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de3c2da402e4'
down_revision: Union[str, Sequence[str], None] = 'd98b492d0c53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('vacancies', sa.Column('external_id', sa.String(length=255), nullable=True))
    op.add_column('vacancies', sa.Column('canonical_id', sa.String(length=255), nullable=True))
    op.add_column('vacancies', sa.Column('salary_from', sa.Integer(), nullable=True))
    op.add_column('vacancies', sa.Column('salary_to', sa.Integer(), nullable=True))
    op.add_column('vacancies', sa.Column('salary_gross_net', sa.String(length=20), server_default='unknown', nullable=False))
    op.add_column('vacancies', sa.Column('salary_rub_normalized', sa.Integer(), nullable=True))
    op.add_column('vacancies', sa.Column('snippet', sa.String(length=1000), nullable=True))
    op.add_column('vacancies', sa.Column('skills', sa.JSON(), nullable=True))
    op.add_column('vacancies', sa.Column('remote_scope', sa.String(length=50), server_default='unknown', nullable=False))
    op.add_column('vacancies', sa.Column('city_norm', sa.String(length=100), nullable=True))
    op.add_column('vacancies', sa.Column('required_experience', sa.String(length=100), nullable=True))
    op.add_column('vacancies', sa.Column('grade', sa.String(length=50), nullable=True))
    op.add_column('vacancies', sa.Column('grade_confidence', sa.Float(), server_default='1.0', nullable=False))
    op.add_column('vacancies', sa.Column('red_flag_level', sa.String(length=50), server_default='safe', nullable=False))
    op.add_column('vacancies', sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('vacancies', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('vacancies', sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False))

    op.create_index('ix_vacancies_canonical_id', 'vacancies', ['canonical_id'], unique=False)
    op.create_index('ix_vacancies_city_remote', 'vacancies', ['city', 'is_remote'], unique=False)
    op.create_index('ix_vacancies_source', 'vacancies', ['source'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_vacancies_source', table_name='vacancies')
    op.drop_index('ix_vacancies_city_remote', table_name='vacancies')
    op.drop_index('ix_vacancies_canonical_id', table_name='vacancies')

    op.drop_column('vacancies', 'is_active')
    op.drop_column('vacancies', 'last_seen_at')
    op.drop_column('vacancies', 'first_seen_at')
    op.drop_column('vacancies', 'red_flag_level')
    op.drop_column('vacancies', 'grade_confidence')
    op.drop_column('vacancies', 'grade')
    op.drop_column('vacancies', 'required_experience')
    op.drop_column('vacancies', 'city_norm')
    op.drop_column('vacancies', 'remote_scope')
    op.drop_column('vacancies', 'skills')
    op.drop_column('vacancies', 'snippet')
    op.drop_column('vacancies', 'salary_rub_normalized')
    op.drop_column('vacancies', 'salary_gross_net')
    op.drop_column('vacancies', 'salary_to')
    op.drop_column('vacancies', 'salary_from')
    op.drop_column('vacancies', 'canonical_id')
    op.drop_column('vacancies', 'external_id')
