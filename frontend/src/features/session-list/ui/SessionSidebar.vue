<script setup>
import { ref, computed, reactive, watch, nextTick, onBeforeUnmount, onMounted } from 'vue'
import { useProject } from '@entities/project'
import { PINNED_PROJECTS_KEY, PINNED_SESSIONS_KEY, compareSessions, loadPinnedIds, savePinnedIds, splitPinnedProjects, togglePinnedId } from '@shared/lib/pinning'
import SessionListItem from './SessionListItem.vue'
import CreateSessionDialog from './CreateSessionDialog.vue'

const COLLAPSED_KEY = 'pf_collapsed_groups'

const props = defineProps({
  sessions: {
    type: Array,
    required: true,
  },
  currentSessionId: {
    type: String,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  scheduleCounts: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits([
  'create',
  'select',
  'delete',
  'batch-delete',
  'rename',
  'create-in-project',
  'open-scheduler',
  'delete-project',
  'reorder-projects',
])

const { projects } = useProject()

const showCreateDialog = ref(false)

// Pinned management
const pinnedProjectIds = ref(loadPinnedIds(PINNED_PROJECTS_KEY))
const pinnedSessionIds = ref(loadPinnedIds(PINNED_SESSIONS_KEY))

function persistPinnedProjects() {
  try {
    savePinnedIds(PINNED_PROJECTS_KEY, pinnedProjectIds.value)
  } catch (e) {
    console.warn('Failed to save pinned projects:', e)
  }
}

function persistPinnedSessions() {
  try {
    savePinnedIds(PINNED_SESSIONS_KEY, pinnedSessionIds.value)
  } catch (e) {
    console.warn('Failed to save pinned sessions:', e)
  }
}

function scheduleCount(projectId) {
  return props.scheduleCounts?.[projectId] || 0
}

function isProjectPinned(projectId) {
  return pinnedProjectIds.value.has(projectId)
}

function toggleProjectPin(projectId) {
  pinnedProjectIds.value = togglePinnedId(pinnedProjectIds.value, projectId)
  persistPinnedProjects()
}

function isSessionPinned(sessionId) {
  return pinnedSessionIds.value.has(sessionId)
}

function toggleSessionPin(sessionId) {
  pinnedSessionIds.value = togglePinnedId(pinnedSessionIds.value, sessionId)
  persistPinnedSessions()
  nextTick(() => scrollToSession(sessionId))
}

// Dynamic max-height for group content (avoids fixed 2000px truncation)
const groupContentRefs = reactive({})

watch(() => props.sessions, () => {
  nextTick(() => {
    for (const [id, el] of Object.entries(groupContentRefs)) {
      if (el && !isGroupCollapsed(id)) {
        el.style.maxHeight = el.scrollHeight + 'px'
      }
    }
  })
}, { deep: true })

// Multi-select mode
const selectionMode = ref(false)
const selectedIds = ref(new Set())

function toggleSelectionMode() {
  selectionMode.value = !selectionMode.value
  if (!selectionMode.value) {
    selectedIds.value = new Set()
  }
}

function toggleSelect(sessionId) {
  const next = new Set(selectedIds.value)
  if (next.has(sessionId)) {
    next.delete(sessionId)
  } else {
    next.add(sessionId)
  }
  selectedIds.value = next
}

function confirmBatchDelete() {
  if (selectedIds.value.size === 0) return
  emit('batch-delete', [...selectedIds.value])
  selectedIds.value = new Set()
  selectionMode.value = false
}

// Delete project confirmation state — two-option menu
const deletingProject = ref(null)
let deleteProjectTimer = null

function requestDeleteProject(projectId) {
  deletingProject.value = projectId
  clearTimeout(deleteProjectTimer)
  deleteProjectTimer = setTimeout(() => {
    deletingProject.value = null
  }, 5000)
}

function confirmDeleteProject(projectId) {
  clearTimeout(deleteProjectTimer)
  deletingProject.value = null
  emit('delete-project', projectId)
}

function enterProjectSessionSelect(projectId) {
  clearTimeout(deleteProjectTimer)
  deletingProject.value = null
  // Enter selection mode with this project's sessions pre-scoped
  selectionMode.value = true
  selectedIds.value = new Set()
  // Auto-expand this project group if collapsed
  if (isGroupCollapsed(projectId)) {
    toggleGroup(projectId)
  }
}

function cancelDeleteProject() {
  clearTimeout(deleteProjectTimer)
  deletingProject.value = null
}

// Collapse state: stores project IDs of collapsed groups
const collapsedGroups = ref(new Set(
  JSON.parse(localStorage.getItem(COLLAPSED_KEY) || '[]')
))

function toggleGroup(id) {
  const next = new Set(collapsedGroups.value)
  if (next.has(id)) {
    // Expand: keep collapsed briefly, measure, then animate open
    next.delete(id)
    const el = groupContentRefs[id]
    if (el) {
      // Force max-height to 0 first (still collapsed visually)
      el.style.maxHeight = '0px'
      el.style.opacity = '0'
      collapsedGroups.value = next
      localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...next]))
      nextTick(() => {
        const targetHeight = el.scrollHeight
        el.style.maxHeight = targetHeight + 'px'
        el.style.opacity = '1'
        const onEnd = () => {
          el.style.maxHeight = 'none'
          el.style.opacity = ''
          el.removeEventListener('transitionend', onEnd)
        }
        el.addEventListener('transitionend', onEnd)
      })
    } else {
      collapsedGroups.value = next
      localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...next]))
    }
  } else {
    // Collapse: set max-height to current height first, then collapse next frame
    next.add(id)
    const el = groupContentRefs[id]
    if (el) {
      el.style.maxHeight = el.scrollHeight + 'px'
      requestAnimationFrame(() => {
        collapsedGroups.value = next
        localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...next]))
      })
    } else {
      collapsedGroups.value = next
      localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...next]))
    }
  }
}

