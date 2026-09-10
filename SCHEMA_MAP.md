# Schema map — where the ORM diverges from `plan.md §2`

The **generated CSVs are authoritative** for the 24 data tables. `plan.md §2` was
written before the dataset existed and is stale on names and columns. The ORM in
`backend/app/models/` mirrors the actual `data/synthetic/sample/*.csv` headers; the
five AI-layer tables (no CSV) follow `plan.md §2`. This file records every material
difference.

## Table-level differences

| `plan.md §2` | Actual schema | Notes |
|---|---|---|
| `courses(id, code, name, credits, dept_id, semester, type)` | **`subjects`** (PK `subject_code`, no `id`) + **`curriculum`** (`id`, `dept_id`, `dept_code`, `semester`, `subject_code`, `subject_name`, `category`, `is_elective`) | `subjects` = master catalog; `curriculum` = per-department semester plan. Two tables, not one. |
| `course_offerings(course_id, faculty_id, term, section)` | `course_offerings(subject_code, subject_name, dept_id, dept_code, term, semester, batch, faculty_id, session_type, division, lab_group, capacity)` | Keyed by `subject_code`, not `course_id`. `section` → `division` + `lab_group`. |
| `students(id, user_id, roll_no, dept_id, semester, batch)` | `students` has **no `user_id`**; full demographics (`gender`, `date_of_birth`, `phone`, `address_*`, `tenth/twelfth_percentage`, `cgpa`, `is_hosteller`, `guardian_*`, `admission_date`, `is_active`), plus `dept_code`, `division`, `lab_group` | Identity link is `users.subject_ref = 'student:<id>'` + email match, not an FK. |
| `faculty(id, user_id, employee_id, dept_id, designation)` | `faculty` has **no `user_id`**; adds `is_hod`, `qualification`, `specialization`, `office_room`, `date_of_joining`, demographics | Same `subject_ref` linkage as students. |
| admin folded into `users` | dedicated **`admins`** table (7 rows) | Own table with `employee_id`, `designation`, demographics. |
| — | **`teaching_assignments`** (`id`, `faculty_id`, `subject_code`, `batch`, `semester`, `session_type`, `division`, `lab_group`) | Not in `plan.md §2` at all. Faculty↔subject mapping distinct from `course_offerings`. |
| `enrollments(id, student_id, offering_id, status)` | adds `subject_code`, `term`, `enrolled_on` | denormalised mirrors kept. |
| `attendance_sessions(... slot_id, marked_by, marked_at)` | `slot_no` (int), no `slot_id` FK; adds `subject_code`, `topic_no` | |
| `assessments(... type, title, max_marks, due_date)` | adds `subject_code`, `term`, `weightage_pct`, `status`; `type` values like `Quiz-1`, `Internal-1`, `Term-Work` | |
| `marks(id, assessment_id, student_id, score)` | adds `is_absent`, `graded_on` | |
| — | **`results_semester`**, **`submissions`**, **`exam_schedule`** present as their own CSVs | `plan.md` mentions these in prose; they are first-class tables. |
| `announcements(author_user_id, scope, scope_ref, title, body)` | adds `audience_roles` (comma string), `posted_at` | `audience_roles` kept as the CSV's `"student,faculty,admin"` string, **not** a Postgres array (contrast `documents.audience_roles`). |
| `academic_calendar(... source_chunk_id)` | matches; `source_chunk_id` is a nullable FK to `doc_chunks.id` (`use_alter`), populated by Phase-3 ingest | |

## Curriculum-detail tables — deferred

`syllabus_units`, `course_outcomes`, `textbooks`, `course_prerequisites` (`plan.md §2`,
"Curriculum" block) are **not modelled**. They are filled by the Phase-3 curriculum
PDF extractor and have no synthetic CSV.

## AI-layer tables — from `plan.md §2`, no CSV

`conversations`, `messages`, `documents`, `doc_chunks`, `audit_log` created empty.
- `doc_chunks.embedding` is `VECTOR(EMBEDDING_DIM)` (pgvector); dim comes from
  `app.config.settings.embedding_dim` (1024), referenced in the migration too.
- `doc_chunks.parent_chunk_id` is a self-FK; `tsv` is `TSVECTOR`.
- `documents.audience_roles` **is** a Postgres `TEXT[]` here (unlike `announcements`).

## Type conventions applied by the loader

- `True`/`False` strings → `Boolean`
- ISO dates → `Date` via `date.fromisoformat` (tolerates 2-digit years like `0018-03-15`
  that appear in `students.date_of_birth`)
- `HH:MM` → `Time`; `...THH:MM:SS` → `DateTime`
- empty cell → `NULL`
- money / percentages / gpa → `Numeric`

## Circular FKs

`departments.hod_faculty_id → faculty.id` and `faculty.dept_id → departments.id` form a
cycle. Both FKs use `use_alter=True`; the loader inserts `departments` with
`hod_faculty_id` held `NULL`, loads `faculty`, then patches the HOD ids.
