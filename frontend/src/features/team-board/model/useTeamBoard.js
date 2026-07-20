import { ref, computed } from 'vue'
import {
  archiveCard as archiveCardApi,
  createCard as createCardApi,
  deleteCard as deleteCardApi,
  getTeamBoard,
  moveCard as moveCardApi,
  retryExecution as retryExecutionApi,
} from '../api/teamBoardApi'

const CARD_STATUS = Object.freeze({
  BACKLOG: 'backlog',
  PREPARING: 'preparing',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
  ARCHIVED: 'archived',
})

const DRAGGABLE_STATUSES = Object.freeze([
  CARD_STATUS.BACKLOG,
  CARD_STATUS.COMPLETED,
  CARD_STATUS.FAILED,
  CARD_STATUS.CANCELLED,
])

const team = ref(null)
const slots = ref([])
const cards = ref([])
const loading = ref(false)
const error = ref(null)

const cardsBySlot = computed(() => {
  const map = new Map()
  map.set(null, [])
  for (const slot of slots.value) {
    map.set(slot.id, [])
  }
  for (const card of cards.value) {
    if (card.status === CARD_STATUS.ARCHIVED) continue
    const key = card.current_slot_id || null
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(card)
  }
  return map
})

const backlogCards = computed(() => cardsBySlot.value.get(null) || [])
const archivedCards = computed(() => cards.value.filter(card => card.status === CARD_STATUS.ARCHIVED))

function isCardDraggable(card) {
  return DRAGGABLE_STATUSES.includes(card.status)
}

function updateCardLocally(cardId, patch) {
  const idx = cards.value.findIndex(c => c.id === cardId)
  if (idx >= 0) {
    cards.value = cards.value.map((c, i) => i === idx ? { ...c, ...patch } : c)
  }
}

export function useTeamBoard() {
  async function loadBoard(teamId, { silent = false } = {}) {
    if (!silent) loading.value = true
    error.value = null
    try {
      const data = await getTeamBoard(teamId)
      team.value = { id: data.team_id, name: data.name }
      slots.value = data.slots || []
      cards.value = (data.cards || []).map(card => ({
        ...card,
        status: String(card.status || '').toLowerCase(),
      }))
    } catch (e) {
      error.value = e.message || 'Failed to load board'
    } finally {
      if (!silent) loading.value = false
    }
  }

  async function moveCardToSlot(cardId, targetSlotId, idempotencyKey) {
    const card = cards.value.find(c => c.id === cardId)
    if (!card || !team.value) return

    const previousSlotId = card.current_slot_id
    const previousVersion = card.version

    // Optimistic update
    updateCardLocally(cardId, {
      current_slot_id: targetSlotId,
      version: card.version + 1,
    })

    try {
      await moveCardApi(team.value.id, cardId, {
        target_slot_id: targetSlotId,
        card_version: previousVersion,
        idempotency_key: idempotencyKey,
      })
      // The execution can finish before this request resolves. Re-read the
      // board so a stale "running" response never overwrites "completed".
      await loadBoard(team.value.id)
    } catch (e) {
      // Rollback
      updateCardLocally(cardId, {
        current_slot_id: previousSlotId,
        version: previousVersion,
      })
      error.value = e.message || 'Move failed'
    }
  }

  async function addCard(title, description) {
    if (!team.value) return
    error.value = null
    try {
      const newCard = await createCardApi(team.value.id, { title, description })
      cards.value = [...cards.value, newCard]
      return newCard
    } catch (e) {
      error.value = e.message || 'Failed to create card'
      return null
    }
  }

  async function archiveCard(cardId) {
    const card = cards.value.find(item => item.id === cardId)
    if (!card || !team.value) return false
    error.value = null
    try {
      await archiveCardApi(team.value.id, cardId, { card_version: card.version })
      await loadBoard(team.value.id, { silent: true })
      return true
    } catch (e) {
      error.value = e.message || 'Archive failed'
      return false
    }
  }

  async function deleteArchivedCard(cardId) {
    if (!team.value) return false
    error.value = null
    try {
      await deleteCardApi(team.value.id, cardId)
      cards.value = cards.value.filter(card => card.id !== cardId)
      return true
    } catch (e) {
      error.value = e.message || 'Delete failed'
      return false
    }
  }

  async function retryCard(executionId) {
    if (!executionId || !team.value) return
    error.value = null
    try {
      await retryExecutionApi(executionId)
      await loadBoard(team.value.id)
    } catch (e) {
      error.value = e.message || 'Retry failed'
    }
  }

  async function handleBoardEvent(event) {
    if (!event?.team_id || event.team_id !== team.value?.id) return
    await loadBoard(event.team_id, { silent: true })
  }

  async function refreshBoardAfterReconnect() {
    if (!team.value?.id) return
    await loadBoard(team.value.id, { silent: true })
  }

  return {
    CARD_STATUS,
    team,
    slots,
    cards,
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
    handleBoardEvent,
    refreshBoardAfterReconnect,
  }
}