function isGroupCollapsed(id) {
  return collapsedGroups.value.has(id)
}

// Build project groups with their sessions
const projectGroups = computed(() => {
  const sessionsByProject = {}
  for (const session of props.sessions) {
    const pid = session.project_id || '__unassigned__'
    if (!sessionsByProject[pid]) {
      sessionsByProject[pid] = []
    }
    sessionsByProject[pid].push(session)
  }

  // Sort sessions within each group: pinned first, running next, then by updated_time descending
  for (const list of Object.values(sessionsByProject)) {
    list.sort((a, b) => compareSessions(a, b, pinnedSessionIds.value))
  }

  // Build ordered project groups (projects are already sorted by sort_order from backend)
  // Separate pinned and unpinned projects
  const pinnedGroups = []
  const unpinnedGroups = []

  const { pinnedProjects, unpinnedProjects } = splitPinnedProjects(projects.value, pinnedProjectIds.value)

  for (const project of [...pinnedProjects, ...unpinnedProjects]) {
    const projectSessions = sessionsByProject[project.id] || []
    if (projectSessions.length === 0) continue

    const group = {
      id: project.id,
      name: project.name,
      sessions: projectSessions,
      pinned: isProjectPinned(project.id),
    }

    if (group.pinned) {
      pinnedGroups.push(group)
    } else {
      unpinnedGroups.push(group)
    }
  }

  // Pinned projects first, then unpinned projects
  const groups = [...pinnedGroups, ...unpinnedGroups]

  // Mark the last pinned project to show separator after it
  if (pinnedGroups.length > 0 && unpinnedGroups.length > 0) {
    groups[pinnedGroups.length - 1].isLastPinned = true
  }

  // Unassigned sessions (no project_id, including claude-code imports)
  const unassigned = sessionsByProject['__unassigned__']
  if (unassigned && unassigned.length > 0) {
    groups.push({
      id: '__unassigned__',
      name: 'Unassigned',
      sessions: unassigned,
    })
  }

  return groups
})

// Drag-and-drop for project reordering
const dragProjectId = ref(null)
const dragOverProjectId = ref(null)

function onDragStart(e, projectId) {
  if (projectId === '__unassigned__') {
    e.preventDefault()
    return
  }
  dragProjectId.value = projectId
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', projectId)
}

function onDragOver(e, projectId) {
  if (projectId === '__unassigned__' || !dragProjectId.value) return
  e.preventDefault()
  dragOverProjectId.value = projectId
}

function onDragLeave() {
  dragOverProjectId.value = null
}

