import { get, post } from '@shared/api/httpClient'

export function listTeamTemplates(language = 'en', mode = '') {
  const params = new URLSearchParams({ language })
  if (mode) params.set('mode', mode)
  return get(`/agents/teams/templates?${params.toString()}`)
}

export function createTeamProject(name, dirPath, teamConfig) {
  return post('/projects/teams', {
    name,
    dir_path: dirPath,
    team_config: teamConfig,
  })
}

export function getTeamTimeline(projectId, sessionId) {
  return get(`/teams/${projectId}/timeline/${sessionId}`)
}

export function getLinkedSessions(projectId, sessionId) {
  return get(`/teams/${projectId}/linked-sessions/${sessionId}`)
}

export function getTeamTaskDetail(projectId, taskId) {
  return get(`/teams/${projectId}/tasks/${taskId}`)
}

export function getSessionArtifacts(sessionId) {
  return get(`/sessions/${sessionId}/artifacts`)
}

export function getWorkerContext(sessionId) {
  return get(`/teams/worker-context/${sessionId}`)
}

export function cancelTeamTask(projectId, taskId) {
  return post(`/teams/${projectId}/tasks/${taskId}/cancel`)
}

export function retryTeamTask(projectId, taskId) {
  return post(`/teams/${projectId}/tasks/${taskId}/retry`)
}
