<script setup>
import { ref, reactive, computed, watch, provide, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { applyVbReviews, fetchSessionTimelineEvents, useSession } from '@entities/session'
import { useProject } from '@entities/project'
import { useImBinding } from '@features/im-binding'
import { createWsConnection, createGlobalEventConnection } from '@shared/api/wsClient'
import { listSchedules } from '@features/scheduler/api/schedulerApi'
import { TeamBoardPage, useTeamBoard } from '@features/team-board'
import { ChatPanelPage } from '@pages/chat-panel'
import { SessionSidebar, useSessionList } from '@features/session-list'
import { NOTIFICATION_TYPE, NotificationBell, useNotifications } from '@features/notification-center'
import { WorkingSessionsButton, useWorkingSessions } from '@features/working-sessions'
import { fetchSessionRunSteps } from '@features/task-progress'
import { fetchTraceRuns } from '@features/trace-viewer'
import { SettingsButton, SettingsDialog } from '@features/settings-manager'
import { GitManagerButton, GitManagerDialog } from '@features/git-manager'
import { TerminalButton, TerminalDrawer } from '@features/terminal'
import { WorkspaceButton, WorkspacePanel } from '@features/workspace'
import { SchedulerDialog } from '@features/scheduler'
import ThemeSwitcher from '@shared/ui/ThemeSwitcher.vue'
import GlobalShortcutInterceptor from '@shared/ui/GlobalShortcutInterceptor.vue'
import AppLogo from '@shared/ui/AppLogo.vue'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys'
import { useHotkeyHint } from '@shared/lib/useHotkeyHint'

const {
  session,
  sessions,
  currentSessionId,
  setCurrentSessionId,
  updateSessionInList,
  // Targeted APIs (write to specific session by ID)
  updateSessionFor,
  addMessageTo,
  removeMessageByClientIdFor,
  setMessagesFor,
  setRunStepsFor,
  upsertRunStepFor,
  setTimelineEventsFor,
  upsertTimelineEventFor,
  upsertTraceSpanFor,
  mergeTraceSpansFor,
  linkUserMessageToRunFor,
  setStatusFor,
  setQueuedFor,
  setQueuedCommandFor,
  setSteeringQueuedFor,
  setErrorFor,
  setCancelingFor,
  getCancelingFor,
  showCancelledHintFor,
  removeState,
  setRestoredPrompt,
} = useSession()

const { projects, currentProject, sidebarMode, setSidebarMode, setCurrentProjectId } = useProject()

const {
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
  switchSession,
  restoreLastSession,
} = useSessionList()

const { fetchStatus: fetchImStatus, fetchChannels: fetchImChannels, resetState: resetImState } = useImBinding()

const { addNotification } = useNotifications()
const { markWorking, markDone } = useWorkingSessions()
const { startListening: startHotkeyHintListening, stopListening: stopHotkeyHintListening } = useHotkeyHint()

const ready = ref(false)
const initError = ref(null)

const settingsDialogVisible = ref(false)
const gitManagerVisible = ref(false)
const terminalDrawerVisible = ref(false)
const terminalDockHeight = ref(0)
const workspaceVisible = ref(false)
const workspaceDockWidth = ref(0)
const schedulerVisible = ref(false)
const schedulerProjectId = ref('')
const scheduleCounts = ref({})
let globalEventConnection = null
const sidebarRef = ref(null)
const { handleBoardEvent, refreshBoardAfterReconnect } = useTeamBoard()
const vbRunning = ref(false)
const vbMessage = ref('')
let vbRefresh = null
const teamBoardVisible = ref(false)

async function handleApplyVb(payload) {
  if (!currentSessionId.value || !currentProject.value || vbRunning.value) return
  vbRunning.value = true
  vbMessage.value = 'Review changes queued'
  vbRefresh = payload.refresh
  try {
    await applyVbReviews(currentSessionId.value, {
      projectId: currentProject.value.id,
      filePath: payload.file_path,
      reviews: payload.reviews,
    })
  } catch (e) {
    vbRunning.value = false
    vbMessage.value = e.message || 'Could not start review changes'
    vbRefresh = null
  }
}

const isMobileSidebarOpen = ref(false)
const isSidebarCollapsed = ref(
  localStorage.getItem('pf_sidebar_collapsed') === 'true'
)

function toggleSidebar() {
  isMobileSidebarOpen.value = !isMobileSidebarOpen.value
}

function toggleSidebarCollapse() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  localStorage.setItem('pf_sidebar_collapsed', isSidebarCollapsed.value)
}

