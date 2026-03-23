import { get, put } from '@shared/api/httpClient'

export function getSettings() {
  return get('/settings')
}

export function updateSettings(data) {
  return put('/settings', data)
}
