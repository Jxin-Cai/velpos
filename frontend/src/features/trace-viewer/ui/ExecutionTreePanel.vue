<script setup>
import { computed, watch } from 'vue'
import { useSession } from '@entities/session'
import { useExecutionTree } from '../model/useExecutionTree'
import ExecutionTreeRow from './ExecutionTreeRow.vue'
import ExecutionDetailViewer from './ExecutionDetailViewer.vue'
import InlineSubagentTree from './InlineSubagentTree.vue'

const props = defineProps({
  runId: { type: String, default: null },
})

const { currentSessionId } = useSession()
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

const selectedLoop = computed(() => {
  if (!selectedLoopId.value) return null
  for (const task of tasks.value) {
    const loop = task.loops?.find(item => item.id === selectedLoopId.value)
    if (loop) return loop
  }
  return null
})

function formatThinking(content) {
  if (content == null) return ''
  if (typeof content === 'string') return content
  try {
    return JSON.stringify(content, null, 2)
  } catch {
    return String(content)
  }
}

watch([() => props.runId, currentSessionId], ([runId, sessionId]) => {
  if (runId && sessionId) {
    loadTree(sessionId, runId)
  }
}, { immediate: true })
</script>

<template>
  <div class="exec-tree-panel">
    <div v-if="loading && !tree" class="exec-loading">
      <span class="exec-spinner" aria-hidden="true"></span>
      <span>Loading execution tree...</span>
    </div>

    <div v-else-if="error" class="exec-error">
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <circle cx="10" cy="10" r="7.25"/><path d="M10 6.5v4.25M10 13.5h.01"/>
      </svg>
      <span>{{ error }}</span>
    </div>

    <div v-else-if="!tree || tasks.length === 0" class="exec-empty">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
        <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/>
        <rect x="9" y="3" width="6" height="4" rx="1"/>
        <path d="M9 12h6M9 16h4"/>
      </svg>
      <p>No execution tasks found for this run</p>
    </div>

    <template v-else>
      <div class="exec-tree-body" :class="{ 'has-detail': selectedLoopId }">
        <div class="exec-tree-section">
          <div class="tree-caption tree-caption--sticky">
            <span>Task call chain</span>
            <span class="tree-count">{{ tasks.length }} tasks</span>
          </div>

          <!-- Main agent tasks -->
          <ExecutionTreeRow
            v-for="task in tasks"
            :key="task.id"
            :node="task"
            node-type="task"
            :depth="0"
            :expanded="expandedTasks.has(task.id)"
            @toggle="toggleTask(task.id)"
          >
            <section v-if="task.thinking?.length" class="task-thinking" aria-label="Task thinking and planning">
              <article v-for="(thought, thoughtIndex) in task.thinking" :key="`${thought.loop_id}-${thoughtIndex}`" class="task-thinking-item">
                <div class="task-thinking-header">
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M8 2.5a4 4 0 0 0-2.4 7.2c.4.3.65.75.65 1.25h3.5c0-.5.25-.95.65-1.25A4 4 0 0 0 8 2.5Z"/><path d="M6.5 13h3M7 11h2"/></svg>
                  <span>{{ thought.phase === 'planning' ? 'Plan before execution' : 'Thinking' }}</span>
                </div>
                <p>{{ formatThinking(thought.content) }}</p>
              </article>
            </section>
            <ExecutionTreeRow
              v-for="loop in task.loops"
              :key="loop.id"
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
                v-for="subagent in loop.subagents"
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
          </ExecutionTreeRow>
        </div>

        <!-- Loop detail pane -->
        <div v-if="selectedLoopId" class="exec-detail-section">
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
.exec-empty p { margin: 0; color: var(--text-secondary); font-size: 13px; }
.subagent-inline-state { padding: 10px 14px 10px 60px; color: var(--text-tertiary); font-size: 11px; }
.subagent-inline-state--error { color: var(--color-error, #ef4444); }
.task-thinking { display: grid; gap: 6px; padding: 4px 8px 7px 48px; }
.task-thinking-item { min-width: 0; padding: 9px 11px; border: 1px solid color-mix(in srgb, var(--text-accent) 22%, var(--border-subtle)); border-radius: 8px; background: color-mix(in srgb, var(--text-accent) 4%, var(--bg-primary)); }
.task-thinking-header { display: flex; align-items: center; gap: 6px; color: var(--text-accent); font-family: var(--font-mono); font-size: 9px; font-weight: 650; letter-spacing: .05em; text-transform: uppercase; }
.task-thinking-item p { max-height: 180px; margin: 7px 0 0; overflow: auto; color: var(--text-secondary); font-size: 11px; line-height: 1.6; white-space: pre-wrap; }
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
