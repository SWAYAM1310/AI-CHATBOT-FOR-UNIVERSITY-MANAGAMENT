"""email outbox

Revision ID: a1b2c3d4e5f6
Revises: cc3862737634
Create Date: 2026-09-16 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'cc3862737634'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'email_outbox',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('to_addr', sa.String(), nullable=False),
        sa.Column('intended_to', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('related_type', sa.String(), nullable=False),
        sa.Column('related_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_email_outbox_idempotency_key'), 'email_outbox', ['idempotency_key'], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_email_outbox_idempotency_key'), table_name='email_outbox')
    op.drop_table('email_outbox')
