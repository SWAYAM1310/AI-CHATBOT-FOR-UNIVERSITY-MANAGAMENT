"""
Static configuration and small helpers for the operational half of the
UniAssist synthetic dataset — terms, class scheduling, assessment templates,
fee structure, academic-calendar events and the assorted enum vocabularies
used by leave / document / scholarship / announcement generation.

Kept separate from generate_synthetic_data.py so the policy-ish constants are
easy to eyeball and tweak without reading generator logic.
"""

from __future__ import annotations

import datetime as dt

# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------
# "As of" clock for the whole dataset. The odd semester is in progress.
AS_OF = dt.date(2026, 8, 27)

CURRENT_TERM = "2026-27-ODD"
PAST_TERM = "2025-26-EVEN"

# batch -> semester in each term (batch 2026 did not exist in the past term)
CURRENT_SEM_BY_BATCH = {2023: 7, 2024: 5, 2025: 3, 2026: 1}
PAST_SEM_BY_BATCH = {2023: 6, 2024: 4, 2025: 2}

# Teaching windows. Odd sem starts mid-June (orientation for the new first-year
# batch runs 2-13 June); ~10.3 weeks of teaching have elapsed by AS_OF.
TERM_WINDOWS = {
    PAST_TERM: {
        "teaching_start": dt.date(2026, 1, 5),
        "teaching_end": dt.date(2026, 5, 8),
        "exam_start": dt.date(2026, 5, 11),
        "exam_end": dt.date(2026, 5, 22),
        "result_date": dt.date(2026, 6, 9),
        "completed": True,
    },
    CURRENT_TERM: {
        "teaching_start": dt.date(2026, 6, 16),
        "teaching_end": dt.date(2026, 11, 6),      # planned
        "exam_start": dt.date(2026, 11, 17),       # planned
        "exam_end": dt.date(2026, 11, 28),         # planned
        "result_date": dt.date(2026, 12, 18),      # planned
        "completed": False,
    },
}

# Public / institute holidays that suppress class sessions (both terms).
HOLIDAYS = {
    dt.date(2026, 1, 14),   # Uttarayan
    dt.date(2026, 1, 15),   # Vasi Uttarayan
    dt.date(2026, 1, 26),   # Republic Day
    dt.date(2026, 3, 4),    # Holi / Dhuleti
    dt.date(2026, 3, 21),   # Ramzan Eid (approx)
    dt.date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    dt.date(2026, 8, 15),   # Independence Day
    dt.date(2026, 8, 26),   # Raksha Bandhan (approx)
    dt.date(2026, 9, 5),    # Janmashtami (approx)
    dt.date(2026, 10, 2),   # Gandhi Jayanti
    dt.date(2026, 10, 20),  # Dussehra (approx)
}

# Mid-term / festival breaks — ranges with no teaching.
BREAKS = [
    (dt.date(2026, 3, 9), dt.date(2026, 3, 14)),     # even-sem mid-term break
    (dt.date(2026, 11, 7), dt.date(2026, 11, 15)),   # Diwali vacation (odd sem)
]

# ---------------------------------------------------------------------------
# Class scheduling
# ---------------------------------------------------------------------------
TEACHING_DAYS = [0, 1, 2, 3, 4, 5]  # Mon..Sat (Python weekday())

# (start, end) lecture/tutorial periods
PERIODS = [
    ("09:00", "10:00"),
    ("10:00", "11:00"),
    ("11:15", "12:15"),
    ("12:15", "13:15"),
    ("14:00", "15:00"),
    ("15:00", "16:00"),
    ("16:15", "17:15"),
]
# lab blocks occupy two consecutive periods
LAB_BLOCKS = [
    ("09:00", "11:00"),
    ("11:15", "13:15"),
    ("14:00", "16:00"),
]

MAX_LECTURES_PER_WEEK = 3   # cap even if the subject lists L=4

