"""announcement approvals

An announcement now waits for the head of department before anyone sees it: one
approval row per department it reaches, each released by that department's HOD.
The email every recipient gets is frozen on the announcement at submission time,
since it is only sent once the HOD approves.

Every announcement that already exists was live before this change, so each one
gets an approved row for every department it reached, dated when it was posted.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-25 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# kept in step with app/seed/load_csv.py APPROVE_LOADED_ANNOUNCEMENTS
BACKFILL = """
INSERT INTO announcement_approvals (announcement_id, dept_code, status, decided_at)
SELECT a.id, d.code, 'approved', a.posted_at
FROM announcements a
JOIN departments d ON a.scope = 'university' OR (a.scope = 'department' AND d.code = a.scope_ref)
WHERE NOT EXISTS (SELECT 1 FROM announcement_approvals x WHERE x.announcement_id = a.id)
UNION ALL
SELECT a.id,
       COALESCE(f.dept_code,
                (SELECT co.dept_code FROM course_offerings co
                 WHERE co.subject_code = a.scope_ref AND co.dept_code IS NOT NULL LIMIT 1),
                '-'),
       'approved', a.posted_at
FROM announcements a
JOIN users u ON u.id = a.author_user_id
LEFT JOIN faculty f ON u.subject_ref = 'faculty:' || f.id
WHERE a.scope = 'course' AND NOT EXISTS (SELECT 1 FROM announcement_approvals x WHERE x.announcement_id = a.id)
ON CONFLICT DO NOTHING
"""


def upgrade() -> None:
    op.add_column('announcements', sa.Column('email_subject', sa.String(), nullable=True))
    op.add_column('announcements', sa.Column('email_body', sa.Text(), nullable=True))
    op.create_table(
        'announcement_approvals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('announcement_id', sa.Integer(), sa.ForeignKey('announcements.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dept_code', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('decided_by', sa.Integer(), sa.ForeignKey('faculty.id'), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.UniqueConstraint('announcement_id', 'dept_code', name='uq_announcement_approvals_dept'),
    )
    op.create_index('ix_announcement_approvals_announcement_id', 'announcement_approvals', ['announcement_id'])
    op.create_index('ix_announcement_approvals_dept_code', 'announcement_approvals', ['dept_code'])
    op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_index('ix_announcement_approvals_dept_code', table_name='announcement_approvals')
    op.drop_index('ix_announcement_approvals_announcement_id', table_name='announcement_approvals')
    op.drop_table('announcement_approvals')
    op.drop_column('announcements', 'email_body')
    op.drop_column('announcements', 'email_subject')
