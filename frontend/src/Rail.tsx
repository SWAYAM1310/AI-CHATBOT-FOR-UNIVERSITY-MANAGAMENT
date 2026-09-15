import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
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

const WIDTH_KEY = 'uniassist.railWidth'
const MIN_WIDTH = 220
const MAX_WIDTH = 480
const DEFAULT_WIDTH = 272

function readStoredWidth(): number {
  const raw = Number(localStorage.getItem(WIDTH_KEY))
  return Number.isFinite(raw) && raw >= MIN_WIDTH && raw <= MAX_WIDTH ? raw : DEFAULT_WIDTH
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
  const [menuId, setMenuId] = useState<number | null>(null)
  const [width, setWidth] = useState<number>(readStoredWidth)
  const [resizing, setResizing] = useState(false)

  // Drag-to-resize: track the pointer while dragging, persist the final width.
  useEffect(() => {
    if (!resizing) return
    function onMove(e: MouseEvent) {
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, e.clientX))
      setWidth(next)
    }
    function onUp() {
      setResizing(false)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
  }, [resizing])

  useEffect(() => {
    if (!resizing) localStorage.setItem(WIDTH_KEY, String(width))
  }, [resizing, width])

  // A ⋯ menu is open: close it on an outside click or Escape, whichever comes first.
  useEffect(() => {
    if (menuId === null) return
    function onDocClick(e: MouseEvent) {
      const target = e.target as HTMLElement
      if (!target.closest?.('.history-menu-wrap')) setMenuId(null)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuId(null)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuId])

  function startRename(c: ConversationOut) {
    setMenuId(null)
    setEditingId(c.id)
    setDraft(c.title || '')
  }

  function commitRename(id: number) {
    const title = draft.trim()
    setEditingId(null)
    if (title) onRename(id, title)
  }

  function askDelete(c: ConversationOut) {
    setMenuId(null)
    if (confirm('Delete this conversation? This cannot be undone.')) onDelete(c.id)
  }

  return (
    <aside
      id="rail"
      className={`rail ${open ? '' : 'rail-closed'} ${resizing ? 'rail-resizing' : ''}`}
      style={open ? ({ '--rail-width': `${width}px` } as CSSProperties) : undefined}
      aria-label="Conversations"
      aria-hidden={!open}
    >
      <div className="rail-head">
        <div className="rail-brand">
          <img src="/Pandit_Deendayal_Energy_University_logo.png" alt="" className="rail-logo" />
          <div>
            <p className="wordmark">UniAssist</p>
            <p className="rail-caption">PDEU</p>
          </div>
        </div>
        <div className="rail-head-actions">
          <button type="button" className="icon-btn" onClick={onNew} aria-label="New conversation" title="New conversation">
            <PlusIcon />
          </button>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Collapse sidebar" title="Collapse sidebar">
            <PanelIcon />
          </button>
        </div>
      </div>

      <section className="rail-section rail-history">
        <h2>Recent</h2>
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
                  <>
                    <button
                      type="button"
                      className={`history-btn ${c.id === activeId ? 'active' : ''}`}
                      onClick={() => onOpen(c.id)}
                      aria-current={c.id === activeId ? 'true' : undefined}
                    >
                      <span className="history-title">{c.title || 'Untitled'}</span>
                    </button>
                    <div className="history-menu-wrap">
                      <button
                        type="button"
                        className="history-more"
                        aria-haspopup="menu"
                        aria-expanded={menuId === c.id}
                        aria-label="Conversation options"
                        onClick={() => setMenuId((id) => (id === c.id ? null : c.id))}
                      >
                        &#8942;
                      </button>
                      {menuId === c.id && (
                        <div className="history-menu" role="menu">
                          <button type="button" role="menuitem" onClick={() => startRename(c)}>
                            Rename
                          </button>
                          <button type="button" role="menuitem" className="danger" onClick={() => askDelete(c)}>
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      {open && (
        <div
          className="rail-resize-handle"
          onMouseDown={(e) => {
            e.preventDefault()
            setResizing(true)
          }}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize sidebar"
        />
      )}
    </aside>
  )
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function PanelIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <line x1="9.5" y1="4" x2="9.5" y2="20" />
    </svg>
  )
}
