"""add_github_refresh_token_to_users

Revision ID: 32b256642a9f
Revises: 6988b0f0df5b
Create Date: 2025-11-22 03:30:39.085353

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32b256642a9f'
down_revision: Union[str, Sequence[str], None] = '6988b0f0df5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('github_refresh_token', sa.String(512), nullable=True))
    op.add_column('users', sa.Column('github_token_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'github_token_expires_at')
    op.drop_column('users', 'github_refresh_token')
