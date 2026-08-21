const RUNNING_STATUSES = new Set(['running', 'reconnecting', 'compacting'])

export function summarizeGroupSessionActivity(sessions = [], unviewedIds = new Set()) {
  let hasRunning = false
  let hasUnviewedCompleted = false

  for (const session of sessions) {
    if (!session || session.source === 'claude-code') continue

    if (RUNNING_STATUSES.has(session.status)) {
      hasRunning = true
      continue
    }

    if ((session.status === 'idle' || !session.status) && unviewedIds.has(session.session_id)) {
      hasUnviewedCompleted = true
    }
  }

  return { hasRunning, hasUnviewedCompleted }
}

export function groupActivityLabel(activity) {
  const parts = []
  if (activity?.hasRunning) parts.push('running')
  if (activity?.hasUnviewedCompleted) parts.push('unviewed')
  return parts.join(', ')
}
