import { get, del } from '@shared/api/httpClient'

export function listClaudeSessions(directory = null, limit = null) {
  const params = new URLSearchParams()
  if (directory) params.set('directory', directory)
  if (limit) params.set('limit', String(limit))
  const qs = params.toString()
  return get(`/claude-sessions${qs ? '?' + qs : ''}`)
}

export function deleteClaudeSession(sessionId, directory = null) {
  const params = new URLSearchParams()
  if (directory) params.set('directory', directory)
  const qs = params.toString()
  return del(`/claude-sessions/${sessionId}${qs ? '?' + qs : ''}`)
}
