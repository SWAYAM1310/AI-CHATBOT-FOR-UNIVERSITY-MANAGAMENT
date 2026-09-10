# UniAssist Synthetic Data Architecture & Relational Guide

This document provides a comprehensive, table-by-table explanation of the entire dataset in [`data/synthetic/`](file:///d:/Coding%20Files/University%20Assistant/data/synthetic), detailing how each table is used by the AI assistant, how tables are interconnected, and how these relationships work together to achieve the core goals of the **UniAssist** project.

---

## 1. Project Goals & Data Role

**UniAssist** is a role-aware AI university management assistant. Rather than functioning as a generic ChatGPT wrapper or relying on unsafe text-to-SQL queries, UniAssist is built on three core pillars:

1. **Provable 3-Tier Role-Based Access Control (RBAC)**:
   - **Student (Scope: `SELF`)**: Can only query or modify their own data (their personal attendance, marks, fees, registered courses, leave requests).
   - **Faculty (Scope: `OWN_COURSES`)**: Can only view data for courses they actively teach (student rosters, attendance sessions, mark sheets, assignment submissions, at-risk flags) or take actions on their mentees/students (deciding leave requests, marking attendance).
   - **Admin (Scope: `UNIVERSITY`)**: Can view aggregated institutional metrics (enrollment statistics, department workloads, fee collection summaries, cross-department exam scheduling).
2. **Personalized Grounding (Relational DB + RAG Regulations)**:
   - Policy retrieval alone only gives abstract rules (e.g., *"Regulation §4.2 states minimum attendance is 75%"*).
   - Database queries alone only give raw numbers (e.g., *"17 out of 25 sessions attended"*).
   - Combining both produces grounded, personalized answers: *"Regulation §4.2 requires 75% attendance. You currently have 68.0% in DBMS (17/25 sessions). You are 7% short and must attend the next 6 consecutive classes."*
3. **Confirmed Transactional Actions**:
   - Write operations (applying for leaves, requesting certificates, posting notices, entering marks) go through a two-phase confirmation step (`preview` &rarr; `user confirmation` &rarr; `execution`).

The 24 synthetic CSV tables provide the foundational ground truth for these capabilities.

---

## 2. Table-by-Table Usage & Schema Breakdown

The 24 tables are organized into 6 core subsystems:

```
Subsystems Overview:
1. Identity, RBAC & Core Organization  (users, students, faculty, admins, departments)
2. Academic Catalog & Infrastructure   (subjects, curriculum, classrooms)
3. Course Operations & Timetable       (course_offerings, enrollments, timetable_slots)
4. Attendance Tracking                 (attendance_sessions, attendance_records)
5. Assessments, Marks & Examinations   (assessments, marks, submissions, results_semester, exam_schedule)
6. Student Life & Administration       (fees, scholarships, leave_requests, document_requests, announcements, academic_calendar)
```

---

### Subsystem 1: Identity, RBAC & Core Organization

#### 1. `users.csv` (4,725 rows)
- **Primary Key**: `id`
- **Key Columns**: `email`, `password_hash`, `role` (`student` | `faculty` | `admin`), `subject_ref`, `is_active`, `last_login_at`
- **What it represents**: The central authentication and identity registry for every person in the institution.
- **How it is used in UniAssist**:
  - When a user logs in, the backend authenticates against `users.csv` and issues a signed JWT.
  - The JWT embeds the user's `role` and `subject_ref` (e.g. `student:17` or `faculty:5`), creating an immutable server-side `AuthContext`.
  - **RBAC Enforcement**: The `role` determines which tools are visible to the LLM during routing (Call A) and execution (Call B). Tools never accept caller-provided identity arguments; identity is pulled strictly from `subject_ref`.

#### 2. `students.csv` (4,600 rows)
- **Primary Key**: `id`
- **Key Columns**: `roll_no`, `full_name`, `university_email`, `personal_email`, `dept_id`, `dept_code`, `batch`, `semester`, `division`, `lab_group`, `tenth_percentage`, `twelfth_percentage`, `cgpa`, `is_hosteller`, `guardian_name`, `guardian_phone`, `admission_date`, `is_active`
- **What it represents**: Comprehensive demographic, academic cohort, and contact profile for every enrolled student.
- **How it is used in UniAssist**:
  - Powers the student tool `get_my_profile()`.
  - Maps a student's cohort position (e.g. Computer Science, Batch 2023, Semester 7, Division 1, Lab Group G1) to find their eligible course offerings, timetable, and faculty mentors.
  - Provides guardian contact and academic history (10th/12th percentages, CGPA) used by admin analytics and mentor advising tools.

#### 3. `faculty.csv` (118 rows)
- **Primary Key**: `id`
- **Key Columns**: `employee_id`, `full_name`, `university_email`, `personal_email`, `dept_id`, `dept_code`, `designation`, `is_hod`, `date_of_joining`, `qualification`, `specialization`, `office_room`, `is_active`
- **What it represents**: Directory of professors, associate professors, assistant professors, and lecturers across all departments.
- **How it is used in UniAssist**:
  - Identifies which instructor owns which course offering and who is authorized to mark attendance or grade assessments.
  - Checks administrative privileges: if `is_hod = True`, the faculty member is granted extra department-level scopes (such as approving student leave requests or reviewing departmental performance).
  - Powers student queries like *"Where is Dr. Krupa Patel's office?"* or *"What is my professor's specialization?"*.

#### 4. `admins.csv` (7 rows)
- **Primary Key**: `id`
- **Key Columns**: `employee_id`, `full_name`, `university_email`, `designation`, `phone`, `date_of_joining`, `is_active`
- **What it represents**: University administrative leadership, including the Registrar, Dean, Controller of Examinations, Academic Coordinator, and Accounts Officer.
- **How it is used in UniAssist**:
  - Grants university-wide scope (`UNIVERSITY`) for institutional reports, global notices, and cross-department queries.

#### 5. `departments.csv` (7 rows)
- **Primary Key**: `id`
- **Key Columns**: `code` (`CP`, `IT`, `EC`, `ME`, `CE`, `CH`, `SH`), `name`, `building`, `hod_faculty_id`
- **What it represents**: The 7 academic departments (Computer Science, ICT, Electronics, Mechanical, Civil, Chemical, and Basic Sciences & Humanities).
- **How it is used in UniAssist**:
  - Acts as the organizational backbone.
  - Connects students, faculty, classrooms, and curriculum under common departmental boundaries.
  - Links directly to the Head of Department via `hod_faculty_id` &rarr; `faculty.id` for approval routing.

---

### Subsystem 2: Academic Catalog & Infrastructure

#### 6. `subjects.csv` (346 rows)
- **Primary Key**: `subject_code` (e.g. `24CS201T`, `24MA101T`)
- **Key Columns**: `subject_name`, `category` (`BSC`, `ESC`, `PCC`, `PEC`, `OEC`, `HSC`), `component` (`Theory`, `Practical`, `Project`), `lecture_hours`, `tutorial_hours`, `practical_hours`, `credits`
- **What it represents**: Master catalog of all approved academic courses in the university syllabus.
- **How it is used in UniAssist**:
  - Provides course metadata (credit weight, lecture/lab hour breakdown) when students ask *"How many credits is DBMS?"* or *"Is Computer Networks a theory or practical subject?"*.
  - Used in CGPA/SGPA calculations by multiplying course grade points with `credits`.

#### 7. `curriculum.csv` (427 rows)
- **Primary Key**: `id`
- **Key Columns**: `dept_id`, `dept_code`, `semester`, `subject_code`, `subject_name`, `category`, `is_elective`
- **What it represents**: The structured semester-by-semester degree plan for each department.
- **How it is used in UniAssist**:
  - Powers curriculum advising queries such as *"What subjects do I have in Semester 5 of Computer Science?"* or *"Which professional electives are offered next term?"*.
  - Ensures course offerings are automatically aligned with official degree requirements.

#### 8. `classrooms.csv` (85 rows)
- **Primary Key**: `id`
- **Key Columns**: `code` (e.g. `CP-101`, `LAB-302`), `building`, `capacity`, `room_type` (`Lecture Hall`, `Computer Lab`, `Hardware Lab`, `Workshop`), `dept_id`
- **What it represents**: Physical campus infrastructure and room inventory with seat capacities.
- **How it is used in UniAssist**:
  - Powers the admin/faculty tool `find_available_classrooms(date, time_slot)` to detect free lecture halls for extra classes or events.
  - Validates room capacity against student cohort size when scheduling exams or courses.

---

### Subsystem 3: Course Operations & Timetable

#### 9. `course_offerings.csv` (1,920 rows)
- **Primary Key**: `id`
- **Key Columns**: `subject_code`, `subject_name`, `dept_id`, `dept_code`, `term` (`2026-27-ODD`, `2025-26-EVEN`), `semester`, `batch`, `faculty_id`, `session_type`, `division`, `lab_group`, `capacity`
- **What it represents**: Concrete, active instances of a subject being taught in a specific academic term, division, and lab group by an assigned faculty member.
- **How it is used in UniAssist**:
  - **Central Operational Anchor**: Almost every runtime operation (attendance, marks, submissions, timetable) references `offering_id`.
  - **Faculty Ownership Anchor**: Resolves which faculty member is teaching what course in which division (`faculty_id`).
  - Enforces `OWN_COURSES` permission for faculty tools: a professor can only access attendance or marks for offerings where `offering.faculty_id == ctx.faculty_id`.

#### 10. `enrollments.csv` (80,800 rows)
- **Primary Key**: `id`
- **Key Columns**: `student_id`, `offering_id`, `subject_code`, `term`, `status` (`enrolled`, `completed`, `dropped`), `enrolled_on`
- **What it represents**: The many-to-many link between students and their active/completed course offerings.
- **How it is used in UniAssist**:
  - Powers the student tool `get_my_courses()` to list active classes for the current term.
  - Powers the faculty tool `list_course_students(course_code)` to generate the official student roster.
  - Acts as the security gate: a student cannot view attendance or marks for a course they are not enrolled in.

#### 11. `timetable_slots.csv` (1,818 rows)
- **Primary Key**: `id`
- **Key Columns**: `offering_id`, `day_of_week` (0=Monday ... 5=Saturday), `start_time`, `end_time`, `classroom_id`, `session_type`
- **What it represents**: The weekly recurring class schedule mapping offerings to time slots and physical rooms.
- **How it is used in UniAssist**:
  - Powers `get_my_timetable(day)` for students to check their daily class schedule and classroom locations.
  - Powers `get_my_teaching_schedule(day)` for faculty to see their upcoming lectures and labs.

---

### Subsystem 4: Attendance Tracking

#### 12. `attendance_sessions.csv` (44,270 rows)
- **Primary Key**: `id`
- **Key Columns**: `offering_id`, `subject_code`, `session_date`, `slot_no`, `marked_by` (`faculty_id`), `marked_at`, `topic_no`
- **What it represents**: Individual class sessions conducted on specific calendar dates.
- **How it is used in UniAssist**:
  - Establishes the exact denominator (total classes held to date) for any course.
  - Audit trail: records exactly which faculty member marked attendance and at what timestamp.
  - Supports the action tool `mark_attendance()`.

#### 13. `attendance_records.csv` (1,997,884 rows)
- **Primary Key**: `id`
- **Key Columns**: `session_id`, `student_id`, `status` (`present`, `absent`, `late`, `excused_leave`)
- **What it represents**: The granular per-student, per-session attendance record.
- **How it is used in UniAssist**:
  - Establishes the numerator (sessions attended) vs denominator (total sessions conducted).
  - Powers `get_my_attendance(course)`: calculates exact attendance percentages and remaining margin before falling below the mandatory 75% threshold.
  - Powers faculty/admin tool `list_students_below_attendance(course_code, threshold=75.0)` to generate defaulter lists.

---

### Subsystem 5: Assessments, Marks, Submissions & Examinations

#### 14. `assessments.csv` (7,825 rows)
- **Primary Key**: `id`
- **Key Columns**: `offering_id`, `subject_code`, `term`, `type` (`Quiz`, `Assignment`, `Mid-Sem`, `Internal Test`, `Term-Work`, `End-Sem`), `title`, `max_marks`, `weightage_pct`, `due_date`, `status` (`scheduled`, `completed`, `graded`)
- **What it represents**: Evaluation milestones configured by faculty for a course offering.
- **How it is used in UniAssist**:
  - Provides due dates, maximum marks, and syllabus weightages for continuous evaluation.
  - Powers `get_my_assignments(status)` and informs students of upcoming tests.

#### 15. `marks.csv` (292,426 rows)
- **Primary Key**: `id`
- **Key Columns**: `assessment_id`, `student_id`, `score`, `is_absent`, `graded_on`
- **What it represents**: Individual scores achieved by students on specific assessments.
- **How it is used in UniAssist**:
  - Powers `get_my_marks(assessment_type)` for students to review scores.
  - Powers faculty tools `get_course_marks_summary(course_code)` and `identify_at_risk_students(course_code)` to compute class averages, standard deviations, and identify struggling students.

#### 16. `submissions.csv` (104,440 rows)
- **Primary Key**: `id`
- **Key Columns**: `assessment_id`, `student_id`, `status` (`submitted`, `missing`, `late`), `submitted_at`
- **What it represents**: Digital assignment/report submission tracking with timestamps.
- **How it is used in UniAssist**:
  - Powers faculty tool `list_missing_submissions(course_code, assessment)` to identify students who failed to submit assignments.
  - Allows students to verify whether their submission was successfully received and whether late penalties apply.

#### 17. `results_semester.csv` (3,450 rows)
- **Primary Key**: `id`
- **Key Columns**: `student_id`, `roll_no`, `term`, `semester`, `credits_registered`, `credits_earned`, `sgpa`, `cgpa`, `result_status` (`Pass`, `Fail`), `backlogs`, `declared_on`
- **What it represents**: Official end-of-semester grade transcripts and academic standing.
- **How it is used in UniAssist**:
  - Powers `get_my_results(semester)` for students.
  - Provides data for admin academic audits, probation lists, and graduation eligibility checks.

#### 18. `exam_schedule.csv` (567 rows)
- **Primary Key**: `id`
- **Key Columns**: `term`, `exam_type` (`Mid-Sem`, `End-Sem`), `subject_code`, `subject_name`, `dept_code`, `semester`, `exam_date`, `start_time`, `end_time`, `classroom_id`, `status`
- **What it represents**: Master institutional timetable for mid-semester and end-semester examinations.
- **How it is used in UniAssist**:
  - Powers `get_my_exam_schedule()` for students and faculty.
  - Enables room allocation conflict detection via `classroom_id`.

---

### Subsystem 6: Student Life & Administrative Operations

#### 19. `fees.csv` (8,050 rows)
- **Primary Key**: `id`
- **Key Columns**: `student_id`, `roll_no`, `term`, `amount_due`, `amount_paid`, `status` (`paid`, `partial`, `unpaid`, `overdue`), `due_date`, `paid_on`
- **What it represents**: Term-wise tuition, hostel, and institutional fee dues and transaction statuses.
- **How it is used in UniAssist**:
  - Powers `get_my_fees()` for students to check outstanding balances and payment deadlines.
  - Powers admin tool `get_fee_collection_summary(dept)` to report total revenue, collected funds, and unpaid arrears.

#### 20. `scholarships.csv` (820 rows)
- **Primary Key**: `id`
- **Key Columns**: `student_id`, `roll_no`, `name`, `amount`, `term`, `status` (`approved`, `pending`, `rejected`), `applied_on`, `decided_on`
- **What it represents**: Merit, sports, and financial aid scholarship applications.
- **How it is used in UniAssist**:
  - Powers `get_my_scholarships()` for students.
  - Cross-references with `fees.csv` to explain fee discrepancies (e.g. why an unpaid fee notice is pending waiver approval).

#### 21. `leave_requests.csv` (1,046 rows)
- **Primary Key**: `id`
- **Key Columns**: `student_id`, `roll_no`, `from_date`, `to_date`, `reason`, `status` (`pending`, `approved`, `rejected`), `applied_on`, `decided_by` (`faculty_id`), `decided_on`
- **What it represents**: Student formal leave applications submitted for medical, personal, or official reasons.
- **How it is used in UniAssist**:
  - Supports the student action tool `apply_for_leave(from, to, reason)` with two-phase confirmation.
  - Supports the faculty/HOD action tool `decide_leave_request(request_id, decision)`.
  - When approved, automatically triggers attendance updates (`status = excused_leave`) in `attendance_records.csv`.

#### 22. `document_requests.csv` (721 rows)
- **Primary Key**: `id`
- **Key Columns**: `student_id`, `roll_no`, `doc_type` (`Bonafide Certificate`, `Transcript`, `Fee Receipt`, `Character Certificate`), `purpose`, `status` (`processing`, `ready`, `collected`, `rejected`), `requested_on`, `ready_on`
- **What it represents**: Formal certificate and document issuance requests.
- **How it is used in UniAssist**:
  - Supports the student action tool `request_document(doc_type, purpose)`.
  - Enables status tracking (*"Is my Bonafide Certificate ready?"*).

#### 23. `announcements.csv` (33 rows)
- **Primary Key**: `id`
- **Key Columns**: `author_user_id`, `scope` (`university`, `department`, `course`), `scope_ref`, `title`, `body`, `audience_roles` (`student`, `faculty`, `admin`), `posted_at`
- **What it represents**: Campus circulars, exam notices, fee deadlines, and departmental announcements.
- **How it is used in UniAssist**:
  - Powers `get_my_announcements()` with multi-level filtering: checks the caller's role, department, and enrolled courses to return only relevant circulars.
  - Supports the faculty/admin action tool `post_announcement()`.

#### 24. `academic_calendar.csv` (25 rows)
- **Primary Key**: `id`
- **Key Columns**: `event`, `event_type` (`term`, `exam`, `holiday`, `registration`, `fee_deadline`, `result`), `start_date`, `end_date`, `applies_to` (`all`, `faculty`, `student`), `term`, `source_chunk_id`
- **What it represents**: Key university dates, term start/end dates, exam periods, and holiday breaks.
- **How it is used in UniAssist**:
  - Powers `get_academic_calendar(event_type)` for queries like *"When do mid-sem exams start?"* or *"What holidays do we have in October?"*.
  - Provides temporal context for relative date queries.

---

## 3. How Inter-Table Relationships Achieve Project Goals

The real intelligence of UniAssist emerges from the relationships connecting these 24 tables. Below is a detailed breakdown of the critical relational pathways and how they fulfill specific system capabilities.

```
Key Relational Pathways:
├── 1. Identity & RBAC Scoping          (users ↔ students/faculty/admins)
├── 2. Departmental Hierarchy           (departments ↔ faculty/students/classrooms)
├── 3. Course Delivery & Timetable     (subjects + faculty + classrooms ↔ course_offerings ↔ timetable_slots)
├── 4. Course Enrollment & Access Gate  (course_offerings ↔ enrollments ↔ students)
├── 5. Attendance Math & Policy RAG     (course_offerings ↔ attendance_sessions ↔ attendance_records ↔ students)
├── 6. Continuous Assessment & Risk     (course_offerings ↔ assessments ↔ marks & submissions ↔ students)
├── 7. Cross-Financial Audit            (students ↔ fees + scholarships)
├── 8. Action Flow & Auto-Excusal       (students ↔ leave_requests ↔ faculty ↔ attendance_records)
└── 9. Role-Scoped Campus Notices       (users ↔ announcements ↔ departments/course_offerings)
```

---

### Relationship 1: Identity & RBAC Scoping
**Tables Involved**: `users.csv` &harr; (`students.csv` | `faculty.csv` | `admins.csv`)  
**Foreign Key Link**: `users.email` matches `students.university_email` / `faculty.university_email` / `admins.university_email`; `users.subject_ref` stores `student:<id>`, `faculty:<id>`, or `admin:<id>`.

```
users (id, email, role, subject_ref)
  ├── role = 'student' ──> students (id, roll_no, dept_id, semester)
  ├── role = 'faculty' ──> faculty  (id, employee_id, dept_id, is_hod)
  └── role = 'admin'   ──> admins   (id, employee_id, designation)
```

**How this achieves project goals**:
- **Prevents Identity Spoofing**: If a student types *"Show attendance for student 23BCP045"*, the backend ignores any passed `student_id` and strictly injects the authenticated `student_id` from the JWT (`AuthContext.student_id`).
- **Dynamic Tool Exposure**: Call A exposes only student tools (`SELF` scope) to students, faculty tools (`OWN_COURSES` scope) to faculty, and admin tools (`UNIVERSITY` scope) to admins.

---

### Relationship 2: Departmental Hierarchy & Governance
**Tables Involved**: `departments.csv` &harr; `faculty.csv` & `students.csv` & `classrooms.csv`  
**Foreign Key Link**: `students.dept_id` &rarr; `departments.id`, `faculty.dept_id` &rarr; `departments.id`, `departments.hod_faculty_id` &rarr; `faculty.id`, `classrooms.dept_id` &rarr; `departments.id`.

**How this achieves project goals**:
- **HOD Approval Routing**: When a student applies for leave, the system queries `departments.hod_faculty_id` for that student's department to route the request to the correct Head of Department.
- **Departmental Boundaries**: Enables admin tools like `get_department_overview(dept_code)` and `get_faculty_workload(dept_code)` to aggregate student counts, faculty teaching hours, and classroom allocations per department.

---

### Relationship 3: Course Delivery & Timetable Scheduling
**Tables Involved**: `subjects.csv` + `faculty.csv` + `classrooms.csv` &harr; `course_offerings.csv` &harr; `timetable_slots.csv`  
**Foreign Key Link**:
- `course_offerings.subject_code` &rarr; `subjects.subject_code`
- `course_offerings.faculty_id` &rarr; `faculty.id`
- `timetable_slots.offering_id` &rarr; `course_offerings.id`
- `timetable_slots.classroom_id` &rarr; `classrooms.id`

```
subjects ────────┐
faculty ─────────┼──> course_offerings ──> timetable_slots ──> classrooms
departments ─────┘
```

**How this achieves project goals**:
- **Resolves "Where is my next class?"**: Joins `enrollments` &rarr; `course_offerings` &rarr; `timetable_slots` &rarr; `classrooms` to tell a student *"Your next lecture is Database Management Systems at 10:00 AM in Room CP-101 (A Block) with Dr. Krupa Patel"*.
- **Prevents Faculty & Room Clashes**: Ensures a faculty member or classroom is not double-booked across overlapping `timetable_slots`.

---

### Relationship 4: Course Enrollment & Access Gating
**Tables Involved**: `students.csv` &harr; `enrollments.csv` &harr; `course_offerings.csv` &harr; `faculty.csv`  
**Foreign Key Link**: `enrollments.student_id` &rarr; `students.id`, `enrollments.offering_id` &rarr; `course_offerings.id`, `course_offerings.faculty_id` &rarr; `faculty.id`.

**How this achieves project goals**:
- **Faculty Course Ownership Guard**: When a professor calls `list_course_students(course_code)`, the SQL filter verifies:
  ```sql
  WHERE course_offerings.subject_code = :course_code
    AND course_offerings.faculty_id = :authenticated_faculty_id
  ```
  This guarantees a faculty member cannot view student lists for courses taught by other professors.
- **Roster Generation**: Provides the exact list of enrolled students for attendance marking and mark entry.

---

### Relationship 5: Attendance Math & Policy Grounding (The Core Demo)
**Tables Involved**: `course_offerings.csv` &harr; `attendance_sessions.csv` &harr; `attendance_records.csv` &harr; `students.csv`  
**Foreign Key Link**:
- `attendance_sessions.offering_id` &rarr; `course_offerings.id`
- `attendance_records.session_id` &rarr; `attendance_sessions.id`
- `attendance_records.student_id` &rarr; `students.id`

```
course_offerings ──> attendance_sessions ──> attendance_records <── students
```

**How this achieves project goals**:
- **Dynamic Percentage Calculation**:
  $$\text{Attendance \%} = \frac{\text{Count}(\text{status} \in \{\text{'present'}, \text{'excused\_leave'}\})}{\text{Total Sessions Held for Offering}} \times 100$$
- **Planted Demo Case (`25BCP017` in `24CS201T`)**:
  - The student has attended 17 out of 25 conducted sessions = **68.0%**.
  - UniAssist runs RAG on `attendance_policy.pdf` (retrieving the 75% requirement rule), queries `attendance_records` (retrieving 17/25 = 68%), and synthesizes:
    > *"University regulation §3.1 requires a minimum of 75% attendance to appear in End-Sem examinations. You currently have 68.0% in DBMS (17/25 sessions). You need 2 more attended classes out of 25 to reach 76%, or you must attend the next 6 consecutive sessions without absence."*

---

### Relationship 6: Continuous Assessment, Grading & Risk Detection
**Tables Involved**: `course_offerings.csv` &harr; `assessments.csv` &harr; `marks.csv` & `submissions.csv` &harr; `students.csv`  
**Foreign Key Link**:
- `assessments.offering_id` &rarr; `course_offerings.id`
- `marks.assessment_id` &rarr; `assessments.id`, `marks.student_id` &rarr; `students.id`
- `submissions.assessment_id` &rarr; `assessments.id`, `submissions.student_id` &rarr; `students.id`

```
                      ┌──> marks ────────┐
course_offerings ──> assessments         ├──> students
                      └──> submissions ──┘
```

**How this achieves project goals**:
- **At-Risk Student Identification**: Faculty tool `identify_at_risk_students(course_code)` joins `marks` and `attendance_records` to flag students who simultaneously have attendance < 75% and test scores < 40%.
- **Missing Submission Audits**: Faculty tool `list_missing_submissions(course_code, assessment)` finds students where `submissions.status = 'missing'` or no submission record exists, enabling targeted reminders.
- **Planted Demo Case (`24CS202T`)**: Surfaces a ~35% failure rate in Internal Test 1 for Digital Logic & Design, triggering an administrative alert card.

---

### Relationship 7: Financial Integrity & Scholarship Reconciliation
**Tables Involved**: `students.csv` &harr; `fees.csv` & `scholarships.csv`  
**Foreign Key Link**: `fees.student_id` &rarr; `students.id`, `scholarships.student_id` &rarr; `students.id`.

**How this achieves project goals**:
- **Intelligent Financial Explanations**: If student `25BCP012` asks *"Why is my fee status showing unpaid?"*, UniAssist inspects both `fees` (status: `unpaid`, due: ₹1,52,500) and `scholarships` (status: `pending`, amount: ₹20,000) to answer:
  > *"Your tuition fee of ₹1,52,500 for Odd Semester 2026-27 is marked unpaid. However, you have a pending Sports Excellence Scholarship application for ₹20,000 under review by the Accounts Office. Once approved, your net payable fee will adjust to ₹1,32,500."*

---

### Relationship 8: Action Execution & Automatic Attendance Excusal
**Tables Involved**: `students.csv` &harr; `leave_requests.csv` &harr; `faculty.csv` &rarr; `attendance_records.csv`  
**Foreign Key Link**: `leave_requests.student_id` &rarr; `students.id`, `leave_requests.decided_by` &rarr; `faculty.id`.

```
students ──> leave_requests (status='pending') ──> faculty (reviews & approves)
                                                          │
                                                          ▼
                                             attendance_records (updates status='excused_leave')
```

**How this achieves project goals**:
- **Two-Phase Action Flow**:
  1. Student asks: *"Apply for medical leave from 2026-09-02 to 2026-09-04."*
  2. Tool validates dates and returns a `ConfirmActionCard` with an HMAC token.
  3. Upon student confirmation, a row is inserted into `leave_requests.csv` with `status = 'pending'`.
- **Downstream Effect**: When the faculty member approves the request via `decide_leave_request()`, the backend updates `attendance_records.csv` for any sessions falling within that date range to `status = 'excused_leave'`, automatically restoring the student's attendance percentage.

---

### Relationship 9: Multi-Tier Targeted Announcements
**Tables Involved**: `users.csv` &harr; `announcements.csv` &harr; `departments.csv` / `course_offerings.csv`  
**Foreign Key Link**: `announcements.author_user_id` &rarr; `users.id`.

**How this achieves project goals**:
- **Contextual Notice Delivery**: When `get_my_announcements()` executes:
  - If `scope = 'university'`, the announcement is delivered to all matching `audience_roles`.
  - If `scope = 'department'`, it matches `scope_ref == student.dept_id`.
  - If `scope = 'course'`, it matches `scope_ref == enrollment.offering_id`.
- Prevents notification fatigue by ensuring Mechanical students never receive Computer Science lab cancellation notices.

---

## 4. Summary Matrix of Assistant Tools and Target Tables

| Assistant Tool | Primary Caller Role | Target Tables Read / Written | Key Purpose |
|---|---|---|---|
| `get_my_profile` | Student / Faculty | `students`, `faculty`, `departments`, `users` | Returns authenticated user profile and academic standing. |
| `get_my_courses` | Student | `enrollments`, `course_offerings`, `subjects`, `faculty` | Lists active semester courses and instructors. |
| `get_my_timetable` | Student / Faculty | `timetable_slots`, `course_offerings`, `classrooms`, `enrollments` | Returns daily class schedule with room numbers. |
| `get_my_attendance` | Student | `attendance_records`, `attendance_sessions`, `course_offerings`, `subjects` | Calculates percentage, attended vs total classes, and shortfall margin. |
| `get_my_marks` | Student | `marks`, `assessments`, `course_offerings`, `subjects` | Lists continuous assessment scores and exam grades. |
| `get_my_results` | Student | `results_semester`, `students` | Returns official SGPA, CGPA, earned credits, and backlogs. |
| `get_my_exam_schedule` | Student / Faculty | `exam_schedule`, `subjects`, `classrooms`, `enrollments` | Lists upcoming mid-sem and end-sem exam dates and halls. |
| `get_my_fees` | Student | `fees`, `scholarships`, `students` | Shows fee dues, payment deadlines, and scholarship credits. |
| `apply_for_leave` | Student | `leave_requests` *(Write)* | Submits leave request via 2-phase confirmation. |
| `request_document` | Student | `document_requests` *(Write)* | Initiates Bonafide or transcript request. |
| `get_my_teaching_schedule` | Faculty | `timetable_slots`, `course_offerings`, `classrooms` | Shows faculty's daily teaching timetable. |
| `list_course_students` | Faculty | `enrollments`, `students`, `course_offerings` | Returns student roster for an assigned course. |
| `get_course_attendance_summary` | Faculty | `attendance_records`, `attendance_sessions`, `course_offerings`, `students` | Computes class-wide attendance averages and defaulter lists. |
| `list_students_below_attendance` | Faculty / Admin | `attendance_records`, `attendance_sessions`, `students`, `course_offerings` | Returns list of students below a given percentage (default 75%). |
| `list_missing_submissions` | Faculty | `submissions`, `assessments`, `students`, `course_offerings` | Flags students who have not submitted assignments. |
| `identify_at_risk_students` | Faculty | `marks`, `attendance_records`, `assessments`, `attendance_sessions`, `students` | Flags students with combined low attendance and low test scores. |
| `mark_attendance` | Faculty | `attendance_sessions`, `attendance_records` *(Write)* | Records class attendance via 2-phase confirmation. |
| `decide_leave_request` | Faculty (HOD/Mentor) | `leave_requests`, `attendance_records` *(Write)* | Approves/rejects student leave and updates attendance. |
| `get_enrollment_stats` | Admin | `enrollments`, `course_offerings`, `departments`, `students` | Aggregates enrollment counts by department and semester. |
| `get_faculty_workload` | Admin | `course_offerings`, `timetable_slots`, `faculty`, `departments` | Calculates weekly teaching hours per instructor. |
| `find_available_classrooms` | Admin / Faculty | `classrooms`, `timetable_slots`, `exam_schedule` | Detects unallocated rooms for a specific day and time slot. |
| `get_fee_collection_summary` | Admin | `fees`, `departments`, `students` | Reports departmental fee collection and overdue amounts. |
| `search_university_policies` | All Roles | `documents`, `doc_chunks` (RAG Vector Store) | Semantic search over regulations, ordinances, and policies. |
| `get_academic_calendar` | All Roles | `academic_calendar` | Returns university dates, holidays, and semester deadlines. |
| `get_my_announcements` | All Roles | `announcements`, `departments`, `enrollments` | Fetches targeted campus circulars matching user context. |