function onDrop(e, targetProjectId) {
  e.preventDefault()
  dragOverProjectId.value = null
  const sourceId = dragProjectId.value
  dragProjectId.value = null

  if (!sourceId || sourceId === targetProjectId || targetProjectId === '__unassigned__') return

  // Compute new order
  const currentOrder = projects.value.map(p => p.id)
  const fromIdx = currentOrder.indexOf(sourceId)
  const toIdx = currentOrder.indexOf(targetProjectId)
  if (fromIdx === -1 || toIdx === -1) return

  currentOrder.splice(fromIdx, 1)
  currentOrder.splice(toIdx, 0, sourceId)

  emit('reorder-projects', currentOrder)
}

function onDragEnd() {
  dragProjectId.value = null
  dragOverProjectId.value = null
}

function handleCreateConfirm(payload) {
  showCreateDialog.value = false
  emit('create', payload)
}

function handleCreateCancel() {
  showCreateDialog.value = false
}

function scrollToSession(sessionId) {
  if (!sessionId) return
  // Find which group the session belongs to
  for (const group of projectGroups.value) {
    const found = group.sessions.find(s => s.session_id === sessionId)
    if (found) {
      // Expand the group if collapsed
      if (isGroupCollapsed(group.id)) {
        toggleGroup(group.id)
      }
      // Wait for DOM update then scroll
      nextTick(() => {
        const el = document.querySelector(`[data-session-id="${sessionId}"]`)
        if (el) {
          el.scrollIntoView({ block: 'center', behavior: 'smooth' })
        }
      })
      break
    }
  }
}

onBeforeUnmount(() => {
  if (deleteProjectTimer) clearTimeout(deleteProjectTimer)
})

// 监听全局session切换事件，自动滚动到目标session
onMounted(() => {
  window.addEventListener('vp-scroll-to-session', handleScrollToSessionEvent)
})

onBeforeUnmount(() => {
  window.removeEventListener('vp-scroll-to-session', handleScrollToSessionEvent)
})

function handleScrollToSessionEvent(event) {
  const { sessionId } = event.detail
  scrollToSession(sessionId)
}

defineExpose({ scrollToSession })
</script>

