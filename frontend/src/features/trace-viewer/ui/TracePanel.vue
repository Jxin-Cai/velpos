<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { formatDuration } from '@shared/lib/formatTime'
import { useSession } from '@entities/session'
import { useEscapeToClose } from '@shared/lib/useDialogManager'
import { useTraceTree } from '../model/useTraceTree'
import TraceSpanRow from './TraceSpanRow.vue'
import TraceHotspotTable from './TraceHotspotTable.vue'
import ExecutionTreePanel from './ExecutionTreePanel.vue'
import {
  fetchExecutionEvent,
  fetchExecutionEvents,
  fetchExecutionTree,
  fetchLoopDetail,
  fetchTelemetrySummary,
  fetchTraceTree,
} from '../api/traceApi'
import {
  buildExecutionErrorReport,
  countExecutionErrors,
  downloadExecutionErrorReport,
} from '../lib/executionErrorExport'
import {
  buildExecutionTraceReport,
  downloadExecutionTraceReport,
} from '../lib/executionTraceExport'
import {
  TracePresentation,
  annotateTraceConcurrency,
  buildSubagentRoster,
  buildTraceAnalysis,
  filterTraceRows,
  filterTraceTree,
  flattenTraceNodes,
  isSubagentTraceSpan,
  rankTraceRows,
} from '../lib/traceAnalysis'
import TraceTelemetryStrip from './TraceTelemetryStrip.vue'

const ViewMode = Object.freeze({ EXECUTION: 'execution', RAW_SPAN: 'raw_span', EVENTS: 'events' })
const ERROR_EVENT_NAMES = Object.freeze(new Set(['api_error', 'api_refusal']))
const HIDDEN_EVENT_ATTRIBUTES = Object.freeze(new Set(['event.name', 'event.timestamp', 'event.sequence']))
const EVENT_ATTRIBUTE_LIMIT = 4

const props = defineProps({
  visible: { type: Boolean, default: false },
  initialRunId: { type: String, default: null },
  initialSubagentSpanId: { type: String, default: null },
})

const emit = defineEmits(['close'])
const dialogEl = ref(null)
const traceBodyEl = ref(null)
const isFullscreen = ref(false)
const viewMode = ref(ViewMode.EXECUTION)
const spanFilter = ref('all')
const spanPresentation = ref(TracePresentation.FLOW)
const telemetry = ref(null)
const telemetryLoading = ref(false)
const telemetryError = ref('')
const executionTree = ref(null)
const focusSubagentRequest = ref(null)
const exceptionCount = ref(0)
const exceptionCountLoading = ref(false)
const exporting = ref('')
const exportError = ref('')
const openEventPayloads = reactive(new Set())
const verbatimPayloads = reactive(new Map())
const payloadLoading = reactive(new Set())
const payloadErrors = reactive(new Map())
const eventPayloadTexts = new Map()
let telemetryRequestId = 0
let exceptionRequestId = 0
let handledInitialSubagentFocus = ''

const {
  session: activeSession,
  status: sessionStatus,
  waitingForSlot,
  recovery,
  canceling,
  telemetryVersion,
} = useSession()

useEscapeToClose(() => props.visible, () => emit('close'))

const {
  currentSessionId,
  traceTree,
  runIds,
  selectedRunId,
  stats,
  loading,
  error,
  selectRun,
  loadTraceForRun,
  loadTraceHistory,
} = useTraceTree()

watch(() => props.initialRunId, (id) => {
  if (id) selectRun(id)
}, { immediate: true })

watch(selectedRunId, () => {
  executionTree.value = null
  focusSubagentRequest.value = null
  exceptionCount.value = 0
  exportError.value = ''
})

watch([
  () => props.visible,
  () => props.initialSubagentSpanId,
  selectedRunId,
], ([visible, spanId, runId]) => {
  if (!visible || !spanId || !runId) return
  const requestKey = `${runId}:${spanId}`
  if (handledInitialSubagentFocus === requestKey) return
  handledInitialSubagentFocus = requestKey
  viewMode.value = ViewMode.EXECUTION
  focusSubagentRequest.value = {
    spanId,
    name: 'Subagent',
    nonce: (focusSubagentRequest.value?.nonce || 0) + 1,
  }
}, { immediate: true, flush: 'post' })

watch(() => props.visible, (visible) => {
  if (!visible) handledInitialSubagentFocus = ''
})

watch(viewMode, () => {
  nextTick(() => {
    if (traceBodyEl.value) traceBodyEl.value.scrollTop = 0
  })
})

watch([() => props.visible, currentSessionId], ([visible]) => {
  if (!visible) {
    isFullscreen.value = false
    return
  }
  if (props.initialRunId) selectRun(props.initialRunId)
  loadTraceHistory()
  nextTick(() => dialogEl.value?.focus())
}, { immediate: true })

watch([
  () => props.visible,
  currentSessionId,
  selectedRunId,
  () => stats.value.spanCount,
  () => stats.value.failedCount,
  telemetryVersion,
], async ([visible, sessionId, runId]) => {
  if (!visible || !sessionId || !runId) return
  const requestId = ++telemetryRequestId
  telemetryLoading.value = true
  telemetryError.value = ''
  try {
    const result = await fetchTelemetrySummary(sessionId, runId)
    if (requestId === telemetryRequestId) telemetry.value = result
  } catch (err) {
    if (requestId === telemetryRequestId) {
      telemetryError.value = err?.message || 'Telemetry summary unavailable'
    }
  } finally {
    if (requestId === telemetryRequestId) telemetryLoading.value = false
  }
}, { immediate: true })

const runPosition = computed(() => {
  const index = runIds.value.indexOf(selectedRunId.value)
  return index < 0 ? '' : `${index + 1} / ${runIds.value.length}`
})

