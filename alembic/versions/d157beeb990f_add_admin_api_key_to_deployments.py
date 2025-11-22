"""add_admin_api_key_to_deployments

Revision ID: d157beeb990f
Revises: 21bdb2ec4aec
Create Date: 2025-11-21 17:42:50.133243

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd157beeb990f'
down_revision: Union[str, Sequence[str], None] = '21bdb2ec4aec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('deployments', sa.Column('admin_api_key', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('deployments', 'admin_api_key')
