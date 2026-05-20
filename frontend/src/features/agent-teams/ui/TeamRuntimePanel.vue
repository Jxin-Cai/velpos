<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useTeamRuntime } from '../model/useTeamRuntime'
import { getProject } from '@entities/project'
import { getWorkspaceDiff } from '@entities/project/api/projectApi'
import { useCancellableAsync } from '@shared/lib/useCancellableAsync'
import { formatDuration } from '@features/message-display'
import { getSessionArtifacts, getTeamTaskDetail, cancelTeamTask, retryTeamTask } from '../api/teamApi'
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
const expandedTasks = ref(new Set())
const taskDetails = ref(new Map())
const taskDetailLoading = ref(new Set())
const taskDetailErrors = ref(new Map())
const taskArtifacts = ref(new Map())
const artifactLoading = ref(new Set())
const artifactErrors = ref(new Map())
const taskDiffs = ref(new Map())
const diffLoading = ref(new Set())
const diffErrors = ref(new Map())

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

function patchSet(refValue, value, present) {
  const next = new Set(refValue.value)
  if (present) next.add(value)
  else next.delete(value)
  refValue.value = next
}

function patchMap(refValue, key, value) {
  const next = new Map(refValue.value)
  if (value === undefined) next.delete(key)
  else next.set(key, value)
  refValue.value = next
}

function taskDetailFor(task) {
  return taskDetails.value.get(task.task_id) || task
}

async function toggleTaskDetail(task) {
  const taskId = task.task_id
  const willOpen = !expandedTasks.value.has(taskId)
  patchSet(expandedTasks, taskId, willOpen)
  if (!willOpen || taskDetails.value.has(taskId) || taskDetailLoading.value.has(taskId)) return

  patchSet(taskDetailLoading, taskId, true)
  patchMap(taskDetailErrors, taskId, undefined)
  try {
    const detail = await getTeamTaskDetail(props.projectId, taskId)
    patchMap(taskDetails, taskId, detail)
  } catch (err) {
    patchMap(taskDetailErrors, taskId, err.message || 'Failed to load task detail')
  } finally {
    patchSet(taskDetailLoading, taskId, false)
  }
}

async function loadArtifacts(task) {
  const detail = taskDetailFor(task)
  const workerSessionId = detail.worker_session_id || task.worker_session_id
  if (!workerSessionId || artifactLoading.value.has(task.task_id)) return
  patchSet(artifactLoading, task.task_id, true)
  patchMap(artifactErrors, task.task_id, undefined)
  try {
    const data = await getSessionArtifacts(workerSessionId)
    patchMap(taskArtifacts, task.task_id, data?.artifacts || data || [])
  } catch (err) {
    patchMap(artifactErrors, task.task_id, err.message || 'Failed to load artifacts')
  } finally {
    patchSet(artifactLoading, task.task_id, false)
  }
}

