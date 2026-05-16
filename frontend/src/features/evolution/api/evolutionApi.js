import { post } from '@shared/api/httpClient'

export function extractEvolutionLessons(payload) {
  return post('/evolution/extract', payload)
}

export function createEvolutionClaudeMdDraft(proposalId, projectDir, lessons) {
  return post(`/evolution/proposals/${encodeURIComponent(proposalId)}/claude-md-draft`, {
    project_dir: projectDir,
    lessons,
  })
}