function handleWorkspaceWidthChange(width) {
  workspaceDockWidth.value = width || 0
}

function handleTerminalHeightChange(height) {
  terminalDockHeight.value = height || 0
}

function handleSessionSelect(id) {
  teamBoardVisible.value = false
  switchSession(id)
  isMobileSidebarOpen.value = false
}

function handleProjectSelect(projectId) {
  setCurrentProjectId(projectId)
  setCurrentSessionId(null)
  teamBoardVisible.value = Boolean(
    projectId && projects.value.find(project => project.id === projectId)?.project_type === 'team'
  )
  isMobileSidebarOpen.value = false
}

function handleTeamNavigate(sessionId) {
  if (!sessionId) return
  setSidebarMode('single')
  handleSessionSelect(sessionId)
}

function handleReturnToTeam(projectId) {
  if (!projectId) return
  setSidebarMode('teams')
  handleProjectSelect(projectId)
}

function handleSidebarModeChange(mode) {
  if (mode === 'single') {
    teamBoardVisible.value = false
    restoreLastSession()
  }
}

function handleNotificationNavigate(sessionId) {
  if (!sessionId) return
  setSidebarMode('single')
  handleSessionSelect(sessionId)
}

function handleLocateSession() {
  if (isSidebarCollapsed.value) {
    isSidebarCollapsed.value = false
    localStorage.setItem('pf_sidebar_collapsed', false)
  }
  if (window.innerWidth <= 768) {
    isMobileSidebarOpen.value = true
  }
  sidebarRef.value?.scrollToSession(currentSessionId.value)
}

function closeProjectScheduler() {
  schedulerVisible.value = false
  loadScheduleCounts()
}

function openProjectScheduler(projectId) {
  schedulerProjectId.value = projectId
  schedulerVisible.value = true
}

async function loadScheduleCounts() {
  try {
    const data = await listSchedules()
    const counts = {}
    for (const task of data.tasks || []) {
      if (!task.project_id) continue
      counts[task.project_id] = (counts[task.project_id] || 0) + 1
    }
    scheduleCounts.value = counts
  } catch {
    scheduleCounts.value = {}
  }
}

async function handleGlobalEvent(data) {
  if (data?.event === 'scheduled_session_created') {
    await loadSessions()
    if (data.session_id) {
      ensureConnection(data.session_id)
    }
  }
  // Forward board card events to the team board composable
  if (data?.event?.startsWith('board_card_')) {
    handleBoardEvent(data)
  }
  if (data?.event === 'session_waiting_for_input' && !_connections.has(data.session_id)) {
    const sess = sessions.value.find(s => s.session_id === data.session_id)
    const proj = sess?.project_id
      ? projects.value.find(p => p.id === sess.project_id)
      : null
    addNotification({
      sessionId: data.session_id,
      sessionName: sess?.name || data.session_id,
      projectName: proj?.name || '',
      type: NOTIFICATION_TYPE.AUTH_REQUIRED,
    })
  }
}

// ── Unified connection pool ──
// All session connections live here; no more foreground/background split.
const _connections = reactive(new Map())

// Computed: auto-follows current session
const wsConnection = computed(() => _connections.get(currentSessionId.value) ?? null)

provide('wsConnection', wsConnection)
provide('wsConnections', _connections) // 提供整个连接池给全局快捷键拦截器
provide('switchSession', switchSession) // 提供session切换函数

function syncRecoveryState(sessionId, sessionData) {
  setQueuedCommandFor(sessionId, sessionData?.recovery?.queued_command || null)
}

async function loadLatestRunSteps(sessionId) {
  try {
    const data = await fetchSessionRunSteps(sessionId)
    setRunStepsFor(sessionId, data?.steps || [])
  } catch (e) {
    console.debug('[VP] load run steps failed:', e?.message || e)
  }
}

async function loadTimelineEvents(sessionId) {
  try {
    const data = await fetchSessionTimelineEvents(sessionId, 500)
    setTimelineEventsFor(sessionId, data?.events || [])
  } catch (e) {
    console.debug('[VP] load timeline events failed:', e?.message || e)
  }
}

async function loadTraceSpans(sessionId) {
  try {
    const data = await fetchTraceRuns(sessionId)
    mergeTraceSpansFor(sessionId, data?.spans || [])
  } catch (e) {
    console.debug('[VP] load trace spans failed:', e?.message || e)
  }
}

