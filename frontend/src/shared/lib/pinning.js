export const PINNED_PROJECTS_KEY = 'pf_pinned_projects'
export const PINNED_SESSIONS_KEY = 'pf_pinned_sessions'

export function loadPinnedIds(key) {
  try {
    const stored = localStorage.getItem(key)
    return stored ? new Set(JSON.parse(stored)) : new Set()
  } catch {
    return new Set()
  }
}

export function savePinnedIds(key, ids) {
  localStorage.setItem(key, JSON.stringify([...ids]))
}

export function togglePinnedId(ids, id) {
  const next = new Set(ids)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  return next
}

function isUnloadedClaudeCodeSession(session) {
  return session.source === 'claude-code'
}

function getSessionActivityTime(session) {
  const timestamp = session.updated_time || session.created_at || session.created_time || session.last_modified
  if (!timestamp) return 0
  const time = new Date(timestamp).getTime()
  return Number.isNaN(time) ? 0 : time
}

export function compareSessions(a, b, pinnedSessionIds = new Set()) {
  const aPinned = pinnedSessionIds.has(a.session_id) ? 1 : 0
  const bPinned = pinnedSessionIds.has(b.session_id) ? 1 : 0
  if (aPinned !== bPinned) return bPinned - aPinned

  const aRunning = a.status === 'running' ? 1 : 0
  const bRunning = b.status === 'running' ? 1 : 0
  if (aRunning !== bRunning) return bRunning - aRunning

  const aUnloadedClaudeCode = isUnloadedClaudeCodeSession(a) ? 1 : 0
  const bUnloadedClaudeCode = isUnloadedClaudeCodeSession(b) ? 1 : 0
  if (aUnloadedClaudeCode !== bUnloadedClaudeCode) return aUnloadedClaudeCode - bUnloadedClaudeCode

  const timeA = getSessionActivityTime(a)
  const timeB = getSessionActivityTime(b)
  return timeB - timeA
}

export function splitPinnedProjects(projects, pinnedProjectIds = new Set()) {
  const pinnedProjects = []
  const unpinnedProjects = []
  for (const project of projects) {
    if (pinnedProjectIds.has(project.id)) {
      pinnedProjects.push(project)
    } else {
      unpinnedProjects.push(project)
    }
  }
  return { pinnedProjects, unpinnedProjects }
}
