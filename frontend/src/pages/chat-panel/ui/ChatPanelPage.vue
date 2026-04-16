<script setup>
import { ref, computed, inject, onMounted, onUnmounted, watch } from 'vue'
import { useSession, listModels } from '@entities/session'
import { useProject, getGitBranches, checkoutGitBranch } from '@entities/project'
import { MessageInput, useSendMessage } from '@features/send-message'
import { CancelButton, useCancelQuery } from '@features/cancel-query'
import { MessageList, ThinkingIndicator } from '@features/message-display'
import { ClearContextButton, useClearContext } from '@features/clear-context'
import { CommandPaletteButton, CommandPalettePopover, useCommandPalette } from '@features/command-palette'
import { PluginManagerDialog } from '@features/plugin-manager'
import { AgentDialog } from '@features/agent-manager'
import { MemoryButton, MemoryDialog } from '@features/memory-manager'
import { VoiceInputButton, VideoInputButton } from '@features/media-input'
import { ImButton, ImDialog, useImBinding } from '@features/im-binding'
import { openPath } from '@features/terminal'
import { useCompactContext } from '@features/compact-context'
import { useSessionStats } from '@features/send-message/model/useSessionStats'
import { TaskProgressPanel, useTaskProgress } from '@features/task-progress'

const { session, messages, status, queued, currentSessionId, queryHistory, setCurrentSessionId, updateSession } = useSession()
const { projects, updateProjectInList } = useProject()

const wsConnection = inject('wsConnection')

const isRunning = computed(() => status.value === 'running')
const debugMode = ref(localStorage.getItem('pf_debug_mode') === 'true')

// Current project for this session
const currentProject = computed(() => {
  const pid = session.value?.project_id
  if (!pid) return null
  return projects.value.find(p => p.id === pid) || null
})

function toggleDebug() {
  debugMode.value = !debugMode.value
  localStorage.setItem('pf_debug_mode', debugMode.value)
}

// Filter messages: when debug is off, hide tool_use blocks, tool_result messages, and system messages
// Exception: keep TodoWrite tool_use blocks — they render as visual progress
const displayMessages = computed(() => {
  if (debugMode.value) return messages.value
  return messages.value
    .filter(msg => msg.type !== 'tool_result' && msg.type !== 'system')
    .map(msg => {
      if (msg.type === 'assistant' && msg.content?.blocks) {
        const filtered = msg.content.blocks.filter(
          b => b.type !== 'tool_result'
            && (b.type !== 'tool_use' || (b.name === 'TodoWrite' && b.input?.todos))
        )
        if (filtered.length === 0) return null
        return { ...msg, content: { ...msg.content, blocks: filtered } }
      }
      return msg
    })
    .filter(Boolean)
})
const projectDir = computed(() => session.value?.project_dir || '')
const projectDirName = computed(() => {
  const dir = projectDir.value
  if (!dir) return ''
  return dir.split('/').filter(Boolean).pop() || dir
})

const { clearing, clearContext } = useClearContext()
const { commands, loading: cmdLoading, visible: cmdVisible, searchQuery, loadCommands, togglePanel, closePanel, invalidateCache: invalidateCmdCache } = useCommandPalette()

const messageInputRef = ref(null)

// Plugin dialog
const pluginDialogVisible = ref(false)

// Agent dialog
const agentDialogVisible = ref(false)
const currentAgentInfo = computed(() => currentProject.value?.agents?.current || null)

// Memory dialog
const memoryDialogVisible = ref(false)

// IM dialog
const imDialogVisible = ref(false)
const { isBoundForSession, hasChannels, boundChannelType, boundInstanceName, fetchChannels: fetchImChannels, fetchStatus: fetchImStatus } = useImBinding()

// Compact context
const { compacting, compactContext } = useCompactContext()

onMounted(async () => {
  try {
    const res = await listModels()
    availableModels.value = res || []
  } catch {
    // fallback to empty — user can still type model names
  }
  // Fetch available IM channels and binding status for current session
  fetchImChannels()
  if (currentSessionId.value) {
    fetchImStatus(currentSessionId.value)
  }
  // Listen for cancel-rewind events to restore prompt to input
  window.addEventListener('vp-cancel-rewind', handleCancelRewind)
})

