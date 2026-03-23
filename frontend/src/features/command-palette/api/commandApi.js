import { get } from '@shared/api/httpClient'

export function fetchCommands(projectDir) {
  return get(`/commands?project_dir=${encodeURIComponent(projectDir)}`)
}
