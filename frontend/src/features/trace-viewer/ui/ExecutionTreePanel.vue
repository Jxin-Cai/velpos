<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useSession } from '@entities/session'
import { useExecutionTree } from '../model/useExecutionTree'
import ExecutionTreeRow from './ExecutionTreeRow.vue'
import ExecutionDetailViewer from './ExecutionDetailViewer.vue'
import InlineSubagentTree from './InlineSubagentTree.vue'
import ExecutionHotspotTable from './ExecutionHotspotTable.vue'
import {
  ExecutionPresentation,
  buildExecutionTaskRows,
  rankExecutionTasks,
} from '../lib/executionAnalysis'

const props = defineProps({
  runId: { type: String, default: null },
  focusSubagent: { type: Object, default: null },
})
const emit = defineEmits(['summary-change'])

const { currentSessionId } = useSession()
const detailSection = ref(null)
const {
  tree,
  loading,
  error,
  tasks,
  provenance,
  selectedLoopId,
  expandedTasks,
  expandedLoops,
  loadTree,
  loadLoopDetail,
  loadSubagentTree,
  toggleTask,
  toggleLoop,
  toggleInlineSubagent,
  selectLoop,
  getLoopDetail,
  getLoopLoadState,
  getSubagentState,
  getInlineSubagentState,
  NodeStatus,
} = useExecutionTree()

const execFilter = ref('all')
const execPresentation = ref(ExecutionPresentation.FLOW)
let handledFocusRequest = null
const subagentTrail = ref([])
const subagentPresentation = ref(ExecutionPresentation.FLOW)
const subagentSelectedLoopId = ref(null)
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
const displayTasks = computed(() => filteredTasks.value.map((task, index) => ({ ...task, sequence: index + 1 })))
const taskAnalysis = computed(() => buildExecutionTaskRows(displayTasks.value))
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

function subagentsForLoop(loop) {
  if (loop?.subagents?.length) return loop.subagents
  const toolUseIds = new Set(loop?.subagent_tool_use_ids || [])
  if (!toolUseIds.size) return []
  return (tree.value?.subagents || []).filter(subagent => toolUseIds.has(subagent.tool_use_id))
}

function causalityLabel(loops, index) {
  if (index === 0) return null
  const prev = loops[index - 1]
  const names = prev?.tool_names || []
  if (!names.length) return null
  const display = names.slice(0, 3).join(', ')
  return names.length > 3 ? `Receives results from: ${display} +${names.length - 3}` : `Receives results from: ${display}`
}