const overallStatus = computed(() => {
  if (!stats.value.spanCount) return { label: 'No data', className: 'is-empty' }
  if (stats.value.runningCount) return { label: 'Running', className: 'is-running' }
  if (stats.value.abandonedCount) return { label: 'Partial trace', className: 'is-abandoned' }
  if (stats.value.failedCount) return { label: 'Needs attention', className: 'is-failed' }
  if (stats.value.cancelledCount) return { label: 'Cancelled', className: 'is-cancelled' }
  return { label: 'Completed', className: 'is-completed' }
})

const sessionSubagents = computed(() => buildSubagentRoster(
  flattenTraceNodes(traceTree.value || []).filter(isSubagentTraceSpan),
  executionTree.value?.subagents || [],
))

// Codex-style state separates active blockers from the terminal run outcome.
const sessionState = computed(() => {
  const isLatestRun = runIds.value.length === 0
    || selectedRunId.value === runIds.value[runIds.value.length - 1]
  const pendingRequest = recovery.value?.pending_request
  if (isLatestRun && pendingRequest) {
    const waitsForChoice = pendingRequest.interaction_type === 'user_choice'
    return {
      label: waitsForChoice ? 'Waiting for your answer' : 'Waiting for permission',
      detail: pendingRequest.tool_name || null,
      tone: 'blocked',
      category: 'Needs input',
      action: waitsForChoice ? 'Respond in the session to continue' : 'Review the pending permission request',
    }
  }

  if (isLatestRun && (canceling.value || recovery.value?.cancel_requested)) {
    return { label: 'Cancelling execution', detail: 'Waiting for the active operation to stop', tone: 'warning', category: 'Active', action: 'No action required' }
  }

  if (isLatestRun && waitingForSlot.value) {
    const position = activeSession.value?.slot_queue_position
    return {
      label: activeSession.value?.waiting_reason === 'waiting_session_runner'
        ? 'Waiting for the current session query'
        : 'Waiting for an execution slot',
      detail: position ? `Queue position ${position}` : null,
      tone: 'blocked',
      category: 'Queued',
      action: 'Execution will start automatically',
    }
  }

  if (isLatestRun && sessionStatus.value === 'reconnecting') {
    return { label: 'Connection interrupted', detail: 'Reconnecting to the session', tone: 'warning', category: 'Recovering', action: 'No action required unless reconnection fails' }
  }

  if (isLatestRun && sessionStatus.value === 'compacting') {
    return { label: 'Compacting context', detail: 'Preparing the next model turn', tone: 'active', category: 'Active', action: 'No action required' }
  }

  const spans = traceTree.value || []
  const flatSpans = flattenTraceNodes(spans)
  const running = flatSpans.filter(s => s.status === 'running')
  const latestTool = running
    .filter(s => s.span_type === 'tool_call')
    .sort((a, b) => (b.started_time || '').localeCompare(a.started_time || ''))[0]
  const turnCount = flatSpans.filter(s => s.span_type === 'llm_turn').length
  if (latestTool && isLatestRun && sessionStatus.value === 'running') {
    return {
      label: `Running ${latestTool.name || 'tool'}`,
      detail: turnCount ? `Step ${turnCount}` : null,
      tone: 'active',
      category: 'Active',
      action: 'No action required',
    }
  }
  if (isLatestRun && sessionStatus.value === 'running') {
    return {
      label: running.length ? 'Model working' : 'Starting agent',
      detail: turnCount ? `Step ${turnCount}` : null,
      tone: 'active',
      category: 'Active',
      action: 'No action required',
    }
  }
  if (stats.value.runningCount) {
    return {
      label: 'Trace has no terminal state',
      detail: 'The run is not active, but some spans are still marked running',
      tone: 'warning',
      category: 'Incomplete',
      action: 'Inspect running spans and exporter shutdown',
    }
  }
  const historical = !isLatestRun ? 'Historical run · ' : ''
  if (stats.value.failedCount) {
    return { label: `${historical}Failed`, detail: `${stats.value.failedCount} failed spans`, tone: 'error', category: 'Terminal', action: 'Open Errors or Duration hotspots' }
  }
  if (stats.value.cancelledCount) {
    return { label: `${historical}Interrupted`, detail: `${stats.value.cancelledCount} cancelled spans`, tone: 'warning', category: 'Terminal', action: 'Inspect the last completed step' }
  }
  if (stats.value.abandonedCount) {
    return { label: `${historical}Partial trace`, detail: `${stats.value.abandonedCount} spans lack a terminal event`, tone: 'warning', category: 'Incomplete', action: 'Inspect exporter and session shutdown' }
  }
  if (stats.value.spanCount) {
    return { label: `${historical}Completed`, detail: `${stats.value.turnCount} turns · ${stats.value.toolCallCount} tools`, tone: 'complete', category: 'Terminal', action: 'No action required' }
  }
  return { label: 'No trace data', detail: 'This run has not emitted spans yet', tone: 'neutral', category: 'Unavailable', action: 'Check OpenTelemetry collection' }
})

const traceAnalysis = computed(() => buildTraceAnalysis(traceTree.value || []))
const highLatencyThreshold = computed(() => traceAnalysis.value.thresholds.p90)

const filteredTree = computed(() => {
  return filterTraceTree(traceTree.value, spanFilter.value, highLatencyThreshold.value)
})
const traceConcurrency = computed(() => annotateTraceConcurrency(filteredTree.value))

const rankedTraceRows = computed(() => {
  const filtered = filterTraceRows(traceAnalysis.value.rows, spanFilter.value, highLatencyThreshold.value)
  return rankTraceRows(filtered, spanPresentation.value).slice(0, 50)
})

