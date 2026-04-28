<script setup>
import { ref, computed, inject, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys'
import { useDialogManager } from '@shared/lib/useDialogManager'
import { useSession, listModels, listSessionArtifacts, createSessionBranch, listSessionBranches, compareSessions, convergeSessionBranches } from '@entities/session'
import { useProject, getGitBranches, checkoutGitBranch } from '@entities/project'
import { MessageInput, useSendMessage } from '@features/send-message'
import { CancelButton, useCancelQuery } from '@features/cancel-query'
import { MessageList, ThinkingIndicator } from '@features/message-display'
import { ClearContextButton, useClearContext } from '@features/clear-context'
import { CommandPaletteButton, CommandPalettePopover, useCommandPalette } from '@features/command-palette'
import { PluginManagerDialog } from '@features/plugin-manager'
import { AgentDialog } from '@features/agent-manager'
import { MemoryButton, MemoryDialog } from '@features/memory-manager'
import { useVoiceInput, useVideoInput } from '@features/media-input'
import { ImButton, ImDialog, useImBinding } from '@features/im-binding'
import { openPath } from '@features/terminal'
import { useCompactContext } from '@features/compact-context'
import { useSessionStats } from '@features/send-message/model/useSessionStats'
import { EvolutionDialog } from '@features/evolution'
import { TaskProgressPanel, useTaskProgress } from '@features/task-progress'

const {
  session, messages, status, queued, waitingForSlot, recovery, currentSessionId,
  queryHistory, setCurrentSessionId, updateSession, setError, addSession,
} = useSession()
const { projects, updateProjectInList } = useProject()

const wsConnection = inject('wsConnection')

const isRunning = computed(() => status.value === 'running')
const recoveryPending = computed(() => recovery.value?.pending_request || null)
const recoveryQueued = computed(() => recovery.value?.queued_command || null)
const isCancelRequested = computed(() => Boolean(recovery.value?.cancel_requested))
const showRecoveryHint = computed(() => Boolean(recoveryPending.value || isCancelRequested.value || (recoveryQueued.value && !isRunning.value)))
const recoveryHintText = computed(() => {
  if (isCancelRequested.value) return 'Cancellation is being restored'
  if (recoveryPending.value?.interaction_type === 'permission') return 'Waiting for permission response'
  if (recoveryPending.value?.interaction_type === 'user_choice') return 'Waiting for your answer'
  if (recoveryQueued.value) return 'Queued prompt restored'
  return ''
})
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

const {
  commands,
  policyRows,
  loading: cmdLoading,
  visible: cmdVisible,
  searchQuery,
  loadCommands,
  updateCommandPolicy,
  togglePanel,
  closePanel,
  invalidateCache: invalidateCmdCache,
} = useCommandPalette()

const messageInputRef = ref(null)
const canceling = ref(false)
const showMediaMenu = ref(false)
const videoEl = ref(null)
const showVideoPreview = ref(false)
const videoPreviewPosition = ref({ x: 0, y: 0 })
const videoDragState = ref(null)
const {
  isRecording: isVoiceRecording,
  supported: voiceSupported,
  stopRecording: stopVoiceRecording,
  toggle: toggleVoiceInput,
} = useVoiceInput()
const {
  isCapturing: isVideoCapturing,
  supported: videoSupported,
  startCapture,
  stopCapture,
  captureFrame,
} = useVideoInput()

// Plugin dialog
const pluginDialogVisible = ref(false)

// Agent dialog
const agentDialogVisible = ref(false)
const currentAgentInfo = computed(() => currentProject.value?.agents?.current || null)

// Memory dialog
const memoryDialogVisible = ref(false)

// Evolution dialog
const evolutionDialogVisible = ref(false)

// IM dialog
const imDialogVisible = ref(false)
const { isBoundForSession, hasChannels, boundChannelType, boundInstanceName, fetchChannels: fetchImChannels, fetchStatus: fetchImStatus } = useImBinding()

// 使用全局弹窗管理器
const { useDialog } = useDialogManager()

// 注册所有弹窗到全局管理器
useDialog('plugin-manager', pluginDialogVisible)
useDialog('agent-manager', agentDialogVisible)
useDialog('memory-manager', memoryDialogVisible)
useDialog('evolution', evolutionDialogVisible)
useDialog('im-binding', imDialogVisible)
useDialog('command-palette', cmdVisible)

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
})

onUnmounted(() => {
  window.removeEventListener('vp-dialog-open', handleDialogOpen)
  window.removeEventListener('vp-debug-toggle', handleDebugToggle)
  window.removeEventListener('vp-voice-toggle', handleVoiceToggle)
  window.removeEventListener('vp-camera-toggle', handleCameraToggle)
  window.removeEventListener('vp-clear-context', handleClearContext)
  window.removeEventListener('pointermove', handleVideoDragMove)
  window.removeEventListener('pointerup', stopVideoDrag)
  stopVoiceRecording()
  stopCapture()
})

// 监听全局快捷键触发的弹窗打开事件
function handleDialogOpen(e) {
  const dialog = e.detail?.dialog
  switch (dialog) {
    case 'agent-manager':
      agentDialogVisible.value = true
      break
    case 'plugin-manager':
      pluginDialogVisible.value = true
      break
    case 'memory-manager':
      memoryDialogVisible.value = true
      break
    case 'evolution':
      evolutionDialogVisible.value = true
      break
    case 'command-palette':
      cmdVisible.value = true
      break
    case 'history':
      showHistory.value = true
      break
    case 'im-binding':
      imDialogVisible.value = true
      break
  }
}

// 监听 debug 模式切换
function handleDebugToggle(e) {
  debugMode.value = e.detail?.enabled ?? false
}

// 监听 voice 切换
function handleVoiceToggle() {
  handleMediaVoice()
}

async function handleCameraToggle() {
  await handleMediaVideo()
}

// 监听 clear context
function handleClearContext() {
  if (!currentSessionId.value) {
    setError('No active session to clear context')
    return
  }
  compactContext(currentSessionId.value)
}

