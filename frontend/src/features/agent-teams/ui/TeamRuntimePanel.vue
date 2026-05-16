<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useTeamRuntime } from '../model/useTeamRuntime'
import { getProject } from '@entities/project'
import { useCancellableAsync } from '@shared/lib/useCancellableAsync'
import { formatDuration } from '@features/message-display'
import WorkflowEditor from './WorkflowEditor.vue'

const props = defineProps({
  projectId: { type: String, required: true },
  sessionId: { type: String, required: true },
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['navigate-to-session', 'close'])

const { getTasksForSession, loadTimeline, loadLinkedSessions, getWorkerSessionState, displayStatusFromTaskStatus } = useTeamRuntime()

const tasks = computed(() => getTasksForSession(props.sessionId).value)
const linkedSessions = ref([])
const loading = ref(false)
const teamConfig = ref(null)
const refreshTracker = useCancellableAsync()

const workflowSteps = computed(() => {
  if (!teamConfig.value) return []
  const mode = teamConfig.value.mode || 'delegation'
  return mode === 'delegation'
    ? (teamConfig.value.pipeline || [])
    : (teamConfig.value.members || [])
})

const workflowMode = computed(() => teamConfig.value?.mode || 'delegation')

const displaySessions = computed(() => linkedSessions.value.map(session => {
  const liveState = getWorkerSessionState(session.session_id) || {}
  const displayStatus = liveState.display_status || session.display_status || displayStatusFromTaskStatus(session.task_status) || session.status || 'idle'
  return {
    ...session,
    ...liveState,
    display_status: displayStatus,
    waiting_for_input: liveState.waiting_for_input ?? session.waiting_for_input ?? displayStatus === 'waiting_input',
  }
}))

async function refresh() {
  if (!props.sessionId || !props.projectId) return
  const version = refreshTracker.start()
  loading.value = true
  try {
    await loadTimeline(props.projectId, props.sessionId)
    if (!refreshTracker.isCurrent(version)) return
    linkedSessions.value = await loadLinkedSessions(props.projectId, props.sessionId)
    if (!refreshTracker.isCurrent(version)) return
    try {
      const project = await getProject(props.projectId)
      if (!refreshTracker.isCurrent(version)) return
      teamConfig.value = project?.team_config || null
    } catch {}
  } finally {
    if (refreshTracker.isCurrent(version)) loading.value = false
  }
}

watch(() => props.visible, (val) => {
  if (val) refresh()
})

watch(() => props.sessionId, () => {
  if (props.visible) refresh()
})

onMounted(() => {
  if (props.visible) refresh()
})

const expandedTasks = ref(new Set())

function toggleTaskDetail(taskId) {
  if (expandedTasks.value.has(taskId)) {
    expandedTasks.value.delete(taskId)
  } else {
    expandedTasks.value.add(taskId)
  }
}

function statusIcon(status) {
  const map = {
    pending: '…',
    idle: '○',
    running: '↻',
    waiting_input: '!',
    completed: '✓',
    failed: '×',
    cancelled: '−',
    waiting_for_help: '?',
  }
  return map[status] || '?'
}

function statusLabel(status) {
  const map = {
    pending: 'Pending',
    idle: 'Idle',
    running: 'Running',
    waiting_input: 'Waiting input',
    completed: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
    waiting_for_help: 'Waiting help',
  }
  return map[status] || status
}

function navigateToWorker(session) {
  emit('navigate-to-session', {
    sessionId: session.session_id,
    projectId: session.project_id,
  })
}
</script>

<template>
  <div v-if="visible" class="team-panel">
    <div class="panel-header">
      <h3 class="panel-title">Team Runtime</h3>
      <button class="panel-close" @click="emit('close')" aria-label="Close">&times;</button>
    </div>

    <div class="panel-body">
      <!-- Workflow Visualization -->
      <section v-if="workflowSteps.length > 0" class="panel-section">
        <h4 class="section-title">Workflow</h4>
        <WorkflowEditor
          :mode="workflowMode"
          :steps="workflowSteps"
          :tasks="tasks"
          :editable="false"
        />
      </section>

      <!-- Pipeline / Tasks -->
      <section class="panel-section">
        <h4 class="section-title">Tasks</h4>
        <div v-if="loading && tasks.length === 0" class="loading-text">Loading...</div>
        <div v-else-if="tasks.length === 0" class="empty-text">No tasks dispatched yet</div>
        <div v-else class="task-list">
          <div
            v-for="task in tasks"
            :key="task.task_id"
            class="task-item"
            :class="'task-' + task.status"
            @click="task.result_data && Object.keys(task.result_data).length > 0 && toggleTaskDetail(task.task_id)"
          >
            <span class="task-icon">{{ statusIcon(task.status) }}</span>
            <div class="task-info">
              <span class="task-role">{{ task.target_role }}</span>
              <span class="task-prompt">{{ task.prompt }}</span>
              <span v-if="task.duration_ms" class="task-duration">{{ formatDuration(task.duration_ms) }}</span>
              <div v-if="expandedTasks.has(task.task_id) && task.result_data" class="task-detail">
                <div v-if="task.result_data.files_changed?.length" class="detail-section">
                  <span class="detail-label">Files</span>
                  <ul class="detail-list">
                    <li v-for="f in task.result_data.files_changed" :key="f">{{ f }}</li>
                  </ul>
                </div>
                <div v-if="task.result_data.issues?.length" class="detail-section">
                  <span class="detail-label">Issues</span>
                  <ul class="detail-list detail-list--warn">
                    <li v-for="(issue, i) in task.result_data.issues" :key="i">{{ issue }}</li>
                  </ul>
                </div>
                <div v-if="task.result_data.next_steps?.length" class="detail-section">
                  <span class="detail-label">Next</span>
                  <ul class="detail-list">
                    <li v-for="(step, i) in task.result_data.next_steps" :key="i">{{ step }}</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Linked Sessions -->
      <section class="panel-section">
        <h4 class="section-title">Worker Sessions</h4>
        <div v-if="displaySessions.length === 0" class="empty-text">No linked sessions</div>
        <div v-else class="session-list">
          <div
            v-for="s in displaySessions"
            :key="s.session_id"
            class="session-item"
            :class="'session-' + s.display_status"
            @click="navigateToWorker(s)"
          >
            <span class="session-status-icon">{{ statusIcon(s.display_status) }}</span>
            <span class="session-role">{{ s.role }}</span>
            <span class="session-name">{{ s.name }}</span>
            <span class="session-state">{{ statusLabel(s.display_status) }}</span>
          </div>
        </div>
      </section>
    </div>

    <div class="panel-footer">
      <button class="refresh-btn" @click="refresh" :disabled="loading">
        {{ loading ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.team-panel {
  display: flex;
  flex-direction: column;
  width: 280px;
  height: 100%;
  border-left: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
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
  margin: 0;
}

.panel-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 18px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.panel-close:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.panel-section {
  margin-bottom: 16px;
}

.section-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 8px 0;
}

.loading-text,
.empty-text {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 0;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
}

.task-item.task-running {
  border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
  background: var(--accent-dim);
}

.task-item.task-completed {
  opacity: 0.8;
}

.task-item.task-failed {
  border-color: color-mix(in srgb, var(--red) 40%, var(--border));
}

.task-item.task-waiting_for_help {
  border-color: color-mix(in srgb, var(--yellow, #e5c07b) 40%, var(--border));
  background: color-mix(in srgb, var(--yellow, #e5c07b) 8%, var(--bg-tertiary));
}

.task-icon {
  font-size: 12px;
  flex-shrink: 0;
  margin-top: 1px;
}

.task-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.task-role {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  text-transform: uppercase;
}

.task-prompt {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-duration {
  font-size: 10px;
  color: var(--text-muted);
}

.task-detail {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--border);
}

.detail-section {
  margin-bottom: 4px;
}

.detail-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
}

.detail-list {
  list-style: none;
  padding: 0;
  margin: 2px 0 0 0;
}

.detail-list li {
  font-size: 11px;
  color: var(--text-secondary);
  padding: 1px 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-list--warn li {
  color: var(--yellow, #e5c07b);
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.session-item {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  grid-template-areas:
    "icon role name"
    "icon state state";
  align-items: center;
  gap: 2px 6px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  border: 1px solid transparent;
  transition: background var(--transition-fast), border-color var(--transition-fast);
}

.session-item.session-running {
  border-color: color-mix(in srgb, var(--accent) 36%, transparent);
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}

.session-item.session-waiting_input {
  border-color: color-mix(in srgb, var(--yellow, #e5c07b) 55%, transparent);
  background: color-mix(in srgb, var(--yellow, #e5c07b) 12%, transparent);
}

.session-item.session-completed {
  opacity: 0.82;
}

.session-item.session-failed {
  border-color: color-mix(in srgb, var(--red) 45%, transparent);
  background: var(--red-dim);
}

.session-item.session-cancelled {
  opacity: 0.66;
}

.session-item.session-waiting_input .session-state {
  color: var(--yellow, #e5c07b);
}

.session-item.session-running .session-state {
  color: var(--accent);
}

.session-item.session-completed .session-state {
  color: var(--green);
}

.session-item:hover {
  background: var(--bg-hover);
}

.session-status-icon {
  grid-area: icon;
  font-size: 11px;
  flex-shrink: 0;
}

.session-role {
  grid-area: role;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  flex-shrink: 0;
}

.session-name {
  grid-area: name;
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-state {
  grid-area: state;
  font-size: 10px;
  color: var(--text-muted);
  font-weight: 600;
}

.panel-footer {
  padding: 8px 12px;
  border-top: 1px solid var(--border);
}

.refresh-btn {
  width: 100%;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
