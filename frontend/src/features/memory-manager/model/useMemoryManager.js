import { ref } from 'vue'
import { readClaudeMd, writeClaudeMd } from '../api/memoryApi'

const content = ref('')
const loading = ref(false)
const editing = ref(false)
const editContent = ref('')
const saving = ref(false)
const error = ref('')

export function useMemoryManager() {
  async function loadClaudeMd(projectDir) {
    if (!projectDir) return
    loading.value = true
    try {
      const data = await readClaudeMd(projectDir)
      content.value = data.content || ''
    } catch {
      content.value = ''
    } finally {
      loading.value = false
    }
  }

  function startEdit() {
    editing.value = true
    editContent.value = content.value
  }

  function cancelEdit() {
    editing.value = false
    editContent.value = ''
  }

  async function save(projectDir) {
    saving.value = true
    try {
      await writeClaudeMd(projectDir, editContent.value)
      content.value = editContent.value
      editing.value = false
    } catch {
      error.value = 'Failed to save'
    } finally {
      saving.value = false
    }
  }

  function reset() {
    content.value = ''
    editing.value = false
    editContent.value = ''
    saving.value = false
  }

  return {
    content,
    loading,
    editing,
    editContent,
    saving,
    error,
    loadClaudeMd,
    startEdit,
    cancelEdit,
    save,
    reset,
  }
}
