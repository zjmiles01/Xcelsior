"""job dedupe group id

Revision ID: a6df27a05079
Revises: 361def3d5abe
Create Date: 2026-07-19 12:53:14.403781

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a6df27a05079'
down_revision: Union[str, Sequence[str], None] = '361def3d5abe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cross-source dedup: each job points at its group's representative row
# (NULL or self = "this row counts"). Assigned by `xcelsior dedupe`;
# nullable so the migration is instant and needs no backfill.


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('jobs', sa.Column('dedupe_group_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_jobs_dedupe_group_id'), 'jobs', ['dedupe_group_id'], unique=False)
    op.create_foreign_key(
        op.f('fk_jobs_dedupe_group_id_jobs'), 'jobs', 'jobs', ['dedupe_group_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('fk_jobs_dedupe_group_id_jobs'), 'jobs', type_='foreignkey')
    op.drop_index(op.f('ix_jobs_dedupe_group_id'), table_name='jobs')
    op.drop_column('jobs', 'dedupe_group_id')
