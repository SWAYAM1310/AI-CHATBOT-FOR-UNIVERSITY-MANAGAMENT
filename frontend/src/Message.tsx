import { Fragment } from 'react'
import { DataCard } from './Cards'
import { Trace } from './Trace'
import type { ConfirmCard, Turn } from './types'

// Assistant text arrives as plain prose with [n] markers. Paragraphs are
// split on blank lines; a line beginning with "- " or "|" is kept verbatim
// (short tables come through as Markdown pipes, which read fine as text).
export function Message({
  turn,
  showTrace,
  onConfirm,
  onCancel,
}: {
  turn: Turn
  showTrace: boolean
  onConfirm: (card: ConfirmCard) => void
  onCancel: () => void
}) {
  if (turn.role === 'user') {
    return (
      <article className="msg msg-user">
        <p>{turn.text}</p>
      </article>
    )
  }
  if (turn.pending) {
    return (
      <article className="msg msg-assistant pending" aria-busy="true">
        <div className="msg-card">
          <p className="thinking">
            <span>{turn.queuedSeconds ? `Queued — the assistant is busy, retrying in ${turn.queuedSeconds}s` : stageLabel(turn.stage)}</span>
            <span className="dot" aria-hidden="true" />
            <span className="dot" aria-hidden="true" />
            <span className="dot" aria-hidden="true" />
          </p>
        </div>
      </article>
    )
  }
  if (turn.error) {
    return (
      <article className="msg msg-assistant">
        <div className="msg-card">
          <p className="msg-error" role="alert">{turn.error}</p>
        </div>
      </article>
    )
  }
  const confirmCard = turn.cards.find((c): c is ConfirmCard => c.type === 'confirm')
  const tools = turn.trace?.tool_runs ?? turn.liveTools ?? []
  return (
    <article className="msg msg-assistant">
      <div className="msg-card">
        {tools.length > 0 && (
          <div className="tool-pills">
            {tools.map((t, i) => (
              <span key={i} className={`tool-pill ${t.ok ? 'ok' : 'bad'}`}>
                <span className="tool-dot" aria-hidden="true" />
                {t.name}
                {Object.keys(t.args ?? {}).length > 0 && <span className="tool-args"> {JSON.stringify(t.args)}</span>}
              </span>
            ))}
          </div>
        )}
        {turn.queuedSeconds ? (
          <p className="muted small">Queued {turn.queuedSeconds}s behind the rate limit.</p>
        ) : null}
        {turn.text && <Prose text={turn.text} />}
        {turn.streaming && <span className="caret" aria-hidden="true" />}
        {confirmCard && (
          <Confirm card={confirmCard} outcome={turn.outcome} onConfirm={() => onConfirm(confirmCard)} onCancel={onCancel} />
        )}
        {turn.cards.filter((c) => c.type !== 'confirm').map((c, i) => (
          <DataCard key={i} card={c} />
        ))}
        {turn.citations.length > 0 && (
          <div className="cited">
            <p className="cited-label">Cited</p>
            <ol className="cited-list" aria-label="Sources">
              {turn.citations.map((c) => (
                <li key={c.n} id={`${turn.id}-fn${c.n}`} value={c.n}>
                  <span className="cited-badge" aria-hidden="true">{c.n}</span>
                  <span className="cited-body">
                    <span className="fn-doc">{c.document ?? 'Document'}</span>
                    {c.section && <span className="fn-section"> · {c.section}</span>}
                    {c.page != null && <span className="fn-page">, p.{c.page}</span>}
                    {c.snippet && <details><summary>passage</summary><p className="fn-snippet">{c.snippet}</p></details>}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
      {showTrace && turn.trace && <Trace trace={turn.trace} queuedSeconds={turn.queuedSeconds} />}
    </article>
  )
}

function stageLabel(stage?: string): string {
  switch (stage) {
    case 'routing':
      return 'Reading your question'
    case 'planning':
      return 'Deciding what to check'
    case 'running_tools':
      return 'Checking your records'
    case 'retrieving':
      return 'Reading the regulations'
    case 'writing':
      return 'Writing'
    default:
      return 'Working on it'
  }
}

// Assistant text is Markdown-ish prose plus the `[n]` citation markers the
// backend adds. Block structure (paragraphs/lists/tables) is split first;
// `withMarks` then handles everything inline in one pass. An unclosed marker
// (a `**bold` that hasn't seen its closing `**` yet, mid-stream) simply fails
// to match and shows as plain text until the rest of it arrives.
function Prose({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/)
  return (
    <div className="prose">
      {blocks.map((block, i) => {
        const trimmed = block.trim()
        if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) return <hr key={i} />

        const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed)
        if (heading) {
          const Tag = `h${heading[1].length + 3}` as 'h4' | 'h5' | 'h6' // stays visually modest inside a chat bubble
          return <Tag key={i} className="md-heading">{withMarks(heading[2])}</Tag>
        }

        const lines = block.split('\n')
        const isTable = lines.length > 1 && lines.every((l) => l.trim().startsWith('|'))
        if (isTable) return <Table key={i} lines={lines} />

        const isOrdered = lines.every((l) => /^\s*\d+[.)]\s/.test(l))
        if (isOrdered)
          return (
            <ol key={i}>
              {lines.map((l, j) => (
                <li key={j}>{withMarks(l.replace(/^\s*\d+[.)]\s/, ''))}</li>
              ))}
            </ol>
          )

        const isBullet = lines.every((l) => /^\s*[-*•]\s/.test(l))
        if (isBullet)
          return (
            <ul key={i}>
              {lines.map((l, j) => (
                <li key={j}>{withMarks(l.replace(/^\s*[-*•]\s/, ''))}</li>
              ))}
            </ul>
          )

        return (
          <p key={i}>
            {lines.map((l, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {withMarks(l)}
              </Fragment>
            ))}
          </p>
        )
      })}
    </div>
  )
}

// `[n]` citation, **bold**/__bold__, `code`, *italic*/_italic_, [text](https://…) —
// bold checked ahead of italic so `**x**` isn't read as `*` + literal `*x*` + `*`.
const INLINE =
  /\[(\d{1,2})\]|\*\*([^*]+)\*\*|__([^_]+)__|`([^`]+)`|\*([^*]+)\*|_([^_]+)_|\[([^[\]]+)\]\((https?:\/\/[^\s)]+)\)/g

function withMarks(text: string) {
  const out: (string | React.JSX.Element)[] = []
  let last = 0
  for (const m of text.matchAll(INLINE)) {
    if (m.index! > last) out.push(text.slice(last, m.index))
    const key = m.index
    if (m[1] !== undefined) out.push(<sup key={key} className="fn-ref">{m[1]}</sup>)
    else if (m[2] !== undefined) out.push(<strong key={key}>{m[2]}</strong>)
    else if (m[3] !== undefined) out.push(<strong key={key}>{m[3]}</strong>)
    else if (m[4] !== undefined) out.push(<code key={key}>{m[4]}</code>)
    else if (m[5] !== undefined) out.push(<em key={key}>{m[5]}</em>)
    else if (m[6] !== undefined) out.push(<em key={key}>{m[6]}</em>)
    else if (m[7] !== undefined && m[8] !== undefined)
      out.push(
        <a key={key} href={m[8]} target="_blank" rel="noopener noreferrer">
          {m[7]}
        </a>,
      )
    last = m.index! + m[0].length
  }
  out.push(text.slice(last))
  return out
}

function Table({ lines }: { lines: string[] }) {
  const rows = lines
    .map((l) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim()))
    .filter((cells) => !cells.every((c) => /^:?-+:?$/.test(c)))
  const [head, ...body] = rows
  return (
    <table>
      <thead>
        <tr>{head.map((c, i) => <th key={i}>{c}</th>)}</tr>
      </thead>
      <tbody>
        {body.map((r, i) => (
          <tr key={i}>{r.map((c, j) => <td key={j}>{withMarks(c)}</td>)}</tr>
        ))}
      </tbody>
    </table>
  )
}

function Confirm({
  card,
  outcome,
  onConfirm,
  onCancel,
}: {
  card: ConfirmCard
  outcome?: { text: string; ok: boolean }
  onConfirm: () => void
  onCancel: () => void
}) {
  const { summary, ...rest } = card.preview
  const fields = Object.entries(rest).filter(([, v]) => v !== null && v !== undefined && v !== '')
  return (
    <section className={`confirm ${outcome ? (outcome.ok ? 'settled' : 'failed') : 'open'}`} aria-label="Confirm action">
      <p className="confirm-title">{summary ?? `Confirm ${card.tool.replaceAll('_', ' ')}`}</p>
      {fields.length > 0 && (
        <dl>
          {fields.map(([k, v]) => (
            <div key={k}>
              <dt>{k.replaceAll('_', ' ')}</dt>
              <dd>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {outcome ? (
        <p className={outcome.ok ? 'confirm-outcome' : 'msg-error'}>{outcome.text}</p>
      ) : (
        <div className="confirm-actions">
          <button type="button" className="primary" onClick={onConfirm}>
            Confirm
          </button>
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
          <span className="muted small">Nothing is written until you confirm.</span>
        </div>
      )}
    </section>
  )
}