function setupUnifiedHandler(connection, sessionId) {
  connection.onEvent((data) => {
    const isCurrent = (currentSessionId.value === sessionId)
    const sess = sessions.value.find(s => s.session_id === sessionId)
    const proj = sess?.project_id
      ? projects.value.find(p => p.id === sess.project_id)
      : null

    switch (data.event) {
      case 'connected':
        console.debug('[VP] WS connected:', {
          session: data.session?.session_id,
          messageCount: data.messages?.length || 0,
          resultCount: data.messages?.filter(m => m.type === 'result').length || 0,
        })
        updateSessionFor(sessionId, data.session)
        if (data.messages) setMessagesFor(sessionId, data.messages, data.session)
        setStatusFor(sessionId, data.session.status || 'idle')
        syncRecoveryState(sessionId, data.session)
        updateSessionInList(sessionId, data.session)
        if (data.session.status === 'running') {
          markWorking(sessionId, { sessionName: sess?.name || data.session.name || '', projectName: proj?.name || '' })
        } else {
          markDone(sessionId)
        }
        loadLatestRunSteps(sessionId)
        loadTimelineEvents(sessionId)
        loadTraceSpans(sessionId)
        break

      case 'message':
        if (getCancelingFor(sessionId)
            && data.data?.type === 'result'
            && data.data?.content?.is_error) {
          break
        }
        addMessageTo(sessionId, data.data)
        if (data.data && data.data.type === 'result') {
          markDone(sessionId)
          if (data.data.content?.is_error) {
            addNotification({
              sessionId,
              sessionName: sess?.name || '',
              projectName: proj?.name || '',
              type: NOTIFICATION_TYPE.ERROR,
              message: data.data.content?.text || '',
            })
          }
          maybeCloseIdle(sessionId)
        }
        break

      case 'status_change':
        setStatusFor(sessionId, data.status)
        updateSessionFor(sessionId, {
          waiting_for_slot: false,
          waiting_reason: null,
          slot_queue_position: null,
        })
        updateSessionInList(sessionId, { status: data.status })
        if (data.status === 'running') {
          // A Team execution can start server-side after the user opens its
          // freshly-created session. In that path there is no client-originated
          // `prompt_started` event, so hydrate the persisted user prompt from
          // the status event. Replacing by message ID also keeps normal sends
          // idempotent when both events arrive.
          if (data.prompt && data.message_id) {
            removeMessageByClientIdFor(sessionId, data.message_id)
            addMessageTo(sessionId, {
              type: 'user',
              content: {
                message_id: data.message_id,
                run_id: data.run_id || '',
                text: data.prompt,
                ...(data.attachments?.length ? { attachments: data.attachments } : {}),
              },
            })
          }
          markWorking(sessionId, { sessionName: sess?.name || '', projectName: proj?.name || '' })
        } else {
          markDone(sessionId)
          maybeCloseIdle(sessionId)
        }
        break

      case 'error':
        if (!getCancelingFor(sessionId)) {
          setErrorFor(sessionId, data.message)
          addNotification({
            sessionId,
            sessionName: sess?.name || '',
            projectName: proj?.name || '',
            type: NOTIFICATION_TYPE.ERROR,
            message: data.message || '',
          })
        }
        break

      case 'ws_disconnected':
        if (sess?.status === 'running') {
          setStatusFor(sessionId, 'reconnecting')
        }
        break

      case 'info':
        break

      case 'message_queued':
        setSteeringQueuedFor(sessionId, false)
        removeMessageByClientIdFor(sessionId, data.message_id)
        setQueuedCommandFor(sessionId, {
          message_id: data.message_id || '',
          prompt: data.prompt || '',
          image_count: data.image_count || 0,
          attachment_count: data.attachment_count || 0,
        })
        break

      case 'prompt_started':
      case 'queue_started':
        setSteeringQueuedFor(sessionId, false)
        setQueuedCommandFor(sessionId, null)
        removeMessageByClientIdFor(sessionId, data.message_id)
        addMessageTo(sessionId, {
          type: 'user',
          content: {
            message_id: data.message_id || '',
            text: data.prompt || '',
            ...(data.image_count ? { image_count: data.image_count } : {}),
            ...(data.attachments?.length ? { attachments: data.attachments } : {}),
          },
        })
        break

      case 'message_steered':
        setSteeringQueuedFor(sessionId, false)
        setQueuedCommandFor(sessionId, null)
        removeMessageByClientIdFor(sessionId, data.message_id)
        addMessageTo(sessionId, {
          type: 'user',
          content: {
            message_id: data.message_id || '',
            run_id: data.run_id || '',
            text: data.prompt || '',
            steered: true,
            ...(data.image_count ? { image_count: data.image_count } : {}),
            ...(data.attachments?.length ? { attachments: data.attachments } : {}),
          },
        })
        break

      case 'steer_failed':
        setSteeringQueuedFor(sessionId, false)
        setErrorFor(sessionId, data.message || 'Unable to steer the queued message')
        break

      case 'queue_cleared':
        setSteeringQueuedFor(sessionId, false)
        setQueuedCommandFor(sessionId, null)
        break

      case 'resource_waiting':
        updateSessionFor(sessionId, {
          waiting_for_slot: true,
          waiting_reason: data.status || 'waiting_slot',
          slot_queue_position: data.queue_position || null,
          slot_capacity: data.capacity || null,
        })
        break

      case 'resource_acquired':
        updateSessionFor(sessionId, {
          waiting_for_slot: false,
          waiting_reason: null,
          slot_queue_position: null,
          slot_capacity: data.capacity || null,
        })
        break

      case 'stream_waiting':
        setStatusFor(sessionId, 'running')
        updateSessionInList(sessionId, { status: 'running' })
        markWorking(sessionId, { sessionName: sess?.name || '', projectName: proj?.name || '' })
        break

      case 'auto_continue':
        setStatusFor(sessionId, 'running')
        updateSessionInList(sessionId, { status: 'running' })
        markWorking(sessionId, { sessionName: sess?.name || '', projectName: proj?.name || '' })
        addMessageTo(sessionId, {
          type: 'system',
          content: {
            subtype: 'auto_continue',
            attempt: data.attempt,
            max: data.max,
          },
        })
        break

      case 'run_step_started':
      case 'run_step_progress':
      case 'run_step_completed':
      case 'run_step_failed':
        upsertRunStepFor(sessionId, data.step)
        break

      case 'timeline_event':
        upsertTimelineEventFor(sessionId, data.timeline_event)
        break

      case 'trace_span':
        upsertTraceSpanFor(sessionId, data.span)
        break

      case 'trace_run_started':
        linkUserMessageToRunFor(sessionId, data.message_id, data.run_id)
        break

      case 'user_choice_request':
        addMessageTo(sessionId, {
          type: 'interactive',
          content: {
            interaction_type: 'user_choice',
            tool_name: data.tool_name,
            questions: data.questions,
          },
        })
        addNotification({
          sessionId,
          sessionName: sess?.name || '',
          projectName: proj?.name || '',
          type: NOTIFICATION_TYPE.AUTH_REQUIRED,
        })
        break

      case 'permission_request':
        addMessageTo(sessionId, {
          type: 'interactive',
          content: {
            interaction_type: 'permission',
            tool_name: data.tool_name,
            tool_input: data.tool_input,
          },
        })
        addNotification({
          sessionId,
          sessionName: sess?.name || '',
          projectName: proj?.name || '',
          type: NOTIFICATION_TYPE.AUTH_REQUIRED,
        })
        break

      case 'im_unbound':
        if (isCurrent) {
          resetImState()
          fetchImStatus(sessionId)
          fetchImChannels()
        }
        break

      case 'vb_started':
        if (isCurrent) {
          vbRunning.value = true
          vbMessage.value = 'Codex is applying review comments…'
        }
        break

      case 'vb_completed':
        if (isCurrent) {
          vbRunning.value = false
          vbMessage.value = 'Review changes applied'
          vbRefresh?.()
          vbRefresh = null
        }
        break

      case 'vb_failed':
        if (isCurrent) {
          vbRunning.value = false
          vbMessage.value = data.message || 'Could not apply review changes'
          vbRefresh = null
        }
        break

      case 'cancel_rewind':
        setCancelingFor(sessionId, false)
        showCancelledHintFor(sessionId)
        updateSessionFor(sessionId, data.session)
        if (data.messages) setMessagesFor(sessionId, data.messages, data.session)
        setStatusFor(sessionId, data.session.status || 'idle')
        updateSessionFor(sessionId, { waiting_for_slot: false })
        setQueuedFor(sessionId, false)
        updateSessionInList(sessionId, data.session)
        markDone(sessionId)
        if (data.prompt && sessionId === currentSessionId.value) {
          setRestoredPrompt(data.prompt)
        }
        break

      case 'status': {
        // Don't overwrite git_branch with empty string
        const sessionUpdate = { ...data.session }
        if (!sessionUpdate.git_branch) {
          delete sessionUpdate.git_branch
        }
        updateSessionFor(sessionId, sessionUpdate)
        if (data.session.status === 'running' || data.session.status === 'idle') {
          updateSessionFor(sessionId, {
            waiting_for_slot: false,
            waiting_reason: null,
            slot_queue_position: null,
          })
        }
        setStatusFor(sessionId, data.session.status || 'idle')
        syncRecoveryState(sessionId, data.session)
        updateSessionInList(sessionId, data.session)
        break
      }
    }
  })
}

