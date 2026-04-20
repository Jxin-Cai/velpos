<script setup>
import { ref, reactive, computed, watch, provide, onMounted, onUnmounted, nextTick } from 'vue'
import { useSession } from '@entities/session'
import { useProject } from '@entities/project'
import { useImBinding } from '@features/im-binding'
import { createWsConnection } from '@shared/api/wsClient'
import { ChatPanelPage } from '@pages/chat-panel'
import { SessionSidebar, useSessionList } from '@features/session-list'
import { NotificationBell, useNotifications } from '@features/notification-center'
import { WorkingSessionsButton, useWorkingSessions } from '@features/working-sessions'
import { SettingsButton, SettingsDialog } from '@features/settings-manager'
import { GitManagerButton, GitManagerDialog } from '@features/git-manager'
import { TerminalButton, TerminalDrawer } from '@features/terminal'
import ThemeSwitcher from '@shared/ui/ThemeSwitcher.vue'
import GlobalShortcutInterceptor from '@shared/ui/GlobalShortcutInterceptor.vue'

const {
  session,
  sessions,
  currentSessionId,
  updateSessionInList,
  // Targeted APIs (write to specific session by ID)
  updateSessionFor,
  addMessageTo,
  setMessagesFor,
  setStatusFor,
  setQueuedFor,
  setErrorFor,
  removeState,
} = useSession()

const { projects } = useProject()

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

const ready = ref(false)
const initError = ref(null)

const settingsDialogVisible = ref(false)
const gitManagerVisible = ref(false)
const terminalDrawerVisible = ref(false)
const sidebarRef = ref(null)

const isMobileSidebarOpen = ref(false)
const isSidebarCollapsed = ref(
  localStorage.getItem('vp_sidebar_collapsed') === 'true'
)

function toggleSidebar() {
  isMobileSidebarOpen.value = !isMobileSidebarOpen.value
}

function toggleSidebarCollapse() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  localStorage.setItem('vp_sidebar_collapsed', isSidebarCollapsed.value)
}

function handleSessionSelect(id) {
  switchSession(id)
  isMobileSidebarOpen.value = false
}

function handleNotificationNavigate(sessionId) {
  switchSession(sessionId)
}

function handleLocateSession() {
  if (isSidebarCollapsed.value) {
    isSidebarCollapsed.value = false
    localStorage.setItem('vp_sidebar_collapsed', false)
  }
  if (window.innerWidth <= 768) {
    isMobileSidebarOpen.value = true
  }
  sidebarRef.value?.scrollToSession(currentSessionId.value)
}

// ── Unified connection pool ──
// All session connections live here; no more foreground/background split.
const _connections = reactive(new Map())

// Computed: auto-follows current session
const wsConnection = computed(() => _connections.get(currentSessionId.value) ?? null)

provide('wsConnection', wsConnection)
provide('wsConnections', _connections) // 提供整个连接池给全局快捷键拦截器
provide('switchSession', switchSession) // 提供session切换函数

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
        updateSessionInList(sessionId, data.session)
        if (data.session.status === 'running') {
          markWorking(sessionId, { sessionName: sess?.name || data.session.name || '', projectName: proj?.name || '' })
        } else {
          markDone(sessionId)
        }
        break

      case 'message':
        addMessageTo(sessionId, data.data)
        if (data.data && data.data.type === 'result') {
          markDone(sessionId)
          addNotification({
            sessionId,
            sessionName: sess?.name || '',
            projectName: proj?.name || '',
          })
          maybeCloseIdle(sessionId)
        }
        break

      case 'status_change':
        setStatusFor(sessionId, data.status)
        updateSessionInList(sessionId, { status: data.status })
        if (data.status === 'running') {
          markWorking(sessionId, { sessionName: sess?.name || '', projectName: proj?.name || '' })
        } else {
          markDone(sessionId)
          maybeCloseIdle(sessionId)
        }
        break

      case 'error':
        setErrorFor(sessionId, data.message)
        break

      case 'ws_disconnected':
        if (sess?.status === 'running') {
          setStatusFor(sessionId, 'reconnecting')
        }
        break

      case 'info':
        break

      case 'message_queued':
        setQueuedFor(sessionId, true)
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
          type: 'auth_required',
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
          type: 'auth_required',
        })
        break

      case 'im_unbound':
        if (isCurrent) {
          resetImState()
          fetchImStatus(sessionId)
          fetchImChannels()
        }
        break

      case 'cancel_rewind':
        updateSessionFor(sessionId, data.session)
        if (data.messages) setMessagesFor(sessionId, data.messages, data.session)
        setStatusFor(sessionId, data.session.status || 'idle')
        updateSessionInList(sessionId, data.session)
        markDone(sessionId)
        if (isCurrent) {
          window.dispatchEvent(new CustomEvent('vp-cancel-rewind', {
            detail: { prompt: data.prompt || '' },
          }))
        }
        break

      case 'status': {
        // Don't overwrite git_branch with empty string
        const sessionUpdate = { ...data.session }
        if (!sessionUpdate.git_branch) {
          delete sessionUpdate.git_branch
        }
        updateSessionFor(sessionId, sessionUpdate)
        setStatusFor(sessionId, data.session.status || 'idle')
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
    restoreLastSession()
    ready.value = true
  } catch (e) {
    initError.value = e.message || 'Failed to load sessions'
  }

  // Listen for Claude Code session import events to scroll to new position
  window.addEventListener('vp-session-imported', handleSessionImported)
})

