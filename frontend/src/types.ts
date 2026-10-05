// Shapes returned by the backend (backend/app/api/*.py). Kept narrow: only
// what the UI reads.

export type Role = 'student' | 'faculty' | 'admin'

export interface Session {
  token: string
  role: Role
  subjectRef: string
}

export interface Me {
  user_id: number
  full_name: string
  has_photo: boolean
  role: Role
  subject_ref: string
  dept_id: number | null
  is_hod: boolean
  term: string
  profile: Record<string, unknown> | null
}

export interface Citation {
  n: number
  chunk_id: number
  document: string | null
  section: string | null
  page: number | null
  snippet: string
}

// A drafted email a confirm card previews (apply_for_leave, decide_leave_request)
// — the exact text that gets sent if the card is confirmed, never redrafted after.
export interface EmailPreview {
  to: string | null
  subject: string
  body: string
}

// A two-phase confirm card: the turn stopped before answering and wants a yes.
export interface ConfirmCard {
  type: 'confirm'
  tool: string
  args: Record<string, unknown>
  preview: Record<string, unknown> & { summary?: string; email_preview?: EmailPreview }
  token: string
  needs_confirmation?: boolean
}

export type Card = ConfirmCard | { type: string; [k: string]: unknown }

export interface ToolRunOut {
  name: string
  args: Record<string, unknown>
  ok: boolean
  error: string | null
  latency_ms?: number  // absent on tool pills that arrive live, and on stored turns
}

// Where a turn's wall time went, in ms; null = that stage did not run this turn.
export interface Timings {
  route_ms: number
  plan_ms: number | null
  tools_ms: number | null
  retrieve_ms: number | null
  synthesize_ms: number | null
  first_token_ms: number | null  // from the start of the turn
  total_ms: number
}

// Reference-free quality signals (backend/app/ai/scoring.py). null = the check
// did not apply this turn (nothing to measure), which is not the same as 0.
export interface Scores {
  passages: number
  top_score: number | null
  both_branches: number
  dense_only: number
  sparse_only: number
  cited: number
  context_precision: number | null
  claims: number
  claims_cited: number
  citation_coverage: number | null
  numbers: number
  numbers_grounded: number
  numeric_grounding: number | null
  ungrounded_numbers: string[]
  tools_run: number
  tools_ok: number
  tool_success: number | null
}

export interface Trace {
  path: string
  intent: string
  tool_runs: ToolRunOut[]
  usage: { tokens_in: number; tokens_out: number }
  timings?: Timings  // absent on a reopened conversation: timings and scores are not stored
  scores?: Scores
}

export interface ChatOut {
  conversation_id: number
  message_id: number
  text: string
  citations: Citation[]
  cards: Card[]
  path: string
  intent: string
  usage: { tokens_in: number; tokens_out: number }
  queued_seconds: number
  trace: Trace
}

export interface ConfirmOut {
  tool: string
  text: string
  result: Record<string, unknown>
  conversation_id: number | null
  message_id: number | null
}

export interface MessageOut {
  id: number
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string | null
  citations: Citation[]
  cards: Card[]
  tokens_in: number | null
  tokens_out: number | null
  created_at: string
  tool_runs: ToolRunOut[]
}

export interface ConversationOut {
  id: number
  title: string | null
  created_at: string
}

// What the transcript renders. `pending` is a user message whose answer is
// still on its way; `error` is a turn the server refused.
export interface Turn {
  id: string
  role: 'user' | 'assistant'
  text: string
  citations: Citation[]
  cards: Card[]
  pending?: boolean
  queuedSeconds?: number
  error?: string
  // set once a confirm card has been answered, so it renders as settled
  outcome?: { text: string; ok: boolean }
  trace?: Trace  // the dev tool-trace panel reads this; hidden by default
  // streaming-in-progress state — cleared once the `done` event lands
  streaming?: boolean
  stage?: string  // "routing" | "planning" | "running_tools" | "retrieving" | "writing"
  liveTools?: ToolRunOut[]  // tool calls as they finish, before the final trace exists
}

// --- faculty portal (backend/app/api/faculty.py) -------------------------------------------

export interface FacultyCourse {
  offering_id: number
  course: string
  name: string
  dept_code: string
  semester: number
  division: string | null
  lab_group: string | null
  session_type: string | null
  enrolled: number | null
}

