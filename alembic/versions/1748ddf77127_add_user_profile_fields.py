"""add_user_profile_fields

Revision ID: 1748ddf77127
Revises: a96f1ad17d85
Create Date: 2025-11-24 23:34:50.590853

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1748ddf77127'
down_revision: Union[str, Sequence[str], None] = 'a96f1ad17d85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('bio', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('primary_stack', sa.String(length=512), nullable=True))
    op.add_column('users', sa.Column('research_interests', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('is_profile_public', sa.Boolean(), nullable=True, server_default='false'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'is_profile_public')
    op.drop_column('users', 'research_interests')
    op.drop_column('users', 'primary_stack')
    op.drop_column('users', 'bio')
