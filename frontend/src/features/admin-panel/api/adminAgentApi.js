import { get, post, put, del } from '@shared/api/httpClient'

export function listAgentTemplates() {
  return get('/admin/agent-templates')
}

export function createAgentTemplate(data) {
  return post('/admin/agent-templates', data)
}

export function updateAgentTemplate(id, data) {
  return put(`/admin/agent-templates/${id}`, data)
}

export function deleteAgentTemplate(id) {
  return del(`/admin/agent-templates/${id}`)
}

export function listClaudeMarketplaces() {
  return get('/admin/plugins/marketplaces')
}

export function addClaudeMarketplace(source, token = '') {
  return post('/admin/plugins/marketplaces', { source, token }, { timeoutMs: 120000 })
}

export function refreshClaudeMarketplace(name, token = '') {
  return post(`/admin/plugins/marketplaces/${encodeURIComponent(name)}/refresh`, { token }, { timeoutMs: 120000 })
}

export function removeClaudeMarketplace(name) {
  return del(`/admin/plugins/marketplaces/${encodeURIComponent(name)}`)
}

export function listClaudeMarketplacePlugins(name) {
  return get(`/admin/plugins/marketplaces/${encodeURIComponent(name)}/plugins`)
}

export function listSystemAgents() {
  return get('/agents?language=zh')
}
