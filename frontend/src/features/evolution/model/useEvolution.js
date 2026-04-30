import { ref } from 'vue'
import { extractEvolutionLessons, createEvolutionClaudeMdDraft } from '../api/evolutionApi'

const visible = ref(false)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const proposal = ref(null)
const lessons = ref([])
const createdDraft = ref(null)

function buildRuleDraftContent(items) {
  return items
    .map((item, index) => {
      const title = String(item.title || '').trim() || `Rule ${index + 1}`
      const body = String(item.content || '').trim()
      return `## ${title}\n\n${body}`
    })
    .join('\n\n')
    .trim()
}

function parseRulePaths(text = '') {
  return text
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean)
}

export function useEvolution() {
  function open() {
    visible.value = true
    error.value = ''
  }

  function close() {
    visible.value = false
  }

  async function extract({ projectId = '', projectDir = '', sessionId = '' }) {
    loading.value = true
    error.value = ''
    createdDraft.value = null
    try {
      const data = await extractEvolutionLessons({
        project_id: projectId,
        project_dir: projectDir,
        session_id: sessionId,
        limit: 80,
      })
      proposal.value = data.proposal || null
      lessons.value = (data.lessons || []).map(item => ({ ...item, enabled: true }))
    } catch (e) {
      error.value = e.message || 'Failed to extract lessons'
    } finally {
      loading.value = false
    }
  }

  function updateLesson(index, patch) {
    if (!lessons.value[index]) return
    lessons.value.splice(index, 1, { ...lessons.value[index], ...patch })
  }

  function removeLesson(index) {
    lessons.value.splice(index, 1)
  }

  function selectedLessons() {
    return lessons.value
      .filter(item => item.enabled !== false && String(item.content || '').trim())
      .map(({ enabled, ...item }) => item)
  }

  async function createClaudeDraft(projectDir) {
    if (!proposal.value) return null
    saving.value = true
    error.value = ''
    try {
      const data = await createEvolutionClaudeMdDraft(proposal.value.id, projectDir, selectedLessons())
      proposal.value = data.proposal || proposal.value
      createdDraft.value = { type: 'claude', revision: data.revision || null }
      return data
    } catch (e) {
      error.value = e.message || 'Failed to create CLAUDE.md draft'
      return null
    } finally {
      saving.value = false
    }
  }

  async function createRuleDraft({ path = '', pathsText = '' } = {}) {
    const selected = selectedLessons()
    if (!selected.length) return null
    saving.value = true
    error.value = ''
    try {
      const ruleDraft = {
        path: String(path || '').trim(),
        paths: parseRulePaths(pathsText),
        content: buildRuleDraftContent(selected),
      }
      createdDraft.value = { type: 'rule', ruleDraft }
      return createdDraft.value
    } catch (e) {
      error.value = e.message || 'Failed to create rule draft'
      return null
    } finally {
      saving.value = false
    }
  }

  function reset() {
    proposal.value = null
    lessons.value = []
    createdDraft.value = null
    error.value = ''
  }

  return {
    visible,
    loading,
    saving,
    error,
    proposal,
    lessons,
    createdDraft,
    open,
    close,
    extract,
    updateLesson,
    removeLesson,
    createClaudeDraft,
    createRuleDraft,
    reset,
  }
}
