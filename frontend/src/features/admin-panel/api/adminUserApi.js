import { get, put } from '@shared/api/httpClient'

export function listUsers() {
  return get('/admin/users')
}

export function updateUserRole(userId, role) {
  return put(`/admin/users/${userId}/role`, { role })
}

export function updateUserStatus(userId, isActive) {
  return put(`/admin/users/${userId}/status`, { is_active: isActive })
}
