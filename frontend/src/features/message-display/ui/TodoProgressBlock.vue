<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  todos: { type: Array, required: true },
})

const collapsed = ref(false)

const counts = computed(() => {
  const c = { pending: 0, in_progress: 0, completed: 0, total: props.todos.length }
  for (const t of props.todos) {
    if (t.status === 'in_progress') c.in_progress++
    else if (t.status === 'completed') c.completed++
    else c.pending++
  }
  return c
})

const pctDone = computed(() => counts.value.total > 0 ? (counts.value.completed / counts.value.total * 100) : 0)
const pctActive = computed(() => counts.value.total > 0 ? (counts.value.in_progress / counts.value.total * 100) : 0)
</script>

<template>
  <div class="todo-progress" :class="{ collapsed }">
    <!-- Header: summary + toggle -->
    <button class="todo-header" @click="collapsed = !collapsed">
      <svg class="todo-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 11l3 3L22 4"/>
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
      </svg>
      <span class="todo-title">Plan</span>
      <span class="todo-fraction">
        <span class="todo-done-num">{{ counts.completed }}</span>
        <span class="todo-sep">/</span>
        <span class="todo-total-num">{{ counts.total }}</span>
      </span>
      <span v-if="counts.in_progress > 0" class="todo-running-badge">{{ counts.in_progress }} running</span>
      <span v-else-if="counts.completed === counts.total && counts.total > 0" class="todo-done-badge">done</span>
      <!-- Chevron -->
      <svg class="todo-chevron" :class="{ open: !collapsed }" width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
        <path d="M4.646 5.646a.5.5 0 0 1 .708 0L8 8.293l2.646-2.647a.5.5 0 0 1 .708.708l-3 3a.5.5 0 0 1-.708 0l-3-3a.5.5 0 0 1 0-.708z"/>
      </svg>
    </button>

    <!-- Progress bar -->
    <div class="todo-bar">
      <div class="todo-bar-done" :style="{ width: pctDone + '%' }"></div>
      <div class="todo-bar-active" :style="{ width: pctActive + '%' }"></div>
    </div>

    <!-- Task list (collapsible) -->
    <div class="todo-list-wrap">
      <div class="todo-list">
        <div
          v-for="(task, idx) in todos"
          :key="idx"
          class="todo-item"
          :class="'todo-item--' + task.status"
        >
          <!-- Rail -->
          <div class="todo-rail">
            <div class="todo-connector todo-connector--top" :class="{ hidden: idx === 0 }"></div>
            <div class="todo-node">
              <span v-if="task.status === 'in_progress'" class="todo-spinner"></span>
              <svg v-else-if="task.status === 'completed'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              <span v-else class="todo-dot"></span>
            </div>
            <div class="todo-connector todo-connector--bot" :class="{ hidden: idx === todos.length - 1 }"></div>
          </div>
          <!-- Content -->
          <div class="todo-content">
            <div class="todo-label" :class="{ 'todo-label--done': task.status === 'completed' }">
              {{ task.status === 'in_progress' && task.activeForm ? task.activeForm : task.subject }}
            </div>
            <div v-if="task.status === 'in_progress' && task.activeForm && task.subject" class="todo-detail">
              {{ task.subject }}
            </div>
          </div>
          <span class="todo-step">{{ idx + 1 }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.todo-progress {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  overflow: hidden;
  margin-top: 4px;
}

.todo-progress:hover {
  border-color: var(--border);
}

/* ── Header ── */
.todo-header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 10px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: var(--font-sans);
  transition: background var(--transition-fast);
}

.todo-header:hover {
  background: var(--bg-hover);
}

.todo-icon {
  color: var(--green);
  flex-shrink: 0;
}

.todo-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.todo-fraction {
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  font-family: var(--font-mono);
}

.todo-done-num { color: var(--green); }
.todo-sep { color: var(--text-muted); font-weight: 400; }
.todo-total-num { color: var(--text-secondary); }

.todo-running-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-weight: 500;
  color: var(--accent);
  background: var(--accent-dim);
}

.todo-done-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-weight: 500;
  color: var(--green);
  background: var(--green-dim);
}

.todo-chevron {
  margin-left: auto;
  color: var(--text-muted);
  transition: transform var(--transition-base);
}

.todo-chevron.open {
  transform: rotate(180deg);
}

/* ── Progress bar ── */
.todo-bar {
  height: 3px;
  background: var(--bg-hover);
  display: flex;
}

.todo-bar-done {
  height: 100%;
  background: var(--green);
  transition: width 0.4s ease;
}

.todo-bar-active {
  height: 100%;
  background: var(--accent);
  transition: width 0.4s ease;
  animation: todo-pulse 2s ease-in-out infinite;
}

@keyframes todo-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ── List ── */
.todo-list-wrap {
  display: grid;
  grid-template-rows: 1fr;
  transition: grid-template-rows 0.25s ease;
}

.collapsed .todo-list-wrap {
  grid-template-rows: 0fr;
}

.todo-list {
  min-height: 0;
  overflow: hidden;
  padding: 2px 0 4px;
}

.collapsed .todo-list {
  opacity: 0;
  transition: opacity 0.15s ease;
}

/* ── Item ── */
.todo-item {
  display: flex;
  align-items: stretch;
  padding: 0 10px 0 8px;
  min-height: 30px;
  transition: background var(--transition-fast);
}

.todo-item:hover {
  background: var(--bg-hover);
}

/* Rail */
.todo-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 22px;
  flex-shrink: 0;
}

.todo-connector {
  width: 2px;
  flex: 1;
  background: var(--border);
  min-height: 3px;
}

.todo-connector.hidden { background: transparent; }

.todo-item--completed .todo-connector { background: var(--green); }
.todo-item--in_progress .todo-connector--top { background: var(--accent); }

.todo-node {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.todo-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  border: 2px solid var(--text-muted);
}

.todo-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid color-mix(in srgb, var(--accent) 30%, transparent);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: todo-spin 0.8s linear infinite;
}

@keyframes todo-spin {
  to { transform: rotate(360deg); }
}

.todo-item--completed .todo-node { color: var(--green); }
.todo-item--in_progress .todo-node { color: var(--accent); }
.todo-item--pending .todo-node { color: var(--text-muted); }

/* Content */
.todo-content {
  flex: 1;
  min-width: 0;
  padding: 4px 0;
}

.todo-label {
  font-size: 12px;
  color: var(--text-primary);
  line-height: 1.4;
  word-break: break-word;
}

.todo-item--in_progress .todo-label {
  font-weight: 600;
  color: var(--accent);
}

.todo-label--done {
  text-decoration: line-through;
  color: var(--text-muted);
}

.todo-detail {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.3;
  margin-top: 1px;
}

.todo-step {
  font-size: 10px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
  padding-top: 5px;
  min-width: 14px;
  text-align: right;
}

.todo-item--completed .todo-step { color: var(--green); }
.todo-item--in_progress .todo-step { color: var(--accent); }
</style>
