import { ref, nextTick } from 'vue'
import { useSession } from '@entities/session'
import { useProject } from '@entities/project'
import {
  listSessions,
  createSession,
  getSession,
  deleteSession,
  batchDeleteSessions,
  renameSession,
  importClaudeSession,
} from '@entities/session'
import {
  listProjects,
  createProject,
  deleteProject as apiDeleteProject,
  reorderProjects,
  ensureProjectsByDirs,
} from '@entities/project'
import { listClaudeSessions, deleteClaudeSession } from '../api/claudeSessionApi'
import { LAST_SESSION_ID_KEY } from '@shared/lib/constants'

export function useSessionList() {
  const {
    sessions,
    currentSessionId,
    setSessions,
    setCurrentSessionId,
    addSession,
    removeSession,
    updateSessionInList,
    removeState,
  } = useSession()

  const {
    projects,
    currentProjectId,
    setProjects,
    setCurrentProjectId,
    addProject,
    removeProject,
    updateProjectInList,
  } = useProject()

  const loading = ref(false)

  async function loadSessions() {
    loading.value = true
    try {
      // Load projects, VP sessions, and Claude Code sessions in parallel
      const [projectsData, vpData, claudeData] = await Promise.all([
        listProjects(),
        listSessions(),
        listClaudeSessions().catch(() => ({ sessions: [] })),
      ])

      // Build a set of sdk_session_ids already tracked by VP to de-duplicate CC sessions
      const trackedSdkIds = new Set(
        vpData.sessions.map(s => s.sdk_session_id).filter(Boolean)
      )

      // Filter CC sessions not yet imported into VP
      const newCcSessions = claudeData.sessions.filter(cs => !trackedSdkIds.has(cs.session_id))

      // Collect unique non-empty cwds from CC sessions
      const cwds = [...new Set(newCcSessions.map(cs => cs.cwd).filter(Boolean))]

      // Ensure projects exist for all cwds, get cwd→project_id mappings
      let dirMappings = {}
      if (cwds.length > 0) {
        const result = await ensureProjectsByDirs(cwds)
        dirMappings = result.mappings || {}
      }

      // Reload projects since new ones may have been auto-created
      const freshProjects = cwds.length > 0
        ? await listProjects()
        : projectsData
      setProjects(freshProjects.projects || [])

      // Convert Claude Code sessions to a compatible format with project_id from mappings
      const claudeSessions = newCcSessions.map(cs => ({
        session_id: cs.session_id,
        project_id: (cs.cwd && dirMappings[cs.cwd]) || '',
        model: '',
        status: 'idle',
        message_count: 0,
        usage: { input_tokens: 0, output_tokens: 0 },
        project_dir: cs.cwd || '',
        name: cs.custom_title || cs.first_prompt || cs.summary || '',
        updated_time: cs.last_modified ? new Date(cs.last_modified * 1000).toISOString() : null,
        source: 'claude-code',
        git_branch: cs.git_branch || '',
      }))

      // Tag VP sessions as local
      const vpSessions = vpData.sessions.map(s => ({ ...s, source: 'velpos' }))

      // Merge: VP sessions first, then Claude Code sessions
      setSessions([...vpSessions, ...claudeSessions])
    } finally {
      loading.value = false
    }
  }

  async function handleCreate({ name, githubUrl }) {
    // Create a new project, which creates the project directory
    const project = await createProject(name, githubUrl || '')
    addProject(project)

    // Create a session in the new project
    const session = await createSession({
      projectId: project.id,
      projectDir: project.dir_path || '',
    })
    addSession({ ...session, source: 'velpos' })
    setCurrentProjectId(project.id)
    switchSession(session.session_id)
  }

  async function handleDelete(sessionId) {
    const session = sessions.value.find(s => s.session_id === sessionId)
    if (!session) return

    if (session.source === 'claude-code') {
      await deleteClaudeSession(sessionId, session.project_dir || null)
    } else {
      await deleteSession(sessionId)
    }
    removeSession(sessionId)

    if (currentSessionId.value === sessionId) {
      const first = sessions.value.find(s => s.source !== 'claude-code')
      if (first) {
        switchSession(first.session_id)
      } else {
        setCurrentSessionId(null)
        removeState(sessionId)
        localStorage.removeItem(LAST_SESSION_ID_KEY)
      }
    }
  }

  async function handleBatchDelete(sessionIds) {
    // Split into VP sessions (batch API) and Claude Code sessions (individual delete)
    const vpIds = []
    const ccIds = []
    for (const id of sessionIds) {
      const s = sessions.value.find(x => x.session_id === id)
      if (!s) continue
      if (s.source === 'claude-code') {
        ccIds.push(id)
      } else {
        vpIds.push(id)
      }
    }

    // Delete VP sessions via batch API
    if (vpIds.length > 0) {
      await batchDeleteSessions(vpIds)
    }

    // Delete Claude Code sessions individually
    for (const id of ccIds) {
      const s = sessions.value.find(x => x.session_id === id)
      await deleteClaudeSession(id, s?.project_dir || null)
    }

    // Remove from local list
    for (const id of sessionIds) {
      removeSession(id)
    }

    // Handle current session being deleted
    if (sessionIds.includes(currentSessionId.value)) {
      const remaining = sessions.value.find(s => s.source !== 'claude-code')
      if (remaining) {
        switchSession(remaining.session_id)
      } else {
        setCurrentSessionId(null)
        removeState(currentSessionId.value)
        localStorage.removeItem(LAST_SESSION_ID_KEY)
      }
    }
  }

  async function handleRename({ sessionId, name }) {
    const data = await renameSession(sessionId, name)
    updateSessionInList(sessionId, data)
  }

  async function handleCreateInProject(projectId) {
    const project = projects.value.find(p => p.id === projectId)
    const session = await createSession({
      projectId,
      projectDir: project?.dir_path || '',
    })
    addSession({ ...session, source: 'velpos' })
    switchSession(session.session_id)
  }

  async function handleDeleteProject(projectId) {
    await apiDeleteProject(projectId)
    removeProject(projectId)

    // Remove sessions belonging to this project from session list
    const projectSessions = sessions.value.filter(s => s.project_id === projectId)
    for (const s of projectSessions) {
      removeSession(s.session_id)
    }

    if (projectSessions.some(s => s.session_id === currentSessionId.value)) {
      const remaining = sessions.value.find(s => s.source !== 'claude-code')
      if (remaining) {
        switchSession(remaining.session_id)
      } else {
        setCurrentSessionId(null)
        for (const s of projectSessions) {
          removeState(s.session_id)
        }
        localStorage.removeItem(LAST_SESSION_ID_KEY)
      }
    }
  }

  async function handleReorderProjects(orderedIds) {
    await reorderProjects(orderedIds)
    // Reorder local projects to match
    const ordered = []
    for (const id of orderedIds) {
      const p = projects.value.find(pr => pr.id === id)
      if (p) ordered.push(p)
    }
    // Append any projects not in orderedIds (shouldn't happen normally)
    for (const p of projects.value) {
      if (!orderedIds.includes(p.id)) ordered.push(p)
    }
    setProjects(ordered)
  }

  async function handleNavigateToInitSession(sessionId) {
    // Ensure the session is in the list, then navigate
    let session = sessions.value.find(s => s.session_id === sessionId)
    if (!session) {
      try {
        const data = await getSession(sessionId)
        addSession({ ...data, source: 'velpos' })
      } catch {}
    }
    switchSession(sessionId)
  }

  const importing = ref(false)

  function switchSession(sessionId) {
    const session = sessions.value.find(s => s.session_id === sessionId)
    if (session && session.source === 'claude-code') {
      handleImportClaudeSession(session)
      return
    }
    setCurrentSessionId(sessionId)
    localStorage.setItem(LAST_SESSION_ID_KEY, sessionId)

    // Auto-select the project that owns this session
    if (session && session.project_id) {
      setCurrentProjectId(session.project_id)
    }
  }

  async function handleImportClaudeSession(ccSession) {
    if (importing.value) return
    importing.value = true
    try {
      const vpSession = await importClaudeSession(
        ccSession.session_id,
        ccSession.project_dir,
        ccSession.name || '',
      )
      // Remove the CC session from list and add the new VP session
      removeSession(ccSession.session_id)
      addSession({ ...vpSession, source: 'velpos' })
      // Switch to the new VP session and select its project
      setCurrentSessionId(vpSession.session_id)
      localStorage.setItem(LAST_SESSION_ID_KEY, vpSession.session_id)
      if (vpSession.project_id) {
        setCurrentProjectId(vpSession.project_id)
      }

      // Trigger event to scroll to the new session position
      nextTick(() => {
        window.dispatchEvent(new CustomEvent('vp-session-imported', {
          detail: { sessionId: vpSession.session_id }
        }))
      })
    } finally {
      importing.value = false
    }
  }

  function restoreLastSession() {
    const lastId = localStorage.getItem(LAST_SESSION_ID_KEY)
    if (lastId && sessions.value.some(s => s.session_id === lastId)) {
      switchSession(lastId)
    }
  }

  return {
    loading,
    importing,
    loadSessions,
    handleCreate,
    handleDelete,
    handleBatchDelete,
    handleRename,
    handleCreateInProject,
    handleDeleteProject,
    handleReorderProjects,
    handleNavigateToInitSession,
    switchSession,
    restoreLastSession,
  }
}
