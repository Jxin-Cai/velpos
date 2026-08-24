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
  getDeliveries,
  retryDelivery,
} from '../api/imApi'

/** Mutations that own the dialog's busy state, one at a time. */
export const ImAction = Object.freeze({
  CREATE: 'create',
  DELETE: 'delete',
  RENAME: 'rename',
  BIND: 'bind',
  COMPLETE: 'complete',
  UNBIND: 'unbind',
  SWITCH: 'switch',
  INITIALIZE: 'initialize',
  RESET: 'reset',
  SYNC: 'sync',
  RETRY_DELIVERY: 'retry_delivery',
})

const bindingState = ref(null)
const error = ref(null)
const availableChannels = ref([])
const initRequired = ref(null)
const syncResult = ref(null)
const deliveryOverview = ref(null)

const statusLoading = ref(false)
const pendingAction = ref(null)
const pendingChannelId = ref('')

const _activeSessionId = ref('')
let _fetchChannelsPromise = null

// Bumped whenever the binding state is deliberately changed. A status read that
// started before the bump is stale by the time it resolves and must be dropped,
// otherwise it resurrects the binding the user just removed.
let _stateVersion = 0

function _nextStateVersion() {
  _stateVersion += 1
  return _stateVersion
}

export function useImBinding() {
  const isBound = computed(() => bindingState.value?.binding_status === 'bound')
  const isBinding = computed(() => bindingState.value?.binding_status === 'binding')
  const hasChannels = computed(() => availableChannels.value.length > 0)
  const currentChannelType = computed(() => bindingState.value?.channel_type || '')
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

  function isPending(action) {
    return pendingAction.value === action
  }

  function beginAction(action, channelId = '') {
    pendingAction.value = action
    pendingChannelId.value = channelId
  }

  function endAction(action) {
    if (pendingAction.value !== action) return
    pendingAction.value = null
    pendingChannelId.value = ''
  }

  /**
   * @param {boolean} force Skip the in-flight reuse. A read that started before
   *   the mutation we just made would report the pre-mutation channel list.
   */
  async function fetchChannels(force = false) {
    if (_fetchChannelsPromise) {
      if (!force) return _fetchChannelsPromise
      await _fetchChannelsPromise
    }
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
      deliveryOverview.value = null
    }
    _activeSessionId.value = sessionId
    const version = _nextStateVersion()
    statusLoading.value = true
    error.value = null
    try {
      const data = await getBindingStatus(sessionId)
      if (version === _stateVersion && sessionId === _activeSessionId.value) {
        bindingState.value = data || null
      }
    } catch {
      if (version === _stateVersion && sessionId === _activeSessionId.value) {
        bindingState.value = null
        error.value = null
      }
    } finally {
      if (sessionId === _activeSessionId.value) {
        statusLoading.value = false
      }
    }
  }

  async function handleCreateChannel(channelType, name = '') {
    beginAction(ImAction.CREATE)
    error.value = null
    try {
      const data = await createChannel(channelType, name)
      await fetchChannels(true)
      return data
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      endAction(ImAction.CREATE)
    }
  }

  async function handleDeleteChannel(channelId) {
    beginAction(ImAction.DELETE, channelId)
    error.value = null
    try {
      await deleteChannel(channelId)
      if (bindingState.value?.channel_id === channelId) {
        _nextStateVersion()
        bindingState.value = null
      }
      await fetchChannels(true)
    } catch (e) {
      error.value = e.message
    } finally {
      endAction(ImAction.DELETE)
    }
  }

  async function handleRenameChannel(channelId, name) {
    beginAction(ImAction.RENAME, channelId)
    error.value = null
    try {
      await renameChannel(channelId, name)
      await fetchChannels(true)
    } catch (e) {
      error.value = e.message
    } finally {
      endAction(ImAction.RENAME)
    }
  }

  async function handleBind(sessionId, channelId, params = {}) {
    if (!sessionId || !channelId) return null
    _activeSessionId.value = sessionId
    beginAction(ImAction.BIND, channelId)
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
      _nextStateVersion()
      bindingState.value = data
      initRequired.value = null
      await fetchChannels(true)
      return data
    } catch (e) {
      if (sessionId === _activeSessionId.value) {
        error.value = e.message
      }
      return null
    } finally {
      endAction(ImAction.BIND)
    }
  }

  async function handleComplete(sessionId, channelId, params = {}) {
    if (!sessionId || !channelId) return null
    beginAction(ImAction.COMPLETE, channelId)
    error.value = null
    try {
      const data = await completeBinding(sessionId, channelId, params)
      if (sessionId === _activeSessionId.value) {
        _nextStateVersion()
        bindingState.value = data
      }
      await fetchChannels(true)
      return data
    } catch (e) {
      if (sessionId === _activeSessionId.value) {
        error.value = e.message
      }
      return null
    } finally {
      endAction(ImAction.COMPLETE)
    }
  }

  /**
   * @param {string} action Distinguishes a plain unbind from the unbind half of
   *   a channel switch, so only the button the user pressed shows a spinner.
   */
  async function handleUnbind(sessionId, action = ImAction.UNBIND) {
    if (!sessionId) return false
    beginAction(action, bindingState.value?.channel_id || '')
    error.value = null
    try {
      await unbindIm(sessionId)
      if (sessionId === _activeSessionId.value) {
        _nextStateVersion()
        bindingState.value = null
        syncResult.value = null
        deliveryOverview.value = null
      }
      await fetchChannels(true)
      return true
    } catch (e) {
      if (sessionId === _activeSessionId.value) {
        error.value = e.message
      }
      return false
    } finally {
      endAction(action)
    }
  }

  /**
   * Apply an ``im_unbound`` broadcast. The event itself is the whole truth, so
   * there is nothing to re-read for the binding — only the channel list, whose
   * instance rows carry the now-cleared session link.
   */
  async function handleRemoteUnbind(sessionId) {
    if (isPending(ImAction.UNBIND) || isPending(ImAction.SWITCH) || isPending(ImAction.BIND)) {
      return
    }
    if (sessionId === _activeSessionId.value) {
      _nextStateVersion()
      bindingState.value = null
      error.value = null
      initRequired.value = null
      syncResult.value = null
      deliveryOverview.value = null
    }
    await fetchChannels(true)
  }

  async function handleInitialize(channelId, params = {}) {
    beginAction(ImAction.INITIALIZE, channelId)
    error.value = null
    try {
      const data = await initializeChannel(channelId, params)
      if (data?.init_status === 'error' && data?.error_message) {
        error.value = data.error_message
      }
      await fetchChannels(true)
      return data
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      endAction(ImAction.INITIALIZE)
    }
  }

  async function handleResetChannel(channelId) {
    beginAction(ImAction.RESET, channelId)
    error.value = null
    try {
      await resetChannel(channelId)
      await fetchChannels(true)
    } catch (e) {
      error.value = e.message
    } finally {
      endAction(ImAction.RESET)
    }
  }

  async function handleSyncContext(sessionId) {
    if (!sessionId) return null
    beginAction(ImAction.SYNC)
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
      endAction(ImAction.SYNC)
    }
  }

  async function fetchDeliveries(sessionId) {
    if (!sessionId) return null
    try {
      const data = await getDeliveries(sessionId)
      if (sessionId === _activeSessionId.value) {
        deliveryOverview.value = data || null
      }
      return data
    } catch {
      // Delivery health is auxiliary — a failed read must not break the dialog.
      if (sessionId === _activeSessionId.value) {
        deliveryOverview.value = null
      }
      return null
    }
  }

  async function handleRetryDelivery(sessionId, kind, deliveryId) {
    if (!sessionId || !deliveryId) return false
    beginAction(ImAction.RETRY_DELIVERY, String(deliveryId))
    error.value = null
    try {
      const data = await retryDelivery(sessionId, kind, deliveryId)
      await fetchDeliveries(sessionId)
      return !!data?.requeued
    } catch (e) {
      if (sessionId === _activeSessionId.value) {
        error.value = e.message
      }
      return false
    } finally {
      endAction(ImAction.RETRY_DELIVERY)
    }
  }

  /** Apply an ``im_delivery_update`` broadcast: refresh the delivery view. */
  async function handleRemoteDeliveryUpdate(sessionId) {
    if (sessionId !== _activeSessionId.value) return
    await fetchDeliveries(sessionId)
  }

  function clearInitRequired() {
    initRequired.value = null
  }

  function clearSyncResult() {
    syncResult.value = null
  }

  function resetState() {
    _nextStateVersion()
    bindingState.value = null
    error.value = null
    initRequired.value = null
    syncResult.value = null
    deliveryOverview.value = null
  }

  return {
    bindingState,
    statusLoading,
    pendingAction,
    pendingChannelId,
    isPending,
    error,
    availableChannels,
    initRequired,
    syncResult,
    deliveryOverview,
    isBound,
    isBinding,
    hasChannels,
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
    handleRemoteUnbind,
    handleInitialize,
    handleResetChannel,
    handleSyncContext,
    fetchDeliveries,
    handleRetryDelivery,
    handleRemoteDeliveryUpdate,
    clearInitRequired,
    clearSyncResult,
    resetState,
  }
}
