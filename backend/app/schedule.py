"""When the timetable runs: the term window and the academic-calendar days that suspend it.

Shared by the faculty calendar (what it shows as scheduled) and the upkeep job (what it
fills in when nobody took the register), so the two can never disagree about a day.
"""
from __future__ import annotations

from datetime import date as Date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import AcademicCalendarEvent

NO_TEACHING = ("holiday", "break", "exam")  # calendar events on which the timetable does not run


def _in_term(term: str):
    return or_(AcademicCalendarEvent.term == term, AcademicCalendarEvent.term.is_(None))


def term_window(db: Session, term: str) -> tuple[Date | None, Date | None]:
    """First and last day of classes, from the term's two "term" events."""
    days = list(
        db.scalars(select(AcademicCalendarEvent.start_date).where(_in_term(term), AcademicCalendarEvent.event_type == "term"))
    )
    return (min(days), max(days)) if days else (None, None)


def events_between(db: Session, term: str, first: Date, last: Date) -> list[AcademicCalendarEvent]:
    """Academic-calendar events of the term that overlap first..last."""
    return list(
        db.scalars(
            select(AcademicCalendarEvent)
            .where(
                _in_term(term),
                AcademicCalendarEvent.start_date <= last,
                func.coalesce(AcademicCalendarEvent.end_date, AcademicCalendarEvent.start_date) >= first,
            )
            .order_by(AcademicCalendarEvent.start_date, AcademicCalendarEvent.id)
        )
    )


def covers(event: AcademicCalendarEvent, d: Date) -> bool:
    return event.start_date <= d <= (event.end_date or event.start_date)


def is_teaching_day(d: Date, events: list[AcademicCalendarEvent], start: Date | None, end: Date | None) -> bool:
    """Inside the term, and no holiday, break or exam falls on it."""
    if start is None or end is None or not start <= d <= end:
        return False
    return not any(e.event_type in NO_TEACHING and covers(e, d) for e in events)
