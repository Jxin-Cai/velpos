import { get, post, del } from '@shared/api/httpClient'

export function listPlugins(projectDir) {
  return get(`/plugins?project_dir=${encodeURIComponent(projectDir)}`)
}

export function installPlugin(plugin, projectDir) {
  return post('/plugins/install', { plugin, project_dir: projectDir })
}

export function uninstallPlugin(plugin, projectDir) {
  return post('/plugins/uninstall', { plugin, project_dir: projectDir })
}

export function upgradePlugin(plugin, projectDir) {
  return post('/plugins/upgrade', { plugin, project_dir: projectDir })
}

export function upgradeAllPlugins(projectDir) {
  return post('/plugins/upgrade-all', { project_dir: projectDir })
}

export function reloadPlugins(projectDir) {
  return post('/plugins/reload', { project_dir: projectDir }, { timeoutMs: 60000 })
}

export function listMarketplaces() {
  return get('/plugins/marketplaces')
}

export function updateMarketplace(name) {
  return post('/plugins/marketplaces/update', { name: name || null })
}

export function removeMarketplace(name) {
  return del(`/plugins/marketplaces/${encodeURIComponent(name)}`)
}
