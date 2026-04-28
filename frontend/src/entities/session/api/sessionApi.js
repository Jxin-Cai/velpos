import { get, post, del, patch } from '@shared/api/httpClient'

export function createSession({ name = '', projectId = '', projectDir = '' } = {}) {
  return post('/sessions', { name, project_id: projectId, project_dir: projectDir })
}

export function listSessions() {
  return get('/sessions')
}

export function getSession(sessionId) {
  return get(`/sessions/${sessionId}`)
}

export function deleteSession(sessionId) {
  return del(`/sessions/${sessionId}`)
}

export function batchDeleteSessions(sessionIds) {
  return post('/sessions/batch-delete', { session_ids: sessionIds })
}

export function clearContext(sessionId) {
  return post(`/sessions/${sessionId}/clear-context`)
}

export function renameSession(sessionId, name) {
  return patch(`/sessions/${sessionId}/name`, { name })
}

export function importClaudeSession(claudeSessionId, cwd, name = '') {
  return post('/sessions/import-claude', {
    claude_session_id: claudeSessionId,
    cwd,
    name,
  })
}

export function listModels() {
  return get('/sessions/meta/models')
}

export function listSessionArtifacts(sessionId) {
  return get(`/sessions/${sessionId}/artifacts`)
}

export function compactSession(sessionId) {
  return post(`/sessions/${sessionId}/compact`)
}

export function createSessionBranch(sessionId, messageIndex, name = '', branchCount = 1, worktreeEnabled = false) {
  return post(`/sessions/${sessionId}/branches`, {
    message_index: messageIndex,
    name,
    branch_count: branchCount,
    worktree_enabled: worktreeEnabled,
  })
}

export function listSessionBranches(sessionId) {
  return get(`/sessions/${sessionId}/branches`)
}

export function compareSessions(sessionId, rightSessionId) {
  return get(`/sessions/${sessionId}/compare?right=${encodeURIComponent(rightSessionId)}`)
}

export function convergeSessionBranches(sessionId, targetSessionId) {
  return post(`/sessions/${sessionId}/branches/converge`, { target_session_id: targetSessionId })
}

export function applyVbReviews(sessionId, { projectId = '', filePath, reviews }) {
  return post(`/sessions/${sessionId}/vb/apply`, {
    project_id: projectId,
    file_path: filePath,
    reviews,
  })
}