function ensureConnection(sessionId) {
  if (_connections.has(sessionId)) return
  const connection = createWsConnection(sessionId)
  _connections.set(sessionId, connection)
  setupUnifiedHandler(connection, sessionId)
}

function forceCloseConnection(sessionId) {
  const conn = _connections.get(sessionId)
  if (conn) {
    conn.close()
    _connections.delete(sessionId)
  }
}

function maybeCloseIdle(sessionId) {
  if (sessionId === currentSessionId.value) return
  const sess = sessions.value.find(s => s.session_id === sessionId)
  if (!sess || sess.status !== 'running') {
    forceCloseConnection(sessionId)
  }
}

// ── Session deletion wrappers (close connections before delegating) ──

async function onDeleteSession(sessionId) {
  forceCloseConnection(sessionId)
  removeState(sessionId)
  await handleDelete(sessionId)
}

async function onBatchDeleteSessions(sessionIds) {
  for (const id of sessionIds) {
    forceCloseConnection(id)
    removeState(id)
  }
  await handleBatchDelete(sessionIds)
}

async function onDeleteProject(projectId) {
  const projectSessions = sessions.value.filter(s => s.project_id === projectId)
  for (const s of projectSessions) {
    forceCloseConnection(s.session_id)
    removeState(s.session_id)
  }
  await handleDeleteProject(projectId)
}

