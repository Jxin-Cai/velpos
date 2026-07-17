<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useTraceTree } from '../model/useTraceTree'
import TraceSpanRow from './TraceSpanRow.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  initialRunId: { type: String, default: null },
})

const emit = defineEmits(['close'])
const dialogEl = ref(null)

const {
  currentSessionId,
  traceTree,
  runIds,
  selectedRunId,
  stats,
  loading,
  error,
  selectRun,
  loadTraceHistory,
} = useTraceTree()

watch(() => props.initialRunId, (id) => {
  if (id) selectRun(id)
}, { immediate: true })

watch([() => props.visible, currentSessionId], ([visible]) => {
  if (!visible) return
  if (props.initialRunId) selectRun(props.initialRunId)
  loadTraceHistory()
  nextTick(() => dialogEl.value?.focus())
}, { immediate: true })

const runPosition = computed(() => {
  const index = runIds.value.indexOf(selectedRunId.value)
  return index < 0 ? '' : `${index + 1} / ${runIds.value.length}`
})

const overallStatus = computed(() => {
  if (!stats.value.spanCount) return { label: 'No data', className: 'is-empty' }
  if (stats.value.runningCount) return { label: 'Running', className: 'is-running' }
  if (stats.value.failedCount) return { label: 'Needs attention', className: 'is-failed' }
  if (stats.value.cancelledCount) return { label: 'Cancelled', className: 'is-cancelled' }
  return { label: 'Completed', className: 'is-completed' }
})

function formatDuration(ms) {
  if (!ms || ms <= 0) return '0ms'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function handleWindowKeydown(event) {
  if (props.visible && event.key === 'Escape') emit('close')
}

onMounted(() => window.addEventListener('keydown', handleWindowKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', handleWindowKeydown))
</script>

<template>
  <Teleport to="body">
    <Transition name="trace-sheet">
      <div v-if="visible" class="trace-overlay" @click.self="emit('close')" @keydown.esc="emit('close')">
        <section
          ref="dialogEl"
          class="trace-panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby="trace-panel-title"
          tabindex="-1"
        >
          <header class="trace-header">
            <div class="trace-heading">
              <div class="trace-eyebrow">
                <span class="eyebrow-mark" aria-hidden="true"></span>
                History
              </div>
              <div class="trace-title-line">
                <h2 id="trace-panel-title" class="trace-title">Execution trace</h2>
                <span class="trace-state" :class="overallStatus.className">
                  <span class="state-dot" aria-hidden="true"></span>
                  {{ overallStatus.label }}
                </span>
              </div>
              <p class="trace-subtitle">Follow each agent turn and inspect every tool request and response in context.</p>
            </div>
            <button class="close-btn" type="button" title="Close" aria-label="关闭历史树" @click="emit('close')">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                <path d="m4 4 8 8M12 4l-8 8" />
              </svg>
            </button>
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
                @change="selectRun($event.target.value)"
              >
                <option v-for="rid in runIds" :key="rid" :value="rid">{{ rid }}</option>
              </select>
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                <path d="m4 6 4 4 4-4" />
              </svg>
            </label>
          </div>

          <main class="trace-body">
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
              <div class="tree-caption">
                <span>Execution flow</span>
                <span>{{ stats.turnCount }} turns · {{ stats.toolCallCount }} tools</span>
              </div>
              <TraceSpanRow v-for="node in traceTree" :key="node.id" :node="node" :depth="0" />
            </div>
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
  width: min(860px, calc(100vw - (var(--dialog-gutter) * 2)));
  height: calc(100dvh - (var(--dialog-gutter) * 2));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--dialog-border);
  border-radius: var(--dialog-radius);
  outline: none;
  background: var(--dialog-surface);
  box-shadow: var(--dialog-shadow);
}
.trace-header {
  display: flex;
  flex-shrink: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 22px 24px 18px;
}
.trace-heading { min-width: 0; }
.trace-eyebrow {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 7px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.eyebrow-mark { width: 5px; height: 5px; border-radius: 50%; background: var(--text-tertiary); }
.trace-title-line { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.trace-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 20px;
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
.trace-subtitle { margin: 7px 0 0; color: var(--text-tertiary); font-size: 12px; line-height: 1.5; }
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
  min-height: 48px;
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 24px;
  border-top: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
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
  padding: 18px 16px 24px;
  scrollbar-gutter: stable;
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
.tree-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px 8px;
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.trace-tree { display: flex; flex-direction: column; gap: 1px; }
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
  .trace-header { padding: 18px 18px 14px; }
  .trace-title { font-size: 18px; }
  .trace-subtitle { max-width: 280px; }
  .run-bar { padding: 8px 18px; }
  .trace-run-id { max-width: 150px; }
  .trace-body { padding: 14px 10px 20px; }
  .trace-footer { gap: 12px; padding: 8px 18px; overflow-x: auto; }
  .footer-divider, .footer-spacer { display: none; }
}
</style>
