import { get, post } from '@shared/api/httpClient'

export function listEvolutionProposals(projectDir) {
  return get(`/evolution/proposals?project_dir=${encodeURIComponent(projectDir)}`)
}

export function extractEvolutionLessons(payload) {
  return post('/evolution/extract', payload)
}

export function createEvolutionClaudeMdDraft(proposalId, projectDir, lessons) {
  return post(`/evolution/proposals/${encodeURIComponent(proposalId)}/claude-md-draft`, {
    project_dir: projectDir,
    lessons,
  })
}

export function approveEvolutionProposal(proposalId) {
  return post(`/evolution/proposals/${encodeURIComponent(proposalId)}/approve`, {})
}

export function rejectEvolutionProposal(proposalId) {
  return post(`/evolution/proposals/${encodeURIComponent(proposalId)}/reject`, {})
}