<template>
  <aside class="session-sidebar">
    <div class="sidebar-header">
      <button
        class="new-session-btn"
        @click="showCreateDialog = true"
        aria-label="Create new project"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="5" x2="12" y2="19"/>
          <line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        New Project
      </button>
      <button
        class="select-mode-btn"
        :class="{ active: selectionMode }"
        @click="toggleSelectionMode"
        :aria-label="selectionMode ? 'Exit selection mode' : 'Enter selection mode'"
        title="Select sessions"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 11 12 14 22 4"/>
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
        </svg>
      </button>
    </div>

    <div class="sidebar-list-wrapper">
      <div class="sidebar-list-fade sidebar-list-fade--top"></div>
      <div class="sidebar-list">
      <!-- Loading skeleton -->
      <template v-if="loading">
        <div v-for="n in 3" :key="'skeleton-' + n" class="skeleton-item">
          <div class="skeleton-main">
            <div class="skeleton-dot"></div>
            <div class="skeleton-text"></div>
          </div>
          <div class="skeleton-meta">
            <div class="skeleton-text-sm"></div>
          </div>
        </div>
      </template>

      <!-- Project groups -->
      <template v-else-if="projectGroups.length > 0">
        <div
          v-for="group in projectGroups"
          :key="group.id"
          class="project-group"
          :class="{
            'drag-over': dragOverProjectId === group.id,
            'dragging': dragProjectId === group.id,
          }"
          :draggable="group.id !== '__unassigned__'"
          @dragstart="onDragStart($event, group.id)"
          @dragover="onDragOver($event, group.id)"
          @dragleave="onDragLeave"
          @drop="onDrop($event, group.id)"
          @dragend="onDragEnd"
        >
          <div class="project-header" :title="group.name" @click="toggleGroup(group.id)">
              <svg
                class="collapse-arrow"
                :class="{ collapsed: isGroupCollapsed(group.id) }"
                width="10" height="10" viewBox="0 0 24 24"
                fill="none" stroke="currentColor"
                stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
              >
                <polyline points="6 9 12 15 18 9"/>
              </svg>
              <svg v-if="group.pinned" class="project-icon project-icon--pinned" width="12" height="12" viewBox="0 0 24 24" fill="var(--accent)" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <span class="project-name">{{ group.name }}</span>
              <span class="project-count">{{ group.sessions.length }}</span>
              <Transition name="confirm-swap" mode="out-in">
              <span v-if="deletingProject === group.id" key="confirm" class="project-delete-confirm" @click.stop>
                <button class="confirm-delete-all" @click.stop="confirmDeleteProject(group.id)" title="Delete project and all sessions">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                  All
                </button>
                <button class="confirm-select-sessions" @click.stop="enterProjectSessionSelect(group.id)" title="Select sessions to delete">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 11 12 14 22 4"/>
                    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                  </svg>
                  Pick
                </button>
                <button class="confirm-no" @click.stop="cancelDeleteProject">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"/>
                    <line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                </button>
              </span>
              <span v-else key="normal" class="project-actions">
                <button
                  v-if="group.id !== '__unassigned__'"
                  class="project-action-btn project-pin-btn"
                  :class="{ pinned: isProjectPinned(group.id) }"
                  @click.stop="toggleProjectPin(group.id)"
                  :aria-label="isProjectPinned(group.id) ? 'Unpin project' : 'Pin project'"
                  :title="isProjectPinned(group.id) ? 'Unpin' : 'Pin'"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="17" x2="12" y2="22"/>
                    <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z"/>
                  </svg>
                </button>
                <button
                  v-if="group.id !== '__unassigned__'"
                  class="project-action-btn project-clock-btn"
                  @click.stop="emit('open-scheduler', group.id)"
                  aria-label="Configure project clock"
                  title="Project clock"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/>
                    <polyline points="12 6 12 12 16 14"/>
                  </svg>
                  <span v-if="scheduleCount(group.id)" class="project-clock-badge">{{ scheduleCount(group.id) }}</span>
                </button>
                <button
                  v-if="group.id !== '__unassigned__'"
                  class="project-action-btn project-add-btn"
                  @click.stop="emit('create-in-project', group.id)"
                  aria-label="Create session in this project"
                  title="New session"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"/>
                    <line x1="5" y1="12" x2="19" y2="12"/>
                  </svg>
                </button>
                <button
                  v-if="group.id !== '__unassigned__'"
                  class="project-action-btn project-delete-btn"
                  @click.stop="requestDeleteProject(group.id)"
                  aria-label="Delete project"
                  title="Delete project"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                </button>
              </span>
              </Transition>
          </div>
          <div
              class="group-content"
              :class="{ collapsed: isGroupCollapsed(group.id) }"
              :ref="el => { if (el) groupContentRefs[group.id] = el }"
            >
            <SessionListItem
              v-for="session in group.sessions"
              :key="session.session_id"
              :data-session-id="session.session_id"
              :session="session"
              :active="session.session_id === currentSessionId"
              :selectable="selectionMode"
              :selected="selectedIds.has(session.session_id)"
              :pinned="isSessionPinned(session.session_id)"
              class="indented-session"
              @select="emit('select', $event)"
              @delete="emit('delete', $event)"
              @rename="emit('rename', $event)"
              @toggle-select="toggleSelect"
              @toggle-pin="toggleSessionPin"
            />
          </div>
          <!-- Separator after last pinned project (outside group-content so it stays visible when collapsed) -->
          <div v-if="group.isLastPinned" class="pinned-separator"></div>
        </div>
      </template>

      <!-- Empty state -->
      <div v-else class="empty-state">
        <div class="empty-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <p class="empty-text">No projects yet</p>
        <p class="empty-hint">Create a new project to get started</p>
      </div>
    </div>
      <div class="sidebar-list-fade sidebar-list-fade--bottom"></div>
    </div>

    <CreateSessionDialog
      :visible="showCreateDialog"
      @confirm="handleCreateConfirm"
      @cancel="handleCreateCancel"
    />

    <!-- Batch delete bar -->
    <Transition name="slide-up">
      <div v-if="selectionMode && selectedIds.size > 0" class="batch-bar">
        <span class="batch-count">{{ selectedIds.size }} selected</span>
        <button class="batch-delete-btn" @click="confirmBatchDelete">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          </svg>
          Delete
        </button>
      </div>
    </Transition>
  </aside>
</template>