// 注册全局事件监听
window.addEventListener('vp-dialog-open', handleDialogOpen)
window.addEventListener('vp-debug-toggle', handleDebugToggle)
window.addEventListener('vp-voice-toggle', handleVoiceToggle)
window.addEventListener('vp-camera-toggle', handleCameraToggle)
window.addEventListener('vp-clear-context', handleClearContext)

function handleCompact() {
  compactContext(currentSessionId.value)
}

// Fetch IM status and channels when session changes
watch(currentSessionId, (newId) => {
  canceling.value = false
  if (newId) {
    fetchImStatus(newId)
    fetchImChannels()
    invalidateCmdCache()
    showArtifacts.value = false
    artifacts.value = []
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
const showArtifacts = ref(false)
const artifacts = ref([])
const artifactLoading = ref(false)
useDialog('history', showHistory)

async function handleArtifactsClick() {
  showArtifacts.value = !showArtifacts.value
  showHistory.value = false
  showModelMenu.value = false
  showPermMenu.value = false
  if (!showArtifacts.value || !currentSessionId.value) return
  artifactLoading.value = true
  try {
    const res = await listSessionArtifacts(currentSessionId.value)
    artifacts.value = res?.artifacts || []
  } catch {
    artifacts.value = []
  } finally {
    artifactLoading.value = false
  }
}

function handleArtifactOpen(path) {
  openPath(path)
  showArtifacts.value = false
}

function formatDuration(ms) {
  if (!ms) return '-'
  const s = (ms / 1000).toFixed(1)
  return `${s}s`
}

function formatTokens(n) {
  const value = Number(n) || 0
  return `${(value / 1000).toFixed(2)}k`
}

function formatCacheHit(usage) {
  const input = Number(usage?.input_tokens) || 0
  const cacheRead = Number(usage?.cache_read_input_tokens) || 0
  if (input <= 0) return '0.00%'
  return `${((cacheRead / input) * 100).toFixed(2)}%`
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

// Get color class for permission mode (matching CC CLI colors)
function getPermColorClass(value) {
  switch (value) {
    case 'acceptEdits': return 'perm-purple'
    case 'plan': return 'perm-green'
    case 'bypassPermissions': return 'perm-red'
    default: return 'perm-gray'
  }
}

function handlePermSelect(mode) {
  showPermMenu.value = false
  currentPermMode.value = mode
  if (wsConnection.value) {
    wsConnection.value.send({ action: 'set_permission_mode', mode })
  }
}

// Cycle through permission modes with Shift+Tab
function cyclePermissionMode() {
  const currentIndex = permModes.findIndex(m => m.value === currentPermMode.value)
  const nextIndex = (currentIndex + 1) % permModes.length
  const nextMode = permModes[nextIndex].value
  handlePermSelect(nextMode)
}

// Global shortcut for cycling permission modes
useGlobalHotkeys({
  keys: 'Shift+Tab',
  handler: (event) => {
    cyclePermissionMode()
    return false // Prevent default behavior
  },
  priority: 50
})

// ESC to close panels/popovers
useGlobalHotkeys({
  keys: 'Escape',
  handler: (event) => {
    // 关闭所有打开的面板和菜单
    if (showHistory.value) {
      showHistory.value = false
      return false
    }
    if (showModelMenu.value) {
      showModelMenu.value = false
      return false
    }
    if (showPermMenu.value) {
      showPermMenu.value = false
      return false
    }
    if (showBranchMenu.value) {
      showBranchMenu.value = false
      return false
    }
    if (showProjectCopyMenu.value) {
      showProjectCopyMenu.value = false
      return false
    }
    // 让事件继续传播，可能需要关闭其他弹窗或取消查询
    return true
  },
  priority: 10 // 高于全局拦截器的优先级
})

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

watch(isRunning, (running) => {
  if (!running) canceling.value = false
})

function handleCancel() {
  if (canceling.value || !isRunning.value) return
  const sent = useCancelQuery(wsConnection.value).cancelQuery()
  if (sent) {
    canceling.value = true
  } else {
    setError('Not connected')
  }
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

function handleCommandPolicyChange(row, patch) {
  updateCommandPolicy(projectDir.value, row, patch)
}

const showMultiSessionDialog = ref(false)
const multiSessionIndex = ref(0)
const multiSessionName = ref('')
const multiSessionCount = ref(2)
const multiSessionWorktree = ref(false)
const parallelBranches = ref([])
const parallelBranchLoading = ref(false)
const compareResult = ref(null)
const showCompareResult = ref(false)
const convergingBranchId = ref('')

const multiSessionCandidates = computed(() => messages.value.map((message, index) => ({
  index,
  type: message.type || 'message',
  preview: messagePreview(message),
})))
const selectedMultiSessionCandidate = computed(() => {
  return multiSessionCandidates.value.find(item => item.index === multiSessionIndex.value) || null
})
const parallelBranchCount = computed(() => parallelBranches.value.length)

function messagePreview(message) {
  const raw = typeof message.content === 'string'
    ? message.content
    : JSON.stringify(message.content || '')
  return raw.replace(/\s+/g, ' ').slice(0, 120) || '(empty message)'
}

async function loadParallelBranches() {
  if (!currentSessionId.value) return
  parallelBranchLoading.value = true
  try {
    const data = await listSessionBranches(currentSessionId.value)
    parallelBranches.value = data.branches || []
  } catch {
    parallelBranches.value = []
  } finally {
    parallelBranchLoading.value = false
  }
}

function branchDisplayName(branch) {
  return branch.name || branch.branch_session_id
}

async function handleKeepBranch(branch) {
  if (!branch?.branch_session_id || !currentSessionId.value) return
  const message = branch.worktree_enabled
    ? '保留该 worktree 会话会把已提交内容 merge 回主干；若有未提交变更会失败并保留现场。继续？'
    : '保留该会话会删除其他并行会话。继续？'
  if (!window.confirm(message)) return
  convergingBranchId.value = branch.branch_session_id
  try {
    await convergeSessionBranches(currentSessionId.value, branch.branch_session_id)
    await loadParallelBranches()
    setCurrentSessionId(branch.branch_session_id)
    showMultiSessionDialog.value = false
  } catch (e) {
    setError(e.message || 'Failed to converge sessions')
  } finally {
    convergingBranchId.value = ''
  }
}

async function compareWithBranch(branch) {
  if (!branch?.branch_session_id || branch.branch_session_id === currentSessionId.value) return
  try {
    compareResult.value = await compareSessions(currentSessionId.value, branch.branch_session_id)
    showCompareResult.value = true
  } catch (e) {
    setError(e.message || 'Failed to compare sessions')
  }
}

async function openMultiSessionDialog() {
  if (!currentSessionId.value || messages.value.length === 0) return
  multiSessionIndex.value = messages.value.length - 1
  multiSessionName.value = session.value?.name || currentSessionId.value
  multiSessionCount.value = 2
  multiSessionWorktree.value = false
  await loadParallelBranches()
  showMultiSessionDialog.value = true
}

async function handleBranchSession() {
  if (!currentSessionId.value || messages.value.length === 0) return
  try {
    const data = await createSessionBranch(
      currentSessionId.value,
      multiSessionIndex.value,
      multiSessionName.value,
      multiSessionCount.value,
      multiSessionWorktree.value,
    )
    const createdSessions = data.sessions || (data.session ? [data.session] : [])
    for (const item of createdSessions) {
      addSession(item)
    }
    if (createdSessions.length > 0) {
      setCurrentSessionId(createdSessions[0].session_id)
      showMultiSessionDialog.value = false
    }
  } catch (e) {
    setError(e.message || 'Failed to create multi-session')
  }
}

function closeCompareResult() {
  showCompareResult.value = false
  compareResult.value = null
}

function handleAnalyzeCompare() {
  if (!compareResult.value?.analysis_prompt) return
  handleSend(compareResult.value.analysis_prompt)
  closeCompareResult()
}

function handleMediaVoice() {
  showMediaMenu.value = false
  toggleVoiceInput((text) => messageInputRef.value?.appendText(text))
}

function resetVideoPreviewPosition() {
  videoPreviewPosition.value = {
    x: Math.max(window.innerWidth - 284, 16),
    y: Math.max(window.innerHeight - 260, 16),
  }
}

function startVideoDrag(event) {
  videoDragState.value = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originX: videoPreviewPosition.value.x,
    originY: videoPreviewPosition.value.y,
  }
  event.currentTarget.setPointerCapture?.(event.pointerId)
  window.addEventListener('pointermove', handleVideoDragMove)
  window.addEventListener('pointerup', stopVideoDrag)
}

function handleVideoDragMove(event) {
  const state = videoDragState.value
  if (!state) return
  const nextX = state.originX + event.clientX - state.startX
  const nextY = state.originY + event.clientY - state.startY
  videoPreviewPosition.value = {
    x: Math.min(Math.max(nextX, 8), window.innerWidth - 260),
    y: Math.min(Math.max(nextY, 8), window.innerHeight - 230),
  }
}

function stopVideoDrag() {
  videoDragState.value = null
  window.removeEventListener('pointermove', handleVideoDragMove)
  window.removeEventListener('pointerup', stopVideoDrag)
}

async function handleMediaVideo() {
  showMediaMenu.value = false
  if (isVideoCapturing.value) {
    stopCapture()
    showVideoPreview.value = false
    return
  }
  const stream = await startCapture()
  if (stream) {
    resetVideoPreviewPosition()
    showVideoPreview.value = true
    await nextTick()
    if (videoEl.value) videoEl.value.srcObject = stream
  }
}

function handleVideoCapture() {
  const frame = captureFrame(videoEl.value)
  if (frame) {
    messageInputRef.value?.addImage(frame.data, frame.media_type)
  }
}

function handleEvolutionDraftCreated() {
  evolutionDialogVisible.value = false
  memoryDialogVisible.value = true
  window.dispatchEvent(new CustomEvent('vp-memory-refresh'))
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
  showMediaMenu.value = false
  showTaskPanel.value = false
  showArtifacts.value = false
}

// Plugin management

// Session stats for bottom status bar
const { gitBranch, lastQueryDuration, contextUsage, toolStats, activeSubagents, usageSummary, projectUsageSummary } = useSessionStats()
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

function formatCost(value) {
  const n = Number(value || 0)
  if (n < 0.01) return `$${n.toFixed(4)}`
  return `$${n.toFixed(2)}`
}

</script>

<template>
  <div class="chat-panel" @click="handleClickOutside">
    <MessageList :messages="displayMessages">
      <template #footer>
        <ThinkingIndicator :visible="isRunning" />
        <div v-if="showRecoveryHint" class="recovery-indicator">
          <span class="recovery-badge">Recovered</span>
          <span>{{ recoveryHintText }}</span>
        </div>
        <div v-if="waitingForSlot" class="queue-indicator">
          <span class="queue-dot"></span>
          Waiting for an available execution slot
        </div>
        <div v-if="queued && isRunning" class="queue-indicator">
          <span class="queue-dot"></span>
          Your message is queued — will run after current task
        </div>
        <CancelButton :visible="isRunning" :pending="canceling || isCancelRequested" @cancel="handleCancel" />
      </template>
    </MessageList>
    <div class="input-section">
      <CommandPalettePopover
        :visible="cmdVisible"
        :commands="commands"
        :policy-rows="policyRows"
        :loading="cmdLoading"
        :search-query="searchQuery"
        @update:search-query="searchQuery = $event"
        @select="handleCommandSelect"
        @policy-change="handleCommandPolicyChange"
        @close="closePanel"
      />
      <!-- Toolbar above input -->
      <div class="input-toolbar">
        <!-- Group 1: Debug -->
        <div class="toolbar-group">
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
        </div>
        <!-- Group 2: Configuration -->
        <div class="toolbar-group">
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
        <button
          class="toolbar-btn multi-session-trigger"
          :disabled="isRunning || !currentSessionId || messages.length === 0"
          @click="openMultiSessionDialog"
          title="Create a new session from selected context"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="6" cy="6" r="3"/>
            <circle cx="18" cy="6" r="3"/>
            <circle cx="12" cy="18" r="3"/>
            <path d="M8.5 8.5 11 15"/>
            <path d="M15.5 8.5 13 15"/>
          </svg>
          <span class="toolbar-btn-label">Multi-session</span>
          <span v-if="parallelBranchCount" class="toolbar-badge multi-session-badge">{{ parallelBranchCount }}</span>
        </button>
        </div>
        <!-- Group 3: Actions -->
        <div class="toolbar-group">
        <div class="dropdown-wrapper" @click.stop>
          <button
            class="toolbar-btn"
            :class="{ 'toolbar-btn--active': isVoiceRecording || isVideoCapturing }"
            :disabled="isRunning || (!voiceSupported && !videoSupported)"
            @click="showMediaMenu = !showMediaMenu"
            title="Media input"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 1a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v1a7 7 0 0 1-14 0v-1"/>
              <path d="M21 8l-5 4 5 4V8z"/>
            </svg>
            <span class="toolbar-btn-label">Media</span>
          </button>
          <Transition name="dropdown-fade">
          <div v-if="showMediaMenu" class="dropdown-menu media-menu">
            <button class="dropdown-item media-item" :disabled="!voiceSupported" @click="handleMediaVoice">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" y1="19" x2="12" y2="23"/>
              </svg>
              <span>{{ isVoiceRecording ? 'Stop voice' : 'Voice' }}</span>
            </button>
            <button class="dropdown-item media-item" :disabled="!videoSupported" @click="handleMediaVideo">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="23 7 16 12 23 17 23 7"/>
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
              </svg>
              <span>{{ isVideoCapturing ? 'Close video' : 'Video' }}</span>
            </button>
          </div>
          </Transition>
          <div
            v-if="showVideoPreview && isVideoCapturing"
            class="video-preview-popup"
            :style="{ left: videoPreviewPosition.x + 'px', top: videoPreviewPosition.y + 'px' }"
          >
            <div class="video-preview-header" @pointerdown="startVideoDrag">
              <span>Video</span>
              <button @click.stop="handleMediaVideo" title="Close video">×</button>
            </div>
            <video ref="videoEl" autoplay muted playsinline class="video-preview"></video>
            <button class="capture-btn" @click="handleVideoCapture" title="Capture frame">
              Capture
            </button>
          </div>
        </div>
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
            <div class="history-header-main">
              <span class="history-title">Query History</span>
              <span class="history-total">
                Context: {{ formatTokens(totalUsage.context) }} / Output: {{ formatTokens(totalUsage.output) }}
              </span>
            </div>
            <div v-if="usageSummary || projectUsageSummary" class="history-usage-row">
              <span v-if="usageSummary" class="history-usage-chip">Session {{ (usageSummary.total_tokens || 0).toLocaleString() }} tok</span>
              <span v-if="projectUsageSummary" class="history-usage-chip">Today {{ formatCost(projectUsageSummary.estimated_cost_usd) }}</span>
            </div>
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
                  <span>Input {{ formatTokens(q.usage?.input_tokens) }}</span>
                  <span>Output {{ formatTokens(q.usage?.output_tokens) }}</span>
                  <span>Cache hit {{ formatCacheHit(q.usage) }}</span>
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
            <span class="context-track-label">
              {{ formatMaxTokens(contextUsage.max) }}<span v-if="compacting" class="context-compacting"> · compacting…</span>
            </span>
          </span>
          <span class="context-pct">{{ contextUsage.percent }}%</span>
        </button>
        <div class="dash-row">
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
              :class="[getPermColorClass(currentPermMode)]"
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
                :class="[getPermColorClass(pm.value), { active: pm.value === currentPermMode }]"
                @click="handlePermSelect(pm.value)"
              >
                {{ pm.label }}
              </button>
            </div>
            </Transition>
          </div>
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
              <template v-else-if="taskCounts.total > 0">Tasks {{ taskCounts.running > 0 ? taskCounts.running : taskCounts.total }}</template>
              <template v-else>Plan</template>
            </button>
            <TaskProgressPanel
              v-if="showTaskPanel"
              @close="showTaskPanel = false"
            />
          </div>
          <div class="dropdown-wrapper" @click.stop>
            <button
              class="dash-chip dash-artifacts"
              :disabled="!currentSessionId"
              @click="handleArtifactsClick"
              title="Session artifacts"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                <line x1="12" y1="22.08" x2="12" y2="12"/>
              </svg>
              Artifacts
              <span v-if="artifacts.length" class="tool-count">{{ artifacts.length }}</span>
            </button>
            <Transition name="dropdown-fade">
            <div v-if="showArtifacts" class="artifact-panel">
              <div class="artifact-header">
                <span class="history-title">Artifacts</span>
              </div>
              <div class="artifact-list">
                <div v-if="artifactLoading" class="dropdown-empty">Loading...</div>
                <div v-else-if="artifacts.length === 0" class="dropdown-empty">No artifacts found</div>
                <button
                  v-else
                  v-for="artifact in artifacts"
                  :key="artifact.id"
                  class="artifact-item"
                  :title="artifact.path"
                  @click="handleArtifactOpen(artifact.path)"
                >
                  <span class="artifact-name">{{ artifact.label }}</span>
                  <span class="artifact-path">{{ artifact.path }}</span>
                </button>
              </div>
            </div>
            </Transition>
          </div>
        </div>
        <div v-if="lastQueryDuration || totalToolCalls > 0 || (projectUsageSummary?.budget_status?.state && projectUsageSummary.budget_status.state !== 'none')" class="dash-row tool-summary-row">
          <span class="dash-chip dash-last-query" v-if="lastQueryDuration" :title="'Last query: ' + formatDurationShort(lastQueryDuration)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            Last {{ formatDurationShort(lastQueryDuration) }}
          </span>
          <span class="dash-chip dash-budget" v-if="projectUsageSummary?.budget_status?.state && projectUsageSummary.budget_status.state !== 'none'" :class="'budget-' + projectUsageSummary.budget_status.state">
            Budget {{ projectUsageSummary.budget_status.state }}
          </span>
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
        </div>
      </div>
    </div>

    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showMultiSessionDialog" class="multi-session-overlay" @click.self="showMultiSessionDialog = false">
          <div class="multi-session-dialog" role="dialog" aria-modal="true" aria-labelledby="multi-session-title">
            <div class="multi-session-header">
              <div>
                <span class="multi-session-kicker">Parallel exploration</span>
                <h3 id="multi-session-title">多会话分支</h3>
                <p>从指定消息复制上下文，快速创建并行会话用于方案探索、对比和收敛。</p>
              </div>
              <button class="close-btn" type="button" aria-label="Close multi-session dialog" @click="showMultiSessionDialog = false">×</button>
            </div>
            <div class="multi-session-body">
              <section class="multi-session-card multi-session-card--setup">
                <div class="multi-session-card-title">
                  <span>01</span>
                  <div>
                    <strong>创建策略</strong>
                    <small>{{ multiSessionWorktree ? '每个会话使用独立 worktree' : '复用当前项目目录' }}</small>
                  </div>
                </div>
                <label class="field-label" for="multi-session-name">Session name prefix</label>
                <input id="multi-session-name" v-model="multiSessionName" class="multi-session-input" placeholder="Session name prefix" />
                <div class="multi-session-options">
                  <label>
                    <span>Parallel sessions</span>
                    <input v-model.number="multiSessionCount" type="number" min="1" max="8" />
                  </label>
                  <label class="checkbox-field multi-session-toggle">
                    <input v-model="multiSessionWorktree" type="checkbox" />
                    <span>Use worktree isolation</span>
                  </label>
                </div>
              </section>

              <section class="multi-session-card multi-session-card--context">
                <div class="multi-session-card-title">
                  <span>02</span>
                  <div>
                    <strong>上下文截点</strong>
                    <small v-if="selectedMultiSessionCandidate">复制到 #{{ selectedMultiSessionCandidate.index + 1 }} · {{ selectedMultiSessionCandidate.type }}</small>
                    <small v-else>请选择一个消息截点</small>
                  </div>
                </div>
                <div v-if="selectedMultiSessionCandidate" class="selected-context-preview">
                  {{ selectedMultiSessionCandidate.preview }}
                </div>
                <div class="message-choice-list">
                  <button
                    v-for="candidate in multiSessionCandidates"
                    :key="candidate.index"
                    type="button"
                    class="message-choice"
                    :class="{ active: multiSessionIndex === candidate.index }"
                    :aria-pressed="multiSessionIndex === candidate.index"
                    @click="multiSessionIndex = candidate.index"
                  >
                    <span class="message-choice-index">#{{ candidate.index + 1 }}</span>
                    <span class="message-choice-type">{{ candidate.type }}</span>
                    <span class="message-choice-preview">{{ candidate.preview }}</span>
                  </button>
                </div>
              </section>

              <section class="multi-session-card multi-session-card--branches">
                <div class="multi-session-card-title">
                  <span>03</span>
                  <div>
                    <strong>并行分支</strong>
                    <small>{{ parallelBranchCount }} branch{{ parallelBranchCount === 1 ? '' : 'es' }} available</small>
                  </div>
                </div>
                <div class="parallel-branch-list">
                  <div v-if="parallelBranchLoading" class="parallel-empty">Loading branches...</div>
                  <div v-else-if="parallelBranches.length === 0" class="parallel-empty">No parallel branches yet</div>
                  <template v-else>
                    <div
                      v-for="branch in parallelBranches"
                      :key="branch.id"
                      class="parallel-branch-item"
                      :class="{ active: branch.branch_session_id === currentSessionId }"
                    >
                      <button
                        class="parallel-branch-main"
                        type="button"
                        :disabled="branch.branch_session_id === currentSessionId"
                        @click="compareWithBranch(branch)"
                      >
                        <span>{{ branchDisplayName(branch) }}</span>
                        <small>{{ branch.worktree_enabled ? 'worktree isolation' : 'shared directory' }}</small>
                      </button>
                      <button
                        class="parallel-keep-btn"
                        type="button"
                        :disabled="!!convergingBranchId"
                        @click="handleKeepBranch(branch)"
                      >
                        {{ convergingBranchId === branch.branch_session_id ? 'Keeping...' : 'Keep' }}
                      </button>
                    </div>
                  </template>
                </div>
              </section>
            </div>
            <div class="multi-session-footer">
              <button class="secondary-btn" type="button" @click="showMultiSessionDialog = false">Cancel</button>
              <button class="primary-btn" type="button" :disabled="isRunning" @click="handleBranchSession">Create {{ multiSessionCount }} session{{ multiSessionCount === 1 ? '' : 's' }}</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="showCompareResult" class="multi-session-overlay" @click.self="closeCompareResult">
          <div class="compare-dialog">
            <div class="multi-session-header">
              <div>
                <h3>Compare Sessions</h3>
                <p>Common prefix and diverged message counts.</p>
              </div>
              <button class="close-btn" @click="closeCompareResult">×</button>
            </div>
            <div v-if="compareResult" class="compare-grid">
              <div><strong>{{ compareResult.common_prefix_count }}</strong><span>Common</span></div>
              <div><strong>{{ compareResult.left_only_count }}</strong><span>Current only</span></div>
              <div><strong>{{ compareResult.right_only_count }}</strong><span>Other only</span></div>
            </div>
            <div v-if="compareResult?.code_diff" class="compare-code-diff">
              <div class="compare-section-title">Code diff</div>
              <div class="compare-branches">
                <span>{{ compareResult.code_diff.left_branch || 'left' }}</span>
                <span>→</span>
                <span>{{ compareResult.code_diff.right_branch || 'right' }}</span>
              </div>
              <div v-if="compareResult.code_diff.changed_files?.length" class="compare-files">
                <span v-for="path in compareResult.code_diff.changed_files" :key="path">{{ path }}</span>
              </div>
              <pre v-if="compareResult.code_diff.diff_stat" class="compare-stat">{{ compareResult.code_diff.diff_stat }}</pre>
              <pre v-if="compareResult.code_diff.patch_excerpt" class="compare-patch">{{ compareResult.code_diff.patch_excerpt }}</pre>
              <div v-if="compareResult.code_diff.truncated" class="compare-truncated">Patch truncated</div>
            </div>
            <div class="compare-actions">
              <button class="secondary-btn" @click="handleAnalyzeCompare">Ask Claude to analyze</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

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
      @evolve="evolutionDialogVisible = true"
    />

    <EvolutionDialog
      :visible="evolutionDialogVisible"
      :project-id="currentProject?.id || ''"
      :project-dir="currentProject?.dir_path || projectDir || ''"
      :session-id="currentSessionId || ''"
      @close="evolutionDialogVisible = false"
      @draft-created="handleEvolutionDraftCreated"
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
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: transparent;
}

.recovery-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 24px;
  font-size: 12px;
  color: var(--text-muted);
}

.recovery-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
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
  justify-content: flex-start;
  gap: 0;
  width: 100%;
  margin: 0;
  padding: 10px clamp(18px, 2.4vw, 32px) 0;
  overflow-x: auto;
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.toolbar-group + .toolbar-group {
  margin-left: 8px;
}

.toolbar-btn {
  position: relative;
  overflow: hidden;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 12%, transparent), transparent);
  color: var(--text-secondary);
  border: 1px solid color-mix(in srgb, var(--accent) 34%, var(--border));
  padding: 4px 9px;
  min-height: 32px;
  border-radius: var(--radius-md);
  font-size: 11px;
  cursor: pointer;
  backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
  transition:
    color var(--transition-fast),
    background var(--transition-fast),
    border-color var(--transition-fast),
    box-shadow var(--transition-fast),
    transform var(--transition-fast);
  font-family: var(--font-sans);
  white-space: nowrap;
}

