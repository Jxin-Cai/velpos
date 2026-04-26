import { get, put } from '@shared/api/httpClient'

export function getSessionUsage(sessionId) {
  return get(`/usage/sessions/${encodeURIComponent(sessionId)}`)
}

export function getProjectUsage(projectId, todayOnly = false) {
  return get(`/usage/projects/${encodeURIComponent(projectId)}?today_only=${todayOnly ? 'true' : 'false'}`)
}

export function getProjectBudget(projectId) {
  return get(`/budgets/projects/${encodeURIComponent(projectId)}`)
}

export function saveProjectBudget(projectId, payload) {
  return put(`/budgets/projects/${encodeURIComponent(projectId)}`, payload)
}
