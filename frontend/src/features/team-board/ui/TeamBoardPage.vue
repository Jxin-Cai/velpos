<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useTeamBoard } from '../model/useTeamBoard'
import WishCardItem from './WishCardItem.vue'
import CreateCardDialog from './CreateCardDialog.vue'

const props = defineProps({
  teamId: { type: String, required: true },
  projectId: { type: String, required: true },
})

const emit = defineEmits(['navigate-session'])

const {
  team,
  slots,
  loading,
  error,
  cardsBySlot,
  backlogCards,
  archivedCards,
  isCardDraggable,
  loadBoard,
  moveCardToSlot,
  addCard,
  archiveCard,
  deleteArchivedCard,
  retryCard,
} = useTeamBoard()

const createDialogVisible = ref(false)
const ariaAnnouncement = ref('')

// Drag state
const dragState = ref(null)
const dropTargetSlotId = ref(null)

function announceToScreenReader(message) {
  ariaAnnouncement.value = ''
  nextTick(() => { ariaAnnouncement.value = message })
}

function generateIdempotencyKey() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function handleCardDragStart({ card, event, keyboard }) {
  if (!isCardDraggable(card)) return
  if (keyboard) {
    // Keyboard drag mode
    dragState.value = { card, keyboard: true }
    announceToScreenReader(`Picked up card: ${card.title}. Use arrow keys to move, Enter or Space to drop, Escape to cancel.`)
    return
  }
  dragState.value = { card, keyboard: false }
  event.dataTransfer.effectAllowed = 'move'
}

function canDropOn(card, targetId) {
  if (!card || !targetId) return false
  if (targetId === 'archive') {
    return ['completed', 'failed', 'cancelled'].includes(card.status)
  }
  return targetId !== 'backlog' && card.current_slot_id !== targetId
}

function handleColumnDragOver(targetId, event) {
  const card = dragState.value?.card
  if (!canDropOn(card, targetId)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  dropTargetSlotId.value = targetId
}

async function dropCard(card, targetId) {
  if (!canDropOn(card, targetId)) return
  if (targetId === 'archive') {
    await archiveCard(card.id)
    announceToScreenReader(`Archived card "${card.title}".`)
  } else {
    await moveCardToSlot(card.id, targetId, generateIdempotencyKey())
    announceToScreenReader(`Moved card "${card.title}" to new column.`)
  }
}

async function handleColumnDrop(targetId, event) {
  event.preventDefault()
  const card = dragState.value?.card
  await dropCard(card, targetId)
  dragState.value = null
  dropTargetSlotId.value = null
}

function handleDragEnd() {
  dragState.value = null
  dropTargetSlotId.value = null
}

function handleBoardKeyDown(e) {
  if (!dragState.value || !dragState.value.keyboard) return
  const allSlotIds = [null, ...slots.value.map(s => s.id), 'archive']
  const currentSlotId = dragState.value.card.current_slot_id || null
  const currentIdx = allSlotIds.indexOf(currentSlotId)

  if (e.key === 'ArrowRight') {
    e.preventDefault()
    const nextIdx = Math.min(currentIdx + 1, allSlotIds.length - 1)
    dropTargetSlotId.value = allSlotIds[nextIdx] === null ? 'backlog' : allSlotIds[nextIdx]
    const slotName = allSlotIds[nextIdx] === 'archive'
      ? 'Archive'
      : nextIdx === 0 ? 'Backlog' : slots.value[nextIdx - 1]?.display_name
    announceToScreenReader(`Over column: ${slotName}`)
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault()
    const prevIdx = Math.max(currentIdx - 1, 0)
    dropTargetSlotId.value = allSlotIds[prevIdx] === null ? 'backlog' : allSlotIds[prevIdx]
    const slotName = allSlotIds[prevIdx] === 'archive'
      ? 'Archive'
      : prevIdx === 0 ? 'Backlog' : slots.value[prevIdx - 1]?.display_name
    announceToScreenReader(`Over column: ${slotName}`)
  } else if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    const card = dragState.value.card
    const targetSlotId = dropTargetSlotId.value
    if (canDropOn(card, targetSlotId)) {
      dropCard(card, targetSlotId)
      announceToScreenReader(`Dropped card "${card.title}".`)
    } else {
      announceToScreenReader(`Card "${card.title}" returned to original position.`)
    }
    dragState.value = null
    dropTargetSlotId.value = null
  } else if (e.key === 'Escape') {
    e.preventDefault()
    announceToScreenReader(`Cancelled drag for card "${dragState.value.card.title}".`)
    dragState.value = null
    dropTargetSlotId.value = null
  }
}