onUnmounted(() => {
  window.removeEventListener('vp-cancel-rewind', handleCancelRewind)
})

function handleCancelRewind(e) {
  const prompt = e.detail?.prompt || ''
  if (prompt && messageInputRef.value) {
    messageInputRef.value.setInput(prompt)
  }
}

function handleCompact() {
  compactContext(currentSessionId.value)
}

// Fetch IM status and channels when session changes
watch(currentSessionId, (newId) => {
  if (newId) {
    fetchImStatus(newId)
    fetchImChannels()
    invalidateCmdCache()
  }
})

// Re-fetch channels when project plugins change
watch(() => currentProject.value?.plugins, () => {
  fetchImChannels()
}, { deep: true })

// Handle prompt-mode IM binding — send prompt via WS
function handleImPrompt(prompt) {
  useSendMessage(wsConnection.value).sendPrompt(prompt)
}

// History popover
const showHistory = ref(false)

function formatDuration(ms) {
  if (!ms) return '-'
  const s = (ms / 1000).toFixed(1)
  return `${s}s`
}

function formatTokens(n) {
  if (!n) return '0'
  return n.toLocaleString()
}

const totalUsage = computed(() => {
  // Context = last query's input_tokens (= current context window size, not cumulative)
  const context = session.value?.last_input_tokens || 0
  // Output = sum of all queries' output_tokens (total generated)
  let output = 0
  for (const q of queryHistory.value) {
    output += q.usage?.output_tokens || 0
  }
  return { context, output }
})

// Model switching — dynamic from backend
const showModelMenu = ref(false)
const currentModel = computed(() => session.value?.model || 'unknown')
const availableModels = ref([])


function getModelLabel(model) {
  const found = availableModels.value.find(m => m.value === model)
  if (found) return found.displayName || found.value
  // Derive short label from model id
  if (model.includes('sonnet')) return 'Sonnet'
  if (model.includes('opus')) return 'Opus'
  if (model.includes('haiku')) return 'Haiku'
  return model
}

function handleModelSelect(modelValue) {
  showModelMenu.value = false
  if (wsConnection.value) {
    wsConnection.value.send({ action: 'set_model', model: modelValue })
  }
}

// Permission mode switching
const showPermMenu = ref(false)
const currentPermMode = ref('bypassPermissions')

// Sync permission mode from backend when session changes
watch(session, (s) => {
  if (s?.permission_mode) {
    currentPermMode.value = s.permission_mode
  }
}, { immediate: true })
const permModes = [
  { value: 'default', label: 'Default' },
  { value: 'acceptEdits', label: 'Accept' },
  { value: 'plan', label: 'Plan' },
  { value: 'bypassPermissions', label: 'Bypass' },
]

function getPermLabel(value) {
  const found = permModes.find(m => m.value === value)
  return found ? found.label : value
}

function handlePermSelect(mode) {
  showPermMenu.value = false
  currentPermMode.value = mode
  if (wsConnection.value) {
    wsConnection.value.send({ action: 'set_permission_mode', mode })
  }
}

// Git branch switching
const showBranchMenu = ref(false)
const branchList = ref([])
const branchCurrent = ref('')
const branchLoading = ref(false)

// Sync branch from backend session data
watch(session, (s) => {
  if (s?.git_branch) {
    branchCurrent.value = s.git_branch
  } else {
    branchCurrent.value = ''
  }
}, { immediate: true })

async function handleBranchClick() {
  showBranchMenu.value = !showBranchMenu.value
  showModelMenu.value = false
  showPermMenu.value = false
  showHistory.value = false
  if (showBranchMenu.value && currentProject.value) {
    branchLoading.value = true
    try {
      const res = await getGitBranches(currentProject.value.id)
      branchList.value = res.branches || []
      branchCurrent.value = res.current || ''
    } catch {
      branchList.value = []
      branchCurrent.value = ''
    } finally {
      branchLoading.value = false
    }
  }
}

