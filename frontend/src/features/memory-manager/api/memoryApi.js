import { get, put, del, post, patch } from '@shared/api/httpClient'

export function readClaudeMd(projectDir) {
  return get(`/memory/claude-md?project_dir=${encodeURIComponent(projectDir)}`)
}

export function createClaudeMdDraft(projectDir, content, baseRevisionId = '') {
  return post('/memory/claude-md/drafts', { project_dir: projectDir, content, base_revision_id: baseRevisionId })
}

export function updateClaudeMdRevision(revisionId, content) {
  return patch(`/memory/claude-md/revisions/${encodeURIComponent(revisionId)}`, { content })
}

export function applyClaudeMdRevision(revisionId, projectDir, expectedBaseRevisionId, expectedFileHash) {
  return post(`/memory/claude-md/revisions/${encodeURIComponent(revisionId)}/apply`, {
    project_dir: projectDir,
    expected_base_revision_id: expectedBaseRevisionId,
    expected_file_hash: expectedFileHash,
  })
}

export function deleteClaudeMdRevision(revisionId) {
  return del(`/memory/claude-md/revisions/${encodeURIComponent(revisionId)}`)
}

export function listRules(projectDir) {
  return get(`/memory/rules?project_dir=${encodeURIComponent(projectDir)}`)
}

function encodeRulePath(rulePath) {
  return rulePath.split('/').map(encodeURIComponent).join('/')
}

export function writeRule(projectDir, rulePath, payload) {
  return put(`/memory/rules/${encodeRulePath(rulePath)}`, { project_dir: projectDir, ...payload })
}

export function deleteRule(projectDir, rulePath) {
  return del(`/memory/rules/${encodeRulePath(rulePath)}?project_dir=${encodeURIComponent(projectDir)}`)
}