<style scoped>
.session-sidebar {
  width: 260px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--glass-bg);
  border-right: 1px solid var(--glass-border);
  box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.03);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  flex-shrink: 0;
  transition: background var(--transition-base), border-color var(--transition-base), box-shadow var(--transition-base);
}

.sidebar-header {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 12px;
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass-bg);
  display: flex;
  gap: 8px;
  align-items: center;
  box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-xs);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.new-session-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: 1;
  min-height: 38px;
  padding: 8px 12px;
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--layer-glass);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition:
    border-color var(--transition-fast),
    color var(--transition-fast),
    background var(--transition-fast),
    box-shadow var(--transition-fast),
    transform var(--transition-fast);
}

.new-session-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-dim);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.new-session-btn:active {
  transform: translateY(0) scale(0.97);
  transition-duration: 100ms;
}

.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
  min-height: 0;
}

.sidebar-list-wrapper {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sidebar-list-fade {
  position: absolute;
  left: 0;
  right: 0;
  height: 32px;
  pointer-events: none;
  z-index: 1;
}

.sidebar-list-fade--top {
  top: 0;
  background: linear-gradient(to bottom, var(--glass-bg), transparent);
}

.sidebar-list-fade--bottom {
  bottom: 0;
  background: linear-gradient(to top, var(--glass-bg), transparent);
}

/* Project group */
.project-group {
  margin-bottom: 2px;
  padding-top: 4px;
  border-top: 1px solid var(--border-subtle);
  transition: opacity 0.2s;
}

.project-group:first-child {
  border-top: none;
  padding-top: 0;
}

.project-group.dragging {
  opacity: 0.5;
}

.project-group.drag-over {
  border-top: 2px solid var(--accent);
}

.group-content {
  overflow: hidden;
  transition: max-height 250ms cubic-bezier(0.4, 0, 0.2, 1), opacity 200ms cubic-bezier(0.4, 0, 0.2, 1);
}

.group-content.collapsed {
  max-height: 0 !important;
  opacity: 0;
}

.indented-session {
  padding-left: 24px;
}

.project-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 4px 8px 2px;
  padding: 8px 8px 6px;
  font-size: 12px;
  color: var(--text-secondary);
  letter-spacing: 0.2px;
  font-weight: 600;
  overflow: hidden;
  cursor: pointer;
  user-select: none;
  border-radius: var(--radius-md);
  transition: background var(--transition-fast), color var(--transition-fast);
}

.collapse-arrow {
  flex-shrink: 0;
  transition: transform 0.15s ease;
}

.collapse-arrow.collapsed {
  transform: rotate(-90deg);
}

.project-header:hover {
  background: var(--layer-glass);
  color: var(--text-primary);
}

.project-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-count {
  font-size: 10px;
  background: var(--layer-glass);
  border: 1px solid var(--glass-border);
  color: var(--text-muted);
  padding: 1px 7px;
  border-radius: 999px;
  flex-shrink: 0;
  font-weight: 600;
}

.project-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  position: relative;
  flex-shrink: 0;
  transition: opacity var(--transition-fast), width var(--transition-fast);
  padding: 0;
  opacity: 0;
  width: 0;
  overflow: hidden;
}

.project-header:hover .project-action-btn {
  opacity: 1;
  width: 18px;
}

.project-clock-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 13px;
  height: 13px;
  padding: 0 3px;
  border-radius: 999px;
  background: var(--accent);
  color: var(--text-on-accent);
  font-size: 9px;
  line-height: 13px;
  font-weight: 700;
}

.project-clock-btn:hover,
.project-add-btn:hover {
  color: var(--accent);
  background: var(--accent-dim);
}

.project-delete-btn:hover {
  color: var(--red);
  background: var(--red-dim);
}

.project-pin-btn {
  color: var(--text-muted);
}

.project-pin-btn:hover {
  color: var(--accent);
  background: var(--accent-dim);
}

.project-pin-btn.pinned {
  color: var(--accent);
}

.project-pin-btn.pinned:hover {
  color: var(--text-primary);
  background: var(--accent-dim);
}

/* Separator between pinned and unpinned projects */
.pinned-separator {
  height: 0;
  margin: 6px 0;
  border: none;
}

