import { get, put } from '@shared/api/httpClient'

export function fetchCommands(projectDir) {
  return get(`/commands?project_dir=${encodeURIComponent(projectDir)}`)
}

export function fetchCommandPolicies(projectDir) {
  return get(`/commands/policies?project_dir=${encodeURIComponent(projectDir)}`)
}

export function saveCommandPolicy(projectDir, policy) {
  return put('/commands/policies', { project_dir: projectDir, ...policy })
}
