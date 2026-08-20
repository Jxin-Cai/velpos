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

export async function fetchExecutionEvents(sessionId, runId, afterSequence = 0, limit = 500) {
  const params = new URLSearchParams({
    after_sequence: String(Math.max(afterSequence, 0)),
    limit: String(limit),
  })
  return get(
    `/sessions/${sessionId}/runs/${runId}/execution-events?${params.toString()}`,
    TRACE_REQUEST_OPTIONS,
  )
}

// The telemetry summary clips oversized audit fields so that a page of raw API
// bodies does not run into megabytes. Use this to pull one event verbatim.
export async function fetchExecutionEvent(sessionId, eventId) {
  return get(
    `/sessions/${sessionId}/execution-events/${encodeURIComponent(eventId)}`,
    TRACE_REQUEST_OPTIONS,
  )
}

// Request summaries carry only counts and a system prompt preview so the list
// stays small; the full envelope is fetched per request on demand.
export async function fetchLlmRequests(sessionId, runId) {
  return get(`/sessions/${sessionId}/runs/${runId}/llm-requests`, TRACE_REQUEST_OPTIONS)
}

export async function fetchLlmRequestDetail(sessionId, eventId) {
  return get(
    `/sessions/${sessionId}/llm-requests/${encodeURIComponent(eventId)}`,
    TRACE_REQUEST_OPTIONS,
  )
}

export async function fetchTelemetrySummary(sessionId, runId) {
  return get(
    `/sessions/${sessionId}/runs/${runId}/telemetry-summary`,
    TRACE_REQUEST_OPTIONS,
  )
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
