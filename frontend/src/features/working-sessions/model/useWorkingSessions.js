import { ref, computed } from 'vue'
import { loadPinnedIds, savePinnedIds } from '@shared/lib/pinning'
import {
  UNVIEWED_COMPLETIONS_KEY,
  applyCompletionViewState,
  markSessionViewed,
  pruneUnviewedIds,
} from '../lib/unviewedCompletions'

// Module-level singleton state
const workingSessions = ref(new Map())
const unviewedIds = ref(loadPinnedIds(UNVIEWED_COMPLETIONS_KEY))

function persistUnviewed() {
  try {
    savePinnedIds(UNVIEWED_COMPLETIONS_KEY, unviewedIds.value)
  } catch (error) {
    console.warn('Failed to save unviewed completions:', error)
  }
}

export function useWorkingSessions() {
  const workingCount = computed(() => workingSessions.value.size)

  const workingList = computed(() =>
    Array.from(workingSessions.value.entries()).map(([sessionId, info]) => ({
      sessionId,
      ...info,
    }))
  )

  function markWorking(sessionId, { sessionName = '', projectName = '' } = {}) {
    const existing = workingSessions.value.get(sessionId)
    if (existing) return // already tracked
    const updated = new Map(workingSessions.value)
    updated.set(sessionId, { sessionName, projectName, startTime: Date.now() })
    workingSessions.value = updated
  }

  function markDone(sessionId, { isCurrent = false } = {}) {
    const wasWorking = workingSessions.value.has(sessionId)
    if (wasWorking) {
      const updated = new Map(workingSessions.value)
      updated.delete(sessionId)
      workingSessions.value = updated
      unviewedIds.value = applyCompletionViewState(unviewedIds.value, sessionId, {
        wasWorking: true,
        isCurrent,
      })
      persistUnviewed()
    }
    return wasWorking
  }

  function markViewed(sessionId) {
    const next = markSessionViewed(unviewedIds.value, sessionId)
    if (next === unviewedIds.value) return
    unviewedIds.value = next
    persistUnviewed()
  }

  function isUnviewed(sessionId) {
    return unviewedIds.value.has(sessionId)
  }

  function syncWorkingSessions(sessions = [], projects = [], currentSessionId = null) {
    const projectNames = new Map(projects.map(project => [project.id, project.name || '']))
    const previousWorking = new Set(workingSessions.value.keys())
    const updated = new Map()

    for (const session of sessions) {
      if (session.status !== 'running') continue
      const existing = workingSessions.value.get(session.session_id)
      const updatedTime = Date.parse(session.updated_time || '')
      updated.set(session.session_id, {
        sessionName: session.name || existing?.sessionName || '',
        projectName: projectNames.get(session.project_id) || existing?.projectName || '',
        startTime: existing?.startTime || (Number.isFinite(updatedTime) ? updatedTime : Date.now()),
      })
    }

    workingSessions.value = updated

    let nextUnviewed = unviewedIds.value
    for (const sessionId of previousWorking) {
      if (updated.has(sessionId)) continue
      nextUnviewed = applyCompletionViewState(nextUnviewed, sessionId, {
        wasWorking: true,
        isCurrent: sessionId === currentSessionId,
      })
    }
    nextUnviewed = pruneUnviewedIds(nextUnviewed, new Set(sessions.map(session => session.session_id)))
    if (nextUnviewed !== unviewedIds.value) {
      unviewedIds.value = nextUnviewed
      persistUnviewed()
    }
  }

  return {
    workingCount,
    workingList,
    unviewedIds,
    markWorking,
    markDone,
    markViewed,
    isUnviewed,
    syncWorkingSessions,
  }
}
