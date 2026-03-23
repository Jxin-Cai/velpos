import { get, post, put } from '@shared/api/httpClient'

export function getGitConfig() {
  return get('/git/config')
}

export function setGitConfig(userName, userEmail) {
  return put('/git/config', { user_name: userName, user_email: userEmail })
}

export function listSshKeys() {
  return get('/git/ssh/keys')
}

export function generateSshKey(keyType = 'ed25519', comment = '') {
  return post('/git/ssh/keys', { key_type: keyType, comment })
}

export function getSshPublicKey(keyName) {
  return get(`/git/ssh/keys/${encodeURIComponent(keyName)}/public`)
}
