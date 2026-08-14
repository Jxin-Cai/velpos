<script setup>
import { computed } from 'vue'
import SpanPayloadViewer from './SpanPayloadViewer.vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  sortMode: { type: String, required: true },
  p90DurationMs: { type: Number, default: 0 },
})

const maxDuration = computed(() => Math.max(...props.rows.map(row => row.selfDurationMs), 1))
const maxTokens = computed(() => Math.max(...props.rows.map(row => row.tokens), 1))

function displayName(span) {
  if (span.span_type === 'llm_turn') return span.metadata?.model || span.metadata?.['gen_ai.request.model'] || 'Model turn'
  if (span.span_type === 'tool_execution') return span.name || 'Tool execution'
  if (span.span_type === 'permission_wait') return span.name || 'Permission wait'
  if (span.span_type === 'subagent') return span.name || 'Subagent'
  return span.name || span.metadata?.['otel.span_name'] || 'Recorded span'
}

function typeLabel(type) {
  return ({
    llm_turn: 'LLM', tool_call: 'Tool', tool_execution: 'Exec', permission_wait: 'Wait',
    subagent: 'Agent', hook: 'Hook', otel_span: 'Span',
  })[type] || 'Event'
}

function formatDuration(ms) {
  if (!ms) return '0ms'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`
  const minutes = Math.floor(ms / 60000)
  return `${minutes}m ${Math.round((ms % 60000) / 1000)}s`
}

function formatTokens(value) {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}m`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  return String(value || 0)
}
</script>

<template>
  <section class="hotspot-panel" :aria-label="sortMode === 'tokens' ? 'Steps ranked by token usage' : 'Steps ranked by duration'">
    <header class="hotspot-header">
      <div>
        <span class="hotspot-kicker">Hotspot analysis</span>
        <h3>{{ sortMode === 'tokens' ? 'Highest token consumption' : 'Longest-running steps' }}</h3>
        <p>{{ sortMode === 'tokens' ? 'Model steps are ranked by input plus output tokens.' : `Ranked by self time to avoid double-counting child work. Wall-time p90 is ${formatDuration(p90DurationMs)}.` }}</p>
      </div>
      <span class="hotspot-count">{{ rows.length }} ranked steps</span>
    </header>

    <div v-if="rows.length" class="hotspot-table" role="table">
      <div class="hotspot-table-head" role="row">
        <span role="columnheader">Rank / step</span>
        <span role="columnheader">Self duration</span>
        <span role="columnheader">Tokens</span>
        <span role="columnheader">Status</span>
      </div>
      <details v-for="(row, index) in rows" :key="row.span.id" class="hotspot-row" :class="`latency-${row.durationBand}`">
        <summary class="hotspot-row-summary" role="row">
          <span class="hotspot-name-cell" role="cell">
            <b class="hotspot-rank">{{ String(index + 1).padStart(2, '0') }}</b>
            <span class="hotspot-type">{{ typeLabel(row.span.span_type) }}</span>
            <span class="hotspot-name" :title="displayName(row.span)">{{ displayName(row.span) }}</span>
            <span v-if="sortMode === 'duration' && row.durationBand === 'hot'" class="outlier-badge">Top 10%</span>
            <span v-else-if="sortMode === 'tokens' && row.tokenShare >= 0.1" class="outlier-badge outlier-badge--tokens">
              {{ Math.round(row.tokenShare * 1000) / 10 }}% tokens
            </span>
          </span>
          <span class="metric-cell" role="cell">
            <span class="metric-value" :title="`Wall time: ${formatDuration(row.durationMs)}`">{{ formatDuration(row.selfDurationMs) }}</span>
            <span class="metric-track" aria-hidden="true"><span class="metric-fill metric-fill--duration" :style="{ width: `${Math.max(row.selfDurationMs / maxDuration * 100, 2)}%` }"></span></span>
          </span>
          <span class="metric-cell" role="cell">
            <span class="metric-value">{{ formatTokens(row.tokens) }}</span>
            <span class="metric-track" aria-hidden="true"><span class="metric-fill metric-fill--tokens" :style="{ width: `${row.tokens ? Math.max(row.tokens / maxTokens * 100, 2) : 0}%` }"></span></span>
          </span>
          <span class="hotspot-status" :class="`status-${row.span.status}`" role="cell"><i aria-hidden="true"></i>{{ row.span.status || 'unknown' }}</span>
          <svg class="hotspot-chevron" width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg>
        </summary>
        <div class="hotspot-detail">
          <div class="hotspot-detail-stats">
            <span><b>{{ formatDuration(row.selfDurationMs) }}</b> self duration</span>
            <span><b>{{ formatDuration(row.durationMs) }}</b> wall duration</span>
            <span><b>{{ formatTokens(row.tokens) }}</b> tokens</span>
            <span v-if="row.tokens"><b>{{ Math.round(row.tokenShare * 1000) / 10 }}%</b> of measured tokens</span>
            <code>{{ row.span.id }}</code>
          </div>
          <div v-if="row.span.input_preview != null || row.span.output_preview != null" class="hotspot-payloads">
            <SpanPayloadViewer v-if="row.span.input_preview != null" :payload="row.span.input_preview" label="Input" />
            <SpanPayloadViewer v-if="row.span.output_preview != null" :payload="row.span.output_preview" label="Output" />
          </div>
          <pre v-if="row.span.error" class="hotspot-error">{{ row.span.error }}</pre>
        </div>
      </details>
    </div>
    <div v-else class="hotspot-empty">No steps contain this metric for the selected filter.</div>
  </section>
