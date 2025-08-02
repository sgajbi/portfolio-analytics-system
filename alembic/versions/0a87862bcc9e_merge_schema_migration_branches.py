"""Merge schema migration branches

Revision ID: 0a87862bcc9e
Revises: 675879892070, e914a5a5874e
Create Date: 2025-08-03 01:01:28.187467

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a87862bcc9e'
down_revision: Union[str, None] = ('675879892070', 'e914a5a5874e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
