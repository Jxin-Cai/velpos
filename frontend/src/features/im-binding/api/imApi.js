import { get, post, del, patch } from '@shared/api/httpClient'

export function getChannels() {
  return get('/im/channels')
}

export function createChannel(channelType, name = '') {
  return post('/im/channels', { channel_type: channelType, name })
}

export function deleteChannel(channelId) {
  return del(`/im/channels/${encodeURIComponent(channelId)}`)
}

export function renameChannel(channelId, name) {
  return patch(`/im/channels/${encodeURIComponent(channelId)}`, { name })
}

export function bindIm(sessionId, channelId, params = {}) {
  return post('/im/bindings', {
    session_id: sessionId,
    channel_id: channelId,
    params,
  })
}

export function completeBinding(sessionId, channelId, params = {}) {
  return post('/im/bindings/complete', {
    session_id: sessionId,
    channel_id: channelId,
    ...params,
  })
}

export function getBindingStatus(sessionId) {
  return get(`/im/bindings/${encodeURIComponent(sessionId)}`)
}

export function unbindIm(sessionId) {
  return del(`/im/bindings/${encodeURIComponent(sessionId)}`)
}

// ── Channel initialization ──

export function getChannelInitStatus(channelId) {
  return get(`/im/channels/${encodeURIComponent(channelId)}/init`)
}

export function initializeChannel(channelId, params = {}) {
  return post(`/im/channels/${encodeURIComponent(channelId)}/init`, { params })
}

export function resetChannel(channelId) {
  return del(`/im/channels/${encodeURIComponent(channelId)}/init`)
}

export function syncContext(sessionId) {
  return post(`/im/bindings/${encodeURIComponent(sessionId)}/sync-context`, {})
}
