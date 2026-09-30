import type { Scores, Timings, Trace as TraceData } from './types'

// The three-call turn, laid bare for the viva: which path the router took,
// which tools ran (and which were refused), what it cost in tokens and where
// the time went. Hidden unless the Trace toggle in the top bar is on.
export function Trace({ trace, queuedSeconds }: { trace: TraceData; queuedSeconds?: number }) {
  const total = trace.usage.tokens_in + trace.usage.tokens_out
  const t = trace.timings
  return (
    <details className="trace">
      <summary>
        Trace — {describePath(trace.path)}
        {trace.tool_runs.length ? ` · ${trace.tool_runs.length} tool ${trace.tool_runs.length === 1 ? 'call' : 'calls'}` : ' · no tools'}
        {` · ${total} tokens`}
        {t ? ` · ${fmtMs(t.total_ms)}` : ''}
      </summary>
      <dl className="trace-grid">
        <dt>Path</dt>
        <dd>
          <code>{trace.path}</code> — {describePath(trace.path)}
        </dd>
        {trace.intent && (
          <>
            <dt>Intent</dt>
            <dd>{trace.intent}</dd>
          </>
        )}
        <dt>Tools</dt>
        <dd>
          {trace.tool_runs.length === 0 ? (
            <span className="muted">none run</span>
          ) : (
            <ul className="trace-tools">
              {trace.tool_runs.map((r, i) => (
                <li key={i} className={r.error === 'denied' ? 'denied' : r.ok ? 'ok' : 'failed'}>
                  <code>{r.name}</code>
                  {Object.keys(r.args ?? {}).length > 0 && <code className="trace-args">{JSON.stringify(r.args)}</code>}
                  <span className="trace-status">{r.error === 'denied' ? 'refused by RBAC' : r.ok ? 'ok' : `failed: ${r.error}`}</span>
                  {r.latency_ms != null && <span className="trace-ms">{fmtMs(r.latency_ms)}</span>}
                </li>
              ))}
            </ul>
          )}
        </dd>
        {t && (
          <>
            <dt>Latency</dt>
            <dd>
              <Latency timings={t} />
            </dd>
          </>
        )}
        {trace.scores && (
          <>
            <dt>Quality</dt>
            <dd>
              <Quality scores={trace.scores} />
            </dd>
          </>
        )}
        <dt>Tokens</dt>
        <dd>
          {trace.usage.tokens_in} in · {trace.usage.tokens_out} out
          {queuedSeconds ? ` · waited ${queuedSeconds}s for the rate limit` : ''}
        </dd>
      </dl>
    </details>
  )
}

interface Row {
  label: string
  detail: string
  value: number | null  // 0..1, or null when the check did not apply
  hint: string
  warn?: boolean
}

function qualityRows(s: Scores): Row[] {
  return [
    {
      label: 'Retrieval',
      detail: s.passages
        ? `${s.passages} passage${s.passages === 1 ? '' : 's'} · ${s.both_branches} on both branches, ${s.dense_only} dense-only, ${s.sparse_only} keyword-only` +
          (s.top_score != null ? ` · best ${s.top_score}` : '')
        : 'no passages retrieved',
      value: null,
      hint: 'Hybrid retrieval: a passage found by both the vector and the keyword branch is the strongest match.',
    },
    {
      label: 'Context precision',
      detail: s.passages ? `${s.cited} of ${s.passages} retrieved passages cited` : 'n/a',
      value: s.context_precision,
      hint: 'Share of the retrieved passages the answer actually cited. Low is normal when only one clause answers the question; it flags retrieval that pulls in noise.',
    },
    {
      label: 'Citation coverage',
      detail: s.claims ? `${s.claims_cited} of ${s.claims} sentences that restate a passage carry a citation` : 'n/a',
      value: s.citation_coverage,
      hint: 'Of the answer sentences that closely follow a retrieved passage, the share that carry a [n] citation.',
    },
    {
      label: 'Numeric grounding',
      detail: s.numbers
        ? `${s.numbers_grounded} of ${s.numbers} figures found in the sources` +
          (s.ungrounded_numbers.length ? ` · not found: ${s.ungrounded_numbers.join(', ')}` : '')
        : 'n/a',
      value: s.numeric_grounding,
      warn: s.ungrounded_numbers.length > 0,
      hint: 'Share of the answer’s figures that appear in the tool results, the passages or your question, or are the difference of two of them (75 − 68). Whole numbers up to 10 are not checked.',
    },
    {
      label: 'Tool success',
      detail: s.tools_run ? `${s.tools_ok} of ${s.tools_run} tool calls succeeded` : 'no tools run',
      value: s.tool_success,
      hint: 'Tool calls that ran, as opposed to being refused by RBAC or failing.',
    },
  ]
}

function Quality({ scores }: { scores: Scores }) {
  return (
    <ul className="trace-quality">
      {qualityRows(scores).map((r) => (
        <li key={r.label} title={r.hint} className={r.warn ? 'warn' : undefined}>
          <span className="trace-q-label">{r.label}</span>
          {r.value != null ? (
            <span className="trace-meter" aria-hidden="true">
              <span style={{ width: `${Math.round(r.value * 100)}%` }} />
            </span>
          ) : (
            <span className="trace-meter empty" aria-hidden="true" />
          )}
          <span className="trace-q-value">{r.value != null ? `${Math.round(r.value * 100)}%` : '–'}</span>
          <span className="trace-q-detail">{r.detail}</span>
        </li>
      ))}
    </ul>
  )
}

// Stage order is the order a turn runs them; a stage that did not run (null) is left out.
function stages(t: Timings): { key: string; label: string; ms: number }[] {
  const all: [string, string, number | null][] = [
    ['route', 'route', t.route_ms],
    ['plan', 'plan', t.plan_ms],
    ['tools', 'tools', t.tools_ms],
    ['retrieve', 'retrieve', t.retrieve_ms],
    ['write', 'write', t.synthesize_ms],
  ]
  return all.filter((s): s is [string, string, number] => s[2] != null).map(([key, label, ms]) => ({ key, label, ms }))
}

function Latency({ timings: t }: { timings: Timings }) {
  const parts = stages(t)
  const sum = parts.reduce((n, p) => n + p.ms, 0) || 1
  return (
    <div className="trace-latency">
      <div>
        <strong>{fmtMs(t.total_ms)}</strong> total
        {t.first_token_ms != null && <> · first word after {fmtMs(t.first_token_ms)}</>}
      </div>
      <div className="trace-bar" role="img" aria-label={parts.map((p) => `${p.label} ${fmtMs(p.ms)}`).join(', ')}>
        {parts.map((p) => (
          <span key={p.key} className={`trace-seg seg-${p.key}`} style={{ flexGrow: Math.max(p.ms, 1) / sum }} />
        ))}
      </div>
      <ul className="trace-stages">
        {parts.map((p) => (
          <li key={p.key}>
            <span className={`trace-swatch seg-${p.key}`} aria-hidden="true" />
            {p.label} <span className="trace-ms">{fmtMs(p.ms)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function fmtMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

function describePath(path: string): string {
  switch (path) {
    case 'smalltalk':
      return 'one call, no tools'
    case 'fast':
      return 'router → tool → answer (planner skipped)'
    case 'full':
      return 'router → planner → tools → answer'
    case 'confirm':
      return 'stopped at the confirmation card'
    case 'stored':
      return 'from the saved transcript'
    default:
      return path
  }
}
