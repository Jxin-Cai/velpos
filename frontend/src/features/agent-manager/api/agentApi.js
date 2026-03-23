import { get, post } from '@shared/api/httpClient'

export function listAgents(language = 'en') {
  return get(`/agents?language=${language}`)
}

export function loadAgent(projectId, agentId, language = 'en', sessionId = '') {
  return post(`/agents/projects/${projectId}/load`, { agent_id: agentId, language, session_id: sessionId })
}

export function unloadAgent(projectId, sessionId = '') {
  return post(`/agents/projects/${projectId}/unload`, { session_id: sessionId })
}
