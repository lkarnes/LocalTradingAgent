"""Initial trading database schema.

Revision ID: 20261120_001
Revises:
Create Date: 2026-11-20

"""

from alembic import op

from app.database import Base


revision = "20261120_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