function formatDuration(ms) {
  const value = Math.max(Number(ms) || 0, 0)
  if (value < 1000) return `${value}ms`
  if (value < 60000) return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)}s`
  return `${Math.floor(value / 60000)}m ${Math.round((value % 60000) / 1000)}s`
}

function formatTokens(value) {
  const number = Math.max(Number(value) || 0, 0)
  if (number >= 1000000) return `${(number / 1000000).toFixed(1)}m`
  if (number >= 1000) return `${(number / 1000).toFixed(1)}k`
  return String(number)
}

function openSubagent(subagent, resetTrail = false) {
  if (!subagent?.span_id) return
  subagentSelectedLoopId.value = null
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
  subagentSelectedLoopId.value = loopId
  const spanId = focusedSubagent.value?.span_id
  const state = getLoopLoadState(loopId, spanId)
  if (state === NodeStatus.IDLE || state === NodeStatus.ERROR) loadLoopDetail(loopId, spanId)
}

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
  const subagent = (tree.value.subagents || []).find(item => item.span_id === request.spanId)
  if (subagent) {
    handledFocusRequest = requestKey
    openSubagent(subagent, true)
  }
}, { immediate: true })

watch(tree, (value) => {
  emit('summary-change', { tree: value })
}, { immediate: true })

watch(selectedLoopId, async (loopId) => {
  if (!loopId) return
  await nextTick()
  if (window.matchMedia('(max-width: 899px)').matches) {
    detailSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
})
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
        <template v-else-if="focusedSubagentTree">
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

          <nav class="exec-presentation-bar subagent-presentation" aria-label="Subagent trace presentation">
            <button type="button" class="exec-presentation-btn" :class="{ active: subagentPresentation === ExecutionPresentation.FLOW }" @click="subagentPresentation = ExecutionPresentation.FLOW">Execution chain</button>
            <button type="button" class="exec-presentation-btn" :class="{ active: subagentPresentation === ExecutionPresentation.DURATION }" @click="subagentPresentation = ExecutionPresentation.DURATION">Duration <span aria-hidden="true">↓</span></button>
            <button type="button" class="exec-presentation-btn" :class="{ active: subagentPresentation === ExecutionPresentation.TOKENS }" @click="subagentPresentation = ExecutionPresentation.TOKENS">Tokens <span aria-hidden="true">↓</span></button>
          </nav>

          <div class="subagent-workspace" :class="{ 'has-detail': subagentSelectedLoopId }">
            <div class="subagent-chain">
              <InlineSubagentTree
                v-if="subagentPresentation === ExecutionPresentation.FLOW"
                :tree="focusedSubagentTree"
                :agent-span-id="focusedSubagent.span_id"
                :get-loop-detail="getLoopDetail"
                :get-loop-load-state="getLoopLoadState"
                :load-loop-detail="loadLoopDetail"
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
            <aside v-if="subagentSelectedLoopId" class="exec-detail-section subagent-detail" aria-live="polite">
              <div class="detail-section-header"><span class="detail-section-title">Subagent step {{ focusedSelectedLoop?.sequence || '—' }}</span><button class="detail-close-btn" type="button" aria-label="Close detail" @click="subagentSelectedLoopId = null"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m4 4 8 8M12 4l-8 8"/></svg></button></div>
              <ExecutionDetailViewer
                :loop-id="subagentSelectedLoopId"
                :loop="focusedSelectedLoop"
                :detail="getLoopDetail(subagentSelectedLoopId, focusedSubagent.span_id)"
                :load-state="getLoopLoadState(subagentSelectedLoopId, focusedSubagent.span_id)"
                :provenance="focusedSubagentTree.provenance"
                :agent-span-id="focusedSubagent.span_id"
                :get-inline-subagent-state="getInlineSubagentState"
                :get-loop-detail="getLoopDetail"
                :get-loop-load-state="getLoopLoadState"
                :load-loop-detail="loadLoopDetail"
                @toggle-inline-subagent="toggleInlineSubagent"
              />
            </aside>
          </div>
        </template>
      </section>
      <div v-else class="exec-tree-body" :class="{ 'has-detail': selectedLoopId }">
        <div class="exec-tree-section">
          <section class="message-scope" aria-label="Current user message execution summary">
            <div class="message-scope-mark" aria-hidden="true">
              <svg viewBox="0 0 16 16"><path d="M2.5 3.5h11v7h-6l-3.5 2v-2h-1.5z"/></svg>
            </div>
            <div class="message-scope-content">
              <div class="message-scope-kicker">This message</div>
              <p>{{ requestSummary }}</p>
              <div class="message-scope-stats">
                <span><strong>{{ plannedTaskCount }}</strong> planned tasks</span>
                <span><strong>{{ totalSteps }}</strong> steps</span>
                <span><strong>{{ totalSubagents }}</strong> subagents</span>
                <span :class="{ 'message-stat--error': totalErrors > 0 }"><strong>{{ totalErrors }}</strong> exceptions</span>
              </div>
            </div>
          </section>
          <!-- Filter bar -->
          <div v-if="hasErrors" class="exec-error-actions">
            <nav class="exec-filter-bar" aria-label="Execution filter">
              <button type="button" class="exec-filter-chip" :class="{ active: execFilter === 'all' }" @click="execFilter = 'all'">All</button>
              <button v-if="totalErrors > 0" type="button" class="exec-filter-chip exec-filter-chip--error" :class="{ active: execFilter === 'errors' }" @click="execFilter = 'errors'">
                Errors only
                <span class="filter-count">{{ totalErrors }}</span>
              </button>
            </nav>
          </div>

          <nav class="exec-presentation-bar" aria-label="Agent flow presentation">
            <button type="button" class="exec-presentation-btn" :class="{ active: execPresentation === ExecutionPresentation.FLOW }" @click="execPresentation = ExecutionPresentation.FLOW">Flow</button>
            <button type="button" class="exec-presentation-btn" :class="{ active: execPresentation === ExecutionPresentation.DURATION }" @click="execPresentation = ExecutionPresentation.DURATION">Task duration <span aria-hidden="true">↓</span></button>
            <button type="button" class="exec-presentation-btn" :class="{ active: execPresentation === ExecutionPresentation.TOKENS }" @click="execPresentation = ExecutionPresentation.TOKENS">Task tokens <span aria-hidden="true">↓</span></button>
          </nav>

          <div v-if="execPresentation === ExecutionPresentation.FLOW" class="tree-caption tree-caption--sticky">
            <span>{{ plannedTaskCount ? 'Tasks created for this message' : 'Direct execution for this message' }}</span>
            <span class="tree-count">{{ plannedTaskCount || totalSteps }}</span>
          </div>

          <!-- Main agent tasks -->
          <template v-if="execPresentation === ExecutionPresentation.FLOW">
            <ExecutionTreeRow
              v-for="task in displayTasks"
              :key="task.id"
              :node="task"
              node-type="task"
              :depth="0"
              :expanded="expandedTasks.has(task.id)"
              @toggle="toggleTask(task.id)"
            >
              <template v-for="(loop, loopIndex) in task.loops" :key="loop.id">
              <!-- Causality label between loops -->
              <div v-if="causalityLabel(task.loops, loopIndex)" class="causality-label">
                <span class="causality-arrow" aria-hidden="true">&#x2190;</span>
                {{ causalityLabel(task.loops, loopIndex) }}
              </div>
              <ExecutionTreeRow
                :node="loop"
                node-type="loop"
                :depth="1"
                :expanded="expandedLoops.has(loop.id)"
                :selected="selectedLoopId === loop.id"
                :load-state="getLoopLoadState(loop.id)"
                @select-loop="selectLoop"
                @toggle="toggleLoop"
              >
              <ExecutionTreeRow
                v-for="subagent in subagentsForLoop(loop)"
                :key="subagent.tool_use_id"
                :node="subagent"
                node-type="subagent"
                :depth="2"
                :load-state="getSubagentState(subagent.span_id)?.loading ? 'loading' : 'idle'"
                @open-subagent="openSubagent"
              />
              </ExecutionTreeRow>
              </template>
            </ExecutionTreeRow>
          </template>
          <ExecutionHotspotTable
            v-else
            :rows="rankedTasks"
            :sort-mode="execPresentation"
            :selected-loop-id="selectedLoopId"
            @select-step="selectLoop"
            @select-subagent="openSubagent"
          />
        </div>

        <!-- Loop detail pane -->
        <div v-if="selectedLoopId" ref="detailSection" class="exec-detail-section" aria-live="polite">
          <div class="detail-section-header">
            <span class="detail-section-title">
              Step {{ selectedLoop?.sequence || '—' }} detail
            </span>
            <button class="detail-close-btn" type="button" @click="selectedLoopId = null" aria-label="Close detail">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                <path d="m4 4 8 8M12 4l-8 8" />
              </svg>
            </button>
          </div>
          <ExecutionDetailViewer
            :loop-id="selectedLoopId"
            :loop="selectedLoop"
            :detail="getLoopDetail(selectedLoopId)"
            :load-state="getLoopLoadState(selectedLoopId)"
            :provenance="provenance"
            :get-inline-subagent-state="getInlineSubagentState"
            :get-loop-detail="getLoopDetail"
            :get-loop-load-state="getLoopLoadState"
            :load-loop-detail="loadLoopDetail"
            @toggle-inline-subagent="toggleInlineSubagent"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.exec-tree-panel {
  display: flex;
  flex-direction: column;
  flex: 0 0 auto;
  min-height: auto;
  overflow: visible;
}
.subagent-drilldown { min-width: 0; padding: 8px 10px 24px; }
.subagent-drilldown-header { position: sticky; z-index: 4; top: 0; min-height: 46px; display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 7px 10px; border: 1px solid var(--border-subtle); border-radius: 9px 9px 0 0; background: color-mix(in srgb, var(--bg-secondary) 94%, var(--dialog-surface)); }
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
.subagent-overview { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 16px; border: 1px solid var(--border-subtle); border-top: 0; background: color-mix(in srgb, var(--text-accent) 4%, var(--bg-primary)); }
.subagent-identity { min-width: 0; display: flex; align-items: center; gap: 11px; }
.subagent-avatar { width: 38px; height: 38px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 10px; background: color-mix(in srgb, var(--text-accent) 12%, var(--bg-secondary)); color: var(--text-accent); }
.subagent-avatar svg { width: 19px; fill: none; stroke: currentColor; stroke-width: 1.35; }
.subagent-identity small { color: var(--text-accent); font-family: var(--font-mono); font-size: 8px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.subagent-identity h3 { margin: 2px 0; color: var(--text-primary); font-size: 15px; }
.subagent-identity code { color: var(--text-tertiary); font-size: 9px; }
.subagent-stats { display: grid; grid-template-columns: repeat(4, minmax(66px, auto)); margin: 0; }
.subagent-stats div { padding: 5px 11px; border-left: 1px solid var(--border-subtle); }
.subagent-stats dt { color: var(--text-tertiary); font-size: 8px; letter-spacing: .05em; text-transform: uppercase; }
.subagent-stats dd { margin: 3px 0 0; color: var(--text-primary); font-family: var(--font-mono); font-size: 11px; font-weight: 650; }
.subagent-presentation { margin-left: 0; }
.subagent-workspace { display: grid; grid-template-columns: minmax(0, 1fr); align-items: start; }
.subagent-workspace.has-detail { grid-template-columns: minmax(360px, .85fr) minmax(480px, 1.35fr); }
.subagent-chain { min-width: 0; }
.subagent-chain :deep(.inline-subagent-container) { margin-top: 0; }
.subagent-detail { min-width: 0; }
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
.exec-error-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px; padding: 6px 10px 2px; }
.exec-presentation-bar { display: inline-flex; align-self: flex-start; gap: 3px; margin: 8px 10px 3px; padding: 3px; border: 1px solid var(--border-subtle); border-radius: 7px; background: var(--bg-secondary); }
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
.causality-label { display: flex; align-items: center; gap: 5px; padding: 2px 10px 2px 52px; color: var(--text-tertiary); font-size: 10px; font-style: italic; }
.causality-arrow { color: var(--text-accent); font-style: normal; font-weight: 600; }
.exec-spinner { width: 16px; height: 16px; border: 1.5px solid var(--border); border-top-color: var(--text-secondary); border-radius: 50%; animation: exec-panel-spin 700ms linear infinite; }
.exec-tree-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-height: auto;
  overflow: visible;
  align-items: start;
}
.exec-tree-section {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  overflow: visible;
  padding: 0 10px 20px 4px;
  scrollbar-gutter: stable;
}
.message-scope {
  position: relative;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 11px;
  margin: 8px 8px 4px;
  padding: 13px 14px 13px 12px;
  border: 1px solid color-mix(in srgb, var(--text-accent) 24%, var(--border-subtle));
  border-radius: 10px;
  background: color-mix(in srgb, var(--text-accent) 4%, var(--bg-primary));
}
.message-scope::after {
  position: absolute;
  bottom: -13px;
  left: 28px;
  width: 1px;
  height: 13px;
  background: color-mix(in srgb, var(--text-accent) 36%, var(--border-subtle));
  content: '';
}
.message-scope-mark {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--text-accent) 13%, var(--bg-secondary));
  color: var(--text-accent);
}
.message-scope-mark svg { width: 15px; fill: none; stroke: currentColor; stroke-width: 1.35; }
.message-scope-content { min-width: 0; }
.message-scope-kicker { color: var(--text-accent); font-family: var(--font-mono); font-size: 9px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.message-scope p { display: -webkit-box; margin: 4px 0 9px; overflow: hidden; color: var(--text-primary); font-size: 12px; line-height: 1.5; white-space: pre-wrap; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.message-scope-stats { display: flex; flex-wrap: wrap; gap: 6px 14px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; }
.message-scope-stats strong { color: var(--text-secondary); font-weight: 650; }
.tree-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 34px;
  padding: 6px 10px 8px;
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.tree-caption--sticky {
  position: sticky;
  z-index: 2;
  top: 0;
  background: var(--dialog-surface);
}
.tree-count {
  padding: 2px 7px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--bg-secondary);
  letter-spacing: 0;
  text-transform: none;
}
.exec-detail-section {
  min-width: 0;
  overflow: visible;
  border-left: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--bg-secondary) 45%, var(--dialog-surface));
  scrollbar-gutter: stable;
}
.detail-section-header {
  position: sticky;
  z-index: 3;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 42px;
  padding: 8px 16px;
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
  width: 30px;
  height: 30px;
  padding: 0;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: background 120ms ease, color 120ms ease;
}
.detail-close-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.detail-close-btn:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
@media (min-width: 900px) {
  .exec-tree-body.has-detail { grid-template-columns: minmax(360px, 0.85fr) minmax(480px, 1.35fr); }
}
@media (max-width: 899px) {
  .exec-tree-body { overflow-y: auto; }
  .exec-tree-section, .exec-detail-section { overflow: visible; }
  .exec-detail-section { border-top: 1px solid var(--border-subtle); border-left: 0; }
  .tree-caption--sticky, .detail-section-header { position: static; }
  .subagent-workspace.has-detail { grid-template-columns: 1fr; }
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
@media (prefers-reduced-motion: reduce) { .exec-spinner { animation: none; } }
</style>
