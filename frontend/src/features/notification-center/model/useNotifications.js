import { ref, computed } from 'vue'

const HALF_DAY_MS = 12 * 60 * 60 * 1000
let nextId = 1

export const NOTIFICATION_TYPE = Object.freeze({
  ERROR: 'error',
  AUTH_REQUIRED: 'auth_required',
})

// Module-level singleton state
const notifications = ref([])

export function useNotifications() {
  const unreadCount = computed(() =>
    notifications.value.filter(n => !n.read).length
  )

  function addNotification({ sessionId, sessionName, projectName, type, message = '' }) {
    if (!Object.values(NOTIFICATION_TYPE).includes(type)) return
    clearExpired()
    notifications.value.unshift({
      id: nextId++,
      sessionId,
      sessionName: sessionName || 'Unnamed session',
      projectName: projectName || '',
      type,
      message,
      timestamp: Date.now(),
      read: false,
    })
  }

  function markAsRead(id) {
    const n = notifications.value.find(n => n.id === id)
    if (n) n.read = true
  }

  function markAllAsRead() {
    for (const n of notifications.value) {
      n.read = true
    }
  }

  function clearExpired() {
    const cutoff = Date.now() - HALF_DAY_MS
    notifications.value = notifications.value.filter(n => n.timestamp > cutoff)
  }

  return {
    notifications,
    unreadCount,
    addNotification,
    markAsRead,
    markAllAsRead,
  }
}
