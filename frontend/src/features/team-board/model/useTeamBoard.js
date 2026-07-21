import { ref, computed } from 'vue'
import {
  archiveCard as archiveCardApi,
  createCard as createCardApi,
  deleteCard as deleteCardApi,
  getTeamBoard,
  moveCard as moveCardApi,
  retryExecution as retryExecutionApi,
} from '../api/teamBoardApi'
import { useWishCards } from '@entities/wish-card'

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

const TERMINAL_STATUSES = new Set([
  CARD_STATUS.COMPLETED,
  CARD_STATUS.FAILED,
  CARD_STATUS.CANCELLED,
  CARD_STATUS.ARCHIVED,
])
const BOARD_RELOAD_DEBOUNCE_MS = 400
const EVENT_CARD_FIELDS = Object.freeze([
  'status',
  'current_slot_id',
  'version',
  'updated_at',
  'session_id',
  'execution_id',
  'failure_reason',
])

const team = ref(null)
const slots = ref([])
const cards = ref([])
const loading = ref(false)
const error = ref(null)

let boardReloadTimer = null
let activeTeamId = null
let activeTeamGeneration = 0
let activeTeamInitialized = false
let requestSequence = 0
let latestRequestId = 0
let loadingRequestId = null

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

function normalizeCard(card) {
  return { ...card, status: String(card.status || '').toLowerCase() }
}

function isNewerOrEqual(incoming, existing) {
  if (!existing) return true
  const inVer = incoming.version ?? -1
  const exVer = existing.version ?? -1
  if (inVer !== exVer) return inVer > exVer
  if (incoming.updated_at && existing.updated_at) {
    return incoming.updated_at >= existing.updated_at
  }
  if (TERMINAL_STATUSES.has(incoming.status) && !TERMINAL_STATUSES.has(existing.status)) return true
  if (!TERMINAL_STATUSES.has(incoming.status) && TERMINAL_STATUSES.has(existing.status)) return false
  return true
}

function mergeCardLocally(cardData) {
  const normalized = normalizeCard(cardData)
  const idx = cards.value.findIndex(c => c.id === normalized.id)
  if (idx >= 0) {
    const existing = cards.value[idx]
    if (isNewerOrEqual(normalized, existing)) {
      const patch = {}
      for (const f of EVENT_CARD_FIELDS) {
        if (normalized[f] !== undefined) patch[f] = normalized[f]
      }
      cards.value = cards.value.map((c, i) => i === idx ? { ...c, ...patch } : c)
    }
  } else {
    cards.value = [...cards.value, normalized]
  }
}

function scheduleBoardReload(teamId, loadFn) {
  if (boardReloadTimer !== null) clearTimeout(boardReloadTimer)
  boardReloadTimer = setTimeout(async () => {
    boardReloadTimer = null
    if (team.value?.id === teamId) {
      await loadFn(teamId, { silent: true })
    }
  }, BOARD_RELOAD_DEBOUNCE_MS)
}

export function useTeamBoard() {
  const { setTeamCards, removeTeamCard, mergeTeamCard } = useWishCards()

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
      setTeamCards(teamId, cards.value)
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
      removeTeamCard(team.value.id, cardId)
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
    if (!event?.team_id) return
    if (event.card) {
      mergeTeamCard(event.team_id, event.card)
    }
    if (event.team_id !== team.value?.id) return
    if (event.card) {
      mergeCardLocally(event.card)
    }
    scheduleBoardReload(event.team_id, loadBoard)
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
