import type { Trace as TraceData } from './types'

// The three-call turn, laid bare for the viva: which path the router took,
// which tools ran (and which were refused), and what it cost in tokens.
// Hidden unless the Trace toggle in the top bar is on.
export function Trace({ trace, queuedSeconds }: { trace: TraceData; queuedSeconds?: number }) {
  const total = trace.usage.tokens_in + trace.usage.tokens_out
  return (
    <details className="trace">
      <summary>
        Trace — {describePath(trace.path)}
        {trace.tool_runs.length ? ` · ${trace.tool_runs.length} tool ${trace.tool_runs.length === 1 ? 'call' : 'calls'}` : ' · no tools'}
        {` · ${total} tokens`}
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
                </li>
              ))}
            </ul>
          )}
        </dd>
        <dt>Tokens</dt>
        <dd>
          {trace.usage.tokens_in} in · {trace.usage.tokens_out} out
          {queuedSeconds ? ` · waited ${queuedSeconds}s for the rate limit` : ''}
        </dd>
      </dl>
    </details>
  )
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
