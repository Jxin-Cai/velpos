import { computed, ref } from 'vue'
import {
  readClaudeMd,
  createClaudeMdDraft,
  updateClaudeMdRevision,
  deleteClaudeMdRevision,
  applyClaudeMdRevision,
  listRules,
  writeRule,
  deleteRule,
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
const rules = ref([])
const selectedRule = ref(null)
const ruleEditing = ref(false)
const ruleDraft = ref({ path: '', content: '', pathsText: '' })

const selectedContent = computed(() => selectedRevision.value?.content ?? content.value)
const canEditSelected = computed(() => !loading.value)

function formatRulePaths(paths = []) {
  return paths.join('\n')
}

function parseRulePaths(text = '') {
  return text
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean)
}

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
      const selectedId = selectedRevision.value?.id
      selectedRevision.value = versions.value.find(item => item.id === selectedId)
        || activeRevision.value
        || versions.value[0]
        || null
    } catch (e) {
      content.value = ''
      error.value = e.message || 'Failed to load CLAUDE.md'
    } finally {
      loading.value = false
    }
  }

  async function loadRules(projectDir) {
    if (!projectDir) return
    loading.value = true
    error.value = ''
    try {
      const data = await listRules(projectDir)
      rules.value = data.rules || []
      const selectedPath = selectedRule.value?.path
      selectedRule.value = rules.value.find(rule => rule.path === selectedPath) || rules.value[0] || null
    } catch (e) {
      rules.value = []
      selectedRule.value = null
      error.value = e.message || 'Failed to load rules'
    } finally {
      loading.value = false
    }
  }

  function selectRule(rule) {
    selectedRule.value = rule
    ruleEditing.value = false
    ruleDraft.value = { path: '', content: '', pathsText: '' }
    error.value = ''
  }

  function startRuleEdit(rule = null) {
    selectedRule.value = rule || selectedRule.value
    ruleEditing.value = true
    const target = rule || selectedRule.value
    ruleDraft.value = target
      ? {
          path: target.path || '',
          content: target.content || '',
          pathsText: formatRulePaths(target.paths || []),
        }
      : { path: '', content: '', pathsText: '' }
    error.value = ''
  }

  function startRuleDraft(draft = {}) {
    selectedRule.value = draft.path
      ? rules.value.find(rule => rule.path === draft.path) || null
      : null
    ruleEditing.value = true
    ruleDraft.value = {
      path: draft.path || '',
      content: draft.content || '',
      pathsText: formatRulePaths(draft.paths || []),
    }
    error.value = ''
  }

  function cancelRuleEdit() {
    ruleEditing.value = false
    ruleDraft.value = { path: '', content: '', pathsText: '' }
  }

  async function saveRule(projectDir) {
    saving.value = true
    error.value = ''
    try {
      const payload = {
        content: ruleDraft.value.content,
        paths: parseRulePaths(ruleDraft.value.pathsText),
      }
      const data = await writeRule(projectDir, ruleDraft.value.path, payload)
      upsertRule(data.rule)
      selectedRule.value = data.rule
      ruleEditing.value = false
    } catch (e) {
      error.value = e.message || 'Failed to save rule'
    } finally {
      saving.value = false
    }
  }

  async function removeRule(projectDir, rulePath) {
    if (!rulePath) return
    saving.value = true
    error.value = ''
    try {
      await deleteRule(projectDir, rulePath)
      rules.value = rules.value.filter(rule => rule.path !== rulePath)
      selectedRule.value = rules.value[0] || null
    } catch (e) {
      error.value = e.message || 'Failed to delete rule'
    } finally {
      saving.value = false
    }
  }

  function upsertRule(rule) {
    if (!rule) return
    const idx = rules.value.findIndex(item => item.path === rule.path)
    if (idx >= 0) {
      rules.value.splice(idx, 1, rule)
    } else {
      rules.value.unshift(rule)
    }
    rules.value.sort((a, b) => a.path.localeCompare(b.path))
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
        const baseRevisionId = selectedRevision.value?.id || activeRevision.value?.id || ''
        const data = await createClaudeMdDraft(projectDir, editContent.value, baseRevisionId)
        revision = data.revision
      }
      upsertRevision(revision)
      selectedRevision.value = revision
      editing.value = false
    } catch (e) {
      error.value = e.message || 'Failed to save version'
    } finally {
      saving.value = false
    }
  }

  async function deleteSelectedRevision(projectDir = '') {
    if (!selectedRevision.value) return
    saving.value = true
    error.value = ''
    try {
      await deleteClaudeMdRevision(selectedRevision.value.id)
      if (projectDir) {
        await loadClaudeMd(projectDir)
      } else {
        versions.value = versions.value.filter(v => v.id !== selectedRevision.value.id)
        selectedRevision.value = activeRevision.value || versions.value[0] || null
      }
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
        conflictMessage.value = 'CLAUDE.md changed on disk. Please reload and create a new version.'
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
    rules.value = []
    selectedRule.value = null
    ruleEditing.value = false
    ruleDraft.value = { path: '', content: '', pathsText: '' }
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
    rules,
    selectedRule,
    ruleEditing,
    ruleDraft,
    loadClaudeMd,
    loadRules,
    selectRule,
    startRuleEdit,
    startRuleDraft,
    cancelRuleEdit,
    saveRule,
    removeRule,
    selectRevision,
    startEdit,
    cancelEdit,
    save,
    deleteSelectedRevision,
    applySelected,
    reset,
  }
}
