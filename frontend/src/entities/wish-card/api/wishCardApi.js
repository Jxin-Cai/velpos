import { get } from '@shared/api/httpClient'

export function fetchTeamCards(teamId) {
  return get(`/teams/${teamId}/board`)
}
