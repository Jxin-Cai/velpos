import { ref } from 'vue'
import { extractEvolutionLessons, createEvolutionClaudeMdDraft } from '../api/evolutionApi'

const visible = ref(false)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const proposal = ref(null)
const lessons = ref([])
const revision = ref(null)

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
    revision.value = null
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

  async function createDraft(projectDir) {
    if (!proposal.value) return null
    saving.value = true
    error.value = ''
    try {
      const selected = lessons.value
        .filter(item => item.enabled !== false && String(item.content || '').trim())
        .map(({ enabled, ...item }) => item)
      const data = await createEvolutionClaudeMdDraft(proposal.value.id, projectDir, selected)
      proposal.value = data.proposal || proposal.value
      revision.value = data.revision || null
      return data
    } catch (e) {
      error.value = e.message || 'Failed to create CLAUDE.md draft'
      return null
    } finally {
      saving.value = false
    }
  }

  function reset() {
    proposal.value = null
    lessons.value = []
    revision.value = null
    error.value = ''
  }

  return {
    visible,
    loading,
    saving,
    error,
    proposal,
    lessons,
    revision,
    open,
    close,
    extract,
    updateLesson,
    removeLesson,
    createDraft,
    reset,
  }
}
