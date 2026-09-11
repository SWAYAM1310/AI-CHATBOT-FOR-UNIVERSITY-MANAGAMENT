import type { ConversationOut, Role } from './types'

// Four or five questions that show each role what the assistant is for.
// They double as the demo script: each one exercises a different path
// (own records, a regulation with a citation, the syllabus, an action).
export const SUGGESTIONS: Record<Role, string[]> = {
  student: [
    'Am I short on attendance in any course?',
    'What are my marks so far this semester?',
    'When is the fee due, and what happens if I pay late?',
    "What's covered in Unit 3 of Database Management Systems?",
    'Apply for leave from 5 to 7 October for a family function',
  ],
  faculty: [
    'Who is below 75% attendance in my courses?',
    'Show the marks summary for Internal Test 1 in my courses',
    'Which of my students have missing submissions?',
    'Are there leave requests waiting for my decision?',
    'Post an announcement to my DBMS class about the lab test on Friday',
  ],
  admin: [
    'Failure rate by department this term',
    'How many students are enrolled in each department?',
    'Which departments have the lowest fee collection?',
    'What is the rule for condonation of attendance shortfall?',
    'Publish a notice to all students about the Diwali vacation dates',
  ],
}

export function Rail({
  role,
  conversations,
  activeId,
  onOpen,
  onNew,
  onAsk,
  open,
  onClose,
}: {
  role: Role
  conversations: ConversationOut[]
  activeId: number | null
  onOpen: (id: number) => void
  onNew: () => void
  onAsk: (text: string) => void
  open: boolean
  onClose: () => void
}) {
  return (
    <aside id="rail" className={`rail ${open ? "rail-open" : ""}`} aria-label="Conversations and suggestions">
      <div className="rail-head">
        <button type="button" className="primary rail-new" onClick={onNew}>
          New conversation
        </button>
        <button type="button" className="linklike rail-close" onClick={onClose} aria-label="Close panel">
          Close
        </button>
      </div>

      <section className="rail-section">
        <h2>Try asking</h2>
        <ul className="suggestions">
          {SUGGESTIONS[role].map((q) => (
            <li key={q}>
              <button type="button" onClick={() => onAsk(q)}>
                {q}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="rail-section rail-history">
        <h2>Earlier</h2>
        {conversations.length === 0 ? (
          <p className="muted small">Your conversations will appear here.</p>
        ) : (
          <ul className="history">
            {conversations.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className={c.id === activeId ? 'active' : ''}
                  onClick={() => onOpen(c.id)}
                  aria-current={c.id === activeId ? 'true' : undefined}
                >
                  <span className="history-title">{c.title || 'Untitled'}</span>
                  <span className="history-date">{shortDate(c.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  )
}

function shortDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}
