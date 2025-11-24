"""add_file_extension_to_model_versions

Revision ID: a96f1ad17d85
Revises: 32b256642a9f
Create Date: 2025-11-24 13:57:50.471187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a96f1ad17d85'
down_revision: Union[str, Sequence[str], None] = '32b256642a9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('model_versions', sa.Column('file_extension', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('model_versions', 'file_extension')