async function handleBranchSelect(branch) {
  if (!currentProject.value || branch === branchCurrent.value) {
    showBranchMenu.value = false
    return
  }
  try {
    const res = await checkoutGitBranch(currentProject.value.id, branch)
    branchCurrent.value = res.current || branch
    // Update session's git_branch so the chip label updates
    if (session.value) {
      updateSession({ git_branch: branchCurrent.value })
    }
  } catch (e) {
    console.error('Branch checkout failed:', e)
  }
  showBranchMenu.value = false
}

function handleSend(textOrData) {
  useSendMessage(wsConnection.value).sendPrompt(textOrData)
}

function handleCancel() {
  useCancelQuery(wsConnection.value).cancelQuery()
}

function handleClear() {
  clearContext(currentSessionId.value)
}

function handleCommandsClick() {
  if (projectDir.value) {
    loadCommands(projectDir.value)
  }
  togglePanel()
}

const LOCAL_COMMAND_HANDLERS = {
  clear: (ctx) => ctx.clearContext(ctx.currentSessionId),
}

function handleCommandSelect(cmd) {
  closePanel()
  if (cmd.type === 'local' || cmd.type === 'local-jsx') {
    const handler = LOCAL_COMMAND_HANDLERS[cmd.name]
    if (handler) {
      handler({ clearContext: () => clearContext(currentSessionId.value), currentSessionId: currentSessionId.value })
    }
    return
  }
  if (messageInputRef.value) {
    messageInputRef.value.setInput('/' + cmd.name + ' ')
  }
}

// Project copy menu
const showProjectCopyMenu = ref(false)
const copiedChip = ref('')  // 'session' or 'project-path' or 'project-name'

function copyToClipboard(text, chipName) {
  navigator.clipboard.writeText(text).then(() => {
    copiedChip.value = chipName
    setTimeout(() => { copiedChip.value = '' }, 1500)
  }).catch(() => {
    // Clipboard API not available or permission denied — ignore silently
  })
}

function copySessionId() {
  copyToClipboard(currentSessionId.value, 'session')
}

function copyProjectPath() {
  showProjectCopyMenu.value = false
  copyToClipboard(projectDir.value, 'project')
}

function copyProjectName() {
  showProjectCopyMenu.value = false
  copyToClipboard(projectDirName.value, 'project')
}

function openProjectDir() {
  showProjectCopyMenu.value = false
  openPath(projectDir.value)
}

// Close menus on click outside
function handleClickOutside() {
  showModelMenu.value = false
  showPermMenu.value = false
  showHistory.value = false
  showProjectCopyMenu.value = false
  showBranchMenu.value = false
  showTaskPanel.value = false
}

// Plugin management

// Session stats for bottom status bar
const { gitBranch, lastQueryDuration, contextUsage, toolStats, activeSubagents } = useSessionStats()
const { allTasks, taskCounts, hasActiveTasks, planTaskCounts, hasPlanTasks } = useTaskProgress()
const showTaskPanel = ref(false)

function formatDurationShort(ms) {
  if (!ms) return '-'
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(ms / 60000)
  const remainS = Math.round((ms % 60000) / 1000)
  return `${m}m${remainS}s`
}

const topTools = computed(() => toolStats.value.slice(0, 5))
const totalToolCalls = computed(() => toolStats.value.reduce((sum, t) => sum + t.count, 0))

// Context color: green < 70%, yellow 70-85%, red > 85% (aligned with claude-hud)
const contextColorClass = computed(() => {
  const p = contextUsage.value.percent
  if (p > 85) return 'danger'
  if (p > 70) return 'warning'
  return 'safe'
})

function formatMaxTokens(n) {
  if (!n) return ''
  if (n >= 1000000) return `${(n / 1000000).toFixed(0)}M`
  return `${Math.round(n / 1000)}k`
}

</script>

