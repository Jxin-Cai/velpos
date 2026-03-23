<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: String,
  session: Object,
  error: String,
})

const projectDirName = computed(() => {
  const dir = props.session?.project_dir
  if (!dir) return ''
  return dir.split('/').filter(Boolean).pop() || dir
})

const modelDisplayName = computed(() => {
  const m = props.session?.model || ''
  if (m.includes('sonnet')) return 'Sonnet'
  if (m.includes('opus')) return 'Opus'
  if (m.includes('haiku')) return 'Haiku'
  return m
})

const statusConfig = {
  disconnected: { label: 'Disconnected', color: 'var(--text-muted)' },
  connecting: { label: 'Connecting...', color: 'var(--yellow)' },
  idle: { label: 'Ready', color: 'var(--green)' },
  running: { label: 'Running', color: 'var(--accent)' },
  error: { label: 'Error', color: 'var(--red)' },
}
</script>

<template>
  <div class="status-bar">
    <div class="status-item session-info" v-if="session">
      <span class="status-label">Session</span>
      <span class="status-value mono">{{ session.session_id }}</span>
    </div>
    <div class="status-item session-info" v-if="session">
      <span class="status-label">Model</span>
      <span class="status-value mono" :title="session.model">{{ modelDisplayName }}</span>
    </div>
    <div class="status-item session-info" v-if="session?.project_dir" :title="session.project_dir">
      <span class="status-label">Project</span>
      <span class="status-value project-dir">{{ projectDirName }}</span>
    </div>
    <div class="status-item">
      <span
        class="status-dot"
        :class="{ pulse: status === 'running' }"
        :style="{ background: statusConfig[status]?.color || 'var(--text-muted)' }"
      ></span>
      <span
        class="status-value"
        :style="{ color: statusConfig[status]?.color || 'var(--text-muted)' }"
      >
        {{ statusConfig[status]?.label || status }}
      </span>
    </div>
    <div class="status-item error-item" v-if="error">
      <span class="status-value" style="color: var(--red)">{{ error }}</span>
    </div>
  </div>
</template>

<style scoped>
.status-bar {
  display: flex;
  align-items: center;
  gap: 20px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.status-label {
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-size: 10px;
  font-weight: 600;
}

.status-value {
  color: var(--text-secondary);
}

.status-value.mono {
  font-family: var(--font-mono);
  font-size: 11px;
}

.status-value.project-dir {
  font-family: var(--font-mono);
  font-size: 11px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.pulse {
  animation: pulse 1.5s ease-in-out infinite;
}

.error-item {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@media (max-width: 768px) {
  .session-info {
    display: none;
  }
}
</style>