</template>

<style scoped>
.hotspot-panel { overflow: hidden; border: 1px solid var(--border-subtle); border-radius: 10px; background: var(--bg-primary); }
.hotspot-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 16px 18px; border-bottom: 1px solid var(--border-subtle); background: color-mix(in srgb, var(--bg-secondary) 72%, transparent); }
.hotspot-kicker { color: var(--text-accent); font-family: var(--font-mono); font-size: 9px; font-weight: 650; letter-spacing: .08em; text-transform: uppercase; }
.hotspot-header h3 { margin: 4px 0 0; color: var(--text-primary); font-size: 14px; font-weight: 620; }
.hotspot-header p { margin: 4px 0 0; color: var(--text-tertiary); font-size: 10px; }
.hotspot-count { flex: 0 0 auto; padding: 4px 8px; border: 1px solid var(--border-subtle); border-radius: 999px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; }
.hotspot-table-head, .hotspot-row-summary { display: grid; grid-template-columns: minmax(250px, 1.45fr) minmax(130px, .65fr) minmax(120px, .6fr) 86px 14px; align-items: center; gap: 12px; }
.hotspot-table-head { min-height: 32px; padding: 0 12px; border-bottom: 1px solid var(--border-subtle); color: var(--text-tertiary); font-size: 9px; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; }
.hotspot-row { border-bottom: 1px solid color-mix(in srgb, var(--border-subtle) 70%, transparent); }
.hotspot-row:last-child { border-bottom: 0; }
.hotspot-row-summary { min-height: 48px; padding: 6px 12px; cursor: pointer; list-style: none; transition: background 160ms ease; }
.hotspot-row-summary::-webkit-details-marker { display: none; }
.hotspot-row-summary:hover { background: var(--bg-hover); }
.hotspot-row-summary:focus-visible { outline: 2px solid var(--text-accent); outline-offset: -2px; }
.hotspot-name-cell { min-width: 0; display: flex; align-items: center; gap: 8px; }
.hotspot-rank { width: 22px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; }
.hotspot-type { min-width: 36px; color: var(--text-tertiary); font-family: var(--font-mono); font-size: 9px; font-weight: 650; text-transform: uppercase; }
.hotspot-name { min-width: 0; overflow: hidden; color: var(--text-primary); font-size: 11px; font-weight: 540; text-overflow: ellipsis; white-space: nowrap; }
.outlier-badge { flex: 0 0 auto; padding: 2px 5px; border-radius: 4px; background: color-mix(in srgb, #ef4444 13%, transparent); color: #dc2626; font-size: 8px; font-weight: 700; text-transform: uppercase; }
.outlier-badge--tokens { background: color-mix(in srgb, #8b5cf6 14%, transparent); color: #7c3aed; }
.metric-cell { min-width: 0; display: grid; grid-template-columns: 50px 1fr; align-items: center; gap: 7px; }
.metric-value { color: var(--text-secondary); font-family: var(--font-mono); font-size: 9px; text-align: right; }
.metric-track { height: 6px; overflow: hidden; border-radius: 999px; background: var(--bg-tertiary); }
.metric-fill { display: block; height: 100%; border-radius: inherit; }
.metric-fill--duration { background: linear-gradient(90deg, #38bdf8, #f59e0b 70%, #ef4444); }
.metric-fill--tokens { background: linear-gradient(90deg, #818cf8, #a855f7); }
.hotspot-status { display: inline-flex; align-items: center; gap: 5px; color: var(--text-tertiary); font-size: 9px; text-transform: capitalize; }
.hotspot-status i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.hotspot-status.status-failed { color: var(--color-error, #ef4444); }
.hotspot-status.status-running { color: var(--text-accent); }
.hotspot-status.status-denied, .hotspot-status.status-cancelled, .hotspot-status.status-abandoned { color: var(--color-warning, #f59e0b); }
.hotspot-chevron { color: var(--text-tertiary); transition: transform 160ms ease; }
.hotspot-row[open] .hotspot-chevron { transform: rotate(180deg); }
.hotspot-detail { display: grid; gap: 10px; padding: 12px 14px 14px 78px; border-top: 1px solid var(--border-subtle); background: color-mix(in srgb, var(--bg-secondary) 50%, var(--bg-primary)); }
.hotspot-detail-stats { display: flex; flex-wrap: wrap; gap: 8px 16px; color: var(--text-tertiary); font-size: 10px; }
.hotspot-detail-stats b { color: var(--text-primary); font-family: var(--font-mono); }
.hotspot-detail-stats code { margin-left: auto; color: var(--text-tertiary); font-size: 9px; }
.hotspot-payloads { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.hotspot-error { margin: 0; color: var(--color-error, #ef4444); font-size: 10px; white-space: pre-wrap; }
.hotspot-empty { padding: 36px 18px; color: var(--text-tertiary); font-size: 11px; text-align: center; }
@media (max-width: 800px) {
  .hotspot-table-head, .hotspot-row-summary { grid-template-columns: minmax(180px, 1fr) 120px 14px; }
  .hotspot-table-head span:nth-child(3), .hotspot-table-head span:nth-child(4), .hotspot-row-summary > :nth-child(3), .hotspot-row-summary > :nth-child(4) { display: none; }
  .hotspot-detail { padding-left: 14px; }
  .hotspot-payloads { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) { .hotspot-row-summary, .hotspot-chevron { transition: none; } }
</style>
