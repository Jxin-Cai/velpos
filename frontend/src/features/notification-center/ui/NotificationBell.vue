<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useNotifications } from '../model/useNotifications'
import { useDialogManager } from '@shared/lib/useDialogManager'
import NotificationPanel from './NotificationPanel.vue'

const emit = defineEmits(['navigate'])

const { unreadCount } = useNotifications()
const showPanel = ref(false)

// 使用全局弹窗管理器
const { useDialog } = useDialogManager()
useDialog('notifications', showPanel)

function togglePanel() {
  showPanel.value = !showPanel.value
}

function handleNavigate(sessionId) {
  emit('navigate', sessionId)
}

function handleClickOutside(e) {
  const el = e.target.closest('.notification-wrapper')
  if (!el) showPanel.value = false
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside, true)
})
</script>

<template>
  <div class="notification-wrapper">
    <button
      class="notification-bell"
      @click="togglePanel"
      aria-label="Notifications"
      title="Notifications"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
        <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
      </svg>
      <span v-if="unreadCount > 0" class="badge">{{ unreadCount > 9 ? '9+' : unreadCount }}</span>
    </button>
    <NotificationPanel
      v-if="showPanel"
      @navigate="handleNavigate"
      @close="showPanel = false"
    />
  </div>
</template>

<style scoped>
.notification-wrapper {
  position: relative;
}

.notification-bell {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 32px;
  background: color-mix(in srgb, var(--glass-bg) 36%, transparent);
  border: 1px solid color-mix(in srgb, var(--glass-border) 70%, transparent);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
}

.notification-bell:hover {
  background: var(--layer-active);
  border-color: var(--accent);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.notification-bell:active {
  transform: scale(0.96);
  transition-duration: 100ms;
}

.badge {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  background: var(--red, #ef4444);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  pointer-events: none;
}
</style>
