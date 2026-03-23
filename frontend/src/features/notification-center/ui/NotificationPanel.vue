<script setup>
import { useNotifications } from '../model/useNotifications'

const emit = defineEmits(['navigate', 'close'])

const { notifications, unreadCount, markAsRead, markAllAsRead } = useNotifications()

function handleClick(notification) {
  markAsRead(notification.id)
  emit('navigate', notification.sessionId)
  emit('close')
}

function formatTime(ts) {
  const diff = Date.now() - ts
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  return `${Math.floor(diff / 3_600_000)}h ago`
}
</script>

<template>
  <div class="notification-panel">
    <div class="panel-header">
      <span class="panel-title">Notifications</span>
      <button
        v-if="unreadCount > 0"
        class="mark-all-btn"
        @click="markAllAsRead"
      >
        Mark all read
      </button>
    </div>
    <div class="panel-body">
      <div
        v-if="notifications.length === 0"
        class="empty-state"
      >
        No notifications
      </div>
      <div
        v-for="n in notifications"
        :key="n.id"
        class="notification-item"
        :class="{ unread: !n.read }"
        @click="handleClick(n)"
      >
        <div class="notification-dot" :class="n.type" v-if="!n.read"></div>
        <div class="notification-content">
          <div class="notification-title" :class="n.type">
            {{ n.type === 'auth_required' ? 'Waiting for authorization' : 'Query completed' }}
          </div>
          <div class="notification-meta">
            <span class="session-id">{{ n.sessionId.slice(0, 8) }}</span>
            <span class="session-name">{{ n.sessionName }}</span>
            <span v-if="n.projectName" class="project-name">{{ n.projectName }}</span>
          </div>
          <div class="notification-time">{{ formatTime(n.timestamp) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.notification-panel {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 8px;
  width: 320px;
  max-height: 400px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  z-index: 200;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.mark-all-btn {
  font-size: 11px;
  color: var(--accent);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.mark-all-btn:hover {
  background: var(--accent-dim);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.empty-state {
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}

.notification-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.notification-item:hover {
  background: var(--bg-hover);
}

.notification-item.unread {
  background: var(--accent-dim);
}

.notification-item.unread:hover {
  filter: brightness(1.05);
}

.notification-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
  margin-top: 6px;
}

.notification-dot.auth_required {
  background: var(--orange, #f59e0b);
}

.notification-content {
  flex: 1;
  min-width: 0;
}

.notification-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.notification-title.auth_required {
  color: var(--orange, #f59e0b);
}

.session-id {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono, monospace);
}

.notification-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}

.session-name {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 160px;
}

.project-name {
  font-size: 10px;
  color: var(--accent);
  background: var(--accent-dim);
  padding: 0 5px;
  border-radius: 6px;
  white-space: nowrap;
}

.notification-time {
  font-size: 11px;
  color: var(--text-muted);
}
</style>
