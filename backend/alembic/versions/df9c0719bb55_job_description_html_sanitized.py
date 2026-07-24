"""job description_html sanitized

Revision ID: df9c0719bb55
Revises: fb2c785dc508
Create Date: 2026-07-20 16:31:02.042146

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df9c0719bb55'
down_revision: Union[str, Sequence[str], None] = 'fb2c785dc508'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Sanitized display HTML (M8): a safe formatting subset of jobs.description,
# produced by extraction (EXTRACTOR_VERSION bumped to 3) and served for rich
# rendering in place of the untrusted raw markup. Nullable, no backfill —
# the next `xcelsior extract` populates it via the version-bump re-queue.
# NOTE: autogenerate also proposed dropping ix_jobs_search_tsv — that index
# is created manually in migration 361def3d5abe (the ORM maps the generated
# column without declaring its index); the drop is spurious and removed.


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('jobs', sa.Column('description_html', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('jobs', 'description_html')
