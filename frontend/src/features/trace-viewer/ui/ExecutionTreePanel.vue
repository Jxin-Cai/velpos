<script setup>
import { watch } from 'vue'
import { useSession } from '@entities/session'
import { useExecutionTree } from '../model/useExecutionTree'
import ExecutionTreeRow from './ExecutionTreeRow.vue'
import ExecutionDetailViewer from './ExecutionDetailViewer.vue'

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
  subagents,
  selectedLoopId,
  expandedTasks,
  expandedLoops,
  loadTree,
  toggleTask,
  toggleLoop,
  toggleSubagent,
  selectLoop,
  getLoopDetail,
  getLoopLoadState,
  getSubagentState,
  NodeStatus,
} = useExecutionTree()

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
      <div class="exec-tree-body">
        <div class="exec-tree-section">
          <div class="tree-caption">
            <span>Task call chain</span>
            <span>{{ tasks.length }} tasks</span>
          </div>

          <!-- Subagent placeholders at top level -->
          <ExecutionTreeRow
            v-for="sa in subagents"
            :key="sa.tool_use_id"
            :node="sa"
            node-type="subagent"
            :depth="0"
            :expanded="Boolean(getSubagentState(sa.span_id))"
            :load-state="getSubagentState(sa.span_id)?.loading ? 'loading' : 'idle'"
            @toggle="toggleSubagent(sa.span_id)"
          >
            <template v-if="getSubagentState(sa.span_id)?.tree?.tasks">
              <ExecutionTreeRow
                v-for="subTask in getSubagentState(sa.span_id).tree.tasks"
                :key="subTask.id"
                :node="subTask"
                node-type="task"
                :depth="1"
                :expanded="expandedTasks.has(subTask.id)"
                @toggle="toggleTask(subTask.id)"
              >
                <ExecutionTreeRow
                  v-for="loop in subTask.loops"
                  :key="loop.id"
                  :node="loop"
                  node-type="loop"
                  :depth="2"
                  :expanded="expandedLoops.has(loop.id)"
                  :load-state="getLoopLoadState(loop.id)"
                  @toggle="toggleLoop(loop.id)"
                  @select-loop="selectLoop"
                />
              </ExecutionTreeRow>
            </template>
          </ExecutionTreeRow>

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
            <ExecutionTreeRow
              v-for="loop in task.loops"
              :key="loop.id"
              :node="loop"
              node-type="loop"
              :depth="1"
              :expanded="expandedLoops.has(loop.id)"
              :load-state="getLoopLoadState(loop.id)"
              @toggle="toggleLoop(loop.id)"
              @select-loop="selectLoop"
            />
          </ExecutionTreeRow>
        </div>

        <!-- Loop detail pane -->
        <div v-if="selectedLoopId" class="exec-detail-section">
          <div class="detail-section-header">
            <span class="detail-section-title">Loop detail</span>
            <button class="detail-close-btn" type="button" @click="selectedLoopId = null" aria-label="Close detail">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                <path d="m4 4 8 8M12 4l-8 8" />
              </svg>
            </button>
          </div>
          <ExecutionDetailViewer
            :loop-id="selectedLoopId"
            :detail="getLoopDetail(selectedLoopId)"
            :load-state="getLoopLoadState(selectedLoopId)"
            :provenance="provenance"
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
.exec-spinner { width: 16px; height: 16px; border: 1.5px solid var(--border); border-top-color: var(--text-secondary); border-radius: 50%; animation: exec-panel-spin 700ms linear infinite; }
.exec-tree-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-gutter: stable;
}
.exec-tree-section {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 0 4px;
}
.tree-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px 8px;
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.exec-detail-section {
  margin-top: 12px;
  border-top: 1px solid var(--border-subtle);
}
.detail-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 4px;
}
.detail-section-title {
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.detail-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: background 120ms ease, color 120ms ease;
}
.detail-close-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
@keyframes exec-panel-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .exec-spinner { animation: none; } }
</style>
