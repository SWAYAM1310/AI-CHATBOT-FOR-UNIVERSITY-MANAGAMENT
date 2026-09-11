import { DataCard } from './Cards'
import type { ConfirmCard, Turn } from './types'

// Assistant text arrives as plain prose with [n] markers. Paragraphs are
// split on blank lines; a line beginning with "- " or "|" is kept verbatim
// (short tables come through as Markdown pipes, which read fine as text).
export function Message({
  turn,
  onConfirm,
  onCancel,
}: {
  turn: Turn
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
        <p className="thinking">
          <span>Working on it</span>
          <span className="dot" aria-hidden="true" />
          <span className="dot" aria-hidden="true" />
          <span className="dot" aria-hidden="true" />
        </p>
      </article>
    )
  }
  if (turn.error) {
    return (
      <article className="msg msg-assistant">
        <p className="msg-error" role="alert">{turn.error}</p>
      </article>
    )
  }
  const confirmCard = turn.cards.find((c): c is ConfirmCard => c.type === 'confirm')
  return (
    <article className="msg msg-assistant">
      {turn.queuedSeconds ? (
        <p className="muted small">Queued {turn.queuedSeconds}s behind the rate limit.</p>
      ) : null}
      {turn.text && <Prose text={turn.text} />}
      {confirmCard && (
        <Confirm card={confirmCard} outcome={turn.outcome} onConfirm={() => onConfirm(confirmCard)} onCancel={onCancel} />
      )}
      {turn.cards.filter((c) => c.type !== 'confirm').map((c, i) => (
        <DataCard key={i} card={c} />
      ))}
      {turn.citations.length > 0 && (
        <ol className="footnotes" aria-label="Sources">
          {turn.citations.map((c) => (
            <li key={c.n} id={`${turn.id}-fn${c.n}`} value={c.n}>
              <span className="fn-doc">{c.document ?? 'Document'}</span>
              {c.section && <span className="fn-section"> — {c.section}</span>}
              {c.page != null && <span className="fn-page">, p.{c.page}</span>}
              {c.snippet && <details><summary>passage</summary><p className="fn-snippet">{c.snippet}</p></details>}
            </li>
          ))}
        </ol>
      )}
    </article>
  )
}

const MARK = /\[(\d{1,2})\]/g

function Prose({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/)
  return (
    <div className="prose">
      {blocks.map((block, i) => {
        const lines = block.split('\n')
        const isList = lines.every((l) => /^\s*([-*•]|\d+[.)])\s/.test(l))
        const isTable = lines.length > 1 && lines.every((l) => l.trim().startsWith('|'))
        if (isTable) return <Table key={i} lines={lines} />
        if (isList)
          return (
            <ul key={i}>
              {lines.map((l, j) => (
                <li key={j}>{withMarks(l.replace(/^\s*([-*•]|\d+[.)])\s/, ''))}</li>
              ))}
            </ul>
          )
        return <p key={i}>{withMarks(block)}</p>
      })}
    </div>
  )
}

function withMarks(text: string) {
  const out: (string | React.JSX.Element)[] = []
  let last = 0
  for (const m of text.matchAll(MARK)) {
    out.push(text.slice(last, m.index))
    out.push(
      <sup key={m.index} className="fn-ref">
        {m[1]}
      </sup>,
    )
    last = (m.index ?? 0) + m[0].length
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