.toolbar-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent, color-mix(in srgb, var(--accent) 18%, transparent), transparent);
  transform: translateX(-120%);
  transition: transform 420ms ease;
}

.toolbar-btn:hover:not(:disabled)::before {
  transform: translateX(120%);
}

.toolbar-btn > * {
  position: relative;
}

.toolbar-btn:hover:not(:disabled) {
  color: var(--accent);
  background: var(--layer-active);
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toolbar-btn:active:not(:disabled) {
  transform: scale(0.96);
  transition-duration: 100ms;
}

.toolbar-btn--active {
  color: var(--accent);
  background: var(--layer-active);
  border-color: var(--accent);
  box-shadow: var(--shadow-active);
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
  bottom: calc(100% + 8px);
  left: 0;
  z-index: 50;
  min-width: 190px;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-glass);
  padding: 6px;
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
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
  background: var(--layer-active);
  color: var(--text-primary);
}

.dropdown-item.active {
  font-weight: 600;
}

/* When active, use the permission color background */
.dropdown-item.perm-purple.active { background: var(--purple-dim); }
.dropdown-item.perm-green.active { background: var(--green-dim); }
.dropdown-item.perm-red.active { background: var(--red-dim); }
.dropdown-item.perm-gray.active { background: var(--bg-tertiary); }

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

