<script setup>
import { formatDuration } from '@shared/lib/formatTime'
import { formatTokens } from '@shared/lib/formatNumber'

defineProps({
  telemetry: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  sessionState: { type: Object, required: true },
  exceptionCount: { type: Number, default: 0 },
  exceptionCountLoading: { type: Boolean, default: false },
})

function formatCost(value) {
  const number = Number(value) || 0
  return number < 0.01 ? `$${number.toFixed(4)}` : `$${number.toFixed(2)}`
}
</script>

<template>
  <section class="telemetry-strip" aria-label="OpenTelemetry run summary" :aria-busy="loading">
    <div class="telemetry-source-card">
      <span class="telemetry-label">Signals</span>
      <strong>{{ telemetry?.source === 'claude_code_otel' ? 'Claude Code native' : 'Compatibility trace' }}</strong>
      <span>{{ telemetry?.trace_count || 0 }} trace · {{ telemetry?.log_event_count || 0 }} logs · {{ telemetry?.metric_sample_count || 0 }} metrics</span>
    </div>
    <div class="telemetry-stat">
      <span>Session</span>
      <strong>{{ sessionState.label }}</strong>
      <small>{{ sessionState.action }}</small>
    </div>
    <div class="telemetry-stat">
      <span>Token usage</span>
      <strong>{{ formatTokens((telemetry?.input_tokens || 0) + (telemetry?.output_tokens || 0)) }}</strong>
      <small>{{ formatTokens(telemetry?.cache_read_tokens || 0) }} cache read</small>
    </div>
    <div class="telemetry-stat">
      <span>Estimated cost</span>
      <strong>{{ formatCost(telemetry?.cost_usd) }}</strong>
      <small>{{ telemetry?.llm_request_count || 0 }} requests · {{ telemetry?.raw_api_body_count || 0 }} raw bodies</small>
    </div>
    <div class="telemetry-stat">
      <span>LLM latency p95</span>
      <strong>{{ formatDuration(telemetry?.llm_latency_p95_ms || 0) }}</strong>
      <small>p50 {{ formatDuration(telemetry?.llm_latency_p50_ms || 0) }} · TTFT {{ formatDuration(telemetry?.ttft_p95_ms || 0) }}</small>
    </div>
    <div class="telemetry-stat" :class="{ 'telemetry-stat--error': exceptionCount > 0 || telemetry?.api_error_count }">
      <span>Exceptions</span>
      <strong>{{ exceptionCountLoading ? '…' : exceptionCount }}</strong>
      <small>{{ telemetry?.api_error_count || 0 }} API errors · {{ telemetry?.retry_count || 0 }} retries</small>
    </div>
  </section>
</template>

<style scoped>
.telemetry-strip {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: minmax(160px, 1.2fr) repeat(5, minmax(112px, 1fr));
  margin: 0 8px 6px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: var(--bg-secondary);
}
.telemetry-source-card,
.telemetry-stat {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  padding: 8px 12px;
  border-right: 1px solid var(--border-subtle);
}
.telemetry-stat:last-child { border-right: 0; }
.telemetry-source-card {
  background: linear-gradient(135deg, color-mix(in srgb, var(--text-accent) 10%, var(--bg-primary)), var(--bg-secondary));
}
.telemetry-label,
.telemetry-stat > span {
  overflow: hidden;
  color: var(--text-tertiary);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: .08em;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}
.telemetry-source-card strong { color: var(--text-primary); font-size: 12px; font-weight: 600; }
.telemetry-source-card > span:last-child,
.telemetry-stat small {
  overflow: hidden;
  color: var(--text-tertiary);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.telemetry-stat strong {
  overflow: hidden;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.telemetry-stat--error strong { color: var(--color-error, #ef4444); }
@media (max-width: 980px) {
  .telemetry-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .telemetry-source-card { grid-column: 1 / -1; border-right: 0; border-bottom: 1px solid var(--border-subtle); }
  .telemetry-stat:nth-child(2), .telemetry-stat:nth-child(3), .telemetry-stat:nth-child(4) { border-bottom: 1px solid var(--border-subtle); }
}
@media (max-width: 640px) {
  .telemetry-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-inline: 4px; }
  .telemetry-stat:nth-child(5) { border-right: 0; }
}
</style>