function normalizeWorkspacePath(path, task) {
  if (!path) return ''
  const value = String(path)
  if (!value.startsWith('/')) return value.replace(/^\.\//, '')
  const detail = taskDetailFor(task)
  const projectDir = detail.target_project_dir || ''
  if (projectDir && value.startsWith(projectDir + '/')) {
    return value.slice(projectDir.length + 1)
  }
  return ''
}

function diffKey(task, path) {
  return `${task.task_id}:${path}`
}

async function loadDiff(task, path) {
  const relativePath = normalizeWorkspacePath(path, task)
  if (!relativePath) return
  const key = diffKey(task, relativePath)
  if (diffLoading.value.has(key)) return
  if (taskDiffs.value.has(key)) {
    patchMap(taskDiffs, key, undefined)
    return
  }
  patchSet(diffLoading, key, true)
  patchMap(diffErrors, key, undefined)
  try {
    const diff = await getWorkspaceDiff(task.target_project_id, relativePath)
    patchMap(taskDiffs, key, diff)
  } catch (err) {
    patchMap(diffErrors, key, err.message || 'Failed to load diff')
  } finally {
    patchSet(diffLoading, key, false)
  }
}

function artifactPath(artifact) {
  return artifact.path || artifact.file_path || artifact.value || ''
}

function copyText(text) {
  if (!text) return
  navigator.clipboard?.writeText(text)
}

function openWorkerForTask(task) {
  const detail = taskDetailFor(task)
  const sessionId = detail.worker_session_id || task.worker_session_id
  if (!sessionId) return
  emit('navigate-to-session', {
    sessionId,
    projectId: detail.target_project_id || task.target_project_id,
  })
}

function formatCost(usd) {
  if (!usd || usd <= 0) return ''
  return usd < 0.01 ? '<$0.01' : `$${usd.toFixed(2)}`
}

function isTaskCancellable(task) {
  return task.status === 'running' || task.status === 'waiting_for_help'
}

const cancellingTasks = ref(new Set())

async function cancelTask(task) {
  if (!isTaskCancellable(task) || cancellingTasks.value.has(task.task_id)) return
  patchSet(cancellingTasks, task.task_id, true)
  try {
    await cancelTeamTask(props.projectId, task.task_id)
  } catch (err) {
    patchMap(taskDetailErrors, task.task_id, err.message || 'Cancel failed')
  } finally {
    patchSet(cancellingTasks, task.task_id, false)
  }
}

function isTaskRetryable(task) {
  return task.status === 'failed' || task.status === 'cancelled'
}

const retryingTasks = ref(new Set())

async function retryTask(task) {
  if (!isTaskRetryable(task) || retryingTasks.value.has(task.task_id)) return
  patchSet(retryingTasks, task.task_id, true)
  try {
    await retryTeamTask(props.projectId, task.task_id)
  } catch (err) {
    patchMap(taskDetailErrors, task.task_id, err.message || 'Retry failed')
  } finally {
    patchSet(retryingTasks, task.task_id, false)
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
          >
            <span class="task-icon">{{ statusIcon(task.status) }}</span>
            <div class="task-info">
              <span class="task-role">{{ task.target_role }}</span>
              <span class="task-prompt">{{ task.prompt }}</span>
              <span v-if="task.duration_ms" class="task-duration">{{ formatDuration(task.duration_ms) }}</span>
              <span v-if="task.cost_usd" class="task-cost">{{ formatCost(task.cost_usd) }}</span>
              <div class="task-actions">
                <button class="task-action" @click="toggleTaskDetail(task)">
                  {{ expandedTasks.has(task.task_id) ? 'Hide' : 'Detail' }}
                </button>
                <button class="task-action" :disabled="!(taskDetailFor(task).worker_session_id || task.worker_session_id)" @click="openWorkerForTask(task)">
                  Worker
                </button>
                <button class="task-action" :disabled="!(taskDetailFor(task).worker_session_id || task.worker_session_id)" @click="loadArtifacts(task)">
                  Artifacts
                </button>
                <button
                  v-if="isTaskCancellable(task)"
                  class="task-action task-action--danger"
                  :disabled="cancellingTasks.has(task.task_id)"
                  @click="cancelTask(task)"
                >
                  {{ cancellingTasks.has(task.task_id) ? 'Cancelling...' : 'Cancel' }}
                </button>
                <button
                  v-if="isTaskRetryable(task)"
                  class="task-action task-action--retry"
                  :disabled="retryingTasks.has(task.task_id)"
                  @click="retryTask(task)"
                >
                  {{ retryingTasks.has(task.task_id) ? 'Retrying...' : 'Retry' }}
                </button>
              </div>
              <div v-if="expandedTasks.has(task.task_id)" class="task-detail">
                <div v-if="taskDetailLoading.has(task.task_id)" class="loading-text">Loading detail...</div>
                <div v-else-if="taskDetailErrors.has(task.task_id)" class="detail-error">{{ taskDetailErrors.get(task.task_id) }}</div>
                <template v-else>
                  <div class="detail-section">
                    <span class="detail-label">Prompt</span>
                    <p class="detail-text">{{ taskDetailFor(task).prompt }}</p>
                  </div>
                  <div v-if="taskDetailFor(task).context" class="detail-section">
                    <span class="detail-label">Context</span>
                    <pre class="detail-pre">{{ taskDetailFor(task).context }}</pre>
                  </div>
                  <div v-if="taskDetailFor(task).result_summary" class="detail-section">
                    <span class="detail-label">Result</span>
                    <p class="detail-text">{{ taskDetailFor(task).result_summary }}</p>
                  </div>
                  <div v-if="taskDetailFor(task).error_message" class="detail-section">
                    <span class="detail-label">Error</span>
                    <p class="detail-error">{{ taskDetailFor(task).error_message }}</p>
                  </div>
                  <div v-if="taskDetailFor(task).result_data?.files_changed?.length" class="detail-section">
                    <span class="detail-label">Files</span>
                    <ul class="detail-list">
                      <li v-for="f in taskDetailFor(task).result_data.files_changed" :key="f" class="file-row">
                        <span>{{ f }}</span>
                        <button
                          v-if="normalizeWorkspacePath(f, task)"
                          class="inline-action"
                          @click="loadDiff(task, f)"
                        >Diff</button>
                      </li>
                    </ul>
                    <div
                      v-for="f in taskDetailFor(task).result_data.files_changed"
                      :key="f + ':diff'"
                      class="diff-block"
                    >
                      <template v-if="normalizeWorkspacePath(f, task) && taskDiffs.has(diffKey(task, normalizeWorkspacePath(f, task)))">
                        <span class="detail-label">Current workspace diff: {{ normalizeWorkspacePath(f, task) }}</span>
                        <pre class="diff-pre">{{ taskDiffs.get(diffKey(task, normalizeWorkspacePath(f, task)))?.patch || taskDiffs.get(diffKey(task, normalizeWorkspacePath(f, task)))?.patch_excerpt || 'No workspace diff for this file' }}</pre>
                      </template>
                      <div v-else-if="normalizeWorkspacePath(f, task) && diffLoading.has(diffKey(task, normalizeWorkspacePath(f, task)))" class="loading-text">Loading diff...</div>
                      <div v-else-if="normalizeWorkspacePath(f, task) && diffErrors.has(diffKey(task, normalizeWorkspacePath(f, task)))" class="detail-error">{{ diffErrors.get(diffKey(task, normalizeWorkspacePath(f, task))) }}</div>
                    </div>
                  </div>
                  <div v-if="taskDetailFor(task).result_data?.issues?.length" class="detail-section">
                    <span class="detail-label">Issues</span>
                    <ul class="detail-list detail-list--warn">
                      <li v-for="(issue, i) in taskDetailFor(task).result_data.issues" :key="i">{{ issue }}</li>
                    </ul>
                  </div>
                  <div v-if="taskDetailFor(task).result_data?.next_steps?.length" class="detail-section">
                    <span class="detail-label">Next</span>
                    <ul class="detail-list">
                      <li v-for="(step, i) in taskDetailFor(task).result_data.next_steps" :key="i">{{ step }}</li>
                    </ul>
                  </div>
                  <div class="detail-section detail-meta">
                    <span>Task {{ taskDetailFor(task).task_id }}</span>
                    <span v-if="taskDetailFor(task).cost_usd">Cost {{ formatCost(taskDetailFor(task).cost_usd) }}</span>
                    <span v-if="taskDetailFor(task).trace_id">Trace {{ taskDetailFor(task).trace_id }}</span>
                    <span v-if="taskDetailFor(task).parent_task_id">Parent {{ taskDetailFor(task).parent_task_id }}</span>
                    <span>Depth {{ taskDetailFor(task).depth || 0 }}</span>
                  </div>
                </template>
                <div v-if="artifactLoading.has(task.task_id)" class="loading-text">Loading artifacts...</div>
                <div v-if="artifactErrors.has(task.task_id)" class="detail-error">{{ artifactErrors.get(task.task_id) }}</div>
                <div v-if="taskArtifacts.has(task.task_id)" class="detail-section">
                  <span class="detail-label">Artifacts</span>
                  <div v-if="taskArtifacts.get(task.task_id).length === 0" class="empty-text">No artifacts found</div>
                  <ul v-else class="detail-list">
                    <li v-for="(artifact, i) in taskArtifacts.get(task.task_id)" :key="i" class="file-row">
                      <span>{{ artifactPath(artifact) || artifact.label || 'artifact' }}</span>
                      <button class="inline-action" @click="copyText(artifactPath(artifact))">Copy</button>
                      <button
                        v-if="normalizeWorkspacePath(artifactPath(artifact), task)"
                        class="inline-action"
                        @click="loadDiff(task, artifactPath(artifact))"
                      >Diff</button>
                    </li>
                  </ul>
                  <div
                    v-for="(artifact, i) in taskArtifacts.get(task.task_id)"
                    :key="i + ':artifact-diff'"
                    class="diff-block"
                  >
                    <template v-if="normalizeWorkspacePath(artifactPath(artifact), task) && taskDiffs.has(diffKey(task, normalizeWorkspacePath(artifactPath(artifact), task)))">
                      <span class="detail-label">Current workspace diff: {{ normalizeWorkspacePath(artifactPath(artifact), task) }}</span>
                      <pre class="diff-pre">{{ taskDiffs.get(diffKey(task, normalizeWorkspacePath(artifactPath(artifact), task)))?.patch || taskDiffs.get(diffKey(task, normalizeWorkspacePath(artifactPath(artifact), task)))?.patch_excerpt || 'No workspace diff for this file' }}</pre>
                    </template>
                    <div v-else-if="normalizeWorkspacePath(artifactPath(artifact), task) && diffLoading.has(diffKey(task, normalizeWorkspacePath(artifactPath(artifact), task)))" class="loading-text">Loading diff...</div>
                    <div v-else-if="normalizeWorkspacePath(artifactPath(artifact), task) && diffErrors.has(diffKey(task, normalizeWorkspacePath(artifactPath(artifact), task)))" class="detail-error">{{ diffErrors.get(diffKey(task, normalizeWorkspacePath(artifactPath(artifact), task))) }}</div>
                  </div>
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

.task-item.task-cancelled {
  opacity: 0.6;
  border-color: var(--border);
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

.task-cost {
  font-size: 10px;
  color: var(--text-muted);
}

.task-action--danger {
  color: var(--red, #e06c75);
}

.task-action--danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--red, #e06c75) 15%, transparent);
}

.task-action--retry {
  color: var(--accent);
}

.task-action--retry:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 15%, transparent);
}

.task-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.task-action,
.inline-action {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 10px;
  padding: 2px 5px;
  cursor: pointer;
}

.task-action:hover:not(:disabled),
.inline-action:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.task-action:disabled,
.inline-action:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.task-detail {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--border);
}

.detail-section {
  margin-bottom: 8px;
}

.detail-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
}

.detail-text,
.detail-error {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-error {
  color: var(--red);
}

.detail-pre,
.diff-pre {
  max-height: 160px;
  overflow: auto;
  margin: 4px 0 0;
  padding: 6px;
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 10px;
  white-space: pre-wrap;
  word-break: break-word;
}

.diff-pre {
  max-height: 220px;
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

.file-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.file-row span {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.diff-block {
  margin-top: 6px;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 10px;
  color: var(--text-muted);
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