<template>
  <div class="chat-panel" @click="handleClickOutside">
    <MessageList :messages="displayMessages">
      <template #footer>
        <ThinkingIndicator :visible="isRunning" />
        <div v-if="queued && isRunning" class="queue-indicator">
          <span class="queue-dot"></span>
          Your message is queued — will run after current task
        </div>
        <CancelButton :visible="isRunning" @cancel="handleCancel" />
      </template>
    </MessageList>
    <div class="input-section">
      <CommandPalettePopover
        :visible="cmdVisible"
        :commands="commands"
        :loading="cmdLoading"
        :search-query="searchQuery"
        @update:search-query="searchQuery = $event"
        @select="handleCommandSelect"
        @close="closePanel"
      />
      <!-- Toolbar above input -->
      <div class="input-toolbar">
        <button
          class="toolbar-btn"
          :class="{ 'toolbar-btn--active': debugMode }"
          @click="toggleDebug"
          title="Toggle debug mode — show/hide tool calls and system messages"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 22c1.1 0 2-.9 2-2h-4a2 2 0 0 0 2 2z"/>
            <path d="M8 2v2"/>
            <path d="M16 2v2"/>
            <rect x="4" y="4" width="16" height="14" rx="2"/>
            <line x1="9" y1="9" x2="9.01" y2="9"/>
            <line x1="15" y1="9" x2="15.01" y2="9"/>
            <path d="M9.5 13a3.5 3.5 0 0 0 5 0"/>
          </svg>
          <span class="toolbar-btn-label">Debug</span>
        </button>
        <!-- Agent button -->
        <button
          class="toolbar-btn"
          :class="{ 'toolbar-btn--active': currentAgentInfo }"
          :disabled="!currentSessionId || !currentProject"
          @click="agentDialogVisible = true"
          :title="currentAgentInfo ? `Agent: ${currentAgentInfo.id}` : 'Select Agent'"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2a4 4 0 0 1 4 4v2H8V6a4 4 0 0 1 4-4z"/>
            <rect x="3" y="8" width="18" height="12" rx="2"/>
            <line x1="9" y1="13" x2="9.01" y2="13"/>
            <line x1="15" y1="13" x2="15.01" y2="13"/>
          </svg>
          <span class="toolbar-btn-label">{{ currentAgentInfo ? currentAgentInfo.id : 'Agent' }}</span>
        </button>
        <!-- Plugin management button -->
        <button
          class="toolbar-btn"
          :disabled="!currentSessionId"
          @click="pluginDialogVisible = true"
          title="Plugin management"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="4" y="4" width="16" height="16" rx="2" ry="2"/>
            <rect x="9" y="9" width="6" height="6"/>
            <line x1="9" y1="1" x2="9" y2="4"/>
            <line x1="15" y1="1" x2="15" y2="4"/>
            <line x1="9" y1="20" x2="9" y2="23"/>
            <line x1="15" y1="20" x2="15" y2="23"/>
            <line x1="20" y1="9" x2="23" y2="9"/>
            <line x1="20" y1="14" x2="23" y2="14"/>
            <line x1="1" y1="9" x2="4" y2="9"/>
            <line x1="1" y1="14" x2="4" y2="14"/>
          </svg>
          <span class="toolbar-btn-label">Plugin</span>
        </button>
        <MemoryButton
          :disabled="!currentSessionId || !projectDir"
          @click="memoryDialogVisible = true"
        />
        <VoiceInputButton :disabled="isRunning" @text="(t) => messageInputRef?.appendText(t)" />
        <VideoInputButton :disabled="isRunning" @capture="(f) => messageInputRef?.addImage(f.data, f.media_type)" />
        <CommandPaletteButton
          :disabled="isRunning || !currentSessionId"
          @click="handleCommandsClick"
        />
        <ClearContextButton
          :disabled="isRunning || !currentSessionId"
          :clearing="clearing"
          @clear="handleClear"
        />
        <!-- History button -->
        <div class="dropdown-wrapper" @click.stop>
          <button
            class="toolbar-btn"
            :disabled="!currentSessionId"
            @click="showHistory = !showHistory; showModelMenu = false; showPermMenu = false"
            title="Query history"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            <span class="toolbar-btn-label">History</span>
            <span v-if="queryHistory.length" class="toolbar-badge">{{ queryHistory.length }}</span>
          </button>
          <Transition name="dropdown-fade">
          <div v-if="showHistory" class="history-panel">
            <div class="history-header">
              <span class="history-title">Query History</span>
              <span class="history-total">
                Context: {{ formatTokens(totalUsage.context) }} / Output: {{ formatTokens(totalUsage.output) }}
              </span>
            </div>
            <div class="history-list">
              <div v-if="queryHistory.length === 0" class="history-empty">No queries yet</div>
              <div
                v-else
                v-for="(q, i) in [...queryHistory].reverse()"
                :key="i"
                class="history-item"
                :class="{ 'history-item--error': q.is_error }"
              >
                <div class="history-item-row">
                  <span class="history-index">#{{ queryHistory.length - i }}</span>
                  <span class="history-duration">{{ formatDuration(q.duration_ms) }}</span>
                  <span class="history-turns">{{ q.num_turns || 0 }} turns</span>
                  <span v-if="q.is_error" class="history-error-tag">Error</span>
                </div>
                <div class="history-item-tokens">
                  {{ formatTokens(q.usage?.input_tokens) }} in / {{ formatTokens(q.usage?.output_tokens) }} out
                </div>
              </div>
            </div>
          </div>
          </Transition>
        </div>
        <ImButton
          v-if="hasChannels"
          :disabled="!currentSessionId"
          :bound="isBoundForSession"
          :channel-type="boundChannelType"
          :instance-name="boundInstanceName"
          @click="imDialogVisible = true"
        />
      </div>
      <div class="input-row">
        <MessageInput ref="messageInputRef" :running="isRunning" @send="handleSend" />
      </div>
      <!-- Session Dashboard -->
      <div class="session-dashboard" v-if="currentSessionId">
        <!-- Context bar: full-width, clickable to compact -->
        <button
          class="context-bar-btn"
          :class="contextColorClass"
          :disabled="isRunning || compacting || !currentSessionId"
          @click.stop="handleCompact"
          :title="`Context: ${contextUsage.current.toLocaleString()} / ${contextUsage.max.toLocaleString()} tokens — Click to compact`"
        >
          <span class="context-bar-track">
            <span
              class="context-bar-fill"
              :style="{ width: contextUsage.percent + '%' }"
              :class="contextColorClass"
            ></span>
          </span>
          <span class="context-bar-label">
            <span class="context-pct">{{ contextUsage.percent }}%</span>
            <span class="context-tokens">{{ contextUsage.current.toLocaleString() }} / {{ formatMaxTokens(contextUsage.max) }}</span>
            <span v-if="compacting" class="context-compacting">compacting…</span>
          </span>
        </button>
        <div class="dash-row">
          <span class="dash-chip" v-if="lastQueryDuration" :title="'Last query: ' + formatDurationShort(lastQueryDuration)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            {{ formatDurationShort(lastQueryDuration) }}
          </span>
          <div class="dropdown-wrapper" v-if="projectDir" @click.stop>
            <button
              class="dash-chip dash-project"
              :class="{ 'dash-chip--copied': copiedChip === 'project' }"
              :title="projectDir"
              @click="showProjectCopyMenu = !showProjectCopyMenu; showModelMenu = false; showPermMenu = false; showHistory = false"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              {{ copiedChip === 'project' ? 'Copied!' : projectDirName }}
            </button>
            <Transition name="dropdown-fade">
            <div v-if="showProjectCopyMenu" class="dropdown-menu">
              <button class="dropdown-item" @click="openProjectDir">
                Open directory
              </button>
              <button class="dropdown-item" @click="copyProjectPath">
                Copy full path
              </button>
              <button class="dropdown-item" @click="copyProjectName">
                Copy project name
              </button>
            </div>
            </Transition>
          </div>
          <button
            class="dash-chip dash-session-id"
            :title="'Session: ' + currentSessionId + ' — Click to locate'"
            @click.stop="$emit('locate-session')"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="9" y1="3" x2="9" y2="21"/>
            </svg>
            {{ currentSessionId }}
          </button>
          <div class="dropdown-wrapper" @click.stop>
            <button
              class="dash-chip dash-model"
              :disabled="!currentSessionId"
              @click="showModelMenu = !showModelMenu; showPermMenu = false; showHistory = false"
              title="Switch model"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
              </svg>
              {{ getModelLabel(currentModel) }}
            </button>
            <Transition name="dropdown-fade">
            <div v-if="showModelMenu" class="dropdown-menu model-menu">
              <button
                v-for="m in availableModels"
                :key="m.value"
                class="dropdown-item"
                :class="{ active: m.value === currentModel }"
                @click="handleModelSelect(m.value)"
                :title="m.description || ''"
              >
                <span class="model-name">{{ m.displayName || m.value }}</span>
                <span v-if="m.description" class="model-desc">{{ m.description }}</span>
              </button>
              <div v-if="!availableModels.length" class="dropdown-empty">No models available</div>
            </div>
            </Transition>
          </div>
          <div class="dropdown-wrapper" @click.stop>
            <button
              class="dash-chip dash-branch"
              v-if="gitBranch || currentProject"
              :title="'Branch: ' + (branchCurrent || gitBranch || '(no branch)')"
              @click="handleBranchClick"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="6" y1="3" x2="6" y2="15"/>
                <circle cx="18" cy="6" r="3"/>
                <circle cx="6" cy="18" r="3"/>
                <path d="M18 9a9 9 0 0 1-9 9"/>
              </svg>
              {{ branchCurrent || gitBranch || 'branch' }}
            </button>
            <Transition name="dropdown-fade">
            <div v-if="showBranchMenu" class="dropdown-menu branch-menu">
              <div v-if="branchLoading" class="dropdown-empty">Loading...</div>
              <div v-else-if="!branchList.length" class="dropdown-empty">No branches</div>
              <template v-else>
                <button
                  v-for="b in branchList"
                  :key="b"
                  class="dropdown-item"
                  :class="{ active: b === branchCurrent }"
                  @click="handleBranchSelect(b)"
                >
                  {{ b }}
                </button>
              </template>
            </div>
            </Transition>
          </div>
          <div class="dropdown-wrapper" @click.stop>
            <button
              class="dash-chip dash-perm"
              :disabled="!currentSessionId"
              @click="showPermMenu = !showPermMenu; showModelMenu = false; showHistory = false"
              title="Permission mode"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
              {{ getPermLabel(currentPermMode) }}
            </button>
            <Transition name="dropdown-fade">
            <div v-if="showPermMenu" class="dropdown-menu">
              <button
                v-for="pm in permModes"
                :key="pm.value"
                class="dropdown-item"
                :class="{ active: pm.value === currentPermMode }"
                @click="handlePermSelect(pm.value)"
              >
                {{ pm.label }}
              </button>
            </div>
            </Transition>
          </div>
          <span class="dash-chip dash-tools" v-if="totalToolCalls > 0" :title="toolStats.map(t => t.name + ': ' + t.count).join(', ')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
            </svg>
            <template v-for="(tool, i) in topTools" :key="tool.name">
              <span v-if="i > 0" class="tool-sep">/</span>
              <span class="tool-name">{{ tool.name }}</span>
              <span class="tool-count">{{ tool.count }}</span>
            </template>
            <span v-if="toolStats.length > 5" class="tool-more">+{{ toolStats.length - 5 }}</span>
          </span>
          <template v-if="taskCounts.total > 0 || hasPlanTasks">
            <div class="dropdown-wrapper" @click.stop>
              <button
                class="dash-chip dash-agent"
                @click="showTaskPanel = !showTaskPanel"
                :title="`Plan: ${planTaskCounts.completed}/${planTaskCounts.total} | Tasks: ${taskCounts.running} running, ${taskCounts.completed} done`"
              >
                <span v-if="hasActiveTasks || planTaskCounts.in_progress > 0" class="agent-dot"></span>
                <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <template v-if="hasPlanTasks">Plan {{ planTaskCounts.completed }}/{{ planTaskCounts.total }}</template>
                <template v-else>Tasks {{ taskCounts.running > 0 ? taskCounts.running : taskCounts.total }}</template>
              </button>
              <TaskProgressPanel
                v-if="showTaskPanel"
                @close="showTaskPanel = false"
              />
            </div>
          </template>
        </div>
      </div>
    </div>

    <PluginManagerDialog
      :visible="pluginDialogVisible"
      :project-dir="projectDir"
      @close="pluginDialogVisible = false"
    />

    <AgentDialog
      :visible="agentDialogVisible"
      :project-id="currentProject?.id || ''"
      :current-agent="currentAgentInfo"
      :session-id="currentSessionId || ''"
      @close="agentDialogVisible = false"
      @update:project="updateProjectInList"
    />

    <MemoryDialog
      :visible="memoryDialogVisible"
      :project-dir="currentProject?.dir_path || ''"
      @close="memoryDialogVisible = false"
    />

    <ImDialog
      :visible="imDialogVisible"
      :session-id="currentSessionId"
      :project-id="currentProject?.id || ''"
      @close="imDialogVisible = false"
      @prompt="handleImPrompt"
      @navigate-session="(id) => { setCurrentSessionId(id); imDialogVisible = false }"
    />
  </div>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.queue-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 24px;
  font-size: 12px;
  color: var(--text-muted);
}