# ---------------------------------------------------------------------------
# Classrooms
# ---------------------------------------------------------------------------
# per department: (lecture halls, dept labs). Two shared exam halls live in the
# central block.
CLASSROOM_PLAN = {
    "CP": (10, 8), "IT": (7, 6), "EC": (6, 6),
    "ME": (6, 7), "CE": (6, 5), "CH": (6, 5),
}
LECTURE_CAPACITY = 72
LAB_CAPACITY = 36
SEMINAR_CAPACITY = 40
EXAM_HALL_CAPACITY = 120

# ---------------------------------------------------------------------------
# Assessment templates  (week is 1-indexed from teaching_start)
# component: LECTURE assessments apply to theory offerings only
# ---------------------------------------------------------------------------
ASSESSMENT_TEMPLATE = [
    # type, title, max_marks, weightage_pct, week, kind
    ("Quiz-1",       "Quiz 1",            10, 5,  3,  "quiz"),
    ("Assignment-1", "Assignment 1",      10, 7,  4,  "assignment"),
    ("Internal-1",   "Internal Test 1",   20, 15, 6,  "test"),
    ("Assignment-2", "Assignment 2",      10, 8,  9,  "assignment"),
    ("Internal-2",   "Internal Test 2",   20, 15, 12, "test"),
    ("End-Sem",      "End Semester Exam", 100, 40, 18, "endsem"),
]
PASS_FRACTION = 0.40   # < 40% of max on an assessment is a fail on that head

# ---------------------------------------------------------------------------
# Fees
# ---------------------------------------------------------------------------
TUITION_PER_SEM = 149000
OTHER_FEES_PER_SEM = 3500          # library + exam + student activity
HOSTEL_FEE_PER_SEM = 62000        # only for hostellers (~45% of students)
FEE_STATUSES = ["paid", "paid", "paid", "paid", "paid", "paid",
                "paid", "partial", "partial", "unpaid", "overdue"]

# ---------------------------------------------------------------------------
# Scholarships
# ---------------------------------------------------------------------------
SCHOLARSHIP_NAMES = [
    ("Merit-cum-Means Scholarship", 40000),
    ("MYSY (Mukhyamantri Yuva Swavalamban Yojana)", 50000),
    ("PDEU Merit Scholarship", 30000),
    ("SC/ST Post-Matric Scholarship", 35000),
    ("EWS Tuition Assistance", 25000),
    ("Sports Excellence Scholarship", 20000),
    ("Girl Child Education Grant", 15000),
]
SCHOLARSHIP_STATUSES = ["disbursed", "disbursed", "approved", "approved",
                        "pending", "pending", "rejected"]

# ---------------------------------------------------------------------------
# Leave requests
# ---------------------------------------------------------------------------
LEAVE_REASONS = [
    "Fever and viral infection, advised rest by doctor",
    "Sister's wedding, out of town",
    "Family function at native place",
    "Medical - dengue, hospitalised",
    "Attending a hackathon at another institute",
    "Grandfather's health emergency",
    "Represented college at inter-university sports meet",
    "Passport appointment and document verification",
    "Religious pilgrimage with family",
    "Dental surgery and recovery",
]
LEAVE_STATUSES = (["approved"] * 7) + (["rejected"] * 2) + ["pending"]

# ---------------------------------------------------------------------------
# Document requests
# ---------------------------------------------------------------------------
DOC_TYPES = [
    "Bonafide Certificate", "Official Transcript", "Migration Certificate",
    "Fee Payment Receipt", "Bus Pass", "Internship NOC",
    "Course Completion Letter", "Character Certificate",
]
DOC_PURPOSES = [
    "Passport application", "Education loan from bank", "Visa application",
    "Internship joining formalities", "Scholarship application",
    "Higher-studies application abroad", "Bank account opening (student)",
    "Local train / bus concession pass",
]
DOC_STATUSES = ["ready", "ready", "processing", "processing", "pending"]

# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------
UNIVERSITY_ANNOUNCEMENTS = [
    ("Odd Semester 2026-27 fee payment window open",
     "The tuition and other fees for the odd semester 2026-27 must be paid "
     "through the student portal by 12 September 2026. A late fee of Rs. 500 "
     "per week applies thereafter."),
    ("Internal Test 1 timetable published",
     "The consolidated Internal Test 1 schedule for all B.Tech programmes is "
     "now available on the department notice boards and the portal. Tests run "
     "from 20 to 25 August 2026."),
    ("Library working hours extended",
     "From 1 August 2026 the Central Library will remain open until 23:00 on "
     "weekdays and 20:00 on weekends to support students during the "
     "assessment period."),
    ("Diwali vacation 7-15 November 2026",
     "The institute will remain closed for the Diwali vacation from 7 to 15 "
     "November 2026. Classes resume on 16 November 2026."),
    ("TReDS / campus placement drive registration",
     "Eighth-semester students may register for the 2026-27 campus placement "
     "season on the Training & Placement portal by 5 September 2026."),
    ("Anti-ragging committee helpline",
     "Students are reminded that the anti-ragging helpline (toll free) and the "
     "online complaint form are active round the clock. All complaints are "
     "handled confidentially."),
    ("Convocation 2026 - graduating batch",
     "The annual convocation for the graduating batch will be held on 20 "
     "December 2026 at the institute auditorium. Registration details to "
     "follow."),
]
DEPT_ANNOUNCEMENT_TEMPLATES = [
    ("Guest lecture: industry perspectives",
     "The {dept} department is hosting a guest lecture on emerging industry "
     "trends on {date} at 15:00 in the seminar hall. Attendance is "
     "recommended for fifth and seventh semester students."),
    ("Lab safety briefing - mandatory",
     "All {dept} students enrolled in laboratory courses this semester must "
     "attend the lab safety and conduct briefing on {date}. Entry to labs "
     "requires a signed undertaking."),
    ("Project allocation for final year",
     "Final-year {dept} students should submit their project group and "
     "preferred domain through the department portal by {date}. Guide "
     "allocation will be announced the following week."),
    ("Department sports and cultural week",
     "The {dept} department sports and cultural week runs from {date}. Sign-up "
     "sheets are on the department notice board."),
]
COURSE_ANNOUNCEMENT_TEMPLATES = [
    ("{course}: lecture rescheduled",
     "Tomorrow's {course} lecture is rescheduled to the 16:15 slot due to a "
     "faculty meeting. The venue is unchanged."),
    ("{course}: Assignment 2 deadline reminder",
     "Assignment 2 for {course} is due on {date}. Submit through the portal; "
     "no email submissions will be accepted."),
    ("{course}: extra doubt-solving session",
     "An additional doubt-solving session for {course} will be held on {date} "
     "before Internal Test 1. Bring your questions."),
    ("{course}: syllabus checkpoint",
     "We have completed Units 1-3 of {course}. Internal Test 1 will cover "
     "these units. Unit 4 begins next week."),
]

