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
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
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

.working-sessions-btn:hover {
  background: var(--layer-active);
  border-color: var(--accent);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.working-sessions-btn:active {
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
