// One thin client over the backend. Every call carries the bearer token; a
// non-2xx response becomes an ApiError with the server's detail, so the UI
// can say what went wrong rather than "something went wrong".
import type {
  ActionResult,
  AdminDashboard,
  AdminNotice,
  AssessmentList,
  AttendanceDay,
  Card,
  ChatOut,
  DeliveryList,
  FeePage,
  FeeRecord,
  ConfirmOut,
  ConversationOut,
  FacultyCalendar,
  FacultyCourse,
  FacultyDashboard,
  MarksSheet,
  Me,
  MessageOut,
  NoticeDraft,
  NoticePreview,
  ProfileOut,
  PublishResult,
  RosterOut,
  Role,
  StudentDashboard,
  StudentResults,
} from './types'

export class ApiError extends Error {
  status: number
  retryAfter: number | null

  constructor(status: number, message: string, retryAfter: number | null = null) {
    super(message)
    this.status = status
    this.retryAfter = retryAfter
  }
}

let token: string | null = null

export function setToken(t: string | null) {
  token = t
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) }
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json' // a file upload sets its own
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(path, { ...init, headers })
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail =
      body && typeof body.detail === 'string'
        ? body.detail
        : body && Array.isArray(body.detail) // a request the server could not parse: say which field
          ? body.detail.map((d: { loc?: unknown[]; msg?: string }) => `${d.loc?.slice(-1)[0] ?? 'request'}: ${d.msg}`).join('; ')
          : res.statusText
    const retry = res.headers.get('Retry-After')
    throw new ApiError(res.status, detail, retry ? Number(retry) : null)
  }
  return body as T
}

// --- streaming chat -----------------------------------------------------
// EventSource can't POST or carry the bearer header, so the SSE frames are
// parsed by hand off a plain fetch stream.

export interface StreamTool {
  name: string
  args: Record<string, unknown>
  ok: boolean
  error: string | null
}

export interface StreamHandlers {
  onStatus?: (stage: string) => void
  onTool?: (tool: StreamTool) => void
  onCards?: (cards: Card[]) => void
  onDelta?: (text: string) => void
  onQueued?: (seconds: number) => void
}

async function chatStream(
  message: string,
  conversationId: number | null,
  handlers: StreamHandlers,
): Promise<ChatOut> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, conversation_id: conversationId }),
  })
  if (!res.ok || !res.body) {
    // the stream never opened at all: same error shape as the blocking endpoint
    const body = await res.json().catch(() => null)
    const detail = body && typeof body.detail === 'string' ? body.detail : res.statusText
    const retry = res.headers.get('Retry-After')
    throw new ApiError(res.status, detail, retry ? Number(retry) : null)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let done: ChatOut | null = null

  while (true) {
    const { value, done: streamDone } = await reader.read()
    if (streamDone) break
    buf += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buf.indexOf('\n\n')) !== -1) {
      const frame = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      const out = handleFrame(frame, handlers)
      if (out) done = out
    }
  }
  if (!done) throw new ApiError(0, 'The stream ended without a reply.')
  return done
}

function handleFrame(frame: string, handlers: StreamHandlers): ChatOut | null {
  let event = 'message'
  let data = ''
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return null
  const payload = JSON.parse(data)
  switch (event) {
    case 'status':
      handlers.onStatus?.(payload.stage)
      return null
    case 'tool':
      handlers.onTool?.(payload as StreamTool)
      return null
    case 'cards':
      handlers.onCards?.(payload.cards as Card[])
      return null
    case 'delta':
      handlers.onDelta?.(payload.text as string)
      return null
    case 'queued':
      handlers.onQueued?.(payload.seconds as number)
      return null
    case 'done':
      return payload as ChatOut
    case 'error':
      throw new ApiError(payload.status, payload.detail, payload.retry_after ?? null)
    default:
      return null
  }
}