.dropdown-item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.media-menu {
  min-width: 150px;
}

.media-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.video-preview-popup {
  position: fixed;
  z-index: 120;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-glass);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.video-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: move;
  color: var(--text-muted);
  font-size: 11px;
  user-select: none;
}

.video-preview-header button {
  width: 24px;
  height: 24px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  transition: color var(--transition-fast), background var(--transition-fast), border-color var(--transition-fast);
}

.video-preview-header button:hover {
  color: var(--accent);
  background: var(--layer-active);
  border-color: var(--glass-border);
}

.video-preview {
  width: 240px;
  height: 180px;
  border-radius: var(--radius-sm);
  background: black;
  object-fit: cover;
}

.capture-btn {
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--accent-dim);
  color: var(--accent);
  padding: 6px 9px;
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast), box-shadow var(--transition-fast);
}

.capture-btn:hover {
  background: var(--layer-active);
  box-shadow: var(--shadow-sm);
}

.multi-session-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--overlay-glass);
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
}

.multi-session-dialog,
.compare-dialog {
  width: 720px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-glass);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.compare-dialog {
  width: 420px;
}

.multi-session-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}

.multi-session-header h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 15px;
}

.multi-session-header p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.4;
}

.multi-session-body {
  padding: 14px;
  overflow-y: auto;
}

