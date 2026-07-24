"""job full text search vector

Revision ID: 361def3d5abe
Revises: 74bc1114f91e
Create Date: 2026-07-19 11:30:06.815449

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '361def3d5abe'
down_revision: Union[str, Sequence[str], None] = '74bc1114f91e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Generated column: the database owns the derivation, so the vector can
# never drift from the text it indexes (no backfill step to forget).
SEARCH_TSV = "to_tsvector('english', title_raw || ' ' || coalesce(description_text, ''))"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'jobs',
        sa.Column(
            'search_tsv',
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_TSV, persisted=True),
            nullable=True,
        ),
    )
    op.create_index('ix_jobs_search_tsv', 'jobs', ['search_tsv'], postgresql_using='gin')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_jobs_search_tsv', table_name='jobs')
    op.drop_column('jobs', 'search_tsv')
