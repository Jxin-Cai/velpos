<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { formatDuration } from '@shared/lib/formatTime'
import { formatTokens } from '@shared/lib/formatNumber'
import { useSession } from '@entities/session'
import { useEscapeToClose } from '@shared/lib/useDialogManager'
import { useExecutionTree } from '../model/useExecutionTree'
import ExecutionTaskList from './ExecutionTaskList.vue'
import ExecutionDetailViewer from './ExecutionDetailViewer.vue'
import ExecutionHotspotTable from './ExecutionHotspotTable.vue'
import SpanPayloadViewer from './SpanPayloadViewer.vue'
import SubagentChainRail from './SubagentChainRail.vue'
import {
  ExecutionPresentation,
  buildExecutionTaskRows,
  buildSubagentChain,
  rankExecutionTasks,
  taskSubagents,
} from '../lib/executionAnalysis'

const props = defineProps({
  runId: { type: String, default: null },
  focusSubagent: { type: Object, default: null },
  // Trace spans can record an agent invocation that the projected tree missed,
  // so both sources feed the chain to keep every delegation visible.
  spanSubagents: { type: Array, default: () => [] },
})
const emit = defineEmits(['summary-change'])

const { currentSessionId } = useSession()
const {
  tree,
  loading,
  error,
  tasks,
  provenance,
  selectedLoopId,
  expandedTasks,
  loadTree,
  loadLoopDetail,
  loadMoreLoopEvents,
  loadSubagentTree,
  toggleTask,
  toggleInlineSubagent,
  selectLoop,
  getLoopDetail,
  getLoopLoadState,
  getSubagentState,
  getInlineSubagentState,
  getLlmRequestForLoop,
  getLlmRequestDetail,
  loadLlmRequestDetail,
  NodeStatus,
} = useExecutionTree()

const selectedLlmRequest = computed(() => (
  selectedLoopId.value ? getLlmRequestForLoop(selectedLoopId.value) : null
))
const selectedLlmRequestState = computed(() => (
  selectedLlmRequest.value ? getLlmRequestDetail(selectedLlmRequest.value.event_id) : null
))

const execFilter = ref('all')
const execPresentation = ref(ExecutionPresentation.FLOW)
let handledFocusRequest = null
const subagentTrail = ref([])
const subagentPresentation = ref(ExecutionPresentation.FLOW)
const subagentSelectedLoopId = ref(null)
const focusedExpandedTasks = reactive(new Set())
const focusedSubagent = computed(() => subagentTrail.value.at(-1) || null)
const focusedSubagentState = computed(() => (
  focusedSubagent.value?.span_id ? getSubagentState(focusedSubagent.value.span_id) : null
))
const focusedSubagentTree = computed(() => focusedSubagentState.value?.tree || null)
const focusedStatus = computed(() => {
  const placeholderStatus = focusedSubagent.value?.status
  if (placeholderStatus && placeholderStatus !== 'unknown') return placeholderStatus
  return focusedSubagentTree.value?.status || 'unknown'
})
const focusedTaskRows = computed(() => buildExecutionTaskRows(focusedSubagentTree.value?.tasks || []))
const focusedRankedTasks = computed(() => rankExecutionTasks(focusedTaskRows.value, subagentPresentation.value))
const focusedDurationMs = computed(() => focusedTaskRows.value.reduce((total, row) => total + row.activeDurationMs, 0))
const focusedTokens = computed(() => focusedTaskRows.value.reduce((total, row) => total + row.tokens, 0))
const focusedStepCount = computed(() => focusedTaskRows.value.reduce((total, row) => total + row.steps.length, 0))
const focusedDisplayTasks = computed(() => (focusedSubagentTree.value?.tasks || []).map((task, index) => ({
  ...task,
  sequence: task.sequence || index + 1,
  subagents: taskSubagents(task, focusedSubagentTree.value?.subagents || []),
})))
const focusedSelectedLoop = computed(() => {
  for (const task of focusedSubagentTree.value?.tasks || []) {
    const loop = (task.loops || []).find(item => item.id === subagentSelectedLoopId.value)
    if (loop) return loop
  }
  return null
})

const selectedLoop = computed(() => {
  if (!selectedLoopId.value) return null
  for (const task of tasks.value) {
    const loop = task.loops?.find(item => item.id === selectedLoopId.value)
    if (loop) return loop
  }
  return null
})