# ---------------------------------------------------------------------------
# Academic calendar
# ---------------------------------------------------------------------------
# event, event_type, start_date, end_date, applies_to
CALENDAR_EVENTS = [
    ("Even Semester 2025-26 classes begin", "term", dt.date(2026, 1, 5), None, "all"),
    ("Uttarayan holiday", "holiday", dt.date(2026, 1, 14), dt.date(2026, 1, 15), "all"),
    ("Republic Day", "holiday", dt.date(2026, 1, 26), None, "all"),
    ("Even-sem mid-term break", "break", dt.date(2026, 3, 9), dt.date(2026, 3, 14), "all"),
    ("Holi / Dhuleti holiday", "holiday", dt.date(2026, 3, 4), None, "all"),
    ("Even Semester 2025-26 classes end", "term", dt.date(2026, 5, 8), None, "all"),
    ("Even Semester end-term examinations", "exam", dt.date(2026, 5, 11), dt.date(2026, 5, 22), "all"),
    ("Even Semester 2025-26 results declared", "result", dt.date(2026, 6, 9), None, "all"),
    ("First-year orientation programme", "orientation", dt.date(2026, 6, 2), dt.date(2026, 6, 13), "semester-1"),
    ("Odd Semester 2026-27 classes begin", "term", dt.date(2026, 6, 16), None, "all"),
    ("Course registration / add-drop window", "registration", dt.date(2026, 6, 16), dt.date(2026, 6, 27), "all"),
    ("Independence Day", "holiday", dt.date(2026, 8, 15), None, "all"),
    ("Raksha Bandhan holiday", "holiday", dt.date(2026, 8, 26), None, "all"),
    ("Internal Test 1", "exam", dt.date(2026, 8, 20), dt.date(2026, 8, 25), "all"),
    ("Odd Semester fee payment last date", "fee", dt.date(2026, 9, 12), None, "all"),
    ("Janmashtami holiday", "holiday", dt.date(2026, 9, 5), None, "all"),
    ("Internal Test 2", "exam", dt.date(2026, 9, 21), dt.date(2026, 9, 26), "all"),
    ("Gandhi Jayanti", "holiday", dt.date(2026, 10, 2), None, "all"),
    ("Dussehra holiday", "holiday", dt.date(2026, 10, 20), None, "all"),
    ("End-semester examination form submission", "registration", dt.date(2026, 10, 12), dt.date(2026, 10, 20), "all"),
    ("Diwali vacation", "break", dt.date(2026, 11, 7), dt.date(2026, 11, 15), "all"),
    ("Odd Semester 2026-27 classes end", "term", dt.date(2026, 11, 6), None, "all"),
    ("Odd Semester end-term examinations", "exam", dt.date(2026, 11, 17), dt.date(2026, 11, 28), "all"),
    ("Odd Semester 2026-27 results declared", "result", dt.date(2026, 12, 18), None, "all"),
    ("Annual convocation", "orientation", dt.date(2026, 12, 20), None, "all"),
]

# ---------------------------------------------------------------------------
# Attendance status weights (present / absent / late / excused)
# ---------------------------------------------------------------------------
ATTENDANCE_STATUS_WEIGHTS = [
    ("present", 0.86), ("absent", 0.10), ("late", 0.03), ("excused", 0.01),
]

# ---------------------------------------------------------------------------
# Deliberately planted demo edge cases (§2 of plan.md)
# ---------------------------------------------------------------------------
DEMO = {
    # student sitting at exactly 68% attendance in DBMS (personalisation demo)
    "attendance_roll": "25BCP017",
    "attendance_subject": "24CS201T",     # Database Management System (CP sem 3)
    "attendance_target_pct": 68.0,

    # course with a ~35% fail rate on Internal Test 1 (admin analytics demo)
    "fail_subject": "24CS202T",           # Digital Logic and Design (CP sem 3)
    "fail_assessment": "Internal-1",
    "fail_rate": 0.35,

    # cohort with missing Assignment 2 submissions (faculty demo)
    "missing_subject": "24CS201T",
    "missing_assessment": "Assignment-2",
    "missing_rate": 0.18,

    # student with unpaid fees and a pending scholarship
    "fee_roll": "25BCP012",
    "fee_scholarship": "MYSY (Mukhyamantri Yuva Swavalamban Yojana)",

    # a few pending leave requests routed to a faculty member for the
    # decide_leave_request demo
    "pending_leave_rolls": ["25BCP003", "25BCP021", "24BCP009", "25BIT004"],
}


def week_index(d: dt.date, start: dt.date) -> int:
    """1-indexed teaching week of date d relative to term start."""
    return (d - start).days // 7 + 1


def in_break(d: dt.date) -> bool:
    return any(a <= d <= b for a, b in BREAKS)


def is_class_day(d: dt.date) -> bool:
    return d.weekday() in TEACHING_DAYS and d not in HOLIDAYS and not in_break(d)
