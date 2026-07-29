"""job employment type index

Revision ID: c4e1a7f2b930
Revises: 9d8b9b49aaf8
Create Date: 2026-07-28 10:14:52.118904

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4e1a7f2b930'
down_revision: Union[str, Sequence[str], None] = '9d8b9b49aaf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The jobs.employment_type column has existed since the initial migration
# but was never written to. Employment typing (ingestion declares it,
# extraction infers it) makes it a filter column, so it needs an index —
# the search predicate and the facet count both group on it.
#
# No backfill here: existing rows keep employment_type NULL and are filled
# by the next `xcelsior extract` run, which reprocesses the corpus anyway
# because EXTRACTOR_VERSION moved 3 -> 4. Until then NULL is served as
# "unspecified" and matched by the `unknown` filter, so nothing 404s or
# silently disappears mid-backfill.


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(op.f('ix_jobs_employment_type'), 'jobs', ['employment_type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_jobs_employment_type'), table_name='jobs')