// ── Session switching: no more reset(), just ensure connection ──

watch(currentSessionId, (newId, oldId) => {
  if (newId) {
    ensureConnection(newId)
  }
  if (oldId && oldId !== newId) {
    maybeCloseIdle(oldId)
  }
})

onMounted(async () => {
  try {
    await loadSessions()
    await loadScheduleCounts()
    globalEventConnection = createGlobalEventConnection()
    globalEventConnection.onEvent(handleGlobalEvent)
    globalEventConnection.onReconnect(() => {
      refreshBoardAfterReconnect()
    })
    window.addEventListener('vp-schedules-changed', loadScheduleCounts)
    if (sidebarMode.value === 'teams') {
      const firstTeam = projects.value.find(project => project.project_type === 'team')
      handleProjectSelect(firstTeam?.id || null)
    } else {
      restoreLastSession()
    }
    ready.value = true
  } catch (e) {
    initError.value = e.message || 'Failed to load sessions'
    ready.value = true
  }

  // Fade out splash screen after app is ready
  nextTick(() => {
    const splash = document.getElementById('vp-splash')
    if (splash) {
      splash.classList.add('fade-out')
      splash.addEventListener('transitionend', () => splash.remove(), { once: true })
    }
  })

  // Listen for Claude Code session import events to scroll to new position
  window.addEventListener('vp-session-imported', handleSessionImported)

  // Start listening for Cmd/Ctrl key for hotkey hints
  startHotkeyHintListening()
})

onBeforeUnmount(() => {
  // Clean up event listener
  window.removeEventListener('vp-session-imported', handleSessionImported)
  window.removeEventListener('vp-schedules-changed', loadScheduleCounts)
  stopHotkeyHintListening()

  if (globalEventConnection) {
    globalEventConnection.close()
    globalEventConnection = null
  }

  for (const conn of _connections.values()) {
    conn.close()
  }
  _connections.clear()
})

function handleSessionImported(event) {
  const { sessionId } = event.detail
  if (isSidebarCollapsed.value) {
    isSidebarCollapsed.value = false
    localStorage.setItem('pf_sidebar_collapsed', false)
  }
  if (window.innerWidth <= 768) {
    isMobileSidebarOpen.value = true
  }
  // Wait for DOM to update then scroll to the new session position
  nextTick(() => {
    sidebarRef.value?.scrollToSession(sessionId)
  })
}

// ── Global shortcuts ──

// Cmd/Ctrl + P: Open settings dialog
useGlobalHotkeys({
  keys: ['Ctrl+P', 'Cmd+P'],
  handler: () => {
    settingsDialogVisible.value = true
    return false
  },
  priority: 100
})

// Cmd/Ctrl + B: Toggle sidebar collapse
useGlobalHotkeys({
  keys: ['Ctrl+B', 'Cmd+B'],
  handler: () => {
    toggleSidebarCollapse()
    return false
  },
  priority: 100
})
</script>

