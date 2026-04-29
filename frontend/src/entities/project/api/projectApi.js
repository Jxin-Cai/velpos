import { API_BASE } from '@shared/lib/constants'
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

export function pickProjectDirectory() {
  return post('/projects/pick-directory', {})
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

export function listWorkspaceFiles(projectId, { changedOnly = false, keyword = '' } = {}) {
  const params = new URLSearchParams()
  params.set('changed_only', changedOnly ? 'true' : 'false')
  if (keyword) params.set('keyword', keyword)
  return get(`/projects/${projectId}/workspace/files?${params.toString()}`)
}

export function readWorkspaceFile(projectId, path) {
  return get(`/projects/${projectId}/workspace/file?path=${encodeURIComponent(path)}`)
}

export function getWorkspaceDiff(projectId, path) {
  return get(`/projects/${projectId}/workspace/diff?path=${encodeURIComponent(path)}`)
}

export function listWorkspaceFileHistory(projectId, path, limit = 20) {
  return get(`/projects/${projectId}/workspace/file-history?path=${encodeURIComponent(path)}&limit=${limit}`)
}

export async function downloadWorkspaceSelection(projectId, paths) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/workspace/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paths }),
  })
  if (!res.ok) {
    let message = `HTTP error: ${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      message = body?.message || message
    } catch {
    }
    throw new Error(message)
  }
  const blob = await res.blob()
  const disposition = res.headers.get('content-disposition') || ''
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || 'workspace-export.zip'
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function readWorkspaceFileAtRef(projectId, path, ref) {
  return get(`/projects/${projectId}/workspace/file-at-ref?path=${encodeURIComponent(path)}&ref=${encodeURIComponent(ref)}`)
}
