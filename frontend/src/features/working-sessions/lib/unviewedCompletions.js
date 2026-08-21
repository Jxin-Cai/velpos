export const UNVIEWED_COMPLETIONS_KEY = 'pf_unviewed_completions'

export function applyCompletionViewState(unviewedIds, sessionId, { wasWorking, isCurrent }) {
  if (!wasWorking || !sessionId) return unviewedIds
  if (isCurrent) {
    if (!unviewedIds.has(sessionId)) return unviewedIds
    const next = new Set(unviewedIds)
    next.delete(sessionId)
    return next
  }
  if (unviewedIds.has(sessionId)) return unviewedIds
  const next = new Set(unviewedIds)
  next.add(sessionId)
  return next
}

export function markSessionViewed(unviewedIds, sessionId) {
  if (!sessionId || !unviewedIds.has(sessionId)) return unviewedIds
  const next = new Set(unviewedIds)
  next.delete(sessionId)
  return next
}

export function pruneUnviewedIds(unviewedIds, validIds) {
  let changed = false
  const next = new Set()
  for (const id of unviewedIds) {
    if (validIds.has(id)) next.add(id)
    else changed = true
  }
  return changed ? next : unviewedIds
}
