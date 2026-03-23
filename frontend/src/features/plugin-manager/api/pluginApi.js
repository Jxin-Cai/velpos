import { get, post } from '@shared/api/httpClient'

export function listPlugins(projectDir) {
  return get(`/plugins?project_dir=${encodeURIComponent(projectDir)}`)
}

export function installPlugin(plugin, projectDir) {
  return post('/plugins/install', { plugin, project_dir: projectDir })
}

export function uninstallPlugin(plugin, projectDir) {
  return post('/plugins/uninstall', { plugin, project_dir: projectDir })
}