.queue-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: queue-pulse 1.5s ease-in-out infinite;
}

@keyframes queue-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

.input-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 16px 0;
}

.toolbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  padding: 3px 8px;
  height: 28px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  cursor: pointer;
  transition:
    color var(--transition-fast),
    background var(--transition-fast),
    border-color var(--transition-fast);
  font-family: var(--font-sans);
  white-space: nowrap;
}

.toolbar-btn:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-hover);
  border-color: var(--accent);
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toolbar-btn:active:not(:disabled) {
  transform: scale(0.96);
  transition-duration: 80ms;
}

.toolbar-btn--active {
  color: var(--accent);
  background: var(--accent-dim);
  border-color: var(--accent);
}

.toolbar-btn-label {
  font-weight: 500;
}

.toolbar-badge {
  font-size: 10px;
  background: var(--accent-dim);
  color: var(--accent);
  padding: 0 4px;
  border-radius: 6px;
  font-weight: 600;
  min-width: 16px;
  text-align: center;
}

.dropdown-wrapper {
  position: relative;
}

.dropdown-menu {
  position: absolute;
  bottom: calc(100% + 4px);
  left: 0;
  z-index: 50;
  min-width: 180px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lg);
  padding: 4px;
}

.dropdown-item {
  display: block;
  width: 100%;
  padding: 6px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-mono);
}

