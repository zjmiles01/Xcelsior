"""resume intelligence tables

Revision ID: fb2c785dc508
Revises: a6df27a05079
Create Date: 2026-07-19 22:45:15.025064

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fb2c785dc508'
down_revision: Union[str, Sequence[str], None] = 'a6df27a05079'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Resume intelligence (M7, ADR-005): raw layer (resumes: uploaded bytes +
# extracted text, parser-versioned) and canonical layer (candidate_profiles
# + skill/experience/education fact tables, evidence offsets into
# resumes.extracted_text). profile_skills.technology_id and
# profile_experiences.canonical_title_id reference the shared taxonomy
# tables so future job matching is a join, not a schema change.
# NOTE: autogenerate also proposed dropping ix_jobs_search_tsv — that index
# is created manually in migration 361def3d5abe (the ORM maps the generated
# column without declaring its index); the drop was spurious and removed.


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('resumes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(), nullable=False),
    sa.Column('content_type', sa.String(), nullable=False),
    sa.Column('file_size', sa.Integer(), nullable=False),
    sa.Column('file_bytes', sa.LargeBinary(), nullable=False),
    sa.Column('content_hash', sa.String(), nullable=False),
    sa.Column('extracted_text', sa.Text(), nullable=True),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('parser_name', sa.String(), nullable=True),
    sa.Column('parser_version', sa.Integer(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_resumes')),
    sa.UniqueConstraint('content_hash', name=op.f('uq_resumes_content_hash'))
    )
    op.create_table('candidate_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('resume_id', sa.Integer(), nullable=False),
    sa.Column('full_name', sa.String(), nullable=True),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('phone', sa.String(), nullable=True),
    sa.Column('extractor_version', sa.Integer(), nullable=False),
    sa.Column('extracted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['resume_id'], ['resumes.id'], name=op.f('fk_candidate_profiles_resume_id_resumes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_candidate_profiles')),
    sa.UniqueConstraint('resume_id', name=op.f('uq_candidate_profiles_resume_id'))
    )
    op.create_table('profile_education',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profile_id', sa.Integer(), nullable=False),
    sa.Column('institution', sa.String(), nullable=True),
    sa.Column('degree_raw', sa.String(), nullable=True),
    sa.Column('degree_level', sa.String(), nullable=True),
    sa.Column('field_of_study', sa.String(), nullable=True),
    sa.Column('start_year', sa.Integer(), nullable=True),
    sa.Column('end_year', sa.Integer(), nullable=True),
    sa.Column('evidence_start', sa.Integer(), nullable=True),
    sa.Column('evidence_end', sa.Integer(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('origin', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['candidate_profiles.id'], name=op.f('fk_profile_education_profile_id_candidate_profiles')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_education'))
    )
    op.create_index(op.f('ix_profile_education_profile_id'), 'profile_education', ['profile_id'], unique=False)
    op.create_table('profile_experiences',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profile_id', sa.Integer(), nullable=False),
    sa.Column('company', sa.String(), nullable=True),
    sa.Column('title_raw', sa.String(), nullable=False),
    sa.Column('canonical_title_id', sa.Integer(), nullable=True),
    sa.Column('level', sa.String(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('is_current', sa.Boolean(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('evidence_start', sa.Integer(), nullable=True),
    sa.Column('evidence_end', sa.Integer(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('origin', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['canonical_title_id'], ['canonical_titles.id'], name=op.f('fk_profile_experiences_canonical_title_id_canonical_titles')),
    sa.ForeignKeyConstraint(['profile_id'], ['candidate_profiles.id'], name=op.f('fk_profile_experiences_profile_id_candidate_profiles')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_experiences'))
    )
    op.create_index(op.f('ix_profile_experiences_canonical_title_id'), 'profile_experiences', ['canonical_title_id'], unique=False)
    op.create_index(op.f('ix_profile_experiences_profile_id'), 'profile_experiences', ['profile_id'], unique=False)
    op.create_table('profile_skills',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profile_id', sa.Integer(), nullable=False),
    sa.Column('technology_id', sa.Integer(), nullable=True),
    sa.Column('label', sa.String(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('occurrences', sa.Integer(), nullable=False),
    sa.Column('evidence_snippet', sa.Text(), nullable=True),
    sa.Column('evidence_start', sa.Integer(), nullable=True),
    sa.Column('origin', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['candidate_profiles.id'], name=op.f('fk_profile_skills_profile_id_candidate_profiles')),
    sa.ForeignKeyConstraint(['technology_id'], ['technologies.id'], name=op.f('fk_profile_skills_technology_id_technologies')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_profile_skills'))
    )
    op.create_index(op.f('ix_profile_skills_profile_id'), 'profile_skills', ['profile_id'], unique=False)
    op.create_index(op.f('ix_profile_skills_technology_id'), 'profile_skills', ['technology_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_profile_skills_technology_id'), table_name='profile_skills')
    op.drop_index(op.f('ix_profile_skills_profile_id'), table_name='profile_skills')
    op.drop_table('profile_skills')
    op.drop_index(op.f('ix_profile_experiences_profile_id'), table_name='profile_experiences')
    op.drop_index(op.f('ix_profile_experiences_canonical_title_id'), table_name='profile_experiences')
    op.drop_table('profile_experiences')
    op.drop_index(op.f('ix_profile_education_profile_id'), table_name='profile_education')
    op.drop_table('profile_education')
    op.drop_table('candidate_profiles')
    op.drop_table('resumes')