const filteredTasks = computed(() => {
  if (execFilter.value !== 'errors') return tasks.value
  return tasks.value
    .filter(task => (task.error_count || 0) > 0 || (task.loops || []).some(loop => (loop.error_count || 0) > 0))
    .map(task => ({
      ...task,
      loops: (task.loops || []).filter(loop => (loop.error_count || 0) > 0),
    }))
})
const displayTasks = computed(() => filteredTasks.value.map((task, index) => ({
  ...task,
  sequence: index + 1,
  subagents: taskSubagents(task, tree.value?.subagents || []),
})))
const taskAnalysis = computed(() => buildExecutionTaskRows(displayTasks.value, tree.value?.subagents || []))
const rankedTasks = computed(() => rankExecutionTasks(taskAnalysis.value, execPresentation.value))
const plannedTaskCount = computed(() => tasks.value.filter(task => task.explicit).length)
const totalSteps = computed(() => tasks.value.reduce((count, task) => count + (task.loops?.length || 0), 0))
const totalSubagents = computed(() => tasks.value.reduce((count, task) => (
  count + (task.loops || []).reduce((loopCount, loop) => loopCount + (loop.subagent_count || 0), 0)
), 0))
const requestSummary = computed(() => {
  const value = tree.value?.request
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    const text = value.filter(block => block?.type === 'text').map(block => block.text).filter(Boolean).join('\n')
    if (text) return text
  }
  if (value == null) return 'Current user message'
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
})

const totalErrors = computed(() => (
  tasks.value.reduce((count, task) => count + (task.error_count || 0), 0)
  + (tree.value?.error_message ? 1 : 0)
))
const hasErrors = computed(() => totalErrors.value > 0)

const subagentChain = computed(() => buildSubagentChain(
  tasks.value,
  [...(tree.value?.subagents || []), ...props.spanSubagents],
))
const focusedSubagentChain = computed(() => buildSubagentChain(
  focusedSubagentTree.value?.tasks || [],
  focusedSubagentTree.value?.subagents || [],
))

function openSubagentFromChain(subagent) {
  openSubagent(subagent, true)
}

function loopSubagents(loop, roster) {
  if (loop?.subagents?.length) return loop.subagents
  const toolUseIds = new Set(loop?.subagent_tool_use_ids || [])
  if (!toolUseIds.size) return []
  return (roster || []).filter(subagent => toolUseIds.has(subagent.tool_use_id))
}

function subagentsForLoop(loop) {
  return loopSubagents(loop, tree.value?.subagents)
}

function focusedSubagentsForLoop(loop) {
  return loopSubagents(loop, focusedSubagentTree.value?.subagents)
}

function subagentLoadState(subagent) {
  return getSubagentState(subagent?.span_id)?.loading ? NodeStatus.LOADING : NodeStatus.IDLE
}

function focusedLoopLoadState(loopId) {
  return getLoopLoadState(loopId, focusedSubagent.value?.span_id)
}

function toggleFocusedTask(taskId) {
  if (focusedExpandedTasks.has(taskId)) focusedExpandedTasks.delete(taskId)
  else focusedExpandedTasks.add(taskId)
}

function openSubagent(subagent, resetTrail = false) {
  if (!subagent?.span_id) return
  subagentSelectedLoopId.value = null
  focusedExpandedTasks.clear()
  subagentPresentation.value = ExecutionPresentation.FLOW
  if (resetTrail) subagentTrail.value = [subagent]
  else if (focusedSubagent.value?.span_id !== subagent.span_id) subagentTrail.value = [...subagentTrail.value, subagent]
  const state = getSubagentState(subagent.span_id)
  if (!state || state.error) loadSubagentTree(subagent.span_id)
}

function leaveSubagent() {
  subagentSelectedLoopId.value = null
  subagentTrail.value = subagentTrail.value.slice(0, -1)
}

function selectFocusedLoop(loopId) {
  if (subagentSelectedLoopId.value === loopId) {
    subagentSelectedLoopId.value = null
    return
  }
  subagentSelectedLoopId.value = loopId
  const spanId = focusedSubagent.value?.span_id
  const state = getLoopLoadState(loopId, spanId)
  if (state === NodeStatus.IDLE || state === NodeStatus.ERROR) loadLoopDetail(loopId, spanId)
}