.field-label {
  display: block;
  margin: 0 0 6px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
}

.multi-session-input {
  width: 100%;
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  padding: 8px 10px;
}

.message-choice-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 360px;
  overflow-y: auto;
}

.message-choice {
  display: grid;
  grid-template-columns: 52px 80px 1fr;
  gap: 8px;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-secondary);
  padding: 8px 10px;
  text-align: left;
  cursor: pointer;
}

.message-choice.active {
  border-color: var(--accent);
  background: var(--accent-dim);
  color: var(--text-primary);
}

.message-choice-index,
.message-choice-type {
  color: var(--text-muted);
  font-size: 11px;
  font-family: var(--font-mono);
}

.message-choice-preview {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.multi-session-options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 12px;
}

.multi-session-options label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  color: var(--text-muted);
  font-size: 11px;
}

.multi-session-options input[type="number"] {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  padding: 7px 8px;
}

.multi-session-options .checkbox-field {
  flex-direction: row;
  align-items: center;
  color: var(--text-secondary);
}

.parallel-branch-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
  max-height: 160px;
  overflow-y: auto;
}

.parallel-empty {
  color: var(--text-muted);
  font-size: 12px;
  padding: 8px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
}

.parallel-branch-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-secondary);
  padding: 7px 9px;
}

.parallel-branch-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.parallel-branch-main:disabled {
  cursor: default;
  opacity: 0.7;
}

