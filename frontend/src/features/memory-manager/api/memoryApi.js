import { get, put, del, post, patch } from '@shared/api/httpClient'

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

export function listClaudeMdVersions(projectDir) {
  return get(`/memory/claude-md/versions?project_dir=${encodeURIComponent(projectDir)}`)
}

export function createClaudeMdDraft(projectDir, content, baseRevisionId = '') {
  return post('/memory/claude-md/drafts', { project_dir: projectDir, content, base_revision_id: baseRevisionId })
}

export function updateClaudeMdRevision(revisionId, content) {
  return patch(`/memory/claude-md/revisions/${encodeURIComponent(revisionId)}`, { content })
}

export function proposeClaudeMdRevision(revisionId) {
  return post(`/memory/claude-md/revisions/${encodeURIComponent(revisionId)}/propose`, {})
}

export function approveClaudeMdRevision(revisionId) {
  return post(`/memory/claude-md/revisions/${encodeURIComponent(revisionId)}/approve`, {})
}

export function rejectClaudeMdRevision(revisionId, reason = '') {
  return post(`/memory/claude-md/revisions/${encodeURIComponent(revisionId)}/reject`, { reason })
}

export function applyClaudeMdRevision(revisionId, projectDir, expectedBaseRevisionId, expectedFileHash) {
  return post(`/memory/claude-md/revisions/${encodeURIComponent(revisionId)}/apply`, {
    project_dir: projectDir,
    expected_base_revision_id: expectedBaseRevisionId,
    expected_file_hash: expectedFileHash,
  })
}

export function diffClaudeMdRevision(revisionId) {
  return get(`/memory/claude-md/revisions/${encodeURIComponent(revisionId)}/diff`)
}

export function deleteClaudeMdRevision(revisionId) {
  return del(`/memory/claude-md/revisions/${encodeURIComponent(revisionId)}`)
}

export function writeClaudeMd(projectDir, content) {  return put('/memory/claude-md', { project_dir: projectDir, content })
}

export function writeMemoryIndex(projectDir, content) {
  return put('/memory/index/update', { project_dir: projectDir, content })
}

export function listProjectMemories(projectDir) {
  return get(`/project-memories?project_dir=${encodeURIComponent(projectDir)}`)
}

export function createProjectMemory(projectDir, payload) {
  return post('/project-memories', { project_dir: projectDir, ...payload })
}

export function updateProjectMemory(memoryId, payload) {
  return patch(`/project-memories/${encodeURIComponent(memoryId)}`, payload)
}

export function deleteProjectMemory(memoryId) {
  return del(`/project-memories/${encodeURIComponent(memoryId)}`)
}
