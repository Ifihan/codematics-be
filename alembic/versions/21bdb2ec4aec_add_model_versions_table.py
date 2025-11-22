"""add_model_versions_table

Revision ID: 21bdb2ec4aec
Revises: 6b590d70e7ce
Create Date: 2025-11-21 17:28:40.840970

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21bdb2ec4aec'
down_revision: Union[str, Sequence[str], None] = '6b590d70e7ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'model_versions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('notebook_id', sa.Integer(), sa.ForeignKey('notebooks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('gcs_path', sa.String(512), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('accuracy', sa.Numeric(5, 2), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'))
    )
    op.create_index('idx_model_versions_notebook', 'model_versions', ['notebook_id'])
    op.create_index('idx_model_versions_active', 'model_versions', ['is_active'])
    op.create_unique_constraint('uq_notebook_version', 'model_versions', ['notebook_id', 'version'])


def downgrade() -> None:
    op.drop_index('idx_model_versions_active', 'model_versions')
    op.drop_index('idx_model_versions_notebook', 'model_versions')
    op.drop_table('model_versions')
