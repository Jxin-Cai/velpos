import { get, post, del, put } from '@shared/api/httpClient'

export function listChannelProfiles() {
  return get('/channel-profiles')
}

export function createChannelProfile(data) {
  return post('/channel-profiles', data)
}

export function updateChannelProfile(profileId, data) {
  return put(`/channel-profiles/${profileId}`, data)
}

export function deleteChannelProfile(profileId) {
  return del(`/channel-profiles/${profileId}`)
}

export function activateChannelProfile(profileId) {
  return post(`/channel-profiles/${profileId}/activate`)
}

export function fetchModelsForChannel(host, apiKey) {
  return post('/settings/fetch-models', { host, api_key: apiKey })
}
