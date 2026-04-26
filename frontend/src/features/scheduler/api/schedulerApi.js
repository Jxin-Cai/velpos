import { get, post, patch, del } from '@shared/api/httpClient'

export function listSchedules(projectId = '') {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return get(`/schedules${query}`)
}

export function createSchedule(payload) {
  return post('/schedules', payload)
}

export function updateSchedule(taskId, payload) {
  return patch(`/schedules/${encodeURIComponent(taskId)}`, payload)
}

export function deleteSchedule(taskId) {
  return del(`/schedules/${encodeURIComponent(taskId)}`)
}

export function runScheduleNow(taskId) {
  return post(`/schedules/${encodeURIComponent(taskId)}/run-now`, {})
}
