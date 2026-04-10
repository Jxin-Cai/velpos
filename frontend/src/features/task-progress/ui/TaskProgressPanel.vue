<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useTaskProgress } from '../model/useTaskProgress'

const emit = defineEmits(['close'])

const { allTasks, taskCounts } = useTaskProgress()

// Tick every second to update elapsed time for running tasks
const now = ref(Date.now())
let timer = null

onMounted(() => {
  timer = setInterval(() => { now.value = Date.now() }, 1000)
})

onBeforeUnmount(() => {
  if (timer) { clearInterval(timer); timer = null }
})

function formatElapsed(startTime) {
  const diff = Math.max(0, now.value - startTime)
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  const remainSecs = secs % 60
  if (mins < 60) return `${mins}m ${remainSecs}s`
  const hrs = Math.floor(mins / 60)
  return `${hrs}h ${mins % 60}m`
}

function truncate(text, max = 80) {
  if (!text || text.length <= max) return text
  return text.slice(0, max) + '...'
}
</script>

<template>
  <div class="task-panel" @click.stop>
    <div class="panel-header">
      <span class="panel-title">Tasks</span>
      <span class="panel-counts">
        <span v-if="taskCounts.running > 0" class="count-badge count-running">{{ taskCounts.running }} running</span>
        <span v-if="taskCounts.completed > 0" class="count-badge count-done">{{ taskCounts.completed }} done</span>
        <span v-if="taskCounts.failed > 0" class="count-badge count-failed">{{ taskCounts.failed }} failed</span>
      </span>
    </div>
    <div class="panel-body">
      <div v-if="allTasks.length === 0" class="empty-state">
        No tasks
      </div>
      <div
        v-for="task in allTasks"
        :key="task.task_id"
        class="task-item"
        :class="'task-' + task.status"
      >
        <div class="task-icon">
          <span v-if="task.status === 'running'" class="task-spinner"></span>
          <svg v-else-if="task.status === 'completed'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </div>
        <div class="task-content">
          <div class="task-desc">{{ task.description || task.task_id }}</div>
          <div class="task-meta" v-if="task.status === 'running'">
            <span v-if="task.last_tool_name" class="task-tool">{{ task.last_tool_name }}</span>
            <span class="task-elapsed">{{ formatElapsed(task.startTime) }}</span>
          </div>
          <div class="task-meta" v-else-if="task.summary">
            <span class="task-summary">{{ truncate(task.summary) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.task-panel {
  position: absolute;
  bottom: calc(100% + 4px);
  left: 0;
  width: 340px;
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
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.panel-counts {
  display: flex;
  gap: 6px;
}

.count-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-weight: 500;
}

.count-running {
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 15%, transparent);
}

.count-done {
  color: var(--green);
  background: color-mix(in srgb, var(--green) 15%, transparent);
}

.count-failed {
  color: var(--red);
  background: color-mix(in srgb, var(--red) 15%, transparent);
}

.panel-body {
  overflow-y: auto;
  max-height: 360px;
  padding: 6px 0;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.task-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 14px;
  transition: background var(--transition-fast);
}

.task-item:hover {
  background: var(--bg-hover);
}

.task-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
}

.task-running .task-icon { color: var(--accent); }
.task-completed .task-icon { color: var(--green); }
.task-failed .task-icon,
.task-stopped .task-icon { color: var(--red); }

.task-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid color-mix(in srgb, var(--accent) 30%, transparent);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: task-spin 0.8s linear infinite;
}

@keyframes task-spin {
  to { transform: rotate(360deg); }
}

.task-content {
  flex: 1;
  min-width: 0;
}

.task-desc {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.4;
  word-break: break-word;
}

.task-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 3px;
  font-size: 11px;
  color: var(--text-muted);
}

.task-tool {
  color: var(--accent);
  font-family: var(--font-mono);
}

.task-elapsed {
  color: var(--text-muted);
}

.task-summary {
  color: var(--text-secondary);
  line-height: 1.3;
}
</style>
