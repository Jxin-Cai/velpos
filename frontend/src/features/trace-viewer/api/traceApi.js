import { get } from '@shared/api/httpClient'

export async function fetchTraceTree(sessionId, runId) {
  return get(`/sessions/${sessionId}/runs/${runId}/trace-tree`)
}

export async function fetchTraceRuns(sessionId) {
  return get(`/sessions/${sessionId}/traces`)
}

export async function fetchSpanDetail(sessionId, spanId) {
  return get(`/sessions/${sessionId}/traces/${spanId}`)
}

export async function fetchExecutionTree(sessionId, runId, agentSpanId = null) {
  const params = agentSpanId ? `?agent_span_id=${encodeURIComponent(agentSpanId)}` : ''
  return get(`/sessions/${sessionId}/runs/${runId}/execution-tree${params}`)
}

export async function fetchLoopDetail(sessionId, runId, loopId, agentSpanId = null, cursor = 0, limit = 100) {
  const searchParams = new URLSearchParams()
  if (agentSpanId) searchParams.set('agent_span_id', agentSpanId)
  if (cursor > 0) searchParams.set('cursor', String(cursor))
  if (limit !== 100) searchParams.set('limit', String(limit))
  const qs = searchParams.toString()
  return get(`/sessions/${sessionId}/runs/${runId}/execution-loops/${loopId}${qs ? `?${qs}` : ''}`)
}
