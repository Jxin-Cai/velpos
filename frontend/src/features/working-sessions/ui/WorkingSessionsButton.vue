<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useWorkingSessions } from '../model/useWorkingSessions'
import { useDialogManager } from '@shared/lib/useDialogManager'
import WorkingSessionsPanel from './WorkingSessionsPanel.vue'

const emit = defineEmits(['navigate'])

const { workingCount } = useWorkingSessions()
const showPanel = ref(false)

// 使用全局弹窗管理器
const { useDialog } = useDialogManager()
useDialog('working-sessions', showPanel)

function togglePanel() {
  showPanel.value = !showPanel.value
}

function handleNavigate(sessionId) {
  emit('navigate', sessionId)
}

function handleClickOutside(e) {
  const el = e.target.closest('.working-sessions-wrapper')
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
  <div class="working-sessions-wrapper">
    <button
      class="working-sessions-btn"
      @click="togglePanel"
      aria-label="Working sessions"
      title="Working sessions"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2v4"/>
        <path d="M12 18v4"/>
        <path d="M4.93 4.93l2.83 2.83"/>
        <path d="M16.24 16.24l2.83 2.83"/>
        <path d="M2 12h4"/>
        <path d="M18 12h4"/>
        <path d="M4.93 19.07l2.83-2.83"/>
        <path d="M16.24 7.76l2.83-2.83"/>
      </svg>
      <span v-if="workingCount > 0" class="badge">{{ workingCount > 9 ? '9+' : workingCount }}</span>
    </button>
    <WorkingSessionsPanel
      v-if="showPanel"
      @navigate="handleNavigate"
      @close="showPanel = false"
    />
  </div>
</template>

<style scoped>
.working-sessions-wrapper {
  position: relative;
}

.working-sessions-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.working-sessions-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
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
  background: var(--yellow, #f59e0b);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  pointer-events: none;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
</style>
