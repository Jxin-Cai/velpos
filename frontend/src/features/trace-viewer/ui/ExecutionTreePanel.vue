<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useSession } from '@entities/session'
import { useExecutionTree } from '../model/useExecutionTree'
import { useTimelineWaterfall } from '../model/useTimelineWaterfall'
import { fetchExecutionTree, fetchLoopDetail } from '../api/traceApi'
import { buildExecutionErrorReport, downloadExecutionErrorReport } from '../lib/executionErrorExport'
import ExecutionTreeRow from './ExecutionTreeRow.vue'
import ExecutionDetailViewer from './ExecutionDetailViewer.vue'
import InlineSubagentTree from './InlineSubagentTree.vue'

const props = defineProps({
  runId: { type: String, default: null },
})

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
  toggleTask,
  toggleLoop,
  toggleSubagent,
  toggleInlineSubagent,
  selectLoop,
  getLoopDetail,
  getLoopLoadState,
  getSubagentState,
  getInlineSubagentState,
  NodeStatus,
} = useExecutionTree()

const execFilter = ref('all')
const exportingErrors = ref(false)
const exportError = ref('')

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
const waterfall = useTimelineWaterfall(filteredTasks)
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

const totalErrors = computed(() => tasks.value.reduce((count, task) => count + (task.error_count || 0), 0))
const hasErrors = computed(() => totalErrors.value > 0 || Boolean(tree.value?.error_message))

async function exportAllErrors() {
  if (!tree.value || exportingErrors.value) return
  exportingErrors.value = true
  exportError.value = ''
  try {
    const report = await buildExecutionErrorReport({
      sessionId: currentSessionId.value,
      runId: props.runId,
      rootTree: tree.value,
      fetchTree: fetchExecutionTree,
      fetchDetail: fetchLoopDetail,
    })
    downloadExecutionErrorReport(report)
  } catch (err) {
    exportError.value = err?.message || 'Failed to collect error details'
  } finally {
    exportingErrors.value = false
  }
}

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