.parallel-keep-btn {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  padding: 4px 8px;
  cursor: pointer;
  font-size: 11px;
}

.parallel-keep-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.parallel-branch-item.active {
  border-color: var(--accent);
  color: var(--accent);
}

.parallel-branch-item:disabled {
  cursor: default;
  opacity: 0.7;
}

.parallel-branch-item small {
  color: var(--text-muted);
}

.multi-session-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 14px;
  border-top: 1px solid var(--border);
}

.primary-btn,
.secondary-btn {
  border-radius: var(--radius-sm);
  padding: 7px 12px;
  cursor: pointer;
}

.primary-btn {
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--text-on-accent);
}

.secondary-btn {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
}

.compare-section-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  margin: 14px 0 8px;
}
.compare-code-diff {
  padding: 0 18px 16px;
}
.compare-branches {
  display: flex;
  gap: 8px;
  align-items: center;
  color: var(--text-muted);
  font-size: 12px;
  margin-bottom: 8px;
}
.compare-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.compare-files span {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 3px 6px;
  color: var(--text-secondary);
  font-size: 11px;
}
.compare-stat,
.compare-patch {
  max-height: 220px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-secondary);
  padding: 10px;
  font-size: 11px;
  white-space: pre-wrap;
}
.compare-truncated {
  color: var(--status-warning);
  font-size: 12px;
  margin-top: 6px;
}
.compare-actions {
  display: flex;
  justify-content: flex-end;
  padding: 0 18px 18px;
}
.compare-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 18px;
}