// A protected file (a profile photo): <img src> cannot send the token, so it is fetched as a blob.
async function photo(userId: number): Promise<Blob> {
  const res = await fetch(`/api/profile/photo/${userId}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new ApiError(res.status, 'no photo', null)
  return res.blob()
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) })

export const api = {
  photo,
  studentDashboard: () => request<StudentDashboard>('/api/student/dashboard'),
  studentResults: () => request<StudentResults>('/api/student/results'),
  profile: () => request<ProfileOut>('/api/profile'),
  updateProfile: (changes: Record<string, string>) =>
    request<{ profile: ProfileOut['profile'] }>('/api/profile', { method: 'PATCH', ...json(changes) }),
  changePassword: (current: string, next: string) =>
    request<void>('/api/profile/password', { method: 'POST', ...json({ current, new: next }) }),
  uploadPhoto: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<void>('/api/profile/photo', { method: 'POST', body: form })
  },
  deletePhoto: () => request<void>('/api/profile/photo', { method: 'DELETE' }),
  facultyDashboard: () => request<FacultyDashboard>('/api/faculty/dashboard'),
  facultyCourses: () => request<FacultyCourse[]>('/api/faculty/courses'),
  roster: (offeringId: number) => request<RosterOut>(`/api/faculty/offerings/${offeringId}/roster`),
  attendanceDay: (offeringId: number, date: string) =>
    request<AttendanceDay>(`/api/faculty/offerings/${offeringId}/attendance?date=${encodeURIComponent(date)}`),
  markAttendance: (offeringId: number, body: { date: string; slot_no: number | null; absent_roll_nos: string[] }) =>
    request<ActionResult>(`/api/faculty/offerings/${offeringId}/attendance`, { method: 'POST', ...json(body) }),
  correctAttendance: (offeringId: number, body: { date: string; slot_no: number | null; absent_roll_nos: string[] }) =>
    request<ActionResult>(`/api/faculty/offerings/${offeringId}/attendance`, { method: 'PUT', ...json(body) }),
  facultyCalendar: (month: string, offeringId?: number) =>
    request<FacultyCalendar>(`/api/faculty/calendar?month=${month}${offeringId ? `&offering_id=${offeringId}` : ''}`),
  assessments: (offeringId: number) => request<AssessmentList>(`/api/faculty/offerings/${offeringId}/assessments`),
  marksSheet: (assessmentId: number) => request<MarksSheet>(`/api/faculty/assessments/${assessmentId}/marks`),
  saveMarks: (assessmentId: number, body: { marks: Record<string, number>; absent_roll_nos: string[] }) =>
    request<ActionResult>(`/api/faculty/assessments/${assessmentId}/marks`, { method: 'POST', ...json(body) }),
  adminDashboard: () => request<AdminDashboard>('/api/admin/dashboard'),
  fees: (filters: { dept?: string; status?: string; q?: string; page?: number }) => {
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(filters)) if (v !== undefined && v !== '') params.set(k, String(v))
    return request<FeePage>(`/api/admin/fees?${params}`)
  },
  recordPayment: (feeId: number, body: { amount: number; paid_on?: string }) =>
    request<ActionResult & { fee: FeeRecord }>(`/api/admin/fees/${feeId}/payment`, { method: 'POST', ...json(body) }),
  notices: () => request<AdminNotice[]>('/api/admin/announcements'),
  previewNotice: (draft: NoticeDraft) => request<NoticePreview>('/api/admin/announcements/preview', { method: 'POST', ...json(draft) }),
  publishNotice: (draft: NoticeDraft) => request<PublishResult>('/api/admin/announcements', { method: 'POST', ...json(draft) }),
  deliveries: (announcementId: number) => request<DeliveryList>(`/api/admin/announcements/${announcementId}/deliveries`),
  login(email: string, password: string) {
    return request<{ access_token: string; role: Role; subject_ref: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },
  me() {
    return request<Me>('/api/me')
  },
  chat(message: string, conversationId: number | null) {
    return request<ChatOut>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id: conversationId }),
    })
  },
  chatStream,
  confirm(confirmToken: string, conversationId: number | null) {
    return request<ConfirmOut>('/api/chat/confirm', {
      method: 'POST',
      body: JSON.stringify({ token: confirmToken, conversation_id: conversationId }),
    })
  },
  conversations() {
    return request<ConversationOut[]>('/api/chat')
  },
  messages(conversationId: number) {
    return request<MessageOut[]>(`/api/chat/${conversationId}`)
  },
  renameConversation(conversationId: number, title: string) {
    return request<ConversationOut>(`/api/chat/${conversationId}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    })
  },
  deleteConversation(conversationId: number) {
    return request<void>(`/api/chat/${conversationId}`, { method: 'DELETE' })
  },
}
