import { ref, computed } from 'vue'

const HALF_DAY_MS = 12 * 60 * 60 * 1000
const DUPLICATE_WINDOW_MS = 5 * 1000
const STORAGE_KEY = 'vp_notifications_v1'

export const NOTIFICATION_TYPE = Object.freeze({
  ERROR: 'error',
  AUTH_REQUIRED: 'auth_required',
})

function isStorageError(error) {
  return typeof DOMException !== 'undefined' && error instanceof DOMException
}

function normalizeNotifications(value) {
  if (!Array.isArray(value)) return []
  const cutoff = Date.now() - HALF_DAY_MS
  return value.filter(item => (
    item
    && typeof item.id === 'string'
    && typeof item.sessionId === 'string'
    && Object.values(NOTIFICATION_TYPE).includes(item.type)
    && Number.isFinite(item.timestamp)
    && item.timestamp > cutoff
  ))
}

function loadNotifications() {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? normalizeNotifications(JSON.parse(raw)) : []
  } catch (error) {
    if (error instanceof SyntaxError || isStorageError(error)) return []
    throw error
  }
}

function persistNotifications(items) {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  } catch (error) {
    if (isStorageError(error)) return
    throw error
  }
}

function createNotificationId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

// Module-level singleton state
const notifications = ref(loadNotifications())

function mergeWithStoredNotifications() {
  const byId = new Map([
    ...loadNotifications().map(item => [item.id, item]),
    ...notifications.value.map(item => [item.id, item]),
  ])
  return [...byId.values()].sort((a, b) => b.timestamp - a.timestamp)
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key !== STORAGE_KEY) return
    if (!event.newValue) {
      notifications.value = []
      return
    }
    try {
      notifications.value = normalizeNotifications(JSON.parse(event.newValue))
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error
    }
  })
}

export function useNotifications() {
  const unreadCount = computed(() =>
    notifications.value.filter(n => !n.read).length
  )

  function addNotification({ sessionId, sessionName, projectName, type, message = '' }) {
    if (!Object.values(NOTIFICATION_TYPE).includes(type)) return
    clearExpired()

    // Re-read before writing so a recently opened second window does not
    // overwrite alerts created by the first one.
    const merged = mergeWithStoredNotifications()
    const now = Date.now()
    const duplicate = merged.some(item => (
      item.sessionId === sessionId
      && item.type === type
      && item.message === message
      && (
        now - item.timestamp < DUPLICATE_WINDOW_MS
        || (type === NOTIFICATION_TYPE.AUTH_REQUIRED && !item.read)
      )
    ))
    if (duplicate) {
      notifications.value = merged.sort((a, b) => b.timestamp - a.timestamp)
      return
    }

    notifications.value = [{
      id: createNotificationId(),
      sessionId,
      sessionName: sessionName || 'Unnamed session',
      projectName: projectName || '',
      type,
      message,
      timestamp: now,
      read: false,
    }, ...merged].sort((a, b) => b.timestamp - a.timestamp)
    persistNotifications(notifications.value)
  }

  function markAsRead(id) {
    const merged = mergeWithStoredNotifications()
    const n = merged.find(item => item.id === id)
    if (n) {
      n.read = true
      notifications.value = merged
      persistNotifications(merged)
    }
  }

  function markAllAsRead() {
    const merged = mergeWithStoredNotifications()
    for (const n of merged) {
      n.read = true
    }
    notifications.value = merged
    persistNotifications(merged)
  }

  function clearExpired() {
    const cutoff = Date.now() - HALF_DAY_MS
    const merged = mergeWithStoredNotifications()
    const active = merged.filter(n => n.timestamp > cutoff)
    notifications.value = active
    if (active.length !== merged.length) {
      persistNotifications(active)
    }
  }

  return {
    notifications,
    unreadCount,
    addNotification,
    markAsRead,
    markAllAsRead,
  }
}
