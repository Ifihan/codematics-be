"""add_analyses_table

Revision ID: 0b5e5c2a04f7
Revises: 4bb2bd35fcbd
Create Date: 2025-11-21 07:44:15.438811

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b5e5c2a04f7'
down_revision: Union[str, Sequence[str], None] = '4bb2bd35fcbd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('notebook_id', sa.Integer(), nullable=False),
        sa.Column('health_score', sa.Integer(), nullable=False),
        sa.Column('cell_classifications', sa.JSON(), nullable=False),
        sa.Column('issues', sa.JSON(), nullable=False),
        sa.Column('recommendations', sa.JSON(), nullable=True),
        sa.Column('resource_estimates', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['notebook_id'], ['notebooks.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('notebook_id')
    )
    op.create_index(op.f('ix_analyses_id'), 'analyses', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_analyses_id'), table_name='analyses')
    op.drop_table('analyses')