const traceTiming = computed(() => {
  const spans = flattenTraceNodes(traceTree.value || [])
  const ranges = spans.map((span) => {
    const start = Date.parse(span.started_time || '')
    if (!Number.isFinite(start)) return null
    const explicitEnd = Date.parse(span.ended_time || '')
    const end = Number.isFinite(explicitEnd)
      ? explicitEnd
      : start + Math.max(Number(span.duration_ms) || 0, 0)
    return { start, end: Math.max(end, start) }
  }).filter(Boolean)
  if (!ranges.length) return { startMs: 0, durationMs: 0, ticks: [] }
  const startMs = Math.min(...ranges.map(range => range.start))
  const endMs = Math.max(...ranges.map(range => range.end))
  const durationMs = Math.max(endMs - startMs, 1)
  return {
    startMs,
    durationMs,
    ticks: [0, 0.25, 0.5, 0.75, 1].map(portion => ({
      portion,
      label: formatDuration(Math.round(durationMs * portion)),
    })),
  }
})

function formatEventTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function eventAttributes(payload) {
  return Object.entries(payload?.attributes || {})
    .filter(([key, value]) => value !== '' && value != null && !HIDDEN_EVENT_ATTRIBUTES.has(key))
    .slice(0, EVENT_ATTRIBUTE_LIMIT)
}

const logEventRows = computed(() => (telemetry.value?.recent_events || []).map((event, index) => {
  const payload = event?.payload || {}
  const name = event?.event_name || payload.event_name || 'log'
  return {
    id: event?.event_id || `log-event-${index}`,
    eventId: event?.event_id || '',
    payload,
    truncated: event?.payload_truncated === true,
    eventTime: event?.event_time || '',
    displayTime: formatEventTime(event?.event_time),
    name,
    spanId: payload.span_id || '',
    isError: ERROR_EVENT_NAMES.has(name),
    attributes: eventAttributes(payload),
  }
}))

// An audit payload can carry a whole API request or response body. Serialize one
// only once the reader opens it, and keep the text so unrelated re-renders of
// this panel do not repeat the work for every listed event.
function eventPayloadText(row) {
  const verbatim = verbatimPayloads.get(row.id)
  const cacheKey = verbatim ? `${row.id}:verbatim` : row.id
  if (!eventPayloadTexts.has(cacheKey)) {
    eventPayloadTexts.set(cacheKey, JSON.stringify(verbatim || row.payload, null, 2))
  }
  return eventPayloadTexts.get(cacheKey)
}

async function toggleEventPayload(row, open) {
  if (!open) {
    openEventPayloads.delete(row.id)
    return
  }
  openEventPayloads.add(row.id)
  await loadVerbatimPayload(row)
}

// The list only carries clipped copies of oversized fields, so reading one event
// in full is a separate request instead of a bigger telemetry response.
async function loadVerbatimPayload(row) {
  if (!row.truncated || !row.eventId) return
  if (verbatimPayloads.has(row.id) || payloadLoading.has(row.id)) return
  const sessionId = currentSessionId.value
  if (!sessionId) return

  payloadLoading.add(row.id)
  payloadErrors.delete(row.id)
  try {
    const event = await fetchExecutionEvent(sessionId, row.eventId)
    verbatimPayloads.set(row.id, event?.payload || row.payload)
  } catch (err) {
    payloadErrors.set(row.id, err?.message || 'Failed to load the full payload')
  } finally {
    payloadLoading.delete(row.id)
  }
}

watch(logEventRows, (rows) => {
  const presentIds = new Set(rows.map(row => row.id))
  for (const id of openEventPayloads) {
    if (!presentIds.has(id)) openEventPayloads.delete(id)
  }
  for (const id of verbatimPayloads.keys()) {
    if (!presentIds.has(id)) verbatimPayloads.delete(id)
  }
  for (const id of payloadErrors.keys()) {
    if (!presentIds.has(id)) payloadErrors.delete(id)
  }
  for (const cacheKey of eventPayloadTexts.keys()) {
    if (!presentIds.has(cacheKey.replace(/:verbatim$/, ''))) eventPayloadTexts.delete(cacheKey)
  }
})

function handleExecutionSummary(summary) {
  const nextTree = summary?.tree || null
  if (executionTree.value === nextTree) return
  executionTree.value = nextTree
  exceptionCountLoading.value = Boolean(nextTree)
  if (!nextTree) exceptionCount.value = 0
}

watch([executionTree, currentSessionId, selectedRunId], async ([tree, sessionId, runId]) => {
  const requestId = ++exceptionRequestId
  if (!tree || !sessionId || !runId) {
    exceptionCount.value = 0
    exceptionCountLoading.value = false
    return
  }
  exceptionCountLoading.value = true
  try {
    const count = await countExecutionErrors({
      sessionId,
      runId,
      rootTree: tree,
      fetchTree: fetchExecutionTree,
    })
    if (requestId === exceptionRequestId) exceptionCount.value = count
  } catch (err) {
    if (requestId === exceptionRequestId) {
      exportError.value = err?.message || 'Failed to count nested exceptions'
    }
  } finally {
    if (requestId === exceptionRequestId) exceptionCountLoading.value = false
  }
})

async function resolveExecutionTree() {
  if (executionTree.value) return executionTree.value
  return fetchExecutionTree(currentSessionId.value, selectedRunId.value)
}

async function exportExceptions() {
  if (!currentSessionId.value || !selectedRunId.value || exporting.value) return
  exporting.value = 'exceptions'
  exportError.value = ''
  try {
    const report = await buildExecutionErrorReport({
      sessionId: currentSessionId.value,
      runId: selectedRunId.value,
      rootTree: await resolveExecutionTree(),
      fetchTree: fetchExecutionTree,
      fetchDetail: fetchLoopDetail,
    })
    exceptionCount.value = report.summary.error_count
    downloadExecutionErrorReport(report)
  } catch (err) {
    exportError.value = err?.message || 'Failed to export exceptions'
  } finally {
    exporting.value = ''
  }
}