const drawerLoopId = computed(() => (
  focusedSubagent.value ? subagentSelectedLoopId.value : selectedLoopId.value
))
const drawerLoop = computed(() => (
  focusedSubagent.value ? focusedSelectedLoop.value : selectedLoop.value
))
const drawerDetail = computed(() => {
  if (!drawerLoopId.value) return null
  return focusedSubagent.value
    ? getLoopDetail(drawerLoopId.value, focusedSubagent.value.span_id)
    : getLoopDetail(drawerLoopId.value)
})
const drawerLoadState = computed(() => {
  if (!drawerLoopId.value) return NodeStatus.IDLE
  return focusedSubagent.value
    ? getLoopLoadState(drawerLoopId.value, focusedSubagent.value.span_id)
    : getLoopLoadState(drawerLoopId.value)
})
const drawerProvenance = computed(() => (
  focusedSubagent.value ? focusedSubagentTree.value?.provenance : provenance.value
))
const drawerTitle = computed(() => {
  const sequence = drawerLoop.value?.sequence || '—'
  return focusedSubagent.value ? `Subagent step ${sequence}` : `Step ${sequence} detail`
})

function closeDetail() {
  if (focusedSubagent.value) subagentSelectedLoopId.value = null
  else selectedLoopId.value = null
}

useEscapeToClose(() => Boolean(drawerLoopId.value), closeDetail, 200)

watch([() => props.runId, currentSessionId], ([runId, sessionId]) => {
  if (runId && sessionId) {
    handledFocusRequest = null
    subagentTrail.value = []
    subagentSelectedLoopId.value = null
    loadTree(sessionId, runId)
  }
}, { immediate: true })

watch([() => props.focusSubagent, tree], ([request]) => {
  if (!request?.spanId || !tree.value) return
  const requestKey = `${request.spanId}:${request.nonce || ''}`
  if (handledFocusRequest === requestKey) return
  const subagent = (tree.value.subagents || []).find(item => item.span_id === request.spanId) || {
    span_id: request.spanId,
    subagent: request.name || 'Subagent',
    is_expandable: true,
  }
  handledFocusRequest = requestKey
  openSubagent(subagent, true)
}, { immediate: true })

watch(tree, (value) => {
  emit('summary-change', { tree: value })
}, { immediate: true })

</script>