.compare-grid div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 14px 10px;
}

.compare-grid strong {
  color: var(--text-primary);
  font-size: 22px;
}

.compare-grid span {
  color: var(--text-muted);
  font-size: 12px;
}

.input-section {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  padding-top: 72px;
  background: linear-gradient(to bottom, transparent 0%, color-mix(in srgb, var(--layer-base) 72%, transparent) 42%, var(--layer-base) 100%);
  pointer-events: none;
}

.input-section > * {
  pointer-events: auto;
}

.input-row {
  width: 100%;
  margin: 0;
  padding: 8px clamp(18px, 2.4vw, 32px) 0;
}

/* History panel */
.history-panel {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  z-index: 50;
  width: 360px;
  max-height: 380px;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-glass);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.history-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--glass-border);
  background: var(--layer-glass);
}

.history-header-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.history-usage-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.history-usage-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--layer-glass);
  border: 1px solid var(--glass-border);
  color: var(--text-secondary);
  font-size: 11px;
  font-family: var(--font-mono);
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
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  margin-top: 2px;
  padding-left: 34px;
}

.artifact-panel {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  z-index: 50;
  width: 360px;
  max-height: 320px;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-glass);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.artifact-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--glass-border);
  background: var(--layer-glass);
}

.artifact-list {
  overflow-y: auto;
  padding: 4px;
}

.artifact-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
  font-family: var(--font-sans);
}

.artifact-item:hover {
  background: var(--layer-active);
}

.artifact-name {
  font-size: 12px;
  color: var(--text-primary);
  font-weight: 500;
}

.artifact-path {
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dash-usage,
.dash-cost,
.dash-budget,
.dash-last-query {
  color: var(--text-secondary);
}

.budget-warning {
  color: #d97706;
  border-color: color-mix(in srgb, #d97706 45%, var(--border));
}

.budget-exceeded {
  color: var(--red);
  border-color: color-mix(in srgb, var(--red) 45%, var(--border));
}

.dash-artifacts {
  color: var(--purple);
  background: var(--purple-dim);
}

/* Session Dashboard */
.session-dashboard {
  width: 100%;
  margin: 0;
  padding: 7px clamp(18px, 2.4vw, 32px) 14px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

/* Context bar — single-line compact monitor */
.context-bar-btn {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(72px, 1fr) max-content;
  align-items: center;
  gap: 9px;
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  cursor: pointer;
  transition: opacity var(--transition-fast);
  text-align: left;
}

.context-bar-btn:hover:not(:disabled) {
  opacity: 0.86;
}

.context-bar-btn:disabled {
  cursor: default;
  opacity: 0.6;
}

.context-bar-track {
  position: relative;
  display: block;
  width: 100%;
  height: 8px;
  background: color-mix(in srgb, var(--text-muted) 18%, transparent);
  border: none;
  border-radius: 999px;
  overflow: hidden;
}

.context-bar-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width 0.4s ease, background 0.4s ease;
}

.context-bar-fill.safe {
  background: var(--status-success);
}

.context-bar-fill.warning {
  background: var(--status-warning);
}

.context-bar-fill.danger {
  background: var(--status-danger);
}

.context-track-label {
  position: absolute;
  inset: 50% auto auto 50%;
  transform: translate(-50%, -50%);
  font-size: 10px;
  line-height: 1;
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--text-primary);
  text-shadow: 0 1px 2px var(--bg-primary);
  white-space: nowrap;
  pointer-events: none;
}

.context-pct {
  font-weight: 700;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  white-space: nowrap;
}

.context-bar-btn.safe .context-pct { color: var(--green); }
.context-bar-btn.warning .context-pct { color: var(--yellow); }
.context-bar-btn.danger .context-pct { color: var(--red); }

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

.tool-summary-row {
  padding-top: 2px;
}

.dash-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  padding: 3px 9px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--glass-bg) 34%, transparent);
  border: 1px solid color-mix(in srgb, var(--glass-border) 62%, transparent);
  cursor: default;
  white-space: nowrap;
  backdrop-filter: blur(calc(var(--glass-blur) * 0.72)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(calc(var(--glass-blur) * 0.72)) saturate(var(--glass-saturate));
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
  min-height: 26px;
}

button.dash-chip {
  cursor: pointer;
}

