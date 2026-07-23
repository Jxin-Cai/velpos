import { get } from '@shared/api/httpClient'

// Large sessions can temporarily block the browser main thread while their
// message DOM is rendered. Give trace reads enough headroom so the shared
// request timer does not abort an otherwise healthy backend response.
const TRACE_REQUEST_TIMEOUT_MS = 120000
const TRACE_REQUEST_OPTIONS = Object.freeze({ timeoutMs: TRACE_REQUEST_TIMEOUT_MS })

export async function fetchTraceTree(sessionId, runId) {
  return get(`/sessions/${sessionId}/runs/${runId}/trace-tree`, TRACE_REQUEST_OPTIONS)
}

export async function fetchTraceRuns(sessionId) {
  return get(`/sessions/${sessionId}/traces`, TRACE_REQUEST_OPTIONS)
}

export async function fetchSpanDetail(sessionId, spanId) {
  return get(`/sessions/${sessionId}/traces/${spanId}`, TRACE_REQUEST_OPTIONS)
}

export async function fetchExecutionTree(sessionId, runId, agentSpanId = null) {
  const params = agentSpanId ? `?agent_span_id=${encodeURIComponent(agentSpanId)}` : ''
  return get(`/sessions/${sessionId}/runs/${runId}/execution-tree${params}`, TRACE_REQUEST_OPTIONS)
}

export async function fetchLoopDetail(sessionId, runId, loopId, agentSpanId = null, cursor = 0, limit = 100) {
  const searchParams = new URLSearchParams()
  if (agentSpanId) searchParams.set('agent_span_id', agentSpanId)
  if (cursor > 0) searchParams.set('cursor', String(cursor))
  if (limit !== 100) searchParams.set('limit', String(limit))
  const qs = searchParams.toString()
  return get(
    `/sessions/${sessionId}/runs/${runId}/execution-loops/${loopId}${qs ? `?${qs}` : ''}`,
    TRACE_REQUEST_OPTIONS,
  )
}