<template>
  <div class="exec-tree-panel">
    <div v-if="loading && !tree" class="exec-loading">
      <span class="exec-spinner" aria-hidden="true"></span>
      <span>Loading execution tree...</span>
    </div>

    <div v-else-if="error && !tree" class="exec-error">
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <circle cx="10" cy="10" r="7.25"/><path d="M10 6.5v4.25M10 13.5h.01"/>
      </svg>
      <span>{{ error }}</span>
    </div>

    <template v-else>
      <div v-if="error" class="exec-refresh-warning" role="status">
        {{ error }}. Showing the last available data.
      </div>
      <div v-if="tree?.error_message" class="exec-run-error" role="alert">
        <div class="exec-run-error-title">
          <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <circle cx="10" cy="10" r="7.25"/><path d="M10 6.5v4.25M10 13.5h.01"/>
          </svg>
          <strong>Execution failed</strong>
        </div>
        <p>{{ tree.error_message }}</p>
      </div>
      <div v-if="!tree || tasks.length === 0" class="exec-empty">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/>
          <rect x="9" y="3" width="6" height="4" rx="1"/>
          <path d="M9 12h6M9 16h4"/>
        </svg>
        <p>No execution tasks found for this run</p>
      </div>
      <section v-else-if="focusedSubagent" class="subagent-drilldown" aria-label="Subagent execution trace">
        <header class="subagent-drilldown-header">
          <button type="button" class="subagent-back" @click="leaveSubagent">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m10 3-5 5 5 5"/></svg>
            {{ subagentTrail.length > 1 ? 'Parent agent' : 'Main agent' }}
          </button>
          <div class="subagent-breadcrumb" aria-label="Agent path">
            <span>Main agent</span>
            <template v-for="agent in subagentTrail" :key="agent.span_id"><i aria-hidden="true">/</i><strong>{{ agent.subagent || agent.agent_id || 'Subagent' }}</strong></template>
          </div>
          <span class="subagent-run-status" :class="`status-${focusedStatus}`"><i></i>{{ focusedStatus }}</span>
        </header>

        <div v-if="focusedSubagentState?.loading" class="exec-loading"><span class="exec-spinner" aria-hidden="true"></span><span>Loading subagent trace…</span></div>
        <div v-else-if="focusedSubagentState?.error" class="exec-error">{{ focusedSubagentState.error }}</div>
        <div v-else-if="focusedSubagentTree" class="subagent-workspace">
          <section class="subagent-overview">
            <div class="subagent-identity">
              <span class="subagent-avatar" aria-hidden="true"><svg viewBox="0 0 16 16"><rect x="3" y="4" width="10" height="8" rx="2"/><path d="M8 2v2M6 8h.01M10 8h.01"/></svg></span>
              <div><small>Subagent execution</small><h3>{{ focusedSubagent.subagent || focusedSubagentTree.agent_id || 'Subagent' }}</h3><code>{{ focusedSubagentTree.agent_id }}</code></div>
            </div>
            <dl class="subagent-stats">
              <div><dt>Tasks</dt><dd>{{ focusedTaskRows.length }}</dd></div>
              <div><dt>Steps</dt><dd>{{ focusedStepCount }}</dd></div>
              <div><dt>Active time</dt><dd>{{ formatDuration(focusedDurationMs || focusedSubagent.duration_ms) }}</dd></div>
              <div><dt>Tokens</dt><dd>{{ formatTokens(focusedTokens) }}</dd></div>
            </dl>
          </section>

          <div class="exec-sticky">
            <SubagentChainRail
              :items="subagentChain"
              :active-span-id="focusedSubagent.span_id"
              @open-subagent="openSubagentFromChain"
            />
            <div class="exec-toolbar">
              <nav class="exec-presentation-bar" aria-label="Subagent trace presentation">
                <button type="button" class="exec-presentation-btn" :class="{ active: subagentPresentation === ExecutionPresentation.FLOW }" @click="subagentPresentation = ExecutionPresentation.FLOW">Execution chain</button>
                <button type="button" class="exec-presentation-btn" :class="{ active: subagentPresentation === ExecutionPresentation.DURATION }" @click="subagentPresentation = ExecutionPresentation.DURATION">Duration <span aria-hidden="true">↓</span></button>
                <button type="button" class="exec-presentation-btn" :class="{ active: subagentPresentation === ExecutionPresentation.TOKENS }" @click="subagentPresentation = ExecutionPresentation.TOKENS">Tokens <span aria-hidden="true">↓</span></button>
              </nav>
            </div>
          </div>

          <SubagentChainRail
            :items="focusedSubagentChain"
            label="Nested subagents"
            @open-subagent="openSubagent"
          />

          <div class="subagent-body">
            <div v-if="focusedSubagentTree.request" class="subagent-context-card">
              <div class="context-card-label">
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M3 8h9M8 4l4 4-4 4"/></svg>
                Input from parent
              </div>
              <SpanPayloadViewer :payload="focusedSubagentTree.request" label="Parent prompt" />
            </div>

            <div class="subagent-steps">
              <ExecutionTaskList
                v-if="subagentPresentation === ExecutionPresentation.FLOW"
                :tasks="focusedDisplayTasks"
                :expanded-tasks="focusedExpandedTasks"
                :selected-loop-id="subagentSelectedLoopId"
                :loop-load-state="focusedLoopLoadState"
                :subagents-for-loop="focusedSubagentsForLoop"
                :subagent-load-state="subagentLoadState"
                @toggle-task="toggleFocusedTask"
                @select-loop="selectFocusedLoop"
                @open-subagent="openSubagent"
              />
              <ExecutionHotspotTable
                v-else
                :rows="focusedRankedTasks"
                :sort-mode="subagentPresentation"
                :selected-loop-id="subagentSelectedLoopId"
                @select-step="selectFocusedLoop"
                @select-subagent="openSubagent"
              />
            </div>

            <div v-if="focusedSubagentTree.status && focusedSubagentTree.status !== 'unknown'" class="subagent-context-card context-output">
              <div class="context-card-label">
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M13 8H4M8 4 4 8l4 4"/></svg>
                Returned to parent
              </div>
              <span class="context-status" :class="`context-status--${focusedSubagentTree.status}`">{{ focusedSubagentTree.status }}</span>
              <span v-if="focusedSubagentTree.error_message" class="context-error">{{ focusedSubagentTree.error_message }}</span>
            </div>
          </div>
        </div>
      </section>
      <div v-else class="exec-tree-body">
        <div class="exec-tree-section">
          <slot name="prelude" />

          <section class="message-scope" aria-label="Current user message execution summary">
            <div class="message-scope-mark" aria-hidden="true">
              <svg viewBox="0 0 16 16"><path d="M2.5 3.5h11v7h-6l-3.5 2v-2h-1.5z"/></svg>
            </div>
            <div class="message-scope-content">
              <p :title="requestSummary">{{ requestSummary }}</p>
              <div class="message-scope-stats">
                <span><strong>{{ plannedTaskCount }}</strong> tasks</span>
                <span><strong>{{ totalSteps }}</strong> steps</span>
                <span><strong>{{ totalSubagents }}</strong> subagents</span>
                <span :class="{ 'message-stat--error': totalErrors > 0 }"><strong>{{ totalErrors }}</strong> exceptions</span>
              </div>
            </div>
          </section>

          <!-- Pinned so the delegation chain and the active agent stay readable
               while the reader scrolls through steps. -->
          <div class="exec-sticky">
            <SubagentChainRail :items="subagentChain" @open-subagent="openSubagentFromChain" />
            <div class="exec-toolbar">
              <nav class="exec-presentation-bar" aria-label="Agent flow presentation">
                <button type="button" class="exec-presentation-btn" :class="{ active: execPresentation === ExecutionPresentation.FLOW }" @click="execPresentation = ExecutionPresentation.FLOW">Flow</button>
                <button type="button" class="exec-presentation-btn" :class="{ active: execPresentation === ExecutionPresentation.DURATION }" @click="execPresentation = ExecutionPresentation.DURATION">Task duration <span aria-hidden="true">↓</span></button>
                <button type="button" class="exec-presentation-btn" :class="{ active: execPresentation === ExecutionPresentation.TOKENS }" @click="execPresentation = ExecutionPresentation.TOKENS">Task tokens <span aria-hidden="true">↓</span></button>
              </nav>
              <nav v-if="hasErrors" class="exec-filter-bar" aria-label="Execution filter">
                <button type="button" class="exec-filter-chip" :class="{ active: execFilter === 'all' }" @click="execFilter = 'all'">All</button>
                <button type="button" class="exec-filter-chip exec-filter-chip--error" :class="{ active: execFilter === 'errors' }" @click="execFilter = 'errors'">
                  Errors only
                  <span class="filter-count">{{ totalErrors }}</span>
                </button>
              </nav>
              <span v-if="execPresentation === ExecutionPresentation.FLOW" class="exec-toolbar-count">
                {{ plannedTaskCount ? 'Tasks for this message' : 'Direct execution' }}
                <strong>{{ plannedTaskCount || totalSteps }}</strong>
              </span>
            </div>
          </div>

          <!-- Main agent tasks -->
          <ExecutionTaskList
            v-if="execPresentation === ExecutionPresentation.FLOW"
            :tasks="displayTasks"
            :expanded-tasks="expandedTasks"
            :selected-loop-id="selectedLoopId"
            :loop-load-state="loopId => getLoopLoadState(loopId)"
            :subagents-for-loop="subagentsForLoop"
            :subagent-load-state="subagentLoadState"
            @toggle-task="toggleTask"
            @select-loop="selectLoop"
            @open-subagent="openSubagent"
          />
          <ExecutionHotspotTable
            v-else
            :rows="rankedTasks"
            :sort-mode="execPresentation"
            :selected-loop-id="selectedLoopId"
            @select-step="selectLoop"
            @select-subagent="openSubagent"
          />
        </div>
      </div>
    </template>

    <!-- Deferred because the host lives in the dialog that mounts in the same
         render pass, so it is not queryable yet when this panel mounts. -->
    <Teleport defer to="#trace-detail-drawer-host">
      <Transition name="exec-drawer">
        <aside
          v-if="drawerLoopId"
          class="exec-detail-drawer"
          role="dialog"
          aria-modal="false"
          aria-labelledby="exec-detail-drawer-title"
          aria-live="polite"
        >
          <div class="detail-section-header">
            <span id="exec-detail-drawer-title" class="detail-section-title">{{ drawerTitle }}</span>
            <button class="detail-close-btn" type="button" aria-label="Close detail" @click="closeDetail">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                <path d="m4 4 8 8M12 4l-8 8" />
              </svg>
            </button>
          </div>
          <div class="exec-detail-drawer-body">
            <ExecutionDetailViewer
              :loop-id="drawerLoopId"
              :loop="drawerLoop"
              :detail="drawerDetail"
              :load-state="drawerLoadState"
              :provenance="drawerProvenance"
              :agent-span-id="focusedSubagent?.span_id"
              :llm-request="focusedSubagent ? null : selectedLlmRequest"
              :llm-request-state="focusedSubagent ? null : selectedLlmRequestState"
              :load-llm-request-detail="loadLlmRequestDetail"
              :get-inline-subagent-state="getInlineSubagentState"
              :get-loop-detail="getLoopDetail"
              :get-loop-load-state="getLoopLoadState"
              :load-loop-detail="loadLoopDetail"
              :load-more-events="loadMoreLoopEvents"
              @toggle-inline-subagent="toggleInlineSubagent"
            />
          </div>
        </aside>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.exec-tree-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.subagent-drilldown {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  padding: 6px 10px 0;
}
.subagent-drilldown-header { flex: 0 0 auto; min-height: 42px; display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 7px 10px; border: 1px solid var(--border-subtle); border-radius: 9px 9px 0 0; background: color-mix(in srgb, var(--bg-secondary) 94%, var(--dialog-surface)); }
.subagent-back { min-height: 30px; display: inline-flex; align-items: center; gap: 5px; padding: 5px 8px; border: 1px solid var(--border-subtle); border-radius: 6px; background: var(--bg-primary); color: var(--text-secondary); font-size: 10px; font-weight: 600; cursor: pointer; }
.subagent-back:hover { border-color: var(--text-accent); color: var(--text-accent); }
.subagent-back:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 2px; }
.subagent-breadcrumb { min-width: 0; display: flex; align-items: center; gap: 6px; overflow: hidden; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; white-space: nowrap; }
.subagent-breadcrumb strong { overflow: hidden; color: var(--text-primary); font-weight: 600; text-overflow: ellipsis; }
.subagent-breadcrumb i { color: var(--border); font-style: normal; }
.subagent-run-status { display: inline-flex; align-items: center; gap: 5px; padding: 3px 7px; border-radius: 999px; background: var(--bg-primary); color: var(--text-tertiary); font-size: 9px; text-transform: capitalize; }
.subagent-run-status i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.subagent-run-status.status-completed { color: var(--color-success, #22c55e); }
.subagent-run-status.status-running { color: var(--text-accent); }
.subagent-run-status.status-failed, .subagent-run-status.status-error { color: var(--color-error, #ef4444); }
.subagent-overview { flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 9px 12px; border: 1px solid var(--border-subtle); border-top: 0; background: color-mix(in srgb, var(--text-accent) 4%, var(--bg-primary)); }
.subagent-identity { min-width: 0; display: flex; align-items: center; gap: 10px; }
.subagent-avatar { width: 30px; height: 30px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 9px; background: color-mix(in srgb, var(--text-accent) 12%, var(--bg-secondary)); color: var(--text-accent); }
.subagent-avatar svg { width: 16px; fill: none; stroke: currentColor; stroke-width: 1.35; }
.subagent-identity small { color: var(--text-accent); font-family: var(--font-mono); font-size: 8px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.subagent-identity h3 { margin: 1px 0; color: var(--text-primary); font-size: 13px; }
.subagent-identity code { color: var(--text-tertiary); font-size: 9px; }
.subagent-stats { display: grid; grid-template-columns: repeat(4, minmax(66px, auto)); margin: 0; }
.subagent-stats div { padding: 5px 11px; border-left: 1px solid var(--border-subtle); }
.subagent-stats dt { color: var(--text-tertiary); font-size: 8px; letter-spacing: .05em; text-transform: uppercase; }
.subagent-stats dd { margin: 3px 0 0; color: var(--text-primary); font-family: var(--font-mono); font-size: 11px; font-weight: 650; }
.subagent-workspace { display: flex; flex: 1; flex-direction: column; min-width: 0; min-height: 0; overflow-y: auto; padding-bottom: 20px; scrollbar-gutter: stable; }
.subagent-workspace > * { flex: 0 0 auto; }
.subagent-body { min-width: 0; }
.subagent-steps { min-width: 0; }
.exec-loading, .exec-error, .exec-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 200px;
  color: var(--text-tertiary);
  font-size: 12px;
}
.exec-error { color: var(--color-error, #ef4444); }
.exec-refresh-warning {
  flex: 0 0 auto;
  margin: 8px 14px 0;
  padding: 7px 10px;
  border: 1px solid color-mix(in srgb, var(--color-warning, #f59e0b) 32%, var(--border-subtle));
  border-radius: 7px;
  background: color-mix(in srgb, var(--color-warning, #f59e0b) 7%, var(--bg-primary));
  color: var(--text-secondary);
  font-size: 11px;
}
.exec-run-error {
  flex: 0 0 auto;
  margin: 8px 14px 4px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--color-error, #ef4444) 35%, var(--border-subtle));
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-error, #ef4444) 8%, var(--bg-primary));
  color: var(--color-error, #ef4444);
}
.exec-run-error-title { display: flex; align-items: center; gap: 7px; font-size: 12px; }
.exec-run-error-title svg { flex: 0 0 auto; }
.exec-run-error p {
  margin: 5px 0 0 22px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.5;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.exec-empty p { margin: 0; color: var(--text-secondary); font-size: 13px; }
.exec-presentation-bar { display: inline-flex; align-self: flex-start; gap: 3px; margin: 4px 0 3px; padding: 3px; border: 1px solid var(--border-subtle); border-radius: 7px; background: var(--bg-secondary); }
.exec-presentation-btn { min-height: 28px; padding: 5px 10px; border: 0; border-radius: 5px; background: transparent; color: var(--text-tertiary); font-size: 10px; font-weight: 600; cursor: pointer; }
.exec-presentation-btn:hover { color: var(--text-primary); }
.exec-presentation-btn.active { background: var(--bg-primary); color: var(--text-accent); box-shadow: 0 1px 2px rgba(0,0,0,.08); }
.exec-presentation-btn:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.exec-filter-bar { display: flex; gap: 4px; }
.exec-filter-chip { min-height: 26px; display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px; border: 1px solid var(--border-subtle); border-radius: 5px; background: var(--bg-primary); color: var(--text-tertiary); font-size: 11px; font-weight: 500; cursor: pointer; transition: all 120ms ease; }
.exec-filter-chip:hover { border-color: var(--text-accent); color: var(--text-primary); }
.exec-filter-chip.active { border-color: var(--text-accent); background: color-mix(in srgb, var(--text-accent) 8%, var(--bg-primary)); color: var(--text-accent); font-weight: 600; }
.exec-filter-chip--error.active { border-color: var(--color-error, #ef4444); background: color-mix(in srgb, var(--color-error) 8%, var(--bg-primary)); color: var(--color-error, #ef4444); }
.filter-count { padding: 1px 5px; border-radius: 3px; background: color-mix(in srgb, var(--color-error, #ef4444) 12%, transparent); font-family: var(--font-mono); font-size: 9px; font-weight: 700; }
.message-stat--error, .message-stat--error strong { color: var(--color-error, #ef4444) !important; }
.subagent-context-card { margin: 6px 10px; padding: 8px 10px; border: 1px solid color-mix(in srgb, var(--text-accent) 28%, var(--border-subtle)); border-radius: 7px; background: var(--bg-primary); }
.subagent-context-card.context-output { border-color: color-mix(in srgb, var(--color-success, #22c55e) 28%, var(--border-subtle)); }
.context-card-label { display: flex; align-items: center; gap: 5px; margin-bottom: 6px; color: var(--text-tertiary); font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.context-card-label svg { color: var(--text-accent); }
.context-output .context-card-label svg { color: var(--color-success, #22c55e); }
.context-status { padding: 2px 7px; border-radius: 4px; background: var(--bg-secondary); color: var(--text-secondary); font-size: 11px; font-weight: 500; }
.context-status--completed { color: var(--color-success, #22c55e); }
.context-status--failed { color: var(--color-error, #ef4444); }
.context-error { display: block; margin-top: 5px; color: var(--color-error, #ef4444); font-size: 11px; white-space: pre-wrap; overflow-wrap: anywhere; }
.exec-spinner { width: 16px; height: 16px; border: 1.5px solid var(--border); border-top-color: var(--text-secondary); border-radius: 50%; animation: exec-panel-spin 700ms linear infinite; }
.exec-tree-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.exec-tree-section {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 0 10px 20px 4px;
  scrollbar-gutter: stable;
}
/* Children must keep their natural height; as flex items they would otherwise
   be squeezed once the task list outgrows the scroller. */
.exec-tree-section > * { flex: 0 0 auto; }
.exec-sticky {
  position: sticky;
  z-index: 5;
  top: 0;
  flex: 0 0 auto;
  padding-bottom: 2px;
  background: var(--dialog-surface);
  box-shadow: 0 6px 10px -8px rgba(0, 0, 0, .35);
}
.exec-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  padding: 0 10px 4px;
}
.exec-toolbar-count {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.exec-toolbar-count strong {
  padding: 2px 7px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  letter-spacing: 0;
}
.message-scope {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: 26px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  margin: 6px 8px 4px;
  padding: 7px 11px;
  border: 1px solid color-mix(in srgb, var(--text-accent) 22%, var(--border-subtle));
  border-radius: 9px;
  background: color-mix(in srgb, var(--text-accent) 4%, var(--bg-primary));
}
.message-scope-mark {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 7px;
  background: color-mix(in srgb, var(--text-accent) 13%, var(--bg-secondary));
  color: var(--text-accent);
}
.message-scope-mark svg { width: 13px; fill: none; stroke: currentColor; stroke-width: 1.35; }
.message-scope-content { display: contents; }
.message-scope p {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 11px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.message-scope-stats { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 2px 12px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; white-space: nowrap; }
.message-scope-stats strong { color: var(--text-secondary); font-weight: 650; }
.exec-detail-drawer {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 30;
  display: flex;
  flex-direction: column;
  width: min(1040px, 88%);
  overflow: hidden;
  pointer-events: auto;
  border-left: 1px solid var(--border-subtle);
  background: var(--dialog-surface);
  box-shadow: -16px 0 40px rgba(0, 0, 0, .18);
}
.exec-detail-drawer::before {
  position: absolute;
  top: 50%;
  left: 6px;
  width: 3px;
  height: 36px;
  border-radius: 99px;
  background: color-mix(in srgb, var(--text-tertiary) 45%, transparent);
  transform: translateY(-50%);
  content: '';
  pointer-events: none;
}
.exec-detail-drawer-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  background: color-mix(in srgb, var(--bg-secondary) 45%, var(--dialog-surface));
  scrollbar-gutter: stable;
}
.detail-section-header {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  min-height: 48px;
  padding: 8px 14px 8px 20px;
  border-bottom: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--bg-secondary) 92%, var(--dialog-surface));
}
.detail-section-title {
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.detail-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: background 160ms ease, color 160ms ease;
}
.detail-close-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.detail-close-btn:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.exec-drawer-enter-active,
.exec-drawer-leave-active {
  transition: transform 220ms cubic-bezier(.2, .8, .2, 1);
}
.exec-drawer-enter-from,
.exec-drawer-leave-to {
  transform: translateX(100%);
}
@media (max-width: 899px) {
  .exec-detail-drawer { width: min(100%, calc(100% - 28px)); }
  .subagent-overview { align-items: flex-start; flex-direction: column; }
  .subagent-stats { width: 100%; }
}
@media (max-width: 640px) {
  .subagent-drilldown-header { grid-template-columns: auto minmax(0, 1fr); }
  .subagent-run-status { display: none; }
  .subagent-stats { grid-template-columns: repeat(2, 1fr); }
  .subagent-stats div:nth-child(3) { border-left: 0; }
}
@keyframes exec-panel-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .exec-spinner { animation: none; }
  .exec-drawer-enter-active,
  .exec-drawer-leave-active { transition: none; }
}
</style>
