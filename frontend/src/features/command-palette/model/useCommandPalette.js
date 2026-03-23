import { ref } from 'vue'
import { fetchCommands } from '../api/commandApi'

const commands = ref([])
const loading = ref(false)
const visible = ref(false)
const error = ref(null)
const searchQuery = ref('')

let cachedProjectDir = null

export function useCommandPalette() {
  async function loadCommands(projectDir) {
    if (!projectDir) return
    if (cachedProjectDir === projectDir && commands.value.length > 0) {
      return
    }
    loading.value = true
    error.value = null
    try {
      const data = await fetchCommands(projectDir)
      commands.value = (data.commands || []).filter(c => c.isUserInvocable !== false)
      cachedProjectDir = projectDir
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
  }

  return {
    commands,
    loading,
    visible,
    error,
    searchQuery,
    loadCommands,
    togglePanel,
    openPanel,
    closePanel,
    invalidateCache,
  }
}