export interface RosterStudent {
  roll_no: string
  full_name: string
  dept_code: string
  division: string | null
  attended: number
  total: number
  attendance_percent: number | null
  missing_submissions: number
}

export interface RosterOut {
  offering: FacultyCourse
  students: RosterStudent[]
}

export interface AttendanceSession {
  id: number
  date: string
  slot_no: number | null
  marked_at: string | null
  /** nobody took this register, so the upkeep job recorded everyone present */
  auto_marked: boolean
  present: number
  absent: number
  absent_roll_nos: string[]
}

export interface AttendanceDay {
  offering: FacultyCourse
  date: string | null
  sessions: AttendanceSession[]
  recent: AttendanceSession[]
}

export interface CalendarEvent {
  event: string
  event_type: string // term | holiday | break | exam | registration | result | orientation | fee
  start_date: string
  end_date: string | null
}

/** held: attendance exists; due: timetabled, today or earlier, not marked; upcoming: timetabled, later. */
export type ClassStatus = 'held' | 'due' | 'upcoming'

export interface CalendarClass extends FacultyCourse {
  start_time: string | null
  end_time: string | null
  room: string | null
  status: ClassStatus
  /** auto: the upkeep job recorded everyone present because nobody took the register */
  sessions: { id: number; slot_no: number | null; present: number; absent: number; auto: boolean }[]
}

export interface CalendarDay {
  date: string
  events: { event: string; event_type: string; start_date: string }[]
  classes: CalendarClass[]
}

export interface FacultyCalendar {
  month: string
  today: string
  term: { start: string | null; end: string | null }
  events: CalendarEvent[]
  days: CalendarDay[]
}

export interface AssessmentRow {
  assessment_id: number
  type: string
  title: string | null
  max_marks: number | null
  weightage_pct: number | null
  due_date: string | null
  status: string | null
  graded: number
  auto_graded: boolean
}

export interface AssessmentList {
  offering: FacultyCourse
  assessments: AssessmentRow[]
}

export interface MarksSheet {
  offering: FacultyCourse
  assessment: { assessment_id: number; type: string; title: string | null; max_marks: number | null; auto_graded: boolean }
  students: { roll_no: string; full_name: string; score: number | null; is_absent: boolean }[]
}

export interface AnnouncementItem {
  title: string
  body: string | null
  scope: string
  posted_at: string | null
}

export interface AtRiskStudent {
  roll_no: string
  full_name: string
  attendance_percent: number | null
  marks_percent: number | null
  missing_submissions: number
  reasons: string
}

export interface PendingLeave {
  leave_request_id: number
  roll_no: string
  full_name: string
  from_date: string
  to_date: string
  reason: string | null
  applied_on: string | null
}

export interface TodayClass extends FacultyCourse {
  start_time: string
  end_time: string
  room: string | null
  attendance_marked: boolean
}

export interface FacultyDashboard {
  faculty: { full_name: string; designation: string | null; dept_code: string; is_hod: boolean }
  term: string
  date: string
  weekday: number
  courses: number
  students: number
  today: TodayClass[]
  at_risk: { count: number; students: AtRiskStudent[] }
  pending_leave: { count: number; requests: PendingLeave[] }
  announcements: AnnouncementItem[]
}

export interface ActionResult {
  done: boolean
  message: string
  [key: string]: unknown
}

// --- student dashboard (backend/app/api/student.py) ------------------------------------------

export interface CourseAttendance {
  course: string
  name: string
  attended: number
  total: number
  percent: number
  below_threshold: boolean
  recover: number | null
  can_skip: number | null
}

export interface FeeEntry {
  term: string
  amount_due: number | null
  amount_paid: number | null
  status: string
  due_date: string | null
  paid_on: string | null
  outstanding: number
}

export interface AssignmentRow {
  course: string
  title: string | null
  due_date: string | null
  status: string
  submitted_at: string | null
}

export interface ExamRow {
  exam_type: string
  course: string
  name: string
  date: string
  start_time: string | null
  end_time: string | null
  room: string | null
}

export interface ClassSlot {
  day_of_week: number
  start_time: string
  end_time: string
  course: string
  name: string
  session_type: string | null
  room: string | null
}

