import { useState } from 'react'
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
  conversations,
  activeId,
  onOpen,
  onNew,
  onRename,
  onDelete,
  open,
  onClose,
}: {
  conversations: ConversationOut[]
  activeId: number | null
  onOpen: (id: number) => void
  onNew: () => void
  onRename: (id: number, title: string) => void
  onDelete: (id: number) => void
  open: boolean
  onClose: () => void
}) {
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draft, setDraft] = useState('')

  function startRename(c: ConversationOut) {
    setEditingId(c.id)
    setDraft(c.title || '')
  }

  function commitRename(id: number) {
    const title = draft.trim()
    setEditingId(null)
    if (title) onRename(id, title)
  }

  return (
    <aside id="rail" className={`rail ${open ? "rail-open" : ""}`} aria-label="Conversations">
      <div className="rail-head">
        <button type="button" className="primary rail-new" onClick={onNew}>
          New conversation
        </button>
        <button type="button" className="linklike rail-close" onClick={onClose} aria-label="Close panel">
          Close
        </button>
      </div>

      <section className="rail-section rail-history">
        <h2>Earlier</h2>
        {conversations.length === 0 ? (
          <p className="muted small">Your conversations will appear here.</p>
        ) : (
          <ul className="history">
            {conversations.map((c) => (
              <li key={c.id} className="history-item">
                {editingId === c.id ? (
                  <input
                    className="history-rename-input"
                    value={draft}
                    autoFocus
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') commitRename(c.id)
                      if (e.key === 'Escape') setEditingId(null)
                    }}
                    onBlur={() => commitRename(c.id)}
                    aria-label="Conversation title"
                  />
                ) : (
                  <button
                    type="button"
                    className={c.id === activeId ? 'active' : ''}
                    onClick={() => onOpen(c.id)}
                    aria-current={c.id === activeId ? 'true' : undefined}
                  >
                    <span className="history-title">{c.title || 'Untitled'}</span>
                    <span className="history-date">{shortDate(c.created_at)}</span>
                  </button>
                )}
                <span className="history-actions">
                  <button
                    type="button"
                    className="linklike history-action"
                    onClick={() => startRename(c)}
                    aria-label="Rename conversation"
                  >
                    Rename
                  </button>
                  <button
                    type="button"
                    className="linklike history-action"
                    onClick={() => {
                      if (confirm('Delete this conversation? This cannot be undone.')) onDelete(c.id)
                    }}
                    aria-label="Delete conversation"
                  >
                    Delete
                  </button>
                </span>
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