function formatTokensK(n) {
  if (!n) return '0'
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function waterfallTooltip(seg) {
  const parts = [`Step ${seg.sequence}: ${seg.name}`]
  if (seg.durationMs > 0) parts.push(formatWaterfallDuration(seg.durationMs))
  if (seg.tokens > 0) parts.push(`${formatTokensK(seg.tokens)} tokens`)
  if (seg.errorCount > 0) parts.push(`${seg.errorCount} error${seg.errorCount > 1 ? 's' : ''}`)
  if (seg.model) parts.push(seg.model.replace(/^claude-/, ''))
  return parts.join(' · ')
}

function formatWaterfallDuration(ms) {
  if (!ms || ms <= 0) return '0ms'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const minutes = Math.floor(ms / 60000)
  const seconds = Math.round((ms % 60000) / 1000)
  return `${minutes}m ${seconds}s`
}

// When switching to errors filter, expand all error tasks
watch(execFilter, (filter) => {
  if (filter === 'errors') {
    for (const task of filteredTasks.value) {
      expandedTasks.add(task.id)
    }
  }
})

watch([() => props.runId, currentSessionId], ([runId, sessionId]) => {
  if (runId && sessionId) {
    loadTree(sessionId, runId)
  }
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
            <button
              type="button"
              class="download-errors-btn"
              :disabled="exportingErrors"
              :aria-busy="exportingErrors"
              @click="exportAllErrors"
            >
              <span v-if="exportingErrors" class="exec-spinner" aria-hidden="true"></span>
              <svg v-else width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                <path d="M3 10v3h10v-3M8 2v8M5 7l3 3 3-3"/>
              </svg>
              {{ exportingErrors ? 'Collecting errors…' : 'Download all errors' }}
            </button>
          </div>
          <p v-if="exportError" class="download-errors-error" role="alert">{{ exportError }}</p>

          <!-- Waterfall timeline (width = time duration) -->
          <div v-if="waterfall.segments.length > 1" class="timeline-waterfall-wrapper">
            <div class="timeline-waterfall-legend">
              <span class="legend-label">Timeline</span>
              <span class="legend-duration">{{ formatWaterfallDuration(waterfall.totalMs) }}</span>
              <span class="legend-hint">
                <span class="legend-swatch legend-swatch--model"></span>model
                <span class="legend-swatch legend-swatch--tool"></span>tool
              </span>
            </div>
            <div class="timeline-waterfall" aria-label="Step duration waterfall">
              <div
                v-for="seg in waterfall.segments"
                :key="seg.id"
                class="waterfall-segment"
                :class="[`waterfall--${seg.type}`, { 'waterfall--error': seg.hasError, 'is-active': selectedLoopId === seg.id }]"
                :style="{ left: seg.startPct + '%', width: seg.widthPct + '%' }"
                :data-tooltip="waterfallTooltip(seg)"
                @click="selectLoop(seg.id)"
              />
            </div>
          </div>

          <div class="tree-caption tree-caption--sticky">
            <span>{{ plannedTaskCount ? 'Tasks created for this message' : 'Direct execution for this message' }}</span>
            <span class="tree-count">{{ plannedTaskCount || totalSteps }}</span>
          </div>

          <!-- Main agent tasks -->
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
                :expanded="Boolean(getSubagentState(subagent.span_id))"
                :load-state="getSubagentState(subagent.span_id)?.loading ? 'loading' : 'idle'"
                @toggle="toggleSubagent(subagent.span_id)"
              >
                <div v-if="getSubagentState(subagent.span_id)?.error" class="subagent-inline-state subagent-inline-state--error">
                  {{ getSubagentState(subagent.span_id).error }}
                </div>
                <InlineSubagentTree
                  v-else-if="getSubagentState(subagent.span_id)?.tree"
                  :tree="getSubagentState(subagent.span_id).tree"
                  :agent-span-id="subagent.span_id"
                  :get-loop-detail="getLoopDetail"
                  :get-loop-load-state="getLoopLoadState"
                  :load-loop-detail="loadLoopDetail"
                />
              </ExecutionTreeRow>
            </ExecutionTreeRow>
            </template>
          </ExecutionTreeRow>
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
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
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
.subagent-inline-state { padding: 10px 14px 10px 60px; color: var(--text-tertiary); font-size: 11px; }
.subagent-inline-state--error { color: var(--color-error, #ef4444); }
.exec-error-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px; padding: 6px 10px 2px; }
.exec-filter-bar { display: flex; gap: 4px; }
.exec-filter-chip { min-height: 26px; display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px; border: 1px solid var(--border-subtle); border-radius: 5px; background: var(--bg-primary); color: var(--text-tertiary); font-size: 11px; font-weight: 500; cursor: pointer; transition: all 120ms ease; }
.exec-filter-chip:hover { border-color: var(--text-accent); color: var(--text-primary); }
.exec-filter-chip.active { border-color: var(--text-accent); background: color-mix(in srgb, var(--text-accent) 8%, var(--bg-primary)); color: var(--text-accent); font-weight: 600; }
.exec-filter-chip--error.active { border-color: var(--color-error, #ef4444); background: color-mix(in srgb, var(--color-error) 8%, var(--bg-primary)); color: var(--color-error, #ef4444); }
.filter-count { padding: 1px 5px; border-radius: 3px; background: color-mix(in srgb, var(--color-error, #ef4444) 12%, transparent); font-family: var(--font-mono); font-size: 9px; font-weight: 700; }
.download-errors-btn { min-height: 32px; display: inline-flex; flex: 0 0 auto; align-items: center; justify-content: center; gap: 6px; padding: 6px 10px; border: 1px solid color-mix(in srgb, var(--color-error, #ef4444) 32%, var(--border-subtle)); border-radius: 6px; background: color-mix(in srgb, var(--color-error, #ef4444) 7%, var(--bg-primary)); color: var(--color-error, #ef4444); font-size: 11px; font-weight: 600; cursor: pointer; transition: background 140ms ease, border-color 140ms ease; }
.download-errors-btn:hover:not(:disabled) { border-color: var(--color-error, #ef4444); background: color-mix(in srgb, var(--color-error, #ef4444) 12%, var(--bg-primary)); }
.download-errors-btn:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 2px; }
.download-errors-btn:disabled { cursor: wait; opacity: .7; }
.download-errors-error { margin: 6px 10px 2px; color: var(--color-error, #ef4444); font-size: 11px; overflow-wrap: anywhere; }
.timeline-waterfall-wrapper { margin: 8px 10px 4px; }
.timeline-waterfall-legend { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; padding: 0 2px; }
.legend-label { color: var(--text-tertiary); font-size: 9px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.legend-duration { color: var(--text-secondary); font-family: var(--font-mono); font-size: 10px; font-weight: 500; }
.legend-hint { margin-left: auto; display: flex; align-items: center; gap: 8px; color: var(--text-tertiary); font-size: 9px; }
.legend-swatch { display: inline-block; width: 10px; height: 6px; margin-right: 3px; border-radius: 2px; }
.legend-swatch--model { background: var(--text-accent); opacity: 0.7; }
.legend-swatch--tool { background: var(--color-success, #22c55e); opacity: 0.7; }
.timeline-waterfall { position: relative; height: 22px; border-radius: 4px; background: var(--bg-secondary); }
.waterfall-segment { position: absolute; top: 3px; bottom: 3px; border-radius: 3px; cursor: pointer; transition: opacity 120ms ease, box-shadow 120ms ease; }
.waterfall-segment:hover { opacity: 1; box-shadow: 0 0 0 1.5px var(--text-primary); z-index: 10; }
.waterfall-segment.is-active { box-shadow: 0 0 0 2px var(--text-accent); z-index: 11; }
.waterfall--model { background: var(--text-accent); opacity: 0.7; }
.waterfall--tool { background: var(--color-success, #22c55e); opacity: 0.7; }
.waterfall--error { background: var(--color-error, #ef4444); opacity: 0.85; }
/* Custom CSS tooltip for waterfall segments */
.waterfall-segment[data-tooltip]::after {
  content: attr(data-tooltip);
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  padding: 5px 9px;
  border-radius: 5px;
  background: var(--text-primary, #1a1a1a);
  color: var(--bg-primary, #fff);
  font-size: 10px;
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 100ms ease;
  z-index: 100;
}
.waterfall-segment[data-tooltip]:hover::after { opacity: 1; }
/* Prevent tooltip from overflowing left/right on edge segments */
.waterfall-segment[data-tooltip]:first-child::after { left: 0; transform: none; }
.waterfall-segment[data-tooltip]:last-child::after { left: auto; right: 0; transform: none; }
.causality-label { display: flex; align-items: center; gap: 5px; padding: 2px 10px 2px 52px; color: var(--text-tertiary); font-size: 10px; font-style: italic; }
.causality-arrow { color: var(--text-accent); font-style: normal; font-weight: 600; }
.exec-spinner { width: 16px; height: 16px; border: 1.5px solid var(--border); border-top-color: var(--text-secondary); border-radius: 50%; animation: exec-panel-spin 700ms linear infinite; }
.exec-tree-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.exec-tree-section {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  overflow-y: auto;
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
  overflow-y: auto;
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
}
@keyframes exec-panel-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .exec-spinner { animation: none; } }
</style>
