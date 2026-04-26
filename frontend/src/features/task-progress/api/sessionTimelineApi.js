import { get } from '@shared/api/httpClient'

export function fetchSessionRunSteps(sessionId, runId = 'latest') {
  return get(`/sessions/${encodeURIComponent(sessionId)}/runs/${encodeURIComponent(runId)}/steps`)
}
