import { computed, ref } from 'vue'
import {
  readClaudeMd,
  createClaudeMdDraft,
  updateClaudeMdRevision,
  proposeClaudeMdRevision,
  approveClaudeMdRevision,
  deleteClaudeMdRevision,
  applyClaudeMdRevision,
  listProjectMemories,
  createProjectMemory,
  updateProjectMemory,
  deleteProjectMemory,
} from '../api/memoryApi'

const content = ref('')
const fileHash = ref('')
const activeRevision = ref(null)
const versions = ref([])
const selectedRevision = ref(null)
const loading = ref(false)
const editing = ref(false)
const editContent = ref('')
const saving = ref(false)
const applying = ref(false)
const error = ref('')
const conflictMessage = ref('')
const projectMemories = ref([])
const selectedMemory = ref(null)
const memoryEditing = ref(false)
const memoryDraft = ref({ title: '', content: '', memory_type: 'note', state: 'active' })

const selectedContent = computed(() => selectedRevision.value?.content ?? content.value)
const canEditSelected = computed(() => {
  const state = selectedRevision.value?.state
  return !selectedRevision.value || state === 'draft' || state === 'conflicted'
})

export function useMemoryManager() {
  async function loadClaudeMd(projectDir) {
    if (!projectDir) return
    loading.value = true
    error.value = ''
    conflictMessage.value = ''
    try {
      const data = await readClaudeMd(projectDir)
      content.value = data.content || ''
      fileHash.value = data.file_hash || ''
      activeRevision.value = data.active_revision || null
      versions.value = data.versions || []
      selectedRevision.value = activeRevision.value || versions.value[0] || null
    } catch (e) {
      content.value = ''
      error.value = e.message || 'Failed to load CLAUDE.md'
    } finally {
      loading.value = false
    }
  }

  async function loadProjectMemories(projectDir) {
    if (!projectDir) return
    loading.value = true
    error.value = ''
    try {
      const data = await listProjectMemories(projectDir)
      projectMemories.value = data.memories || []
      selectedMemory.value = projectMemories.value[0] || null
    } catch (e) {
      projectMemories.value = []
      selectedMemory.value = null
      error.value = e.message || 'Failed to load project memories'
    } finally {
      loading.value = false
    }
  }

  function selectMemory(memory) {
    selectedMemory.value = memory
    memoryEditing.value = false
    memoryDraft.value = { title: '', content: '', memory_type: 'note', state: 'active' }
    error.value = ''
  }

  function startMemoryEdit(memory = null) {
    selectedMemory.value = memory || selectedMemory.value
    memoryEditing.value = true
    const target = memory || selectedMemory.value
    memoryDraft.value = target
      ? {
          title: target.title || '',
          content: target.content || '',
          memory_type: target.memory_type || 'note',
          state: target.state || 'active',
        }
      : { title: '', content: '', memory_type: 'note', state: 'active' }
  }

  function cancelMemoryEdit() {
    memoryEditing.value = false
    memoryDraft.value = { title: '', content: '', memory_type: 'note', state: 'active' }
  }

  async function saveProjectMemory(projectDir) {
    saving.value = true
    error.value = ''
    try {
      const payload = {
        title: memoryDraft.value.title,
        content: memoryDraft.value.content,
        memory_type: memoryDraft.value.memory_type || 'note',
        state: memoryDraft.value.state || 'active',
      }
      const data = selectedMemory.value
        ? await updateProjectMemory(selectedMemory.value.id, payload)
        : await createProjectMemory(projectDir, payload)
      upsertProjectMemory(data.memory)
      selectedMemory.value = data.memory
      memoryEditing.value = false
    } catch (e) {
      error.value = e.message || 'Failed to save project memory'
    } finally {
      saving.value = false
    }
  }

  async function removeProjectMemory(memoryId) {
    if (!memoryId) return
    saving.value = true
    error.value = ''
    try {
      await deleteProjectMemory(memoryId)
      projectMemories.value = projectMemories.value.filter(memory => memory.id !== memoryId)
      selectedMemory.value = projectMemories.value[0] || null
    } catch (e) {
      error.value = e.message || 'Failed to delete project memory'
    } finally {
      saving.value = false
    }
  }

  async function toggleProjectMemory(memory) {
    if (!memory) return
    saving.value = true
    error.value = ''
    try {
      const nextState = memory.state === 'disabled' ? 'active' : 'disabled'
      const data = await updateProjectMemory(memory.id, { state: nextState })
      upsertProjectMemory(data.memory)
      selectedMemory.value = data.memory
    } catch (e) {
      error.value = e.message || 'Failed to update project memory'
    } finally {
      saving.value = false
    }
  }

  function upsertProjectMemory(memory) {
    if (!memory) return
    const idx = projectMemories.value.findIndex(item => item.id === memory.id)
    if (idx >= 0) {
      projectMemories.value.splice(idx, 1, memory)
    } else {
      projectMemories.value.unshift(memory)
    }
  }

  function selectRevision(revision) {
    selectedRevision.value = revision
    editing.value = false
    editContent.value = ''
    error.value = ''
  }

  function startEdit() {
    if (!canEditSelected.value) return
    editing.value = true
    editContent.value = selectedContent.value
  }

  function cancelEdit() {
    editing.value = false
    editContent.value = ''
  }

  async function save(projectDir) {
    saving.value = true
    error.value = ''
    try {
      let revision
      if (selectedRevision.value && ['draft', 'conflicted'].includes(selectedRevision.value.state)) {
        const data = await updateClaudeMdRevision(selectedRevision.value.id, editContent.value)
        revision = data.revision
      } else {
        const baseRevisionId = activeRevision.value?.id || selectedRevision.value?.id || ''
        const data = await createClaudeMdDraft(projectDir, editContent.value, baseRevisionId)
        revision = data.revision
      }
      upsertRevision(revision)
      selectedRevision.value = revision
      editing.value = false
    } catch (e) {
      error.value = e.message || 'Failed to save draft'
    } finally {
      saving.value = false
    }
  }

  async function proposeSelected() {
    if (!selectedRevision.value) return
    await transitionSelected(() => proposeClaudeMdRevision(selectedRevision.value.id))
  }

  async function approveSelected() {
    if (!selectedRevision.value) return
    await transitionSelected(() => approveClaudeMdRevision(selectedRevision.value.id))
  }

  async function rejectSelected(reason = '') {
    if (!selectedRevision.value) return
    await transitionSelected(() => rejectClaudeMdRevision(selectedRevision.value.id, reason))
  }

  async function deleteSelectedRevision() {
    if (!selectedRevision.value) return
    saving.value = true
    error.value = ''
    try {
      await deleteClaudeMdRevision(selectedRevision.value.id)
      versions.value = versions.value.filter(v => v.id !== selectedRevision.value.id)
      selectedRevision.value = activeRevision.value || versions.value[0] || null
    } catch (e) {
      error.value = e.message || 'Failed to delete revision'
    } finally {
      saving.value = false
    }
  }

  async function applySelected(projectDir) {
    if (!selectedRevision.value) return
    applying.value = true
    error.value = ''
    conflictMessage.value = ''
    try {
      const data = await applyClaudeMdRevision(
        selectedRevision.value.id,
        projectDir,
        selectedRevision.value.base_revision_id,
        selectedRevision.value.base_file_hash || fileHash.value,
      )
      upsertRevision(data.revision)
      selectedRevision.value = data.revision
      if (data.conflict) {
        conflictMessage.value = 'CLAUDE.md changed on disk. Please reload and create a new draft.'
      } else {
        await loadClaudeMd(projectDir)
      }
    } catch (e) {
      conflictMessage.value = e.message || 'Failed to apply revision'
      await loadClaudeMd(projectDir)
    } finally {
      applying.value = false
    }
  }

  async function transitionSelected(fn) {
    saving.value = true
    error.value = ''
    try {
      const data = await fn()
      upsertRevision(data.revision)
      selectedRevision.value = data.revision
    } catch (e) {
      error.value = e.message || 'Failed to update revision'
    } finally {
      saving.value = false
    }
  }

  function upsertRevision(revision) {
    if (!revision) return
    const idx = versions.value.findIndex(v => v.id === revision.id)
    if (idx >= 0) {
      versions.value.splice(idx, 1, revision)
    } else {
      versions.value.unshift(revision)
    }
    versions.value.sort((a, b) => (b.version_no || 0) - (a.version_no || 0))
    if (revision.state === 'applied') {
      activeRevision.value = revision
      content.value = revision.content
      fileHash.value = revision.content_hash
    }
  }

  function reset() {
    content.value = ''
    fileHash.value = ''
    activeRevision.value = null
    versions.value = []
    selectedRevision.value = null
    projectMemories.value = []
    selectedMemory.value = null
    memoryEditing.value = false
    memoryDraft.value = { title: '', content: '', memory_type: 'note', state: 'active' }
    editing.value = false
    editContent.value = ''
    saving.value = false
    applying.value = false
    error.value = ''
    conflictMessage.value = ''
  }

  return {
    content,
    fileHash,
    activeRevision,
    versions,
    selectedRevision,
    selectedContent,
    canEditSelected,
    loading,
    editing,
    editContent,
    saving,
    applying,
    error,
    conflictMessage,
    projectMemories,
    selectedMemory,
    memoryEditing,
    memoryDraft,
    loadClaudeMd,
    loadProjectMemories,
    selectMemory,
    startMemoryEdit,
    cancelMemoryEdit,
    saveProjectMemory,
    removeProjectMemory,
    toggleProjectMemory,
    selectRevision,
    startEdit,
    cancelEdit,
    save,
    proposeSelected,
    approveSelected,
    rejectSelected,
    deleteSelectedRevision,
    applySelected,
    reset,
  }
}