export interface StudentDashboard {
  student: { full_name: string; roll_no: string; dept_code: string; semester: number; division: string | null; cgpa: number | null }
  term: string
  generated_at: string
  date: string
  weekday: number
  attendance: { threshold: number; overall_percent: number | null; short_courses: number; courses: CourseAttendance[] }
  fees: { all_paid: boolean; outstanding: number; entries: FeeEntry[] }
  assignments: AssignmentRow[]
  exams: ExamRow[]
  today: ClassSlot[]
  announcements: AnnouncementItem[]
}

// --- student results (backend/app/api/student.py) -------------------------------------------

export interface ResultAssessment {
  type: string
  title: string | null
  max_marks: number | null
  weightage_pct: number | null
  due_date: string | null
  status: string | null // scheduled | completed | graded
  entered: boolean // a mark row exists for this student
  score: number | null
  is_absent: boolean
}

export interface InternalAssessment {
  score: number // weighted, out of `out_of`
  out_of: number
  graded_out_of: number
  complete: boolean
}

export interface ResultCourse {
  course: string
  name: string
  component: string | null
  assessments: ResultAssessment[]
  ia: InternalAssessment | null
}

export interface ResultSemesterSummary {
  sgpa: number | null
  cgpa: number | null
  result_status: string | null
  credits_earned: number | null
  credits_registered: number | null
  backlogs: number | null
  declared_on: string | null
}

export interface ResultsSemester {
  semester: number
  term: string
  current: boolean
  result: ResultSemesterSummary | null
  courses: ResultCourse[]
}

export interface StudentResults {
  term: string
  semesters: ResultsSemester[] // newest first
}

// --- profile (backend/app/api/profile.py) ---------------------------------------------------

export interface ProfileOut {
  role: Role
  editable: string[]
  has_photo: boolean
  profile: Record<string, string | number | boolean | null>
}

// --- admin portal (backend/app/api/admin.py) ------------------------------------------------

export interface DeliveryCounts {
  sent: number
  queued: number
  held: number
  failed: number
  suppressed: number
  total: number
}

export interface AdminNotice {
  announcement_id: number
  title: string
  body: string | null
  scope: string
  dept: string | null
  /** comma-separated roles, e.g. "student,faculty" */
  audience: string
  semester: number | null
  posted_at: string | null
  delivery: DeliveryCounts
}

export interface DepartmentRow {
  dept: string
  name: string
  hod: string | null
  students: number
  faculty: number
  offerings_this_term: number
  avg_attendance_percent: number | null
  below_attendance: number
  fee_collection_percent: number | null
  fee_outstanding: number | null
}

export interface AdminDashboard {
  admin: { full_name: string; designation: string | null }
  term: string
  kpis: {
    students: number
    faculty: number
    departments: number
    avg_attendance_percent: number | null
    below_attendance: number
    fees_billed: number
    fees_collected: number
    fees_outstanding: number
    fee_collection_percent: number | null
  }
  departments: DepartmentRow[]
  recent_announcements: AdminNotice[]
}

export const FEE_STATUSES = ['paid', 'partial', 'unpaid', 'overdue'] as const
export type FeeStatus = (typeof FEE_STATUSES)[number]

export interface FeeRecord {
  fee_id: number
  roll_no: string
  full_name: string
  dept_code: string
  semester: number
  term: string
  amount_due: number
  amount_paid: number
  outstanding: number
  status: FeeStatus
  due_date: string | null
  paid_on: string | null
}

export interface FeePage {
  term: string
  total: number
  page: number
  page_size: number
  counts: Record<FeeStatus, number>
  fees: FeeRecord[]
}

export type NoticeAudience = 'all' | 'student' | 'faculty'

export interface NoticeDraft {
  title: string
  body: string
  audience: NoticeAudience
  dept?: string
  semester?: number
  email_subject?: string
  email_body?: string
}

export interface NoticePreview {
  preview: {
    summary: string
    recipients_students: number
    recipients_faculty: number
    emails_to_send: number
    emails_held: number
  }
  /** null when email is switched off on the server: the notice is then in-app only */
  email: { to: string; subject: string; body: string } | null
  emailing: boolean
}

export interface PublishResult extends ActionResult {
  announcement_id: number
  recipients: number
  emails_queued: number
  emails_held: number
}

export interface DeliveryList {
  announcement_id: number
  delivery: DeliveryCounts
  emails: { intended_to: string; to: string; status: string; attempts: number; error: string | null; sent_at: string | null }[]
}
