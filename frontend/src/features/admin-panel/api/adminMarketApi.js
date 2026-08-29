import { get, post, put, del } from '@shared/api/httpClient'

function buildQuery({ keyword = '', category = '', onlyActive = false, source = '' } = {}) {
  const params = new URLSearchParams()
  if (keyword) params.set('keyword', keyword)
  if (category) params.set('category', category)
  if (onlyActive) params.set('only_active', 'true')
  if (source) params.set('source', source)
  const query = params.toString()
  return query ? `?${query}` : ''
}

function buildMarketplaceQuery({ keyword = '', page = 1, limit = 30, sort = 'stars' } = {}) {
  const params = new URLSearchParams()
  if (keyword) params.set('keyword', keyword)
  params.set('page', String(page))
  params.set('limit', String(limit))
  params.set('sort', sort)
  return `?${params.toString()}`
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

export function browseMcpMarketplace(filters) {
  return get(`/admin/market/mcp-servers/marketplace${buildMarketplaceQuery(filters)}`)
}

export function importMcpMarketplaceEntry(ref) {
  return post('/admin/market/mcp-servers/marketplace/import', { ref })
}

export function browseSkillMarketplace(filters) {
  return get(`/admin/market/skills/marketplace${buildMarketplaceQuery(filters)}`)
}

export function importSkillMarketplaceEntry(ref) {
  return post('/admin/market/skills/marketplace/import', { ref })
}