<template>
  <div class="app-layout">
    <!-- Global shortcut interceptor -->
    <GlobalShortcutInterceptor />
    <!-- Skeleton: shown while loadSessions() is pending (ready=false, no error) -->
    <template v-if="!ready && !initError">
      <header class="app-header">
        <div class="header-left">
          <AppLogo prefix="logo" />
        </div>
        <div class="header-right">
          <div class="skel-circle"></div>
          <div class="skel-circle"></div>
          <div class="skel-circle"></div>
          <div class="skel-circle"></div>
        </div>
      </header>
      <div class="app-body">
        <!-- Sidebar skeleton -->
        <aside class="skel-sidebar">
          <div class="skel-sidebar-header">
            <div class="skel-bar" style="width:60%;height:12px"></div>
          </div>
          <div class="skel-sidebar-list">
            <div v-for="i in 6" :key="i" class="skel-session-item">
              <div class="skel-bar" :style="{ width: (50 + i * 7) + '%', height: '10px' }"></div>
              <div class="skel-bar" style="width:40%;height:8px;margin-top:6px"></div>
            </div>
          </div>
        </aside>
        <!-- Main area skeleton -->
        <main class="app-main skel-main">
          <div class="skel-main-inner">
            <div class="skel-msg skel-msg-assistant">
              <div class="skel-bar" style="width:75%;height:10px"></div>
              <div class="skel-bar" style="width:90%;height:10px;margin-top:8px"></div>
              <div class="skel-bar" style="width:55%;height:10px;margin-top:8px"></div>
            </div>
            <div class="skel-msg skel-msg-user">
              <div class="skel-bar" style="width:45%;height:10px"></div>
            </div>
            <div class="skel-msg skel-msg-assistant">
              <div class="skel-bar" style="width:85%;height:10px"></div>
              <div class="skel-bar" style="width:65%;height:10px;margin-top:8px"></div>
            </div>
          </div>
          <!-- Input bar skeleton -->
          <div class="skel-input-bar">
            <div class="skel-bar" style="width:100%;height:36px;border-radius:8px"></div>
          </div>
        </main>
      </div>
    </template>

    <!-- Real UI: shown after ready or on error -->
    <template v-else>
      <header class="app-header">
        <div class="header-left">
          <button class="mobile-menu-btn" @click="toggleSidebar" aria-label="Toggle menu">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="3" y1="12" x2="21" y2="12"></line>
              <line x1="3" y1="6" x2="21" y2="6"></line>
              <line x1="3" y1="18" x2="21" y2="18"></line>
            </svg>
          </button>
          <AppLogo prefix="hdr" />
        </div>
        <div class="header-right">
          <NotificationBell @navigate="handleNotificationNavigate" />
          <WorkingSessionsButton @navigate="handleNotificationNavigate" />
          <GitManagerButton @click="gitManagerVisible = true" />
          <SettingsButton @click="settingsDialogVisible = true" />
          <WorkspaceButton :active="workspaceVisible" @click="workspaceVisible = !workspaceVisible" />
          <TerminalButton :active="terminalDrawerVisible" @click="terminalDrawerVisible = !terminalDrawerVisible" />
          <ThemeSwitcher />
        </div>
      </header>

      <div
        class="app-body"
        :style="{
          paddingBottom: terminalDrawerVisible ? terminalDockHeight + 'px' : '0px',
          paddingRight: workspaceVisible ? workspaceDockWidth + 'px' : '0px',
        }"
      >
        <div
          v-if="isMobileSidebarOpen"
          class="mobile-sidebar-overlay"
          @click="isMobileSidebarOpen = false"
        ></div>
        <SessionSidebar
          ref="sidebarRef"
          class="main-sidebar"
          :class="{ 'sidebar-open': isMobileSidebarOpen, 'sidebar-collapsed': isSidebarCollapsed }"
          :sessions="sessions"
          :current-session-id="currentSessionId"
          :loading="loading"
          :schedule-counts="scheduleCounts"
          @create="handleCreate"
          @select="handleSessionSelect"
          @delete="onDeleteSession"
          @batch-delete="onBatchDeleteSessions"
          @rename="handleRename"
          @create-in-project="handleCreateInProject"
          @delete-project="onDeleteProject"
          @open-scheduler="openProjectScheduler"
          @reorder-projects="handleReorderProjects"
          @select-project="handleProjectSelect"
          @mode-change="handleSidebarModeChange"
        />
        <div class="sidebar-collapse-area" :class="{ collapsed: isSidebarCollapsed }">
          <div class="sidebar-hover-zone"></div>
          <button
            class="sidebar-collapse-btn"
            :class="{ collapsed: isSidebarCollapsed }"
            @click="toggleSidebarCollapse"
            :title="isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline :points="isSidebarCollapsed ? '9 18 15 12 9 6' : '15 18 9 12 15 6'"/>
            </svg>
          </button>
        </div>
        <main class="app-main">
          <div v-if="initError" class="init-error">
            <div class="error-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <line x1="15" y1="9" x2="9" y2="15"/>
                <line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
            </div>
            <div class="error-text">
              <div class="error-title">Connection Failed</div>
              <div class="error-detail">{{ initError }}</div>
              <div class="error-hint">Make sure the backend server is running on port 8083</div>
            </div>
          </div>
          <TeamBoardPage
            v-else-if="teamBoardVisible && currentProject?.project_type === 'team' && currentProject?.team_config?.team_id"
            :key="currentProject.team_config.team_id"
            :team-id="currentProject.team_config.team_id"
            :project-id="currentProject.id"
            @navigate-session="handleTeamNavigate"
          />
          <div v-else-if="sidebarMode === 'teams'" class="empty-state">
            <div class="empty-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
                <circle cx="9" cy="7" r="4"/>
                <path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
                <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
              </svg>
            </div>
            <div class="empty-text">Select or create a team to open its board</div>
          </div>
          <ChatPanelPage
            v-else-if="currentSessionId && !importing"
            @locate-session="handleLocateSession"
            @return-team="handleReturnToTeam"
          />
          <div v-else-if="importing" class="loading">
            <div class="loading-shimmer-container">
              <div class="shimmer-block w-full h-24"></div>
              <div class="shimmer-block w-3/4 h-16"></div>
              <div class="shimmer-block w-full h-32"></div>
            </div>
            <span>Importing Claude Code session...</span>
          </div>
          <div v-else-if="!currentSessionId" class="empty-state">
            <div class="empty-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <div class="empty-text">Select or create a session to start</div>
          </div>
        </main>
      </div>

      <SettingsDialog
        :visible="settingsDialogVisible"
        @close="settingsDialogVisible = false"
      />
      <GitManagerDialog
        :visible="gitManagerVisible"
        @close="gitManagerVisible = false"
      />
      <WorkspacePanel
        :visible="workspaceVisible"
        :project="currentProject"
        :vb-running="vbRunning"
        :vb-message="vbMessage"
        @apply-vb="handleApplyVb"
        @width-change="handleWorkspaceWidthChange"
        @close="workspaceVisible = false"
      />
      <TerminalDrawer
        :visible="terminalDrawerVisible"
        :project-dir="session?.project_dir || ''"
        :git-branch="session?.git_branch || ''"
        @close="terminalDrawerVisible = false"
        @height-change="handleTerminalHeightChange"
      />
      <SchedulerDialog
        :visible="schedulerVisible"
        :project-id="schedulerProjectId"
        session-id=""
        @close="closeProjectScheduler"
      />
    </template>
  </div>
