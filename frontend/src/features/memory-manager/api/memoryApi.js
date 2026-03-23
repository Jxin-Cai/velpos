import { get, put, del } from '@shared/api/httpClient'

export function listMemoryFiles(projectDir) {
  return get(`/memory?project_dir=${encodeURIComponent(projectDir)}`)
}

export function readMemoryFile(filename, projectDir) {
  return get(`/memory/${encodeURIComponent(filename)}?project_dir=${encodeURIComponent(projectDir)}`)
}

export function writeMemoryFile(filename, projectDir, content) {
  return put(`/memory/${encodeURIComponent(filename)}`, { project_dir: projectDir, content })
}

export function deleteMemoryFile(filename, projectDir) {
  return del(`/memory/${encodeURIComponent(filename)}?project_dir=${encodeURIComponent(projectDir)}`)
}

export function readMemoryIndex(projectDir) {
  return get(`/memory/index?project_dir=${encodeURIComponent(projectDir)}`)
}

export function readClaudeMd(projectDir) {
  return get(`/memory/claude-md?project_dir=${encodeURIComponent(projectDir)}`)
}

export function writeClaudeMd(projectDir, content) {
  return put('/memory/claude-md', { project_dir: projectDir, content })
}

export function writeMemoryIndex(projectDir, content) {
  return put('/memory/index/update', { project_dir: projectDir, content })
}
