"""auto flags, half-step marks

Attendance a faculty member never took and marks nobody entered are filled in by the
upkeep job (app/jobs/upkeep.py); these flags say which rows it wrote. Marks only ever
come in steps of 0.5, which the database now enforces.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-05 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('attendance_sessions', sa.Column('auto_marked', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('assessments', sa.Column('auto_graded', sa.Boolean(), nullable=False, server_default=sa.false()))
    # rows loaded before the dataset was rounded would fail the check: round them first
    op.execute("UPDATE marks SET score = round(score * 2) / 2 WHERE score * 2 <> trunc(score * 2)")
    op.create_check_constraint('ck_marks_score_half_step', 'marks', 'score IS NULL OR score * 2 = trunc(score * 2)')


def downgrade() -> None:
    op.drop_constraint('ck_marks_score_half_step', 'marks', type_='check')
    op.drop_column('assessments', 'auto_graded')
    op.drop_column('attendance_sessions', 'auto_marked')