async function exportFullTrace() {
  if (!currentSessionId.value || !selectedRunId.value || exporting.value) return
  exporting.value = 'trace'
  exportError.value = ''
  try {
    const report = await buildExecutionTraceReport({
      sessionId: currentSessionId.value,
      runId: selectedRunId.value,
      rootTree: await resolveExecutionTree(),
      fetchTree: fetchExecutionTree,
      fetchDetail: fetchLoopDetail,
      fetchTraceTree,
      fetchExecutionEvents,
      fetchTelemetrySummary,
    })
    downloadExecutionTraceReport(report)
  } catch (err) {
    exportError.value = err?.message || 'Failed to export the complete trace'
  } finally {
    exporting.value = ''
  }
}

</script>

<template>
  <Teleport to="body">
    <Transition name="trace-sheet">
      <div v-if="visible" class="trace-overlay" :class="{ 'trace-overlay--fullscreen': isFullscreen }" @click.self="emit('close')">
        <section
          ref="dialogEl"
          class="trace-panel"
          :class="{ 'trace-panel--fullscreen': isFullscreen }"
          role="dialog"
          aria-modal="true"
          aria-labelledby="trace-panel-title"
          tabindex="-1"
        >
          <div id="trace-detail-drawer-host" class="trace-detail-drawer-host"></div>
          <header class="trace-header">
            <div class="trace-heading">
              <div class="trace-title-line">
                <h2 id="trace-panel-title" class="trace-title">Execution trace</h2>
                <span v-if="telemetry?.source === 'claude_code_otel'" class="native-otel-badge" title="Captured from Claude Code's native OpenTelemetry exporter">
                  Native OTel
                </span>
                <span class="trace-state" :class="overallStatus.className">
                  <span class="state-dot" aria-hidden="true"></span>
                  {{ overallStatus.label }}
                </span>
              </div>
            </div>
            <div class="trace-header-actions">
              <button class="header-icon-btn" type="button" :title="isFullscreen ? 'Exit full screen' : 'Observe in full screen'" :aria-label="isFullscreen ? 'Exit full screen trace view' : 'Open full screen trace view'" :aria-pressed="isFullscreen" @click="isFullscreen = !isFullscreen">
                <svg v-if="!isFullscreen" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M6 2.5H2.5V6M10 2.5h3.5V6M6 13.5H2.5V10M10 13.5h3.5V10"/></svg>
                <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M2.5 6H6V2.5M13.5 6H10V2.5M2.5 10H6v3.5M13.5 10H10v3.5"/></svg>
              </button>
              <button class="close-btn" type="button" title="Close" aria-label="关闭历史树" @click="emit('close')">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                  <path d="m4 4 8 8M12 4l-8 8" />
                </svg>
              </button>
            </div>
          </header>

          <div v-if="selectedRunId" class="run-bar">
            <div class="run-identity">
              <span class="run-label">Run</span>
              <code class="trace-run-id">{{ selectedRunId }}</code>
              <span v-if="runPosition" class="run-position">{{ runPosition }}</span>
            </div>
            <label v-if="runIds.length > 1" class="run-picker">
              <span>Switch run</span>
              <select
                class="run-selector"
                :value="selectedRunId"
                aria-label="选择 Trace 运行记录"
                @change="loadTraceForRun($event.target.value)"
              >
                <option v-for="(rid, index) in runIds" :key="rid" :value="rid">{{ index + 1 }} · {{ rid }}</option>
              </select>
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                <path d="m4 6 4 4 4-4" />
              </svg>
            </label>
            <div class="run-actions">
              <button type="button" class="trace-download-btn trace-download-btn--error" :disabled="Boolean(exporting)" :aria-busy="exporting === 'exceptions'" :title="exporting === 'exceptions' ? 'Collecting exceptions…' : 'Export exceptions, including nested agents'" @click="exportExceptions">
                <span v-if="exporting === 'exceptions'" class="loading-ring loading-ring--small" aria-hidden="true"></span>
                <svg v-else width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 10v3h10v-3M8 2v8M5 7l3 3 3-3"/></svg>
                <span>Exceptions</span>
                <strong v-if="exceptionCount > 0" class="run-action-count">{{ exceptionCount }}</strong>
              </button>
              <button type="button" class="trace-download-btn" :disabled="Boolean(exporting)" :aria-busy="exporting === 'trace'" :title="exporting === 'trace' ? 'Collecting full trace…' : 'Export the complete trace'" @click="exportFullTrace">
                <span v-if="exporting === 'trace'" class="loading-ring loading-ring--small" aria-hidden="true"></span>
                <svg v-else width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 10v3h10v-3M8 2v8M5 7l3 3 3-3"/></svg>
                <span>Full trace</span>
              </button>
            </div>
          </div>

          <nav class="view-mode-bar" aria-label="View mode">
            <button
              type="button"
              class="view-mode-btn"
              :class="{ active: viewMode === ViewMode.EXECUTION }"
              @click="viewMode = ViewMode.EXECUTION"
            >Agent flow</button>
            <button
              type="button"
              class="view-mode-btn"
              :class="{ active: viewMode === ViewMode.RAW_SPAN }"
              @click="viewMode = ViewMode.RAW_SPAN"
            >Trace spans</button>
            <button
              type="button"
              class="view-mode-btn"
              :class="{ active: viewMode === ViewMode.EVENTS }"
              @click="viewMode = ViewMode.EVENTS"
            >Log events <span v-if="telemetry?.log_event_count" class="mode-count">{{ telemetry.log_event_count }}</span></button>
          </nav>

          <main ref="traceBodyEl" class="trace-body" :class="{ 'trace-body--execution': viewMode === ViewMode.EXECUTION }">
            <p v-if="telemetryError" class="telemetry-error" role="status">{{ telemetryError }}</p>
            <p v-if="exportError" class="trace-export-error" role="alert">{{ exportError }}</p>

            <template v-if="viewMode === ViewMode.EXECUTION">
              <ExecutionTreePanel
                :run-id="selectedRunId"
                :focus-subagent="focusSubagentRequest"
                :span-subagents="sessionSubagents"
                @summary-change="handleExecutionSummary"
              >
                <!-- Rendered inside the step scroller so it frees space once the reader scrolls. -->
                <template #prelude>
                  <TraceTelemetryStrip
                    :telemetry="telemetry"
                    :loading="telemetryLoading"
                    :session-state="sessionState"
                    :exception-count="exceptionCount"
                    :exception-count-loading="exceptionCountLoading"
                  />
                </template>
              </ExecutionTreePanel>
            </template>

            <template v-else-if="viewMode === ViewMode.RAW_SPAN">
              <TraceTelemetryStrip
                :telemetry="telemetry"
                :loading="telemetryLoading"
                :session-state="sessionState"
                :exception-count="exceptionCount"
                :exception-count-loading="exceptionCountLoading"
              />
              <div v-if="loading" class="trace-empty">
                <span class="loading-ring" aria-hidden="true"></span>
                <p>Loading execution history…</p>
              </div>
              <div v-else-if="error" class="trace-empty trace-empty--error">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                  <circle cx="10" cy="10" r="7.25"/><path d="M10 6.5v4.25M10 13.5h.01"/>
                </svg>
                <p>{{ error }}</p>
              </div>
              <div v-else-if="traceTree.length === 0" class="trace-empty">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
                  <circle cx="6" cy="5" r="2"/><circle cx="18" cy="12" r="2"/><circle cx="10" cy="19" r="2"/><path d="M6 7v8a4 4 0 0 0 4 4M8 5h3a7 7 0 0 1 7 7"/>
                </svg>
                <p>No execution history yet</p>
                <p class="trace-empty-hint">Trace activity appears here while the agent works.</p>
              </div>
              <div v-else class="trace-tree">
                <div class="trace-analysis-toolbar">
                  <nav class="span-presentation-bar" aria-label="Trace presentation">
                    <button type="button" class="presentation-btn" :class="{ active: spanPresentation === TracePresentation.FLOW }" @click="spanPresentation = TracePresentation.FLOW">Flow</button>
                    <button type="button" class="presentation-btn" :class="{ active: spanPresentation === TracePresentation.DURATION }" @click="spanPresentation = TracePresentation.DURATION">
                      Duration <span aria-hidden="true">↓</span>
                    </button>
                    <button type="button" class="presentation-btn" :class="{ active: spanPresentation === TracePresentation.TOKENS }" @click="spanPresentation = TracePresentation.TOKENS">
                      Tokens <span aria-hidden="true">↓</span>
                    </button>
                  </nav>
                  <nav class="span-filter-bar" aria-label="Span filter">
                    <button v-for="f in ['all','errors','slow','tools','subagents']" :key="f" type="button" class="filter-chip" :class="{ active: spanFilter === f }" @click="spanFilter = f">{{ f === 'all' ? 'All' : f === 'errors' ? 'Errors' : f === 'slow' ? 'High latency' : f === 'tools' ? 'Tools' : 'Subagents' }}</button>
                  </nav>
                </div>

                <template v-if="spanPresentation === TracePresentation.FLOW">
                  <section class="trace-flow-overview" aria-label="Trace execution overview">
                    <div><small>Trace start</small><strong>{{ traceTiming.startMs ? new Date(traceTiming.startMs).toLocaleTimeString() : '—' }}</strong></div>
                    <div><small>End-to-end</small><strong>{{ formatDuration(traceTiming.durationMs) }}</strong></div>
                    <div><small>Parallel splits</small><strong>{{ traceConcurrency.groupCount }}</strong></div>
                    <div><small>Peak concurrency</small><strong>{{ traceConcurrency.maxConcurrency }} spans</strong></div>
                    <p>Rows share one clock. Horizontal overlap means work ran at the same time; purple split/join markers expose parallel branches.</p>
                  </section>
                  <div class="latency-legend" aria-label="Duration heat legend">
                    <span>Duration heat</span>
                    <i class="latency-gradient" aria-hidden="true"></i>
                    <span>Shorter</span>
                    <span>Longer</span>
                    <strong v-if="highLatencyThreshold">High latency ≥ {{ formatDuration(highLatencyThreshold) }} · p90</strong>
                  </div>
                  <div class="trace-waterfall-header" aria-hidden="true">
                    <div class="trace-waterfall-label">
                      <span>Span hierarchy</span>
                      <small>{{ stats.turnCount }} turns · {{ stats.toolCallCount }} tools</small>
                    </div>
                    <div class="trace-waterfall-axis">
                      <span v-for="tick in traceTiming.ticks" :key="tick.portion" :style="{ left: `${tick.portion * 100}%` }">{{ tick.label }}</span>
                    </div>
                  </div>
                  <TraceSpanRow v-for="node in traceConcurrency.tree" :key="node.id" :node="node" :depth="0" :trace-start-ms="traceTiming.startMs" :trace-duration-ms="traceTiming.durationMs" :duration-thresholds="traceAnalysis.thresholds" />
                </template>

                <TraceHotspotTable
                  v-else
                  :rows="rankedTraceRows"
                  :sort-mode="spanPresentation"
                  :p90-duration-ms="highLatencyThreshold"
                />
              </div>
            </template>

            <template v-else>
              <div v-if="telemetryLoading && !telemetry" class="trace-empty">
                <span class="loading-ring" aria-hidden="true"></span>
                <p>Loading OpenTelemetry events…</p>
              </div>
              <div v-else-if="!logEventRows.length" class="trace-empty">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
                  <path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/>
                </svg>
                <p>No structured log events for this run</p>
                <p class="trace-empty-hint">Claude Code API, tool, permission and hook events appear here.</p>
              </div>
              <section v-else class="otel-events" aria-label="Structured OpenTelemetry log events">
                <header class="events-header">
                  <div>
                    <span class="events-kicker">OTLP logs</span>
                    <h3>Structured events</h3>
                  </div>
                  <span>Showing latest {{ logEventRows.length }}</span>
                </header>
                <ol class="event-list">
                  <li v-for="row in logEventRows" :key="row.id" class="event-row">
                    <time :datetime="row.eventTime">{{ row.displayTime }}</time>
                    <span class="event-marker" :class="{ 'is-error': row.isError }" aria-hidden="true"></span>
                    <div class="event-content">
                      <div class="event-title-line">
                        <strong>{{ row.name }}</strong>
                        <code v-if="row.spanId">{{ row.spanId }}</code>
                      </div>
                      <div v-if="row.attributes.length" class="event-attributes">
                        <span v-for="([key, value]) in row.attributes" :key="key"><b>{{ key }}</b> {{ value }}</span>
                      </div>
                      <details class="event-payload" @toggle="toggleEventPayload(row, $event.target.open)">
                        <summary>Full audit payload</summary>
                        <template v-if="openEventPayloads.has(row.id)">
                          <p v-if="payloadLoading.has(row.id)" class="event-payload-note">Loading the full payload…</p>
                          <p v-else-if="payloadErrors.get(row.id)" class="event-payload-note event-payload-note--error">{{ payloadErrors.get(row.id) }}</p>
                          <p v-else-if="row.truncated && !verbatimPayloads.has(row.id)" class="event-payload-note">Oversized fields are clipped in this copy.</p>
                          <pre>{{ eventPayloadText(row) }}</pre>
                        </template>
                      </details>
                    </div>
                  </li>
                </ol>
              </section>
            </template>
          </main>

          <footer v-if="traceTree.length > 0" class="trace-footer">
            <div class="footer-stat"><span>Duration</span><strong>{{ formatDuration(stats.totalDurationMs) }}</strong></div>
            <div class="footer-divider" aria-hidden="true"></div>
            <div class="footer-stat"><span>Turns</span><strong>{{ stats.turnCount }}</strong></div>
            <div class="footer-stat"><span>Tools</span><strong>{{ stats.toolCallCount }}</strong></div>
            <div class="footer-stat"><span>Subagents</span><strong>{{ stats.subagentCount }}</strong></div>
            <div class="footer-spacer"></div>
            <div v-if="stats.failedCount" class="footer-alert stat-error">{{ stats.failedCount }} failed</div>
            <div v-if="stats.cancelledCount" class="footer-alert stat-cancelled">{{ stats.cancelledCount }} cancelled</div>
            <div v-if="stats.abandonedCount" class="footer-alert stat-abandoned">{{ stats.abandonedCount }} abandoned</div>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.trace-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: stretch;
  justify-content: flex-end;
  padding: var(--dialog-gutter);
  background: var(--dialog-overlay);
  backdrop-filter: blur(8px);
}
.trace-panel {
  position: relative;
  width: min(1280px, calc(100vw - (var(--dialog-gutter) * 2)));
  height: calc(100dvh - (var(--dialog-gutter) * 2));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--dialog-border);
  border-radius: var(--dialog-radius);
  outline: none;
  background: var(--dialog-surface);
  box-shadow: var(--dialog-shadow);
  user-select: text;
  -webkit-user-select: text;
}
.trace-detail-drawer-host {
  position: absolute;
  inset: 0;
  z-index: 20;
  pointer-events: none;
}
.trace-overlay--fullscreen { padding: 0; }
.trace-panel.trace-panel--fullscreen { width: 100vw; height: 100dvh; border: 0; border-radius: 0; }
.trace-panel button,
.trace-panel select,
.run-picker {
  user-select: none;
  -webkit-user-select: none;
}
.trace-header {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 12px 20px 10px;
}
.trace-header-actions { display: inline-flex; align-items: center; gap: 4px; }
.header-icon-btn { width: 36px; height: 36px; display: grid; place-items: center; padding: 0; border: 1px solid transparent; border-radius: 9px; background: transparent; color: var(--text-tertiary); cursor: pointer; }
.header-icon-btn:hover { border-color: var(--border-subtle); background: var(--bg-hover); color: var(--text-primary); }
.header-icon-btn:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.trace-heading { min-width: 0; }
.trace-title-line { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.trace-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.02em;
}
.trace-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
}
.state-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-tertiary); }
.trace-state.is-running .state-dot { background: var(--text-accent); animation: trace-pulse 1.3s ease-in-out infinite; }
.trace-state.is-completed .state-dot { background: var(--color-success, #22c55e); }
.trace-state.is-failed .state-dot { background: var(--color-error, #ef4444); }
.trace-state.is-cancelled .state-dot { background: var(--color-warning, #f59e0b); }
.trace-state.is-abandoned .state-dot { background: var(--color-warning, #f59e0b); }
.native-otel-badge {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border: 1px solid color-mix(in srgb, var(--text-accent) 38%, var(--border-subtle));
  border-radius: 999px;
  background: color-mix(in srgb, var(--text-accent) 9%, var(--bg-primary));
  color: var(--text-accent);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .02em;
}
.close-btn {
  display: flex;
  flex: 0 0 36px;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: color 160ms ease, background 160ms ease, border-color 160ms ease;
}
.close-btn:hover { border-color: var(--border-subtle); background: var(--bg-hover); color: var(--text-primary); }
.run-bar {
  min-height: 38px;
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 4px 20px;
  border-top: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
}
.run-identity { display: flex; align-items: center; min-width: 0; gap: 8px; }
.run-label, .run-position { color: var(--text-tertiary); font-size: 11px; }
.trace-run-id {
  max-width: 280px;
  overflow: hidden;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-position { padding-left: 8px; border-left: 1px solid var(--border-subtle); font-family: var(--font-mono); }
.run-actions { display: flex; flex-shrink: 0; align-items: center; gap: 6px; margin-left: auto; }
.run-action-count {
  padding: 1px 5px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-error, #ef4444) 15%, transparent);
  font-family: var(--font-mono);
  font-size: 9px;
}
.view-mode-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 24px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
}
.view-mode-btn {
  padding: 5px 12px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: background 140ms ease, color 140ms ease, border-color 140ms ease;
}
.view-mode-btn:hover { color: var(--text-secondary); background: var(--bg-hover); }
.view-mode-btn.active { color: var(--text-primary); background: var(--bg-primary); border-color: var(--border-subtle); box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.view-mode-btn:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.mode-count {
  margin-left: 4px;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--bg-hover);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 9px;
}
.run-picker {
  position: relative;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 8px 5px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
}
.run-selector { position: absolute; inset: 0; width: 100%; opacity: 0; cursor: pointer; }
.close-btn:focus-visible, .run-picker:focus-within { outline: 2px solid var(--text-accent); outline-offset: 2px; }
.trace-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 16px 24px;
  scrollbar-gutter: stable;
}
/* The step list owns the remaining height and scrolls on its own, so the run
   summary never pushes the steps out of view. */
.trace-body--execution {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding-bottom: 0;
}
.trace-flow-overview { display: grid; grid-template-columns: repeat(4, minmax(105px, auto)) minmax(220px, 1fr); align-items: center; gap: 8px 18px; margin: 8px 0; padding: 10px 12px; border: 1px solid var(--border-subtle); border-radius: 9px; background: color-mix(in srgb, #8b5cf6 4%, var(--bg-secondary)); }
.trace-flow-overview div { display: grid; gap: 2px; }
.trace-flow-overview small { color: var(--text-tertiary); font-size: 8px; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; }
.trace-flow-overview strong { color: var(--text-primary); font-family: var(--font-mono); font-size: 10px; }
.trace-flow-overview p { margin: 0; color: var(--text-tertiary); font-size: 9px; line-height: 1.45; }
.telemetry-error { margin: 0 14px 5px; color: var(--color-warning, #f59e0b); font-size: 11px; }
.trace-download-btn { min-height: 32px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 5px 9px; border: 1px solid var(--border-subtle); border-radius: 7px; background: var(--bg-primary); color: var(--text-secondary); font-size: 10px; font-weight: 600; cursor: pointer; transition: background 150ms ease, border-color 150ms ease, color 150ms ease; }
.trace-download-btn:hover:not(:disabled) { border-color: var(--text-accent); background: var(--bg-hover); color: var(--text-primary); }
.trace-download-btn--error { border-color: color-mix(in srgb, var(--color-error, #ef4444) 30%, var(--border-subtle)); color: var(--color-error, #ef4444); }
.trace-download-btn--error:hover:not(:disabled) { border-color: var(--color-error, #ef4444); background: color-mix(in srgb, var(--color-error, #ef4444) 7%, var(--bg-primary)); color: var(--color-error, #ef4444); }
.trace-download-btn:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 2px; }
.trace-download-btn:disabled { cursor: wait; opacity: .68; }
.trace-export-error { margin: 3px 14px 5px; color: var(--color-error, #ef4444); font-size: 11px; overflow-wrap: anywhere; }
.otel-events { padding: 2px 8px 24px; }
.events-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 8px 12px;
  border-bottom: 1px solid var(--border-subtle);
}
.events-header h3 { margin: 3px 0 0; color: var(--text-primary); font-size: 14px; font-weight: 600; }
.events-header > span { color: var(--text-tertiary); font-size: 10px; }
.events-kicker { color: var(--text-accent); font-family: var(--font-mono); font-size: 9px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; }
.event-list { margin: 0; padding: 0; list-style: none; }
.event-row {
  display: grid;
  grid-template-columns: 78px 10px minmax(0, 1fr);
  align-items: flex-start;
  gap: 10px;
  padding: 11px 8px;
  border-bottom: 1px solid var(--border-subtle);
}
.event-row time { padding-top: 2px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; }
.event-marker { width: 7px; height: 7px; margin-top: 5px; border-radius: 50%; background: var(--text-accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--text-accent) 12%, transparent); }
.event-marker.is-error { background: var(--color-error, #ef4444); box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-error, #ef4444) 12%, transparent); }
.event-content { min-width: 0; }
.event-title-line { display: flex; align-items: baseline; gap: 8px; }
.event-title-line strong { color: var(--text-primary); font-family: var(--font-mono); font-size: 11px; font-weight: 600; }
.event-title-line code { overflow: hidden; color: var(--text-tertiary); font-size: 9px; text-overflow: ellipsis; }
.event-attributes { display: flex; flex-wrap: wrap; gap: 5px 12px; margin-top: 5px; }
.event-attributes span { color: var(--text-secondary); font-family: var(--font-mono); font-size: 9px; }
.event-attributes b { margin-right: 3px; color: var(--text-tertiary); font-weight: 500; }
.event-payload { margin-top: 7px; }
.event-payload-note { margin: 8px 0 0; color: var(--text-tertiary); font-size: 10px; }
.event-payload-note--error { color: var(--color-error, #ef4444); }
.event-payload summary {
  width: fit-content;
  color: var(--text-tertiary);
  font-size: 10px;
  cursor: pointer;
  user-select: none;
}
.event-payload summary:hover { color: var(--text-primary); }
.event-payload pre {
  max-height: 360px;
  margin: 8px 0 0;
  padding: 10px 12px;
  overflow: auto;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
.trace-empty {
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-tertiary);
  text-align: center;
}
.trace-empty p { margin: 0; color: var(--text-secondary); font-size: 13px; }
.trace-empty-hint { max-width: 340px; color: var(--text-tertiary) !important; font-size: 12px !important; }
.trace-empty--error { color: var(--color-error, #ef4444); }
.loading-ring { width: 18px; height: 18px; border: 1.5px solid var(--border); border-top-color: var(--text-secondary); border-radius: 50%; animation: spin 800ms linear infinite; }
.loading-ring--small { width: 13px; height: 13px; }
.trace-analysis-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 2px 10px 10px; }
.span-presentation-bar { display: inline-flex; padding: 2px; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--bg-secondary); }
.presentation-btn { min-height: 30px; padding: 5px 10px; border: 0; border-radius: 6px; background: transparent; color: var(--text-tertiary); font-size: 10px; font-weight: 600; cursor: pointer; transition: background 140ms ease, color 140ms ease, box-shadow 140ms ease; }
.presentation-btn:hover { color: var(--text-secondary); }
.presentation-btn.active { background: var(--bg-primary); color: var(--text-primary); box-shadow: 0 1px 3px rgba(0,0,0,.1); }
.presentation-btn:focus-visible, .filter-chip:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.latency-legend { min-height: 30px; display: flex; align-items: center; justify-content: flex-end; gap: 7px; padding: 0 12px 7px; color: var(--text-tertiary); font-size: 9px; }
.latency-legend > span:first-child { margin-right: auto; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; }
.latency-gradient { width: 88px; height: 7px; border-radius: 999px; background: linear-gradient(90deg, #38bdf8 0%, #818cf8 42%, #f59e0b 72%, #ef4444 100%); }
.latency-legend strong { margin-left: 8px; color: var(--text-secondary); font-family: var(--font-mono); font-size: 9px; font-weight: 550; }
.trace-waterfall-header { position: sticky; z-index: 4; top: 0; display: grid; grid-template-columns: minmax(320px, 1.35fr) minmax(260px, 1fr); min-height: 34px; border-top: 1px solid var(--border-subtle); border-bottom: 1px solid var(--border-subtle); background: color-mix(in srgb, var(--dialog-surface) 94%, transparent); backdrop-filter: blur(8px); }
.trace-waterfall-label { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 7px 12px; border-right: 1px solid var(--border-subtle); }
.trace-waterfall-label span { color: var(--text-tertiary); font-size: 9px; font-weight: 650; letter-spacing: .07em; text-transform: uppercase; }
.trace-waterfall-label small { color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; }
.trace-waterfall-axis { position: relative; min-width: 0; background-image: linear-gradient(to right, color-mix(in srgb, var(--border-subtle) 65%, transparent) 1px, transparent 1px); background-size: 25% 100%; }
.trace-waterfall-axis span { position: absolute; top: 8px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; transform: translateX(-50%); white-space: nowrap; }
.trace-waterfall-axis span:first-child { transform: none; }
.trace-waterfall-axis span:last-child { transform: translateX(-100%); }
.trace-tree { display: flex; flex-direction: column; gap: 1px; }
.span-filter-bar { display: flex; gap: 4px; flex-wrap: wrap; }
.filter-chip { padding: 4px 10px; border: 1px solid var(--border-subtle); border-radius: 999px; background: transparent; color: var(--text-tertiary); font-size: 10px; font-weight: 500; cursor: pointer; transition: all 140ms ease; }
.filter-chip:hover { color: var(--text-secondary); border-color: var(--border); }
.filter-chip.active { color: var(--text-primary); background: var(--bg-secondary); border-color: var(--border); }
.trace-footer {
  min-height: 50px;
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 18px;
  padding: 8px 24px;
  border-top: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
}
.footer-stat { display: flex; align-items: baseline; gap: 7px; white-space: nowrap; }
.footer-stat span { color: var(--text-tertiary); font-size: 11px; }
.footer-stat strong { color: var(--text-primary); font-family: var(--font-mono); font-size: 11px; font-weight: 500; }
.footer-divider { width: 1px; height: 16px; background: var(--border-subtle); }
.footer-spacer { flex: 1; }
.footer-alert { font-size: 11px; white-space: nowrap; }
.stat-error { color: var(--color-error, #ef4444); }
.stat-cancelled { color: var(--color-warning, #f59e0b); }
.stat-abandoned { color: var(--color-warning, #f59e0b); }
.trace-sheet-enter-active, .trace-sheet-leave-active { transition: opacity 180ms ease; }
.trace-sheet-enter-active .trace-panel, .trace-sheet-leave-active .trace-panel { transition: transform 220ms cubic-bezier(.2,.8,.2,1), opacity 180ms ease; }
.trace-sheet-enter-from, .trace-sheet-leave-to { opacity: 0; }
.trace-sheet-enter-from .trace-panel, .trace-sheet-leave-to .trace-panel { transform: translateX(18px); opacity: 0; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes trace-pulse { 50% { opacity: .35; } }
@media (prefers-reduced-motion: reduce) {
  .trace-sheet-enter-active, .trace-sheet-leave-active,
  .trace-sheet-enter-active .trace-panel, .trace-sheet-leave-active .trace-panel { transition: none; }
  .loading-ring, .trace-state.is-running .state-dot { animation: none; }
}
@media (max-width: 640px) {
  .trace-overlay { padding: 0; }
  .trace-panel { width: 100vw; height: 100dvh; border: 0; border-radius: 0; }
  .trace-header { padding: 12px 16px 8px; }
  .trace-title { font-size: 16px; }
  .run-bar { padding: 4px 16px; }
  .trace-run-id { max-width: 150px; }
  .trace-body { padding: 10px 10px 20px; }
  .trace-download-btn { flex: 1; }
  .trace-waterfall-header { grid-template-columns: minmax(210px, 1fr) minmax(160px, .9fr); }
  .run-actions { width: 100%; }
  .trace-analysis-toolbar { align-items: flex-start; flex-direction: column; }
  .latency-legend { flex-wrap: wrap; justify-content: flex-start; }
  .latency-legend > span:first-child { width: 100%; margin: 0; }
  .latency-legend strong { width: 100%; margin-left: 0; }
  .event-row { grid-template-columns: 62px 8px minmax(0, 1fr); gap: 7px; }
  .trace-footer { gap: 12px; padding: 8px 18px; overflow-x: auto; }
  .trace-flow-overview { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .trace-flow-overview p { grid-column: 1 / -1; }
  .footer-divider, .footer-spacer { display: none; }
}
@media (min-width: 1440px) {
  .trace-panel { width: min(1440px, calc(100vw - (var(--dialog-gutter) * 2))); }
}
</style>