function handleNavigateSession(sessionId) {
  emit('navigate-session', sessionId)
}

function handleRetry(executionId) {
  retryCard(executionId)
}

async function handleCreateCard({ title, description }) {
  const result = await addCard(title, description)
  if (result) {
    createDialogVisible.value = false
  }
}

function isDropTarget(slotId) {
  return dropTargetSlotId.value === slotId
}

onMounted(() => {
  loadBoard(props.teamId)
  document.addEventListener('keydown', handleBoardKeyDown)
})

watch(() => props.teamId, (teamId, previousTeamId) => {
  if (teamId && teamId !== previousTeamId) loadBoard(teamId)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleBoardKeyDown)
})
</script>

<template>
  <div class="team-board">
    <!-- Aria live region for announcements -->
    <div class="sr-only" aria-live="assertive" aria-atomic="true">{{ ariaAnnouncement }}</div>

    <header class="board-header">
      <div class="board-header__left">
        <h1 class="board-title">{{ team?.name || 'Team Board' }}</h1>
      </div>
      <button class="btn-add-card" @click="createDialogVisible = true" aria-label="Create wish card">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
          <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        New Card
      </button>
    </header>

    <div v-if="loading" class="board-loading">
      <div class="board-loading__text">Loading board...</div>
    </div>

    <div v-else-if="error" class="board-error">
      <span class="board-error__text">{{ error }}</span>
      <button class="btn-retry" @click="loadBoard(props.teamId)">Retry</button>
    </div>

    <div v-else class="board-columns" role="list" aria-label="Board columns">
      <!-- Backlog column -->
      <section
        class="board-column"
        :class="{ 'board-column--drop-target': isDropTarget('backlog') }"
        data-slot-id="backlog"
      role="listitem"
      aria-label="Backlog"
      @dragover="handleColumnDragOver('backlog', $event)"
      @drop="handleColumnDrop('backlog', $event)"
      >
        <div class="column-header">
          <span class="column-header__name">Backlog</span>
          <span class="column-header__count">{{ backlogCards.length }}</span>
        </div>
        <div class="column-cards" role="list">
          <WishCardItem
            v-for="card in backlogCards"
            :key="card.id"
            :card="card"
            :project-id="projectId"
            :draggable="isCardDraggable(card)"
            :keyboard-dragging="Boolean(dragState?.keyboard && dragState.card.id === card.id)"
            @dragstart="handleCardDragStart"
            @dragend="handleDragEnd"
            @navigate="handleNavigateSession"
            @retry="handleRetry"
            @delete="deleteArchivedCard"
          />
          <div v-if="backlogCards.length === 0" class="column-empty">No cards</div>
        </div>
      </section>

      <!-- Agent slot columns -->
      <section
        v-for="slot in slots"
        :key="slot.id"
        class="board-column"
        :class="{ 'board-column--drop-target': isDropTarget(slot.id) }"
        :data-slot-id="slot.id"
        role="listitem"
        :aria-label="slot.display_name"
        @dragover="handleColumnDragOver(slot.id, $event)"
        @drop="handleColumnDrop(slot.id, $event)"
      >
        <div class="column-header">
          <div class="column-header__avatar">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <circle cx="12" cy="8" r="4" /><path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
            </svg>
          </div>
          <span class="column-header__name">{{ slot.display_name }}</span>
          <span class="column-header__count">{{ (cardsBySlot.get(slot.id) || []).length }}</span>
        </div>
        <div class="column-cards" role="list">
          <WishCardItem
            v-for="card in (cardsBySlot.get(slot.id) || [])"
            :key="card.id"
            :card="card"
            :project-id="projectId"
            :draggable="isCardDraggable(card)"
            :keyboard-dragging="Boolean(dragState?.keyboard && dragState.card.id === card.id)"
            @dragstart="handleCardDragStart"
            @dragend="handleDragEnd"
            @navigate="handleNavigateSession"
            @retry="handleRetry"
            @delete="deleteArchivedCard"
          />
          <div v-if="(cardsBySlot.get(slot.id) || []).length === 0" class="column-empty">No cards</div>
        </div>
      </section>

      <!-- Archive is a terminal board column, never an execution target. -->
      <section
        class="board-column board-column--archive"
        :class="{ 'board-column--drop-target': isDropTarget('archive') }"
        data-slot-id="archive"
        role="listitem"
        aria-label="Archive"
        @dragover="handleColumnDragOver('archive', $event)"
        @drop="handleColumnDrop('archive', $event)"
      >
        <div class="column-header">
          <div class="column-header__avatar column-header__avatar--archive">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M3 6h18" /><path d="M5 6v14h14V6" /><path d="M9 10h6" /><path d="M4 3h16v3H4z" />
            </svg>
          </div>
          <span class="column-header__name">Archive</span>
          <span class="column-header__count">{{ archivedCards.length }}</span>
        </div>
        <div class="column-cards" role="list">
          <WishCardItem
            v-for="card in archivedCards"
            :key="card.id"
            :card="card"
            :project-id="projectId"
            :draggable="false"
            @navigate="handleNavigateSession"
            @delete="deleteArchivedCard"
          />
          <div v-if="archivedCards.length === 0" class="column-empty column-empty--archive">
            Drop finished cards here
          </div>
        </div>
      </section>
    </div>

    <CreateCardDialog
      :visible="createDialogVisible"
      @confirm="handleCreateCard"
      @cancel="createDialogVisible = false"
    />
  </div>
