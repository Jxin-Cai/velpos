<script setup>
import { ref } from 'vue'
import { useNotifications } from '../model/useNotifications'
import { useDialogManager } from '@shared/lib/useDialogManager'
import { useClickOutside } from '@shared/lib/useClickOutside'
import NotificationPanel from './NotificationPanel.vue'

const emit = defineEmits(['navigate'])

const { unreadCount } = useNotifications()
const showPanel = ref(false)
const wrapperRef = ref(null)

// 使用全局弹窗管理器
const { useDialog } = useDialogManager()
useDialog('notifications', showPanel)

function togglePanel() {
  showPanel.value = !showPanel.value
}

function handleNavigate(sessionId) {
  emit('navigate', sessionId)
}

useClickOutside(wrapperRef, () => { showPanel.value = false }, { event: 'click' })
</script>

<template>
  <div class="notification-wrapper" ref="wrapperRef">
    <button
      class="glass-btn glass-btn--icon notification-bell"
      @click="togglePanel"
      aria-label="Alerts"
      title="Alerts"
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
