<script setup>
import { computed, ref } from 'vue'
import WishCardDetailDialog from './WishCardDetailDialog.vue'

const props = defineProps({
  card: { type: Object, required: true },
  projectId: { type: String, required: true },
  draggable: { type: Boolean, default: true },
  keyboardDragging: { type: Boolean, default: false },
})

const emit = defineEmits(['dragstart', 'dragend', 'navigate', 'retry', 'delete'])

const STATUS_CONFIG = {
  backlog: { label: 'Backlog', cssClass: 'badge--muted' },
  preparing: { label: 'Preparing', cssClass: 'badge--info' },
  running: { label: 'Running', cssClass: 'badge--running' },
  completed: { label: 'Done', cssClass: 'badge--success' },
  failed: { label: 'Failed', cssClass: 'badge--danger' },
  cancelled: { label: 'Cancelled', cssClass: 'badge--muted' },
  archived: { label: 'Archived', cssClass: 'badge--muted' },
}

const statusConfig = computed(() => STATUS_CONFIG[props.card.status] || STATUS_CONFIG.backlog)
const isRunning = computed(() => props.card.status === 'running')
const canRetry = computed(() => props.card.status === 'failed' || props.card.status === 'cancelled')
const executionHistory = computed(() => Array.isArray(props.card.execution_history)
  ? props.card.execution_history
  : [])
const latestOutput = computed(() => {
  for (let index = executionHistory.value.length - 1; index >= 0; index -= 1) {
    if (executionHistory.value[index]?.output) return executionHistory.value[index].output
  }
  return null
})
const latestSummary = computed(() => latestOutput.value?.content?.stage_summary || '')
const readinessLabel = computed(() => {
  const readiness = props.card.handoff_readiness
  if (readiness === 'ready') return 'Context ready'
  if (readiness === 'degraded') return 'Review context'
  if (readiness === 'legacy') return 'Context on move'
  if (props.card.status === 'completed') return 'Preparing context'
  return ''
})
const detailsVisible = ref(false)
const deleteConfirmationVisible = ref(false)

function handleDragStart(event) {
  if (!props.draggable) {
    event.preventDefault()
    return
  }
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', props.card.id)
  emit('dragstart', { card: props.card, event })
}

function handleRetry(e) {
  e.stopPropagation()
  if (props.card.execution_id) emit('retry', props.card.execution_id)
}

function handleAnswer(e) {
  e.stopPropagation()
  if (props.card.session_id) emit('navigate', props.card.session_id)
}

function handleDelete(e) {
  e.stopPropagation()
  if (!deleteConfirmationVisible.value) {
    deleteConfirmationVisible.value = true
    return
  }
  emit('delete', props.card.id)
  deleteConfirmationVisible.value = false
}

function handleKeyDown(e) {
  // Once keyboard drag mode is active, the board-level handler owns arrow,
  // drop and cancel keys. Let those events bubble to it.
  if (props.keyboardDragging) return
  if (e.key === 'Enter' || e.key === ' ') {
    if (props.draggable) {
      e.preventDefault()
      e.stopPropagation()
      emit('dragstart', { card: props.card, event: e, keyboard: true })
    }
  }
}
</script>

<template>
  <div
    class="wish-card"
    :class="{
      'wish-card--draggable': draggable,
      'wish-card--running': isRunning,
      'wish-card--preparing': card.status === 'preparing',
      'wish-card--completed': card.status === 'completed',
      'wish-card--failed': card.status === 'failed',
      'wish-card--needs-attention': card.needs_user_action,
    }"
    :data-wish-card-id="card.id"
    :draggable="draggable"
    :tabindex="draggable ? 0 : -1"
    :aria-grabbed="keyboardDragging"
    :aria-label="`Card: ${card.title}, status: ${statusConfig.label}${card.needs_user_action ? ', needs your attention' : ''}`"
    role="listitem"
    @dragstart="handleDragStart"
    @dragend="emit('dragend')"
    @keydown="handleKeyDown"
  >
    <div class="wish-card__header">
      <span class="wish-card__title">{{ card.title }}</span>
      <span class="wish-card__badge" :class="statusConfig.cssClass">
        {{ statusConfig.label }}
      </span>
    </div>
    <p v-if="card.description" class="wish-card__desc">{{ card.description }}</p>
    <p v-if="latestSummary" class="wish-card__summary">{{ latestSummary }}</p>
    <div v-if="executionHistory.length || readinessLabel" class="wish-card__context-meta">
      <span v-if="executionHistory.length">
        {{ executionHistory.length }} {{ executionHistory.length === 1 ? 'stage' : 'stages' }}
      </span>
      <span
        v-if="readinessLabel"
        class="wish-card__readiness"
        :data-readiness="card.handoff_readiness"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path v-if="card.handoff_readiness === 'ready'" d="m5 12 4 4L19 6" />
          <template v-else>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5l3 2" />
          </template>
        </svg>
        {{ readinessLabel }}
      </span>
    </div>
    <div v-if="isRunning" class="wish-card__progress">
      <div class="progress-bar">
        <div class="progress-bar__fill"></div>
      </div>
    </div>
    <div class="wish-card__actions" @pointerdown.stop @dragstart.stop.prevent>
      <button
        type="button"
        class="wish-card__action"
        @click.stop="detailsVisible = true"
      >
        Details
      </button>
      <button
        v-if="card.needs_user_action && card.session_id"
        type="button"
        class="wish-card__action wish-card__action--answer"
        @click="handleAnswer"
      >
        Answer
      </button>
      <button
        v-if="canRetry && card.execution_id"
        type="button"
        class="wish-card__action"
        @click="handleRetry"
      >
        Retry
      </button>
      <button
        v-if="card.status === 'archived'"
        type="button"
        class="wish-card__action wish-card__action--danger"
        @click="handleDelete"
      >
        {{ deleteConfirmationVisible ? 'Confirm delete' : 'Delete' }}
      </button>
    </div>

    <WishCardDetailDialog
      :visible="detailsVisible"
      :card="card"
      :project-id="projectId"
      @close="detailsVisible = false"
      @navigate="(sessionId) => emit('navigate', sessionId)"
    />
  </div>
