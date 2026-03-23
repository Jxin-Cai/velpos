import { get, post, del, patch } from '@shared/api/httpClient'

export function createProject(name, githubUrl = '') {
  return post('/projects', { name, github_url: githubUrl })
}

export function listProjects() {
  return get('/projects')
}

export function getProject(projectId) {
  return get(`/projects/${projectId}`)
}

export function deleteProject(projectId) {
  return del(`/projects/${projectId}`)
}

export function reorderProjects(orderedIds) {
  return patch('/projects/reorder', { ordered_ids: orderedIds })
}

export function ensureProjectsByDirs(dirPaths) {
  return post('/projects/ensure-by-dirs', { dir_paths: dirPaths })
}

export function initPlugin(projectId, pluginType, sessionId) {
  return post(`/projects/${projectId}/init-plugin`, { plugin_type: pluginType, session_id: sessionId })
}

export function completePluginInit(projectId, pluginType) {
  return post(`/projects/${projectId}/complete-plugin-init`, { plugin_type: pluginType })
}

export function resetPlugin(projectId, pluginType) {
  return post(`/projects/${projectId}/reset-plugin`, { plugin_type: pluginType })
}

export function getGitBranches(projectId) {
  return get(`/projects/${projectId}/git/branches`)
}

export function checkoutGitBranch(projectId, branch) {
  return post(`/projects/${projectId}/git/checkout`, { branch })
}
