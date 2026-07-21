import { reactive, computed } from 'vue'
import { fetchTeamCards } from '../api/wishCardApi'

const ARCHIVED = 'archived'

const state = reactive({
  cardsByTeam: new Map(),
  loadingTeams: new Set(),
  errorByTeam: new Map(),
})

function activeCardsForTeam(teamId) {
  const cards = state.cardsByTeam.get(teamId) || []
  return cards.filter(c => c.status !== ARCHIVED)
}

function setTeamCards(teamId, cards) {
  const normalized = cards.map(c => ({ ...c, status: String(c.status || '').toLowerCase() }))
  state.cardsByTeam.set(teamId, normalized)
}

function removeTeamCard(teamId, cardId) {
  const cards = state.cardsByTeam.get(teamId)
  if (!cards) return
  state.cardsByTeam.set(teamId, cards.filter(c => c.id !== cardId))
}

function mergeTeamCard(teamId, cardData) {
  const normalized = { ...cardData, status: String(cardData.status || '').toLowerCase() }
  const cards = state.cardsByTeam.get(teamId)
  if (!cards) {
    state.cardsByTeam.set(teamId, [normalized])
    return
  }
  const idx = cards.findIndex(c => c.id === normalized.id)
  if (idx >= 0) {
    const updated = [...cards]
    updated[idx] = { ...updated[idx], ...normalized }
    state.cardsByTeam.set(teamId, updated)
  } else {
    state.cardsByTeam.set(teamId, [...cards, normalized])
  }
}

async function loadTeamCards(teamId) {
  if (state.loadingTeams.has(teamId)) return
  state.loadingTeams.add(teamId)
  state.errorByTeam.delete(teamId)
  try {
    const data = await fetchTeamCards(teamId)
    setTeamCards(teamId, data.cards || [])
  } catch (e) {
    state.errorByTeam.set(teamId, e.message || 'Failed to load cards')
  } finally {
    state.loadingTeams.delete(teamId)
  }
}

function isTeamLoaded(teamId) {
  return state.cardsByTeam.has(teamId)
}

export function useWishCards() {
  return {
    state,
    activeCardsForTeam,
    setTeamCards,
    removeTeamCard,
    mergeTeamCard,
    loadTeamCards,
    isTeamLoaded,
  }
}
