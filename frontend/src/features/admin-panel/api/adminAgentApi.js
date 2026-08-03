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
