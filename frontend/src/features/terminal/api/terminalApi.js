import { get, post } from '@shared/api/httpClient'

export function openPath(path, app = null) {
  return post('/terminal/open-path', { path, app })
}

export function listApplications() {
  return get('/terminal/applications')
}
