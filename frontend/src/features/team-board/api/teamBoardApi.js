import { del, get, post } from '@shared/api/httpClient'

export function createTeam(payload) {
  return post('/teams', payload)
}

export function listTeams(projectId) {
  return get(`/teams?project_id=${encodeURIComponent(projectId)}`)
}

export function getTeamBoard(teamId) {
  return get(`/teams/${teamId}/board`)
}

export function createCard(teamId, payload) {
  return post(`/teams/${teamId}/cards`, payload)
}

export function moveCard(teamId, cardId, payload) {
  return post(`/teams/${teamId}/cards/${cardId}/moves`, payload)
}

export function archiveCard(teamId, cardId, payload) {
  return post(`/teams/${teamId}/cards/${cardId}/archive`, payload)
}

export function deleteCard(teamId, cardId) {
  return del(`/teams/${teamId}/cards/${cardId}`)
}

export function retryExecution(executionId) {
  return post(`/teams/executions/${executionId}/retry`)
}

export function getExecutionHistory(executionId) {
  return get(`/teams/executions/${executionId}/history`)
}

export function getExecutionDetail(executionId) {
  return get(`/teams/executions/${executionId}`)
}

export function getTeamArtifactUrl(projectId, path) {
  const params = new URLSearchParams({ path })
  return `/api/projects/${encodeURIComponent(projectId)}/workspace/file-raw?${params.toString()}`
}
