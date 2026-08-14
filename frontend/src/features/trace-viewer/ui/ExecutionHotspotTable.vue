<script setup>
import { computed } from 'vue'
import { executionMetricPercent } from '../lib/executionAnalysis'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  sortMode: { type: String, required: true },
  selectedLoopId: { type: String, default: null },
})

const emit = defineEmits(['select-step', 'select-subagent'])
const maxTaskMetric = computed(() => Math.max(...props.rows.map(taskMetric), 1))
const maxStepMetric = computed(() => Math.max(
  ...props.rows.flatMap(row => row.steps.map(stepMetric)),
  1,
))

function taskMetric(row) {
  return props.sortMode === 'tokens' ? row.tokens : row.activeDurationMs
}

function stepMetric(step) {
  return props.sortMode === 'tokens' ? step.tokens : step.durationMs
}

function taskTitle(row) {
  return row.task.subject || (row.task.explicit === false ? 'Direct execution' : `Task ${row.sequence}`)
}

function stepTitle(step) {
  const tools = step.loop.tool_names || []
  if (tools.length) return tools.join(' + ')
  return step.loop.model ? `${step.loop.model.replace(/^claude-/, '')} response` : 'Model response'
}

function formatDuration(ms) {
  if (!ms) return '0ms'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`
}

function formatTokens(value) {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}m`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  return String(value || 0)
}

function metricPercent(value, maximum) {
  return executionMetricPercent(value, maximum)
}

function subagentName(subagent) {
  return subagent.subagent || subagent.agent_id || 'Subagent'
}
</script>

<template>
  <section class="task-hotspots" :aria-label="sortMode === 'tokens' ? 'Tasks ranked by token consumption' : 'Tasks ranked by duration'">
    <header class="task-hotspots-header">
      <div>
        <span>Task diagnostics</span>
        <h3>{{ sortMode === 'tokens' ? 'Highest-token tasks' : 'Longest-running tasks' }}</h3>
        <p>Tasks and their steps use the same ranking metric. Select a step to inspect its complete event chain.</p>
      </div>
      <strong>{{ rows.length }} tasks</strong>
    </header>

    <div v-if="rows.length" class="metric-scale" aria-label="Bar chart scale">
      <span>Step bars · one global scale across all visible steps</span>
      <span>0</span>
      <span>Max {{ sortMode === 'tokens' ? formatTokens(maxStepMetric) : formatDuration(maxStepMetric) }}</span>
    </div>

    <div v-if="rows.length" class="task-hotspot-list">
      <details v-for="(row, taskIndex) in rows" :key="row.task.id" class="task-hotspot-card">
        <summary class="task-hotspot-summary">
          <span class="task-rank">{{ String(taskIndex + 1).padStart(2, '0') }}</span>
          <span class="task-name">
            <small>{{ row.task.explicit === false ? 'Execution' : `Task ${row.sequence}` }}</small>
            <strong>{{ taskTitle(row) }}</strong>
          </span>
          <span class="task-metric">
            <b>{{ sortMode === 'tokens' ? formatTokens(row.tokens) : formatDuration(row.activeDurationMs) }}</b>
            <small>{{ sortMode === 'tokens' ? `${Math.round(row.tokenShare * 1000) / 10}% of tokens` : `${Math.round(row.durationShare * 1000) / 10}% of measured time` }}</small>
          </span>
          <span class="task-bar" :class="{ 'is-tokens': sortMode === 'tokens' }" aria-hidden="true"><i :style="{ width: `${metricPercent(taskMetric(row), maxTaskMetric)}%` }"></i></span>
          <span class="task-secondary">
            <small>{{ row.steps.length }} steps</small>
            <small v-if="row.wallDurationMs !== row.activeDurationMs">{{ formatDuration(row.wallDurationMs) }} wall</small>
          </span>
          <svg class="task-chevron" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg>
        </summary>

        <ol class="task-step-list">
          <li v-for="(step, stepIndex) in row.steps" :key="step.loop.id">
            <div
              class="task-step-row"
              :class="{ 'is-selected': selectedLoopId === step.loop.id }"
            >
              <span class="step-rank">{{ stepIndex + 1 }}</span>
              <button type="button" class="step-name step-open" @click="emit('select-step', step.loop.id)"><small>Step {{ step.sequence }}</small><strong>{{ stepTitle(step) }}</strong></button>
              <span class="step-bar" :class="{ 'is-tokens': sortMode === 'tokens' }" aria-hidden="true"><i :style="{ width: `${metricPercent(stepMetric(step), maxStepMetric)}%` }"></i></span>
              <span class="step-duration"><small>Duration</small><b>{{ formatDuration(step.durationMs) }}</b></span>
              <span class="step-tokens"><small>Tokens</small><b>{{ formatTokens(step.tokens) }}</b></span>
              <span class="step-outcome">
                <span class="step-status" :class="`status-${step.loop.error_count ? 'failed' : 'completed'}`"><i></i>{{ step.loop.error_count ? `${step.loop.error_count} errors` : (step.loop.stop_reason || 'recorded') }}</span>
                <span v-if="step.loop.subagents?.length" class="step-agent-links">
                  <button v-for="subagent in step.loop.subagents" :key="subagent.tool_use_id" type="button" :disabled="!subagent.span_id" @click="emit('select-subagent', subagent)">
                    <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><rect x="3" y="4" width="10" height="8" rx="2"/><path d="M8 2v2M6 8h.01M10 8h.01"/></svg>
                    {{ subagentName(subagent) }}
                  </button>
                </span>
              </span>
              <button type="button" class="step-chevron" aria-label="Inspect complete step" @click="emit('select-step', step.loop.id)"><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 4 4 4-4 4"/></svg></button>
            </div>
          </li>
        </ol>
      </details>
    </div>
    <div v-else class="task-hotspot-empty">No tasks contain the selected metric.</div>
  </section>