</template>

<style scoped>
.app-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--layer-base);
  transition: background var(--transition-base);
}

.app-header {
  position: relative;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 48px;
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass-bg);
  flex-shrink: 0;
  box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-sm);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  transition: background var(--transition-base), border-color var(--transition-base), box-shadow var(--transition-base);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
  background: var(--layer-workspace);
  border-top: 1px solid var(--border-subtle);
  transition:
    padding-bottom var(--motion-emphasis) var(--ease-out),
    padding-right var(--motion-medium) var(--ease-out),
    background var(--transition-base);
}

.mobile-menu-btn {
  display: none;
  align-items: center;
  justify-content: center;
  min-width: var(--touch-target);
  min-height: var(--touch-target);
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  margin-right: 8px;
  border-radius: var(--radius-md);
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast);
}

.mobile-menu-btn:hover {
  background: var(--layer-active);
  border-color: var(--glass-border);
  color: var(--accent);
}

.mobile-sidebar-overlay {
  display: none;
  position: absolute;
  inset: 0;
  background: var(--overlay-glass);
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
  z-index: 40;
}

.main-sidebar {
  transition: transform var(--transition-base), width var(--transition-base), min-width var(--transition-base), opacity var(--transition-base), filter var(--transition-base);
  overflow: hidden;
}

.main-sidebar.sidebar-collapsed {
  width: 0 !important;
  min-width: 0 !important;
  border-right: none;
  opacity: 0;
  pointer-events: none;
}

.sidebar-collapse-area {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 310px;
  z-index: 15;
  pointer-events: none;
}

.sidebar-collapse-area.collapsed {
  width: 260px;
}

.sidebar-hover-zone {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 260px;
  width: 50px;
  pointer-events: auto;
}

