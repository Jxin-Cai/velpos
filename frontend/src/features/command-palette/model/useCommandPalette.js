import { ref, computed } from 'vue'
import { fetchCommands, fetchCommandPolicies, saveCommandPolicy } from '../api/commandApi'

const commands = ref([])
const policies = ref([])
const loading = ref(false)
const visible = ref(false)
const error = ref(null)
const searchQuery = ref('')

let cachedProjectDir = null

const policyRows = computed(() => {
  const rowsByKey = new Map()
  for (const cmd of commands.value) {
    const key = `${cmd.name}:${cmd.type}`
    rowsByKey.set(key, {
      command_name: cmd.name,
      command_type: cmd.type || 'unknown',
      description: cmd.description || '',
      enabled: cmd.enabled !== false,
      visible: cmd.visible !== false,
      default_args: cmd.default_args || {},
      source: 'command',
    })
  }
  for (const policy of policies.value) {
    const key = `${policy.command_name}:${policy.command_type}`
    const existing = rowsByKey.get(key) || {
      command_name: policy.command_name,
      command_type: policy.command_type || 'unknown',
      description: '',
      source: 'policy',
    }
    rowsByKey.set(key, {
      ...existing,
      policy_id: policy.id,
      enabled: policy.enabled !== false,
      visible: policy.visible !== false,
      default_args: policy.default_args || {},
    })
  }
  return Array.from(rowsByKey.values()).sort((a, b) => a.command_name.localeCompare(b.command_name))
})

export function useCommandPalette() {
  async function loadCommands(projectDir, force = false) {
    if (!projectDir) return
    if (!force && cachedProjectDir === projectDir && commands.value.length > 0) {
      return
    }
    loading.value = true
    error.value = null
    try {
      const [commandData, policyData] = await Promise.all([
        fetchCommands(projectDir),
        fetchCommandPolicies(projectDir),
      ])
      commands.value = (commandData.commands || []).filter(c => c.isUserInvocable !== false)
      policies.value = policyData.policies || []
      cachedProjectDir = projectDir
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function updateCommandPolicy(projectDir, row, patch = {}) {
    if (!projectDir || !row?.command_name) return
    loading.value = true
    error.value = null
    try {
      await saveCommandPolicy(projectDir, {
        command_name: row.command_name,
        command_type: row.command_type || 'unknown',
        enabled: row.enabled !== false,
        visible: row.visible !== false,
        default_args: row.default_args || {},
        ...patch,
      })
      await loadCommands(projectDir, true)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  function togglePanel() {
    visible.value = !visible.value
    if (!visible.value) {
      searchQuery.value = ''
    }
  }

  function openPanel() {
    visible.value = true
    searchQuery.value = ''
  }

  function closePanel() {
    visible.value = false
    searchQuery.value = ''
  }

  function invalidateCache() {
    cachedProjectDir = null
    commands.value = []
    policies.value = []
  }

  return {
    commands,
    policies,
    policyRows,
    loading,
    visible,
    error,
    searchQuery,
    loadCommands,
    updateCommandPolicy,
    togglePanel,
    openPanel,
    closePanel,
    invalidateCache,
  }
}
