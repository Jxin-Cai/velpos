import { get, post } from '@shared/api/httpClient'

export function listTeamTemplates(language = 'en', mode = '') {
  const params = new URLSearchParams({ language })
  if (mode) params.set('mode', mode)
  return get(`/agents/teams/templates?${params.toString()}`)
}

export function createTeamProject(name, teamConfig) {
  return post('/projects/teams', {
    name,
    team_config: teamConfig,
  })
}