</template>

<style scoped>
.wish-card {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
  touch-action: none;
}

.wish-card--draggable {
  cursor: grab;
}

.wish-card--draggable:hover {
  border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
  box-shadow: var(--shadow-xs);
}

.wish-card--dragging {
  opacity: 0.6;
  transform: scale(0.97);
  cursor: grabbing;
}

.wish-card--running {
  border-color: #f2c94c;
  box-shadow: 0 0 0 1px color-mix(in srgb, #f2c94c 25%, transparent);
}

.wish-card--preparing {
  border-color: color-mix(in srgb, #61afef 70%, var(--border));
}

.wish-card--completed {
  border-color: #42b883;
  box-shadow: 0 0 0 1px color-mix(in srgb, #42b883 20%, transparent);
}

.wish-card--failed {
  border-color: #e06c75;
  box-shadow: 0 0 0 1px color-mix(in srgb, #e06c75 22%, transparent);
}

.wish-card--needs-attention {
  animation: wish-card-attention 1.25s ease-in-out infinite;
}

@keyframes wish-card-attention {
  0%, 100% { box-shadow: 0 0 0 1px color-mix(in srgb, #f2c94c 25%, transparent); }
  50% { box-shadow: 0 0 0 3px color-mix(in srgb, #f2c94c 60%, transparent), 0 0 18px color-mix(in srgb, #f2c94c 40%, transparent); }
}

@media (prefers-reduced-motion: reduce) {
  .wish-card--needs-attention { animation: none; }
}

.wish-card:focus-visible {
  outline: none;
  box-shadow: var(--ring);
  border-color: var(--accent);
}

.wish-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.wish-card__summary {
  display: -webkit-box;
  margin: 8px 0 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.wish-card__context-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 9px;
  color: var(--text-muted);
  font-size: 10px;
}

.wish-card__readiness {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.wish-card__readiness[data-readiness="ready"] {
  color: var(--status-success);
}

.wish-card__readiness[data-readiness="degraded"] {
  color: var(--status-running);
}

.wish-card__title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.wish-card__badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
}

.badge--muted {
  background: var(--bg-hover);
  color: var(--text-muted);
}

.badge--info {
  background: var(--accent-dim);
  color: var(--accent);
}

.badge--running {
  background: var(--status-running-bg);
  color: var(--status-running);
}

.badge--success {
  background: var(--status-success-bg);
  color: var(--status-success);
}

.badge--danger {
  background: var(--status-danger-bg);
  color: var(--status-danger);
}

.wish-card__desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.wish-card__progress {
  margin-top: 8px;
}

.wish-card__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
  padding-top: 7px;
  border-top: 1px solid var(--border-subtle);
}

.wish-card__action {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
}

.wish-card__action:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.wish-card__action--answer {
  border-color: color-mix(in srgb, #f2c94c 55%, var(--border));
  background: color-mix(in srgb, #f2c94c 12%, transparent);
  color: color-mix(in srgb, #f2c94c 82%, var(--text-primary));
}

.wish-card__action--danger:hover {
  border-color: var(--status-danger);
  background: var(--status-danger-bg);
  color: var(--status-danger);
}

.progress-bar {
  height: 3px;
  border-radius: 2px;
  background: var(--bg-hover);
  overflow: hidden;
}

.progress-bar__fill {
  height: 100%;
  width: 60%;
  border-radius: 2px;
  background: var(--accent);
  animation: progress-pulse 1.8s ease-in-out infinite;
}

@keyframes progress-pulse {
  0%, 100% { width: 30%; margin-left: 0; }
  50% { width: 60%; margin-left: 20%; }
}

</style>