.sidebar-collapse-area.collapsed .sidebar-hover-zone {
  width: 100%;
  left: 0;
}

.sidebar-collapse-btn {
  position: absolute;
  top: 50%;
  left: 260px;
  transform: translateY(-50%);
  z-index: 30;
  width: 24px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-left: none;
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  color: var(--text-muted);
  cursor: pointer;
  transition: opacity var(--transition-fast), color var(--transition-fast), background var(--transition-fast), left var(--transition-base), box-shadow var(--transition-fast);
  padding: 0;
  pointer-events: auto;
  opacity: 0;
  box-shadow: var(--shadow-sm);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.sidebar-hover-zone:hover + .sidebar-collapse-btn,
.sidebar-collapse-btn:hover {
  opacity: 1;
  color: var(--accent);
  background: var(--glass-bg-strong);
  box-shadow: var(--shadow-active);
}

.sidebar-collapse-btn.collapsed {
  left: 0;
  border-left: none;
  border-right: 1px solid var(--border);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

.sidebar-collapse-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

@media (max-width: 768px) {
  .mobile-menu-btn {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .main-sidebar {
    position: absolute;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 50;
    transform: translateX(-100%);
  }

  .main-sidebar.sidebar-open {
    transform: translateX(0);
  }

  .main-sidebar.sidebar-collapsed {
    width: 260px !important;
    min-width: 260px !important;
    opacity: 1;
  }

  .mobile-sidebar-overlay {
    display: block;
  }

  .sidebar-collapse-area,
  .sidebar-collapse-btn {
    display: none;
  }
}

.app-main {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent 22%),
    var(--layer-workspace);
  transition: background var(--transition-base);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 100%;
  color: var(--text-muted);
}

.empty-icon {
  opacity: 0.3;
}

.empty-text {
  font-size: 14px;
}

.init-error {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: auto;
  padding: 24px 32px;
  background: var(--bg-secondary);
  border: 1px solid var(--red);
  border-radius: var(--radius-lg);
  max-width: 480px;
  box-shadow: var(--shadow-lg);
}

.error-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--red-dim);
  color: var(--red);
  border-radius: 50%;
  flex-shrink: 0;
}

.error-title {
  font-weight: 600;
  color: var(--red);
  margin-bottom: 4px;
}

.error-detail {
  color: var(--text-secondary);
  font-size: 13px;
}

.error-hint {
  color: var(--text-muted);
  font-size: 12px;
  margin-top: 8px;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  margin: auto;
  color: var(--text-secondary);
  width: 100%;
  max-width: 600px;
  padding: 40px;
}

.loading-shimmer-container {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.shimmer-block {
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  animation: shimmer 1.5s ease-in-out infinite;
  background-image: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0) 0,
    rgba(255, 255, 255, 0.05) 20%,
    rgba(255, 255, 255, 0.1) 60%,
    rgba(255, 255, 255, 0)
  );
  background-size: 200% 100%;
}

[data-theme="light"] .shimmer-block,
[data-theme="sepia"] .shimmer-block {
  background-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0,
    rgba(0, 0, 0, 0.02) 20%,
    rgba(0, 0, 0, 0.04) 60%,
    rgba(0, 0, 0, 0)
  );
}

.w-full { width: 100%; }
.w-3\/4 { width: 75%; }
.h-24 { height: 96px; }
.h-16 { height: 64px; }
.h-32 { height: 128px; }

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ===================================================================
   SKELETON — Layout-accurate loading state
   =================================================================== */
.skel-bar {
  background: var(--bg-hover);
  border-radius: 4px;
  animation: skel-pulse 1.5s ease-in-out infinite;
}

.skel-circle {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--bg-hover);
  animation: skel-pulse 1.5s ease-in-out infinite;
}

.skel-sidebar {
  width: 260px;
  min-width: 260px;
  border-right: 1px solid var(--glass-border);
  background: var(--glass-bg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.03);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  transition: background var(--transition-base), border-color var(--transition-base);
}

.skel-sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--border);
}

.skel-sidebar-list {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.skel-session-item {
  padding: 10px 12px;
  border-radius: var(--radius-md);
}

.skel-main {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.skel-main-inner {
  flex: 1;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow: hidden;
}

.skel-msg {
  max-width: 65%;
  padding: 14px 18px;
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
}

.skel-msg-user {
  align-self: flex-end;
  background: var(--accent-dim);
}

.skel-msg-assistant {
  align-self: flex-start;
}

.skel-input-bar {
  padding: 12px 24px 20px;
}

@media (max-width: 768px) {
  .skel-sidebar {
    display: none;
  }
}
</style>
