"""account deletion cascades

Revision ID: b21c9f4ad3e7
Revises: c4e1a7f2b930
Create Date: 2026-07-31 09:12:33.480215

M11 — Delete account. `DELETE /api/v1/account` erases an account by deleting
one row (`users`) and letting the database cascade the rest, so the erasure
is atomic and complete no matter which path removes a user.

Four foreign keys were missing the `ON DELETE CASCADE` that would make that
true:

- `candidate_profiles.resume_id -> resumes.id`
- `profile_skills.profile_id -> candidate_profiles.id`
- `profile_experiences.profile_id -> candidate_profiles.id`
- `profile_education.profile_id -> candidate_profiles.id`

The ORM already declares these as `cascade="all, delete-orphan"` (see
app/profile/models.py), so this only makes the database enforce what the
model has always promised — and closes the orphan-row hole that a delete
issued outside the ORM would otherwise leave. `users -> resumes`,
`users -> candidate_profiles`, `users -> saved_jobs` and `users -> sessions`
already cascade (revision 9d8b9b49aaf8); nothing else changes, and no data
is touched.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b21c9f4ad3e7'
down_revision: Union[str, Sequence[str], None] = 'c4e1a7f2b930'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (constraint, table, column, referred table) — one entry per edge that has
# to fall with its parent.
_CASCADING_EDGES = [
    ('fk_candidate_profiles_resume_id_resumes', 'candidate_profiles', 'resume_id', 'resumes'),
    (
        'fk_profile_skills_profile_id_candidate_profiles',
        'profile_skills',
        'profile_id',
        'candidate_profiles',
    ),
    (
        'fk_profile_experiences_profile_id_candidate_profiles',
        'profile_experiences',
        'profile_id',
        'candidate_profiles',
    ),
    (
        'fk_profile_education_profile_id_candidate_profiles',
        'profile_education',
        'profile_id',
        'candidate_profiles',
    ),
]


def upgrade() -> None:
    """Upgrade schema."""
    for name, table, column, referred in _CASCADING_EDGES:
        op.drop_constraint(name, table, type_='foreignkey')
        op.create_foreign_key(
            name, table, referred, [column], ['id'], ondelete='CASCADE'
        )


def downgrade() -> None:
    """Downgrade schema. Restores the plain (NO ACTION) foreign keys; after
    this, deleting a user leaves the profile fact tables orphaned unless the
    ORM does the deleting."""
    for name, table, column, referred in _CASCADING_EDGES:
        op.drop_constraint(name, table, type_='foreignkey')
        op.create_foreign_key(name, table, referred, [column], ['id'])
