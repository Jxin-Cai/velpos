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

export function compareSessions(a, b, pinnedSessionIds = new Set()) {
  const aPinned = pinnedSessionIds.has(a.session_id) ? 1 : 0
  const bPinned = pinnedSessionIds.has(b.session_id) ? 1 : 0
  if (aPinned !== bPinned) return bPinned - aPinned

  const aRunning = a.status === 'running' ? 1 : 0
  const bRunning = b.status === 'running' ? 1 : 0
  if (aRunning !== bRunning) return bRunning - aRunning

  const timeA = a.updated_time ? new Date(a.updated_time).getTime() : 0
  const timeB = b.updated_time ? new Date(b.updated_time).getTime() : 0
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
