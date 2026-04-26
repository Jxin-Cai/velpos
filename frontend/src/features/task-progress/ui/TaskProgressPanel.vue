<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useTaskProgress } from '../model/useTaskProgress'

const emit = defineEmits(['close'])

const {
  allTasks, taskCounts, planTasks, planTaskCounts, hasPlanTasks,
  timelineSteps, timelineCounts, hasTimelineSteps,
} = useTaskProgress()

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
  return formatDuration(diff)
}

function formatDuration(ms) {
  const secs = Math.floor(Math.max(0, ms) / 1000)
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

function stepMeta(step) {
  if (step.status === 'running') return formatElapsed(step.startedAt)
  if (step.duration_ms) return formatDuration(step.duration_ms)
  return ''
}

function stepDetail(step) {
  const payload = step.payload || {}
  if (payload.error) return payload.error
  const tools = Array.isArray(payload.last_tool_names) ? payload.last_tool_names.filter(Boolean) : []
  if (tools.length > 0) return tools.join(', ')
  if (payload.last_message_type) return payload.last_message_type
  return ''
}

// Segmented progress: percentage for completed and in_progress
const planProgressCompleted = computed(() => {
  const t = planTaskCounts.value.total
  return t > 0 ? (planTaskCounts.value.completed / t * 100) : 0
})
const planProgressActive = computed(() => {
  const t = planTaskCounts.value.total
  return t > 0 ? (planTaskCounts.value.in_progress / t * 100) : 0
})
</script>

<template>
  <div class="task-panel" @click.stop>
    <!-- Run timeline section -->
    <template v-if="hasTimelineSteps">
      <div class="panel-header">
        <span class="panel-title">Run Timeline</span>
        <span class="panel-counts">
          <span v-if="timelineCounts.running > 0" class="count-badge count-running">{{ timelineCounts.running }} running</span>
          <span v-if="timelineCounts.completed > 0" class="count-badge count-done">{{ timelineCounts.completed }} done</span>
          <span v-if="timelineCounts.failed > 0" class="count-badge count-failed">{{ timelineCounts.failed }} failed</span>
        </span>
      </div>
      <div class="panel-body timeline-body">
        <div
          v-for="step in timelineSteps"
          :key="step.id"
          class="task-item"
          :class="'task-' + step.status"
        >
          <div class="task-icon">
            <span v-if="step.status === 'running'" class="task-spinner"></span>
            <svg v-else-if="step.status === 'completed'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </div>
          <div class="task-content">
            <div class="task-desc">{{ step.title }}</div>
            <div class="task-meta">
              <span v-if="stepDetail(step)" class="task-tool">{{ truncate(stepDetail(step), 70) }}</span>
              <span v-if="stepMeta(step)" class="task-elapsed">{{ stepMeta(step) }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Plan tasks section -->
    <template v-if="hasPlanTasks">
      <div class="panel-header" :class="{ 'panel-header--border': hasTimelineSteps }">
        <span class="panel-title">Plan</span>
        <span class="plan-summary">
          <span class="plan-fraction">{{ planTaskCounts.completed }}<span class="plan-sep">/</span>{{ planTaskCounts.total }}</span>
          <span v-if="planTaskCounts.in_progress > 0" class="count-badge count-running">{{ planTaskCounts.in_progress }} running</span>
        </span>
      </div>
      <!-- Segmented progress bar: green (done) + accent pulse (running) + gray (pending) -->
      <div class="plan-progress-bar">
        <div class="plan-progress-done" :style="{ width: planProgressCompleted + '%' }"></div>
        <div class="plan-progress-active" :style="{ width: planProgressActive + '%' }"></div>
      </div>
      <div class="panel-body plan-body">
        <div
          v-for="(task, index) in planTasks"
          :key="task.id"
          class="plan-item"
          :class="'plan-item--' + task.status"
        >
          <!-- Timeline connector -->
          <div class="plan-rail">
            <div class="plan-connector plan-connector--top" :class="{ 'plan-connector--hidden': index === 0 }"></div>
            <div class="plan-node">
              <span v-if="task.status === 'in_progress'" class="plan-spinner"></span>
              <svg v-else-if="task.status === 'completed'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              <span v-else class="plan-dot"></span>
            </div>
            <div class="plan-connector plan-connector--bottom" :class="{ 'plan-connector--hidden': index === planTasks.length - 1 }"></div>
          </div>
          <!-- Content -->
          <div class="plan-content">
            <div class="plan-label" :class="{ 'plan-label--done': task.status === 'completed' }">
              {{ task.status === 'in_progress' && task.activeForm ? task.activeForm : task.subject }}
            </div>
            <div v-if="task.status === 'in_progress' && task.subject && task.activeForm" class="plan-detail">
              {{ truncate(task.subject, 60) }}
            </div>
          </div>
          <!-- Step number -->
          <span class="plan-step">{{ index + 1 }}</span>
        </div>
      </div>
    </template>

    <!-- Agent tasks section -->
    <div class="panel-header" :class="{ 'panel-header--border': hasPlanTasks || hasTimelineSteps }">
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
  width: 380px;
  max-height: 460px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  z-index: 200;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Header ── */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.panel-header--border {
  border-top: 1px solid var(--border);
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.plan-summary {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plan-fraction {
  font-size: 13px;
  font-weight: 600;
  color: var(--green);
  font-variant-numeric: tabular-nums;
}

.plan-sep {
  color: var(--text-muted);
  font-weight: 400;
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

/* ── Segmented progress bar ── */
.plan-progress-bar {
  height: 3px;
  background: var(--bg-hover);
  flex-shrink: 0;
  display: flex;
}

.plan-progress-done {
  height: 100%;
  background: var(--green);
  transition: width 0.4s var(--ease-smooth);
}

.plan-progress-active {
  height: 100%;
  background: var(--accent);
  transition: width 0.4s var(--ease-smooth);
  animation: bar-pulse 2s ease-in-out infinite;
}

@keyframes bar-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ── Panel body ── */
.panel-body {
  overflow-y: auto;
  max-height: 360px;
  padding: 6px 0;
}

.timeline-body {
  max-height: 180px;
}

.plan-body {
  max-height: 240px;
  padding: 4px 0;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

/* ── Plan item (timeline layout) ── */
.plan-item {
  display: flex;
  align-items: stretch;
  gap: 0;
  padding: 0 14px 0 10px;
  min-height: 32px;
  transition: background var(--transition-fast);
}

.plan-item:hover {
  background: var(--bg-hover);
}

/* Timeline rail: connector + node */
.plan-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 24px;
  flex-shrink: 0;
}

.plan-connector {
  width: 2px;
  flex: 1;
  background: var(--border);
  min-height: 4px;
}

.plan-connector--hidden {
  background: transparent;
}

.plan-item--completed .plan-connector {
  background: var(--green);
}

.plan-item--in_progress .plan-connector--top {
  background: var(--accent);
}

.plan-node {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

/* Status: pending dot */
.plan-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 2px solid var(--text-muted);
  background: transparent;
}

/* Status: in_progress spinner */
.plan-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid color-mix(in srgb, var(--accent) 30%, transparent);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: task-spin 0.8s linear infinite;
}

/* Status: completed check */
.plan-item--completed .plan-node {
  color: var(--green);
}

.plan-item--in_progress .plan-node {
  color: var(--accent);
}

.plan-item--pending .plan-node {
  color: var(--text-muted);
}

/* Content */
.plan-content {
  flex: 1;
  min-width: 0;
  padding: 5px 0;
}

.plan-label {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.4;
  word-break: break-word;
}

.plan-item--in_progress .plan-label {
  font-weight: 600;
  color: var(--accent);
}

.plan-label--done {
  text-decoration: line-through;
  color: var(--text-muted);
  font-weight: 400;
}

.plan-detail {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.3;
  margin-top: 2px;
}

/* Step number */
.plan-step {
  font-size: 10px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
  padding-top: 7px;
  min-width: 14px;
  text-align: right;
}

.plan-item--completed .plan-step {
  color: var(--green);
}

.plan-item--in_progress .plan-step {
  color: var(--accent);
}

/* ── Agent task items ── */
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