button.dash-chip:hover:not([disabled]) {
  background: var(--layer-active);
  border-color: var(--accent);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

button.dash-chip:active:not([disabled]) {
  transform: scale(0.96);
  transition-duration: 100ms;
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
  transition: color var(--transition-fast), background var(--transition-fast);
}

/* Permission mode colors - matching CC CLI */
.dash-perm.perm-purple,
.dropdown-item.perm-purple {
  color: var(--purple);
  background: var(--purple-dim);
}

.dash-perm.perm-green,
.dropdown-item.perm-green {
  color: var(--green);
  background: var(--green-dim);
}

.dash-perm.perm-red,
.dropdown-item.perm-red {
  color: var(--red);
  background: var(--red-dim);
}

.dash-perm.perm-gray,
.dropdown-item.perm-gray {
  color: var(--text-muted);
  background: var(--bg-tertiary);
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
  .context-track-label,
  .context-pct {
    font-size: 11px;
  }
}


.multi-session-trigger {
  position: relative;
  overflow: hidden;
}

.multi-session-badge {
  min-width: 18px;
}

.multi-session-dialog {
  width: min(920px, calc(100vw - 32px));
  background:
    radial-gradient(circle at 12% 0%, color-mix(in srgb, var(--accent) 18%, transparent), transparent 32%),
    var(--bg-secondary);
  border-color: color-mix(in srgb, var(--accent) 26%, var(--border));
}

.multi-session-header {
  align-items: flex-start;
  padding: 18px 20px;
}

.multi-session-kicker {
  display: inline-flex;
  margin-bottom: 6px;
  color: var(--accent);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.multi-session-header .close-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background var(--transition-fast);
  display: flex;
  align-items: center;
  font-size: 24px;
  line-height: 1;
}

.multi-session-header .close-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.multi-session-body {
  display: grid;
  grid-template-columns: minmax(280px, 0.9fr) minmax(320px, 1.1fr);
  gap: 12px;
  padding: 14px;
  background: color-mix(in srgb, var(--bg-primary) 52%, transparent);
}

.multi-session-card {
  border: 1px solid color-mix(in srgb, var(--border) 82%, transparent);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--bg-secondary) 88%, transparent);
  padding: 12px;
  transition: border-color 200ms ease, box-shadow 200ms ease, transform 200ms ease;
}

.multi-session-card:focus-within,
.multi-session-card:hover {
  border-color: color-mix(in srgb, var(--accent) 42%, var(--border));
  box-shadow: 0 12px 34px color-mix(in srgb, #000 14%, transparent);
}

.multi-session-card--context {
  grid-row: span 2;
}

.multi-session-card-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.multi-session-card-title > span {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 10px;
  background: var(--accent-dim);
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 800;
}

.multi-session-card-title strong,
.multi-session-card-title small {
  display: block;
}

.multi-session-card-title strong {
  color: var(--text-primary);
  font-size: 13px;
}

.multi-session-card-title small {
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.35;
}

.multi-session-input,
.multi-session-options input[type="number"] {
  border-radius: 12px;
  transition: border-color 180ms ease, box-shadow 180ms ease;
}

.multi-session-input:focus,
.multi-session-options input[type="number"]:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 16%, transparent);
}

.multi-session-toggle {
  min-height: 38px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-primary);
}

.selected-context-preview {
  margin-bottom: 10px;
  padding: 10px 12px;
  border: 1px dashed color-mix(in srgb, var(--accent) 42%, var(--border));
  border-radius: 12px;
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.message-choice-list {
  max-height: 330px;
  padding-right: 3px;
}

.message-choice {
  border-radius: 12px;
  transition: transform 180ms ease, border-color 180ms ease, background 180ms ease, box-shadow 180ms ease;
}

.message-choice:hover:not(.active) {
  transform: translateX(3px);
  border-color: color-mix(in srgb, var(--accent) 36%, var(--border));
  background: var(--bg-secondary);
}

.message-choice.active {
  box-shadow: inset 3px 0 0 var(--accent);
}

.parallel-branch-list {
  max-height: 230px;
}

.parallel-branch-item {
  border-radius: 12px;
  transition: transform 180ms ease, border-color 180ms ease, background 180ms ease;
}

.parallel-branch-item:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--accent) 38%, var(--border));
}

.parallel-branch-item.active {
  background: var(--accent-dim);
}

.parallel-keep-btn {
  border-radius: 999px;
  font-weight: 700;
  transition: transform 180ms ease, color 180ms ease, border-color 180ms ease, background 180ms ease;
}

.parallel-keep-btn:hover:not(:disabled) {
  color: var(--text-on-accent);
  border-color: var(--accent);
  background: var(--accent);
  transform: translateY(-1px);
}

.multi-session-footer {
  background: color-mix(in srgb, var(--bg-secondary) 92%, transparent);
}

.dialog-fade-enter-active .multi-session-dialog,
.dialog-fade-leave-active .multi-session-dialog,
.dialog-fade-enter-active .compare-dialog,
.dialog-fade-leave-active .compare-dialog {
  transition: transform var(--transition-enter), opacity var(--transition-enter);
}

.dialog-fade-enter-from .multi-session-dialog,
.dialog-fade-leave-to .multi-session-dialog,
.dialog-fade-enter-from .compare-dialog,
.dialog-fade-leave-to .compare-dialog {
  opacity: 0;
  transform: translateY(18px) scale(0.98);
}

@media (max-width: 780px) {
  .multi-session-body {
    grid-template-columns: 1fr;
  }

  .multi-session-card--context {
    grid-row: auto;
  }

  .message-choice {
    grid-template-columns: 48px 72px 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .multi-session-trigger::before,
  .multi-session-card,
  .message-choice,
  .parallel-branch-item,
  .parallel-keep-btn,
  .multi-session-dialog,
  .compare-dialog {
    transition: none;
  }

  .message-choice:hover:not(.active),
  .parallel-branch-item:hover,
  .parallel-keep-btn:hover:not(:disabled),
  .dialog-fade-enter-from .multi-session-dialog,
  .dialog-fade-leave-to .multi-session-dialog,
  .dialog-fade-enter-from .compare-dialog,
  .dialog-fade-leave-to .compare-dialog {
    transform: none;
  }
}
</style>
