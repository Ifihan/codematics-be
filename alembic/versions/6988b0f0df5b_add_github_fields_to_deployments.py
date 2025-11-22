"""add_github_fields_to_deployments

Revision ID: 6988b0f0df5b
Revises: 19f318f7e812
Create Date: 2025-11-22 03:17:36.479417

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6988b0f0df5b'
down_revision: Union[str, Sequence[str], None] = '19f318f7e812'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('deployments', sa.Column('github_repo_url', sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column('deployments', 'github_repo_url')