</template>

<style scoped>
.team-board {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.board-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.board-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.btn-add-card {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast), color var(--transition-fast);
}

.btn-add-card:hover {
  background: var(--accent-dim);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  color: var(--accent);
}

.board-loading,
.board-error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex: 1;
  color: var(--text-muted);
  font-size: 13px;
}

.board-error__text {
  color: var(--red);
}

.btn-retry {
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.btn-retry:hover {
  background: var(--bg-hover);
}

.board-columns {
  display: flex;
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 16px 12px;
  gap: 12px;
}

.board-column {
  flex: 0 0 240px;
  min-width: 240px;
  max-height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  transition: border-color var(--transition-fast), background var(--transition-fast);
}

.board-column--drop-target {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 5%, var(--bg-tertiary));
}

.board-column--archive {
  border-style: dashed;
  background: color-mix(in srgb, var(--bg-tertiary) 78%, var(--bg-secondary));
}

.board-column--archive.board-column--drop-target {
  border-style: solid;
}

.column-header__avatar--archive {
  border-radius: var(--radius-sm);
}

.column-empty--archive {
  min-height: 72px;
  padding: 10px;
  line-height: 1.45;
  text-align: center;
}

.column-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.column-header__avatar {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--bg-hover);
  color: var(--text-muted);
  flex-shrink: 0;
}

.column-header__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.column-header__count {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  background: var(--bg-hover);
  padding: 1px 6px;
  border-radius: 999px;
  flex-shrink: 0;
}

.column-cards {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.column-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  color: var(--text-muted);
  font-size: 12px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
}

@media (max-width: 768px) {
  .board-columns {
    padding: 12px 8px;
  }

  .board-column {
    flex: 0 0 200px;
    min-width: 200px;
  }
}
</style>
