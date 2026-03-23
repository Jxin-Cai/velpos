import { ref } from 'vue'
import { listAgents, loadAgent, unloadAgent } from '../api/agentApi'

// Module-level singleton state
const categories = ref([])
const loading = ref(false)
const operating = ref(false)
const error = ref(null)
const language = ref(localStorage.getItem('pf_agent_lang') || 'zh')

export function useAgentManager() {
  async function fetchAgents() {
    loading.value = true
    error.value = null
    try {
      const data = await listAgents(language.value)
      categories.value = data.categories || []
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function handleLoad(projectId, agentId, sessionId = '') {
    operating.value = true
    error.value = null
    try {
      const project = await loadAgent(projectId, agentId, language.value, sessionId)
      return project
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      operating.value = false
    }
  }

  async function handleUnload(projectId, sessionId = '') {
    operating.value = true
    error.value = null
    try {
      const project = await unloadAgent(projectId, sessionId)
      return project
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      operating.value = false
    }
  }

  function setLanguage(lang) {
    language.value = lang
    localStorage.setItem('pf_agent_lang', lang)
    fetchAgents()
  }

  return {
    categories,
    loading,
    operating,
    error,
    language,
    fetchAgents,
    handleLoad,
    handleUnload,
    setLanguage,
  }
}
