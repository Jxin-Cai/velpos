<script setup>
import { ref, computed, reactive, watch, nextTick, onBeforeUnmount } from 'vue'
import { useProject } from '@entities/project'
import SessionListItem from './SessionListItem.vue'
import CreateSessionDialog from './CreateSessionDialog.vue'

const COLLAPSED_KEY = 'pf_collapsed_groups'
const PINNED_KEY = 'pf_pinned_projects'

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
})

const emit = defineEmits([
  'create',
  'select',
  'delete',
  'batch-delete',
  'rename',
  'create-in-project',
  'delete-project',
  'reorder-projects',
])

const { projects } = useProject()

const showCreateDialog = ref(false)

// Pinned projects management
const pinnedProjectIds = ref(new Set())

// Load pinned projects from localStorage on mount
try {
  const stored = localStorage.getItem(PINNED_KEY)
  if (stored) {
    pinnedProjectIds.value = new Set(JSON.parse(stored))
  }
} catch (e) {
  console.warn('Failed to load pinned projects:', e)
}

function isProjectPinned(projectId) {
  return pinnedProjectIds.value.has(projectId)
}

function toggleProjectPin(projectId) {
  const newSet = new Set(pinnedProjectIds.value)
  if (newSet.has(projectId)) {
    newSet.delete(projectId)
  } else {
    newSet.add(projectId)
  }
  pinnedProjectIds.value = newSet

  // Save to localStorage
  try {
    localStorage.setItem(PINNED_KEY, JSON.stringify([...newSet]))
  } catch (e) {
    console.warn('Failed to save pinned projects:', e)
  }
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
    next.delete(id)
    // Expand: set max-height to scrollHeight
    nextTick(() => {
      const el = groupContentRefs[id]
      if (el) el.style.maxHeight = el.scrollHeight + 'px'
    })
  } else {
    next.add(id)
    // Collapse: set max-height to 0 via CSS class
    const el = groupContentRefs[id]
    if (el) el.style.maxHeight = null
  }
  collapsedGroups.value = next
  localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...next]))
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

  // Sort sessions within each group: running first, then by updated_time descending
  for (const list of Object.values(sessionsByProject)) {
    list.sort((a, b) => {
      // Running sessions always come first
      const aRunning = a.status === 'running' ? 1 : 0
      const bRunning = b.status === 'running' ? 1 : 0
      if (aRunning !== bRunning) return bRunning - aRunning
      const timeA = a.updated_time ? new Date(a.updated_time).getTime() : 0
      const timeB = b.updated_time ? new Date(b.updated_time).getTime() : 0
      return timeB - timeA
    })
  }

  // Build ordered project groups (projects are already sorted by sort_order from backend)
  // Separate pinned and unpinned projects
  const pinnedGroups = []
  const unpinnedGroups = []

  for (const project of projects.value) {
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
            <template v-if="deletingProject === group.id">
              <span class="project-delete-confirm" @click.stop>
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
            </template>
            <template v-else>
              <svg
                class="collapse-arrow"
                :class="{ collapsed: isGroupCollapsed(group.id) }"
                width="10" height="10" viewBox="0 0 24 24"
                fill="none" stroke="currentColor"
                stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
              >
                <polyline points="6 9 12 15 18 9"/>
              </svg>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <span class="project-name">{{ group.name }}</span>
              <span class="project-count">{{ group.sessions.length }}</span>
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
            </template>
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
              class="indented-session"
              @select="emit('select', $event)"
              @delete="emit('delete', $event)"
              @rename="emit('rename', $event)"
              @toggle-select="toggleSelect"
            />
          </div>
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
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
  flex-shrink: 0;
  transition: background var(--transition-base), border-color var(--transition-base);
}

.sidebar-header {
  padding: 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 8px;
  align-items: center;
}

.new-session-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: 1;
  padding: 8px 12px;
  border: 1px dashed var(--border-active);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition:
    border-color var(--transition-fast),
    color var(--transition-fast),
    background var(--transition-fast),
    box-shadow var(--transition-fast),
    transform var(--transition-spring);
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
  transition-duration: 80ms;
}

.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

/* Project group */
.project-group {
  margin-bottom: 2px;
  transition: opacity 0.2s;
}

.project-group.dragging {
  opacity: 0.5;
}

.project-group.drag-over {
  border-top: 2px solid var(--accent);
}

.group-content {
  overflow: hidden;
  opacity: 1;
  transition: max-height 0.25s ease, opacity 0.2s ease;
}

.group-content:not(.collapsed) {
  max-height: none;
}

.group-content.collapsed {
  max-height: 0;
  opacity: 0;
}

.indented-session {
  padding-left: 24px;
}

.project-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px 6px;
  font-size: 12px;
  color: var(--text-secondary);
  letter-spacing: 0.2px;
  font-weight: 600;
  overflow: hidden;
  cursor: pointer;
  user-select: none;
}

.collapse-arrow {
  flex-shrink: 0;
  transition: transform 0.15s ease;
}

.collapse-arrow.collapsed {
  transform: rotate(-90deg);
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
  background: var(--accent-dim);
  color: var(--accent);
  padding: 1px 6px;
  border-radius: 8px;
  flex-shrink: 0;
  font-weight: 600;
}

.project-action-btn {
  display: none;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
  padding: 0;
}

.project-header:hover .project-action-btn {
  display: flex;
}

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
  display: flex;
}

.project-pin-btn.pinned:hover {
  color: var(--text-primary);
  background: var(--accent-dim);
}

/* Project delete confirm */
.project-delete-confirm {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
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
  color: var(--text-muted);
  opacity: 0.5;
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
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
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
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
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
  transition-duration: 80ms;
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
</style>
