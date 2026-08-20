export function flattenTraceTree(nodes) {
  const result = []
  for (const node of nodes) {
    const { children = [], ...span } = node
    result.push(span, ...flattenTraceTree(children))
  }
  return result
}

export function mergeTraceSpans(persisted, current) {
  const byId = new Map(persisted.map(span => [span.id, span]))
  for (const span of current) {
    const saved = byId.get(span.id)
    // Keep terminal live updates when the periodic DB flush is slightly behind.
    if (!saved || (saved.status === 'running' && span.status !== 'running')) {
      byId.set(span.id, span)
    }
  }
  return [...byId.values()].sort((a, b) => (
    (a.started_time || '').localeCompare(b.started_time || '')
  ))
}

export function listRunIds(spans) {
  // Order by each run's earliest span so Switch run stays chronological
  // even after loadTraceForRun appends the selected run's spans last.
  const firstStarted = new Map()
  for (const span of spans || []) {
    const runId = span?.run_id
    if (!runId) continue
    const started = span.started_time || ''
    const previous = firstStarted.get(runId)
    if (previous == null || started < previous) firstStarted.set(runId, started)
  }
  return [...firstStarted.keys()].sort((a, b) => {
    const timeA = firstStarted.get(a) || ''
    const timeB = firstStarted.get(b) || ''
    if (timeA !== timeB) return timeA < timeB ? -1 : 1
    return a < b ? -1 : a > b ? 1 : 0
  })
}

export function resolveSelectedRunId(selectedRunId, spans) {
  if (selectedRunId) return selectedRunId
  const runIds = listRunIds(spans)
  return runIds.length ? runIds[runIds.length - 1] : null
}

export function traceRunVersion(spans, runId) {
  if (!runId) return 'none'

  let count = 0
  let maxSequence = 0
  let revisionTotal = 0
  for (const span of spans) {
    if (span.run_id !== runId) continue
    count += 1
    maxSequence = Math.max(maxSequence, Number(span.sequence) || 0)
    revisionTotal += Number(span.revision) || 0
  }
  return `${runId}:${count}:${maxSequence}:${revisionTotal}`
}