</template>

<style scoped>
.task-hotspots { container-type: inline-size; overflow: hidden; margin: 4px 6px 20px; border: 1px solid var(--border-subtle); border-radius: 10px; background: var(--bg-primary); }
.task-hotspots-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 15px 16px; border-bottom: 1px solid var(--border-subtle); background: color-mix(in srgb, var(--bg-secondary) 72%, transparent); }
.task-hotspots-header span { color: var(--text-accent); font-family: var(--font-mono); font-size: 9px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.task-hotspots-header h3 { margin: 4px 0 0; color: var(--text-primary); font-size: 14px; }
.task-hotspots-header p { margin: 4px 0 0; color: var(--text-tertiary); font-size: 10px; }
.task-hotspots-header > strong { padding: 4px 8px; border: 1px solid var(--border-subtle); border-radius: 999px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; white-space: nowrap; }
.metric-scale { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 14px; padding: 6px 14px; border-bottom: 1px solid var(--border-subtle); background: var(--bg-primary); color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; }
.metric-scale span:first-child { color: var(--text-secondary); }
.task-hotspot-card { border-bottom: 1px solid var(--border-subtle); }
.task-hotspot-card:last-child { border-bottom: 0; }
.task-hotspot-summary { min-height: 62px; display: grid; grid-template-columns: 28px minmax(180px, 1fr) 104px minmax(90px, .55fr) 84px 14px; align-items: center; gap: 10px; padding: 8px 12px; cursor: pointer; list-style: none; }
.task-hotspot-summary::-webkit-details-marker { display: none; }
.task-hotspot-summary:hover { background: var(--bg-hover); }
.task-hotspot-summary:focus-visible, .step-open:focus-visible, .step-chevron:focus-visible, .step-agent-links button:focus-visible { outline: 2px solid var(--text-accent); outline-offset: 1px; }
.task-rank { color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; font-weight: 650; }
.task-name, .task-metric, .task-secondary, .step-name, .step-duration, .step-tokens { min-width: 0; display: grid; gap: 2px; }
.task-name small, .task-metric small, .task-secondary small, .step-name small, .step-duration small, .step-tokens small { color: var(--text-tertiary); font-size: 9px; }
.task-name strong { overflow: hidden; color: var(--text-primary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.task-metric b, .step-duration b, .step-tokens b { color: var(--text-secondary); font-family: var(--font-mono); font-size: 10px; }
.task-bar, .step-bar { height: 7px; overflow: hidden; border-radius: 999px; background: var(--bg-tertiary); }
.task-bar i, .step-bar i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #38bdf8, #f59e0b 72%, #ef4444); }
.task-bar.is-tokens i, .step-bar.is-tokens i { background: linear-gradient(90deg, #818cf8, #a855f7); }
.task-chevron { color: var(--text-tertiary); transition: transform 160ms ease; }
.task-hotspot-card[open] .task-chevron { transform: rotate(180deg); }
.task-step-list { margin: 0; padding: 0 0 5px 40px; list-style: none; background: color-mix(in srgb, var(--bg-secondary) 38%, var(--bg-primary)); }
.task-step-row { width: 100%; min-height: 54px; display: grid; grid-template-columns: 24px minmax(150px, 1fr) minmax(80px, .6fr) 66px 58px minmax(82px, auto) 30px; align-items: center; gap: 9px; padding: 6px 12px; border: 0; border-top: 1px solid color-mix(in srgb, var(--border-subtle) 65%, transparent); background: transparent; color: inherit; text-align: left; }
.task-step-row:hover { background: var(--bg-hover); }
.task-step-row.is-selected { background: color-mix(in srgb, var(--text-accent) 7%, var(--bg-primary)); box-shadow: inset 3px 0 0 var(--text-accent); }
.step-rank { width: 22px; height: 22px; display: grid; place-items: center; border: 1px solid var(--border-subtle); border-radius: 50%; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; }
.step-name strong { overflow: hidden; color: var(--text-primary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.step-open, .step-chevron { padding: 0; border: 0; background: transparent; color: inherit; cursor: pointer; text-align: left; }
.step-chevron { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 5px; color: var(--text-tertiary); }
.step-chevron:hover { background: var(--bg-tertiary); color: var(--text-primary); }
.step-outcome { min-width: 0; display: grid; gap: 4px; }
.step-agent-links { display: flex; flex-wrap: wrap; gap: 3px; }
.step-agent-links button { min-width: 0; display: inline-flex; align-items: center; gap: 3px; padding: 2px 5px; border: 1px solid color-mix(in srgb, var(--text-accent) 28%, var(--border-subtle)); border-radius: 4px; background: color-mix(in srgb, var(--text-accent) 6%, var(--bg-primary)); color: var(--text-accent); font-size: 8px; cursor: pointer; }
.step-agent-links button:disabled { opacity: .5; cursor: not-allowed; }
.step-status { display: inline-flex; align-items: center; gap: 5px; color: var(--text-tertiary); font-size: 9px; white-space: nowrap; }
.step-status i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.step-status.status-failed { color: var(--color-error, #ef4444); }
.task-hotspot-empty { padding: 34px 16px; color: var(--text-tertiary); font-size: 11px; text-align: center; }
@media (max-width: 760px) {
  .task-hotspot-summary { grid-template-columns: 24px minmax(130px, 1fr) 90px 14px; }
  .task-bar, .task-secondary { display: none; }
  .task-step-list { padding-left: 14px; }
  .task-step-row { grid-template-columns: 22px minmax(120px, 1fr) 60px minmax(70px, auto) 30px; }
  .step-bar, .step-tokens, .step-status { display: none; }
}
@container (max-width: 650px) {
  .task-hotspot-summary { grid-template-columns: 24px minmax(130px, 1fr) 90px 14px; }
  .task-bar, .task-secondary { display: none; }
  .task-step-list { padding-left: 14px; }
  .task-step-row { grid-template-columns: 22px minmax(120px, 1fr) 60px minmax(70px, auto) 30px; }
  .step-bar, .step-tokens, .step-status { display: none; }
}
@media (prefers-reduced-motion: reduce) { .task-chevron { transition: none; } }
</style>
