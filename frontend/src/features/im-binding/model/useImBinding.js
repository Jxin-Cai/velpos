import { ref, computed } from 'vue'
import {
  getChannels,
  createChannel,
  deleteChannel,
  renameChannel,
  bindIm,
  completeBinding,
  getBindingStatus,
  unbindIm,
  initializeChannel,
  resetChannel,
  syncContext,
} from '../api/imApi'

const bindingState = ref(null)
const loading = ref(false)
const error = ref(null)
const availableChannels = ref([])
const initRequired = ref(null)
const syncResult = ref(null)

const _activeSessionId = ref('')
let _fetchChannelsPromise = null

export function useImBinding() {
  const isBound = computed(() => bindingState.value?.binding_status === 'bound')
  const isBinding = computed(() => bindingState.value?.binding_status === 'binding')
  const isUnbound = computed(() => !bindingState.value || bindingState.value.binding_status === 'unbound')
  const hasChannels = computed(() => availableChannels.value.length > 0)
  const currentChannelType = computed(() => bindingState.value?.channel_type || '')
  const currentChannelId = computed(() => bindingState.value?.channel_id || '')
  const bindingMode = computed(() => bindingState.value?.ui_data?.mode || '')

  // Find the bound instance across all channel types for active session
  const boundInstanceForSession = computed(() => {
    if (!_activeSessionId.value) return null
    for (const ch of availableChannels.value) {
      const inst = (ch.instances || []).find(i => i.bound_session_id === _activeSessionId.value)
      if (inst) return { ...inst, channel_type: ch.channel_type, display_name: ch.display_name }
    }
    return null
  })

  const isBoundForSession = computed(() => !!boundInstanceForSession.value || isBound.value)
  const boundChannelType = computed(() => boundInstanceForSession.value?.channel_type || currentChannelType.value)
  const boundInstanceName = computed(() => boundInstanceForSession.value?.name || '')

  async function fetchChannels() {
    // Deduplicate concurrent calls — reuse in-flight request
    if (_fetchChannelsPromise) return _fetchChannelsPromise
    _fetchChannelsPromise = (async () => {
      try {
        const data = await getChannels()
        availableChannels.value = data || []
      } catch {
        availableChannels.value = []
      } finally {
        _fetchChannelsPromise = null
      }
    })()
    return _fetchChannelsPromise
  }

  async function fetchStatus(sessionId) {
    if (!sessionId) return
    if (sessionId !== _activeSessionId.value) {
      bindingState.value = null
      error.value = null
      initRequired.value = null
      syncResult.value = null
    }
    _activeSessionId.value = sessionId
    loading.value = true
    error.value = null
    try {
      const data = await getBindingStatus(sessionId)
      if (sessionId === _activeSessionId.value) {
        bindingState.value = data || null
      }
    } catch {
      if (sessionId === _activeSessionId.value) {
        bindingState.value = null
        error.value = null
      }
    } finally {
      if (sessionId === _activeSessionId.value) {
        loading.value = false
      }
    }
  }

  async function handleCreateChannel(channelType, name = '') {
    loading.value = true
    error.value = null
    try {
      const data = await createChannel(channelType, name)
      await fetchChannels()
      return data
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  async function handleDeleteChannel(channelId) {
    error.value = null
    try {
      await deleteChannel(channelId)
      await fetchChannels()
    } catch (e) {
      error.value = e.message
    }
  }

  async function handleRenameChannel(channelId, name) {
    error.value = null
    try {
      await renameChannel(channelId, name)
      await fetchChannels()
    } catch (e) {
      error.value = e.message
    }
  }

  async function handleBind(sessionId, channelId, params = {}) {
    if (!sessionId || !channelId) return null
    _activeSessionId.value = sessionId
    loading.value = true
    error.value = null
    try {
      const data = await bindIm(sessionId, channelId, params)
      if (sessionId !== _activeSessionId.value) return null
      if (data?.action === 'init_required') {
        initRequired.value = data
        return data
      }
      if (data?.ui_data?.mode === 'prompt' && data?.binding_status === 'binding') {
        return data
      }
      bindingState.value = data
      initRequired.value = null
      await fetchChannels()
      return data
    } catch (e) {
      if (sessionId === _activeSessionId.value) {
        error.value = e.message
      }
      return null
    } finally {
      if (sessionId === _activeSessionId.value) {
        loading.value = false
      }
    }
  }

  async function handleComplete(sessionId, channelId, params = {}) {
    if (!sessionId || !channelId) return null
    loading.value = true
    error.value = null
    try {
      const data = await completeBinding(sessionId, channelId, params)
      if (sessionId === _activeSessionId.value) {
        bindingState.value = data
      }
      await fetchChannels()
      return data
    } catch (e) {
      if (sessionId === _activeSessionId.value) {
        error.value = e.message
      }
      return null
    } finally {
      if (sessionId === _activeSessionId.value) {
        loading.value = false
      }
    }
  }

  async function handleUnbind(sessionId) {
    if (!sessionId) return
    loading.value = true
    error.value = null
    try {
      await unbindIm(sessionId)
      if (sessionId === _activeSessionId.value) {
        bindingState.value = null
      }
      await fetchChannels()
    } catch (e) {
      if (sessionId === _activeSessionId.value) {
        error.value = e.message
      }
    } finally {
      if (sessionId === _activeSessionId.value) {
        loading.value = false
      }
    }
  }

  async function handleInitialize(channelId, params = {}) {
    loading.value = true
    error.value = null
    try {
      const data = await initializeChannel(channelId, params)
      if (data?.init_status === 'error' && data?.error_message) {
        error.value = data.error_message
      }
      await fetchChannels()
      return data
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  async function handleResetChannel(channelId) {
    loading.value = true
    error.value = null
    try {
      await resetChannel(channelId)
      await fetchChannels()
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function handleSyncContext(sessionId) {
    if (!sessionId) return null
    loading.value = true
    error.value = null
    syncResult.value = null
    try {
      const data = await syncContext(sessionId)
      syncResult.value = data
      return data
    } catch (e) {
      error.value = e.message
      syncResult.value = { error: e.message }
      return null
    } finally {
      loading.value = false
    }
  }

  function clearInitRequired() {
    initRequired.value = null
  }

  function clearSyncResult() {
    syncResult.value = null
  }

  function resetState() {
    bindingState.value = null
    error.value = null
    initRequired.value = null
    syncResult.value = null
  }

  return {
    bindingState,
    loading,
    error,
    availableChannels,
    initRequired,
    syncResult,
    isBound,
    isBinding,
    isUnbound,
    hasChannels,
    currentChannelType,
    currentChannelId,
    bindingMode,
    isBoundForSession,
    boundChannelType,
    boundInstanceName,
    fetchChannels,
    fetchStatus,
    handleCreateChannel,
    handleDeleteChannel,
    handleRenameChannel,
    handleBind,
    handleComplete,
    handleUnbind,
    handleInitialize,
    handleResetChannel,
    handleSyncContext,
    clearInitRequired,
    clearSyncResult,
    resetState,
  }
}
