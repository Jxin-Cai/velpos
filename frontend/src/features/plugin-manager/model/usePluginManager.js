import { ref } from 'vue'
import {
  listPlugins,
  installPlugin,
  uninstallPlugin,
  upgradePlugin,
  upgradeAllPlugins as apiUpgradeAll,
  listMarketplaces as apiListMarketplaces,
  updateMarketplace as apiUpdateMarketplace,
  removeMarketplace as apiRemoveMarketplace,
} from '../api/pluginApi'

export function usePluginManager() {
  const plugins = ref([])
  const marketplaces = ref([])
  const loading = ref(false)
  const operating = ref(null) // plugin key or marketplace name currently being operated on
  const error = ref(null)
  let _loadSeq = 0

  async function loadPlugins(projectDir) {
    if (!projectDir) return
    loading.value = true
    error.value = null
    const seq = ++_loadSeq
    try {
      const data = await listPlugins(projectDir)
      if (seq !== _loadSeq) return
      plugins.value = data.plugins || []
    } catch (e) {
      if (seq !== _loadSeq) return
      error.value = e.message
    } finally {
      if (seq === _loadSeq) loading.value = false
    }
  }

  async function loadMarketplaces() {
    error.value = null
    try {
      const data = await apiListMarketplaces()
      marketplaces.value = data.marketplaces || []
    } catch (e) {
      error.value = e.message
    }
  }

  async function withPluginOp(pluginKey, apiFn, projectDir) {
    operating.value = pluginKey
    error.value = null
    try {
      await apiFn(pluginKey, projectDir)
      await loadPlugins(projectDir)
    } catch (e) {
      error.value = e.message
    } finally {
      operating.value = null
    }
  }

  function handleInstall(pluginKey, projectDir) {
    return withPluginOp(pluginKey, installPlugin, projectDir)
  }

  function handleUninstall(pluginKey, projectDir) {
    return withPluginOp(pluginKey, uninstallPlugin, projectDir)
  }

  function handleUpgradePlugin(pluginKey, projectDir) {
    return withPluginOp(pluginKey, upgradePlugin, projectDir)
  }

  async function handleUpgradeAllPlugins(projectDir) {
    if (!projectDir) return
    operating.value = '__upgrade_all__'
    error.value = null
    try {
      await apiUpgradeAll(projectDir)
      await loadPlugins(projectDir)
    } catch (e) {
      error.value = e.message
    } finally {
      operating.value = null
    }
  }

  async function handleUpdateMarketplace(name) {
    operating.value = name || '__update_all_marketplaces__'
    error.value = null
    try {
      await apiUpdateMarketplace(name)
      await loadMarketplaces()
    } catch (e) {
      error.value = e.message
    } finally {
      operating.value = null
    }
  }

  async function handleRemoveMarketplace(name) {
    operating.value = name
    error.value = null
    try {
      await apiRemoveMarketplace(name)
      await loadMarketplaces()
    } catch (e) {
      error.value = e.message
    } finally {
      operating.value = null
    }
  }

  return {
    plugins,
    marketplaces,
    loading,
    operating,
    error,
    loadPlugins,
    loadMarketplaces,
    handleInstall,
    handleUninstall,
    handleUpgradePlugin,
    handleUpgradeAllPlugins,
    handleUpdateMarketplace,
    handleRemoveMarketplace,
  }
}
