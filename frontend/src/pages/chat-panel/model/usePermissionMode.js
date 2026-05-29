import { ref, watch } from 'vue'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys'

const permModes = [
  { value: 'default', label: 'Default' },
  { value: 'acceptEdits', label: 'Accept' },
  { value: 'plan', label: 'Plan' },
  { value: 'bypassPermissions', label: 'Bypass' },
]

function _permStorageKey(sessionId) {
  return sessionId ? `pf_perm_mode_${sessionId}` : null
}

/**
 * Composable that encapsulates permission mode state and logic.
 *
 * @param {import('vue').Ref} session - reactive session object
 * @param {import('vue').Ref} currentSessionId - reactive current session ID
 * @param {import('vue').Ref} wsConnection - reactive WebSocket connection
 */
export function usePermissionMode({ session, currentSessionId, wsConnection }) {
  const showPermMenu = ref(false)
  const currentPermMode = ref('bypassPermissions')
  let _permSyncedForSession = null

  // localStorage is authoritative (user's explicit choice).
  // Backend value is only used as seed when no local record exists.
  watch(session, (s) => {
    if (!s) return
    const key = _permStorageKey(s.session_id)
    const stored = key && localStorage.getItem(key)
    if (stored) {
      if (currentPermMode.value !== stored) {
        currentPermMode.value = stored
      }
      if (_permSyncedForSession !== s.session_id && wsConnection.value) {
        wsConnection.value.send({ action: 'set_permission_mode', mode: stored })
        _permSyncedForSession = s.session_id
      }
    } else if (s.permission_mode) {
      currentPermMode.value = s.permission_mode
      if (key) localStorage.setItem(key, s.permission_mode)
    }
  }, { immediate: true })

  function getPermLabel(value) {
    const found = permModes.find(m => m.value === value)
    return found ? found.label : value
  }

  // Get color class for permission mode (matching CC CLI colors)
  function getPermColorClass(value) {
    switch (value) {
      case 'acceptEdits': return 'perm-purple'
      case 'plan': return 'perm-green'
      case 'bypassPermissions': return 'perm-red'
      default: return 'perm-gray'
    }
  }

  function handlePermSelect(mode) {
    showPermMenu.value = false
    currentPermMode.value = mode
    const key = _permStorageKey(currentSessionId.value)
    if (key) localStorage.setItem(key, mode)
    if (wsConnection.value) {
      wsConnection.value.send({ action: 'set_permission_mode', mode })
    }
  }

  // Cycle through permission modes with Shift+Tab
  function cyclePermissionMode() {
    const currentIndex = permModes.findIndex(m => m.value === currentPermMode.value)
    const nextIndex = (currentIndex + 1) % permModes.length
    const nextMode = permModes[nextIndex].value
    handlePermSelect(nextMode)
  }

  // Global shortcut for cycling permission modes
  useGlobalHotkeys({
    keys: 'Shift+Tab',
    handler: (event) => {
      cyclePermissionMode()
      return false // Prevent default behavior
    },
    priority: 50
  })

  return {
    showPermMenu,
    currentPermMode,
    permModes,
    getPermLabel,
    getPermColorClass,
    handlePermSelect,
    cyclePermissionMode,
  }
}
