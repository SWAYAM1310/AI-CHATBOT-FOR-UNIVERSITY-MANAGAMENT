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

// A two-phase confirm card: the turn stopped before answering and wants a yes.
export interface ConfirmCard {
  type: 'confirm'
  tool: string
  args: Record<string, unknown>
  preview: Record<string, unknown> & { summary?: string }
  token: string
  needs_confirmation?: boolean
}

export type Card = ConfirmCard | { type: string; [k: string]: unknown }

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
}
