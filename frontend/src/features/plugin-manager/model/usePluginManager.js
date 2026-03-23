import { ref } from 'vue'
import { listPlugins, installPlugin, uninstallPlugin } from '../api/pluginApi'

export function usePluginManager() {
  const plugins = ref([])
  const loading = ref(false)
  const operating = ref(null) // plugin key currently being operated on
  const error = ref(null)

  async function loadPlugins(projectDir) {
    if (!projectDir) return
    loading.value = true
    error.value = null
    try {
      const data = await listPlugins(projectDir)
      plugins.value = data.plugins || []
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function handleInstall(pluginKey, projectDir) {
    operating.value = pluginKey
    error.value = null
    try {
      await installPlugin(pluginKey, projectDir)
      await loadPlugins(projectDir)
    } catch (e) {
      error.value = e.message
    } finally {
      operating.value = null
    }
  }

  async function handleUninstall(pluginKey, projectDir) {
    operating.value = pluginKey
    error.value = null
    try {
      await uninstallPlugin(pluginKey, projectDir)
      await loadPlugins(projectDir)
    } catch (e) {
      error.value = e.message
    } finally {
      operating.value = null
    }
  }

  return {
    plugins,
    loading,
    operating,
    error,
    loadPlugins,
    handleInstall,
    handleUninstall,
  }
}
