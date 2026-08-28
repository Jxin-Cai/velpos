import { get, post, put, del } from '@shared/api/httpClient'

function buildQuery({ keyword = '', category = '', onlyActive = false } = {}) {
  const params = new URLSearchParams()
  if (keyword) params.set('keyword', keyword)
  if (category) params.set('category', category)
  if (onlyActive) params.set('only_active', 'true')
  const query = params.toString()
  return query ? `?${query}` : ''
}

export function listMcpServerEntries(filters) {
  return get(`/admin/market/mcp-servers${buildQuery(filters)}`)
}

export function listMcpCategories() {
  return get('/admin/market/mcp-servers/categories')
}

export function createMcpServerEntry(data) {
  return post('/admin/market/mcp-servers', data)
}

export function updateMcpServerEntry(id, data) {
  return put(`/admin/market/mcp-servers/${encodeURIComponent(id)}`, data)
}

export function deleteMcpServerEntry(id) {
  return del(`/admin/market/mcp-servers/${encodeURIComponent(id)}`)
}

export function listSkillEntries(filters) {
  return get(`/admin/market/skills${buildQuery(filters)}`)
}

export function listSkillCategories() {
  return get('/admin/market/skills/categories')
}

export function getSkillEntry(id) {
  return get(`/admin/market/skills/${encodeURIComponent(id)}`)
}

export function createSkillEntry(data) {
  return post('/admin/market/skills', data)
}

export function updateSkillEntry(id, data) {
  return put(`/admin/market/skills/${encodeURIComponent(id)}`, data)
}

export function deleteSkillEntry(id) {
  return del(`/admin/market/skills/${encodeURIComponent(id)}`)
}
