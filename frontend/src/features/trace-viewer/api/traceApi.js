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