onUnmounted(() => {
  // Clean up event listener
  window.removeEventListener('vp-session-imported', handleSessionImported)

  for (const conn of _connections.values()) {
    conn.close()
  }
  _connections.clear()
})

function handleSessionImported(event) {
  const { sessionId } = event.detail
  if (isSidebarCollapsed.value) {
    isSidebarCollapsed.value = false
    localStorage.setItem('vp_sidebar_collapsed', false)
  }
  if (window.innerWidth <= 768) {
    isMobileSidebarOpen.value = true
  }
  // Wait for DOM to update then scroll to the new session position
  nextTick(() => {
    sidebarRef.value?.scrollToSession(sessionId)
  })
}
</script>

<template>
  <div class="app-layout">
    <!-- Global shortcut interceptor -->
    <GlobalShortcutInterceptor />
    <!-- Skeleton: shown while loadSessions() is pending (ready=false, no error) -->
    <template v-if="!ready && !initError">
      <header class="app-header">
        <div class="header-left">
          <div class="logo">
            <span class="logo-icon">VP</span>
            <span class="logo-text">Velpos</span>
          </div>
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
          <div class="logo">
            <span class="logo-icon">VP</span>
            <span class="logo-text">Velpos</span>
          </div>
        </div>
        <div class="header-right">
          <NotificationBell @navigate="handleNotificationNavigate" />
          <WorkingSessionsButton @navigate="handleNotificationNavigate" />
          <GitManagerButton @click="gitManagerVisible = true" />
          <SettingsButton @click="settingsDialogVisible = true" />
          <TerminalButton @click="terminalDrawerVisible = true" />
          <ThemeSwitcher />
        </div>
      </header>

      <div class="app-body">
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
          @create="handleCreate"
          @select="handleSessionSelect"
          @delete="onDeleteSession"
          @batch-delete="onBatchDeleteSessions"
          @rename="handleRename"
          @create-in-project="handleCreateInProject"
          @delete-project="onDeleteProject"
          @reorder-projects="handleReorderProjects"
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
          <ChatPanelPage v-else-if="currentSessionId && !importing" @locate-session="handleLocateSession" />
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
      <TerminalDrawer
        :visible="terminalDrawerVisible"
        :project-dir="session?.project_dir || ''"
        :git-branch="session?.git_branch || ''"
        @close="terminalDrawerVisible = false"
      />
    </template>
  </div>
</template>

<style scoped>
.app-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  transition: background var(--transition-base);
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 48px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
  box-shadow: var(--shadow-xs);
  transition: background var(--transition-base), border-color var(--transition-base);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-divider {
  width: 1px;
  height: 20px;
  background: var(--border);
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 14px;
  color: var(--text-on-accent);
  background: linear-gradient(135deg, var(--accent), var(--purple));
  padding: 3px 6px;
  border-radius: var(--radius-sm);
  letter-spacing: 1px;
  box-shadow: var(--shadow-sm);
}

.logo-text {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.app-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}

.mobile-menu-btn {
  display: none;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  margin-right: 8px;
  border-radius: var(--radius-sm);
}

.mobile-menu-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.mobile-sidebar-overlay {
  display: none;
  position: absolute;
  inset: 0;
  background: var(--bg-overlay);
  z-index: 40;
}

.main-sidebar {
  transition: transform var(--transition-base), width var(--transition-base), min-width var(--transition-base), opacity var(--transition-base);
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
  width: 20px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-left: none;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--text-muted);
  cursor: pointer;
  transition: opacity 0.2s, color var(--transition-fast), background var(--transition-fast), left var(--transition-base);
  padding: 0;
  pointer-events: auto;
  opacity: 0;
}

.sidebar-hover-zone:hover + .sidebar-collapse-btn,
.sidebar-collapse-btn:hover {
  opacity: 1;
  color: var(--text-primary);
  background: var(--bg-hover);
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

.sidebar-collapse-btn.collapsed {
  left: 0;
  border-left: none;
  border-right: 1px solid var(--border);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
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
  background: var(--bg-primary);
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
@keyframes skel-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.8; }
}

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
  border-right: 1px solid var(--border);
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: background var(--transition-base);
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
