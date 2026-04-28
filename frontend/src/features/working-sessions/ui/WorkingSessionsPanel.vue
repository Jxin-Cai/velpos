<script setup>
import { useWorkingSessions } from '../model/useWorkingSessions'

const emit = defineEmits(['navigate', 'close'])

const { workingList } = useWorkingSessions()

function handleClick(item) {
  emit('navigate', item.sessionId)
  emit('close')
}

function formatElapsed(startTime) {
  const diff = Date.now() - startTime
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ${sec % 60}s`
  const hr = Math.floor(min / 60)
  return `${hr}h ${min % 60}m`
}
</script>

<template>
  <div class="working-panel">
    <div class="panel-header">
      <span class="panel-title">Working Sessions</span>
      <span v-if="workingList.length" class="panel-count">{{ workingList.length }}</span>
    </div>
    <div class="panel-body">
      <div v-if="workingList.length === 0" class="empty-state">
        No active sessions
      </div>
      <div
        v-for="item in workingList"
        :key="item.sessionId"
        class="working-item"
        @click="handleClick(item)"
      >
        <div class="working-dot"></div>
        <div class="working-content">
          <div class="working-name">{{ item.sessionName || item.sessionId.slice(0, 8) }}</div>
          <div class="working-meta">
            <span v-if="item.projectName" class="project-tag">{{ item.projectName }}</span>
            <span class="elapsed">{{ formatElapsed(item.startTime) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.working-panel {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 8px;
  width: 300px;
  max-height: 360px;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-glass);
  z-index: 200;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--glass-border);
  background: var(--layer-glass);
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.panel-count {
  font-size: 11px;
  font-weight: 700;
  color: var(--yellow, #f59e0b);
  background: var(--yellow-dim, rgba(245, 158, 11, 0.1));
  padding: 0 6px;
  border-radius: 8px;
  min-width: 18px;
  text-align: center;
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

.working-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.working-item:hover {
  background: var(--layer-active);
}

.working-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--yellow, #f59e0b);
  flex-shrink: 0;
  margin-top: 5px;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.working-content {
  flex: 1;
  min-width: 0;
}

.working-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 3px;
}

.working-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.project-tag {
  font-size: 10px;
  color: var(--accent);
  background: var(--accent-dim);
  border: 1px solid var(--glass-border);
  padding: 0 5px;
  border-radius: 999px;
  white-space: nowrap;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.elapsed {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
}
</style>
