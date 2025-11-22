"""add_github_fields_to_users

Revision ID: 19f318f7e812
Revises: d157beeb990f
Create Date: 2025-11-21 23:18:26.904205

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19f318f7e812'
down_revision: Union[str, Sequence[str], None] = 'd157beeb990f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('github_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('github_username', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'github_username')
    op.drop_column('users', 'github_token')
