"""user accounts sessions ownership saved jobs

Revision ID: 9d8b9b49aaf8
Revises: df9c0719bb55
Create Date: 2026-07-21 18:14:42.015067

M10 — Authentication & user accounts. Turns the single-user product into a
multi-user SaaS:

- `users` (email + Argon2 password hash) and `sessions` (server-side session
  records; the cookie holds an opaque token, only its SHA-256 hash is stored)
- `resumes.user_id` and `candidate_profiles.user_id` — every piece of
  personal data now belongs to exactly one account. `resumes.content_hash`
  uniqueness moves from global to per-user (two users may upload the same
  file as independent private documents).
- `saved_jobs` — a user's saved-job edges.

Pre-M10 personal data (resumes + profiles from the single-user era) has no
owner to assign it to: it was gated by one shared token, not tied to any
account. The upgrade deletes those orphan rows before adding the NOT NULL
`user_id` columns. The immutable job/market corpus is untouched; only
personal data is affected, and it is re-created by signing up and
re-uploading. This is written explicitly, not via autogenerate, to avoid the
spurious `ix_jobs_search_tsv` drop autogenerate emits in this repo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d8b9b49aaf8'
down_revision: Union[str, Sequence[str], None] = 'df9c0719bb55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
        sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    )

    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_sessions_user_id_users'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions')),
        sa.UniqueConstraint('token_hash', name=op.f('uq_sessions_token_hash')),
    )
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)

    # Delete pre-M10 single-user personal data (no account owns it). Children
    # first, then parents; the market/job corpus is not touched.
    op.execute('DELETE FROM profile_skills')
    op.execute('DELETE FROM profile_experiences')
    op.execute('DELETE FROM profile_education')
    op.execute('DELETE FROM candidate_profiles')
    op.execute('DELETE FROM resumes')

    # resumes: add ownership, move content_hash uniqueness to per-user.
    op.drop_constraint(op.f('uq_resumes_content_hash'), 'resumes', type_='unique')
    op.add_column('resumes', sa.Column('user_id', sa.Integer(), nullable=False))
    op.create_index(op.f('ix_resumes_user_id'), 'resumes', ['user_id'], unique=False)
    op.create_foreign_key(
        op.f('fk_resumes_user_id_users'), 'resumes', 'users',
        ['user_id'], ['id'], ondelete='CASCADE',
    )
    op.create_unique_constraint(
        'uq_resumes_user_content_hash', 'resumes', ['user_id', 'content_hash']
    )

    # candidate_profiles: add ownership.
    op.add_column('candidate_profiles', sa.Column('user_id', sa.Integer(), nullable=False))
    op.create_index(
        op.f('ix_candidate_profiles_user_id'), 'candidate_profiles', ['user_id'], unique=False
    )
    op.create_foreign_key(
        op.f('fk_candidate_profiles_user_id_users'), 'candidate_profiles', 'users',
        ['user_id'], ['id'], ondelete='CASCADE',
    )

    op.create_table(
        'saved_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['job_id'], ['jobs.id'],
            name=op.f('fk_saved_jobs_job_id_jobs'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_saved_jobs_user_id_users'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_saved_jobs')),
        sa.UniqueConstraint('user_id', 'job_id', name='uq_saved_jobs_user_job'),
    )
    op.create_index(op.f('ix_saved_jobs_user_id'), 'saved_jobs', ['user_id'], unique=False)
    op.create_index(op.f('ix_saved_jobs_job_id'), 'saved_jobs', ['job_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema. Reverses cleanly; personal data deleted on upgrade
    is not restored (it had no owner to restore it to)."""
    op.drop_index(op.f('ix_saved_jobs_job_id'), table_name='saved_jobs')
    op.drop_index(op.f('ix_saved_jobs_user_id'), table_name='saved_jobs')
    op.drop_table('saved_jobs')

    op.drop_constraint(
        op.f('fk_candidate_profiles_user_id_users'), 'candidate_profiles', type_='foreignkey'
    )
    op.drop_index(op.f('ix_candidate_profiles_user_id'), table_name='candidate_profiles')
    op.drop_column('candidate_profiles', 'user_id')

    op.drop_constraint('uq_resumes_user_content_hash', 'resumes', type_='unique')
    op.drop_constraint(op.f('fk_resumes_user_id_users'), 'resumes', type_='foreignkey')
    op.drop_index(op.f('ix_resumes_user_id'), table_name='resumes')
    op.drop_column('resumes', 'user_id')
    op.create_unique_constraint(op.f('uq_resumes_content_hash'), 'resumes', ['content_hash'])

    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_table('users')