/* Project delete confirm */
.project-delete-confirm {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.project-actions {
  display: inline-flex;
  align-items: center;
  gap: 0;
}

.project-delete-confirm .confirm-delete-all,
.project-delete-confirm .confirm-select-sessions,
.project-delete-confirm .confirm-no {
  display: flex;
  align-items: center;
  gap: 3px;
  border: none;
  border-radius: var(--radius-sm);
  padding: 2px 8px;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.project-delete-confirm .confirm-delete-all {
  background: var(--red-dim);
  color: var(--red);
}

.project-delete-confirm .confirm-delete-all:hover {
  filter: brightness(1.3);
}

.project-delete-confirm .confirm-select-sessions {
  background: var(--accent-dim);
  color: var(--accent);
}

.project-delete-confirm .confirm-select-sessions:hover {
  filter: brightness(1.3);
}

.project-delete-confirm .confirm-no {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  padding: 2px 4px;
}

.project-delete-confirm .confirm-no:hover {
  background: var(--bg-hover);
}

/* Skeleton loading */
.skeleton-item {
  padding: 10px 12px;
  border-left: 3px solid transparent;
}

.skeleton-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.skeleton-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--bg-hover);
  animation: shimmer 1.5s ease-in-out infinite;
  background-image: linear-gradient(90deg, rgba(255,255,255,0) 0, rgba(255,255,255,0.05) 20%, rgba(255,255,255,0.1) 60%, rgba(255,255,255,0));
  background-size: 200% 100%;
}

.skeleton-text {
  height: 14px;
  width: 80px;
  border-radius: 3px;
  background: var(--bg-hover);
  animation: shimmer 1.5s ease-in-out infinite;
  animation-delay: 0.1s;
  background-image: linear-gradient(90deg, rgba(255,255,255,0) 0, rgba(255,255,255,0.05) 20%, rgba(255,255,255,0.1) 60%, rgba(255,255,255,0));
  background-size: 200% 100%;
}

.skeleton-meta {
  margin-top: 6px;
  padding-left: 16px;
}

.skeleton-text-sm {
  height: 10px;
  width: 100px;
  border-radius: 3px;
  background: var(--bg-hover);
  animation: shimmer 1.5s ease-in-out infinite;
  animation-delay: 0.2s;
  background-image: linear-gradient(90deg, rgba(255,255,255,0) 0, rgba(255,255,255,0.05) 20%, rgba(255,255,255,0.1) 60%, rgba(255,255,255,0));
  background-size: 200% 100%;
}

[data-theme="light"] .skeleton-dot,
[data-theme="light"] .skeleton-text,
[data-theme="light"] .skeleton-text-sm,
[data-theme="sepia"] .skeleton-dot,
[data-theme="sepia"] .skeleton-text,
[data-theme="sepia"] .skeleton-text-sm {
  background-image: linear-gradient(90deg, rgba(0,0,0,0) 0, rgba(0,0,0,0.02) 20%, rgba(0,0,0,0.04) 60%, rgba(0,0,0,0));
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
}

.empty-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
  background: var(--layer-active);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  opacity: 0.86;
  margin-bottom: 12px;
}

.empty-text {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.empty-hint {
  font-size: 11px;
  color: var(--text-muted);
}

/* Selection mode header */
.select-mode-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--layer-glass);
  color: var(--text-muted);
  cursor: pointer;
  flex-shrink: 0;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.select-mode-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-dim);
}

.select-mode-btn.active {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-dim);
}

/* Batch delete bar */
.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-top: 1px solid var(--glass-border);
  background: var(--glass-bg-strong);
  box-shadow: 0 -10px 28px rgba(0, 0, 0, 0.16);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.batch-count {
  font-size: 12px;
  color: var(--text-secondary);
  flex: 1;
  font-weight: 600;
}

.batch-delete-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--red-dim);
  color: var(--red);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.batch-delete-btn:hover {
  filter: brightness(1.2);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.batch-delete-btn:active {
  transform: translateY(0) scale(0.97);
  transition-duration: 100ms;
}

/* Slide up transition */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.2s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}

@media (max-width: 768px) {
  .session-sidebar {
    display: none;
  }
}

/* Confirm swap transition */
.confirm-swap-enter-active,
.confirm-swap-leave-active {
  transition: opacity 120ms cubic-bezier(0.4, 0, 0.2, 1);
}
.confirm-swap-enter-from,
.confirm-swap-leave-to {
  opacity: 0;
}
</style>