.dropdown-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.dropdown-item.active {
  color: var(--accent);
  background: var(--accent-dim);
}

.model-menu {
  min-width: 260px;
}

.model-menu .dropdown-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
}

.model-name {
  font-weight: 500;
  color: inherit;
}

.model-desc {
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-sans);
  white-space: normal;
  line-height: 1.3;
}

.dropdown-empty {
  padding: 12px;
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
}

.input-section {
  position: relative;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
  transition: background var(--transition-base), border-color var(--transition-base);
}

.input-row {
  padding-top: 8px;
}

/* History panel */
.history-panel {
  position: absolute;
  bottom: calc(100% + 4px);
  left: 0;
  z-index: 50;
  width: 340px;
  max-height: 360px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xl);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}

.history-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.history-total {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--accent);
}

.history-list {
  overflow-y: auto;
  padding: 4px;
}

.history-empty {
  padding: 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.history-item {
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  transition: background 0.1s;
}

.history-item:hover {
  background: var(--bg-hover);
}

.history-item--error {
  border-left: 2px solid var(--red);
}

.history-item-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}

.history-index {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text-muted);
  min-width: 24px;
}

.history-duration {
  font-family: var(--font-mono);
  color: var(--text-secondary);
}

.history-turns {
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.history-error-tag {
  font-size: 10px;
  padding: 0 5px;
  border-radius: 3px;
  color: var(--red);
  background: var(--red-dim);
  font-weight: 600;
}

.history-item-tokens {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  margin-top: 2px;
  padding-left: 34px;
}

/* Session Dashboard */
.session-dashboard {
  padding: 6px 16px 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

/* Context bar — wide, prominent, clickable */
.context-bar-btn {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 3px;
  background: transparent;
  border: none;
  padding: 4px 0 2px;
  cursor: pointer;
  transition: opacity var(--transition-fast);
  text-align: left;
}

.context-bar-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.context-bar-btn:disabled {
  cursor: default;
  opacity: 0.6;
}

.context-bar-track {
  display: block;
  width: 100%;
  height: 7px;
  background: var(--bg-hover);
  border-radius: 4px;
  overflow: hidden;
}

.context-bar-fill {
  display: block;
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease, background 0.4s ease;
}

.context-bar-fill.safe {
  background: var(--green);
}

.context-bar-fill.warning {
  background: var(--yellow);
}

.context-bar-fill.danger {
  background: var(--red);
}

.context-bar-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.context-pct {
  font-weight: 700;
  font-size: 11px;
}

.context-bar-btn.safe .context-pct { color: var(--green); }
.context-bar-btn.warning .context-pct { color: var(--yellow); }
.context-bar-btn.danger .context-pct { color: var(--red); }

.context-tokens {
  color: var(--text-muted);
  opacity: 0.8;
}

.context-compacting {
  color: var(--accent);
  animation: blink 1s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.dash-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.dash-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  border: none;
  cursor: default;
  white-space: nowrap;
  transition: all var(--transition-fast);
  height: 24px;
}

button.dash-chip {
  cursor: pointer;
}

button.dash-chip:hover:not([disabled]) {
  filter: brightness(1.2);
}

button.dash-chip:active:not([disabled]) {
  transform: scale(0.96);
  transition-duration: 80ms;
}

button.dash-chip[disabled] {
  opacity: 0.4;
  cursor: not-allowed;
}

.dash-project {
  color: var(--text-secondary);
}

.dash-session-id {
  color: var(--text-muted);
  font-size: 10px;
  opacity: 0.8;
  cursor: pointer;
}

.dash-chip--copied {
  color: var(--green) !important;
  border-color: var(--green) !important;
  transition: color 0.2s, border-color 0.2s;
}

.dash-model {
  color: var(--accent);
  background: var(--accent-dim);
}

.dash-branch {
  color: var(--purple);
  background: var(--purple-dim);
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dash-perm {
  color: var(--green);
  background: var(--green-dim);
}

.dash-tools {
  gap: 3px;
}

.tool-sep {
  color: var(--border);
  margin: 0 1px;
}

.tool-name {
  color: var(--text-secondary);
}

.tool-count {
  font-size: 10px;
  color: var(--accent);
  font-weight: 600;
}

.tool-more {
  color: var(--text-muted);
  font-size: 10px;
}

.dash-agent {
  color: var(--green);
  gap: 4px;
}

.agent-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--green);
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Touch device: expand hit area to 44x44px without changing visual size */
@media (pointer: coarse) {
  .toolbar-btn,
  button.dash-chip {
    position: relative;
  }
  .toolbar-btn::after,
  button.dash-chip::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    min-width: 44px;
    min-height: 44px;
    width: 100%;
    height: 100%;
  }
}

/* Mobile: enforce minimum font size */
@media (max-width: 768px) {
  .toolbar-btn-label {
    font-size: 12px;
  }
  .dash-chip {
    font-size: 12px;
  }
  .context-bar-label {
    font-size: 11px;
  }
  .context-pct {
    font-size: 12px;
  }
}
</style>
