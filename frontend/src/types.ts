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
