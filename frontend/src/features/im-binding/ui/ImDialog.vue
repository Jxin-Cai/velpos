<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick, computed } from 'vue'
import QRCode from 'qrcode'
import { useImBinding } from '../model/useImBinding'
import ChannelPicker from './ChannelPicker.vue'
import ChannelInitDialog from './ChannelInitDialog.vue'
import PromptBinder from './PromptBinder.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
  sessionId: {
    type: String,
    default: '',
  },
  projectId: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['close', 'prompt', 'navigate-session'])

const {
  bindingState,
  loading,
  error,
  availableChannels,
  initRequired,
  syncResult,
  isBound,
  isBinding,
  isUnbound,
  bindingMode,
  fetchChannels,
  fetchStatus,
  handleCreateChannel,
  handleDeleteChannel,
  handleRenameChannel,
  handleBind,
  handleComplete,
  handleUnbind,
  handleInitialize,
  handleResetChannel,
  handleSyncContext,
  clearInitRequired,
  clearSyncResult,
  resetState,
} = useImBinding()

const qrCanvas = ref(null)
const friendUserIdInput = ref('')
const selectedInstance = ref(null) // { id, name, channel_type, display_name, ... }
const bindUiData = ref(null)

const stage = computed(() => {
  if (bindUiData.value) return 'prompt-confirm'
  if (isBound.value) return 'bound'
  if (initRequired.value) return 'init'
  if (isBinding.value) return bindingMode.value === 'prompt' ? 'prompt-binding' : 'qr-binding'
  return 'pick'
})

watch(() => props.visible, (val) => {
  if (val) {
    resetState()
    selectedInstance.value = null
    bindUiData.value = null
    friendUserIdInput.value = ''
    if (props.sessionId) fetchStatus(props.sessionId)
    fetchChannels()
  }
})

watch([isBinding, () => bindingState.value?.qr_code_data], async () => {
  if (isBinding.value && bindingState.value?.qr_code_data) {
    await nextTick()
    renderQR(bindingState.value.qr_code_data)
  }
})

async function renderQR(data) {
  if (!qrCanvas.value || !data) return
  try {
    await QRCode.toCanvas(qrCanvas.value, data, {
      width: 200,
      margin: 2,
      color: { dark: '#000000', light: '#ffffff' },
    })
  } catch {
    // QR render failed silently
  }
}

async function onInstanceSelect(instance) {
  selectedInstance.value = instance
  const result = await handleBind(props.sessionId, instance.id)
  if (result?.action === 'init_required') {
    return
  }
  if (result?.ui_data?.mode === 'prompt') {
    bindUiData.value = result.ui_data
  } else if (result?.binding_status === 'bound') {
    setTimeout(() => emit('close'), 600)
  }
}

async function onChannelCreate(channelType, name) {
  const result = await handleCreateChannel(channelType, name || channelType)
  if (result?.id) {
    // Auto-select the new instance for init/bind
    selectedInstance.value = {
      id: result.id,
      name: result.name,
      channel_type: result.channel_type,
      init_status: result.init_status,
    }
    // Try binding — if not initialized, will return init_required
    const bindResult = await handleBind(props.sessionId, result.id)
    if (bindResult?.action === 'init_required') {
      return
    }
    if (bindResult?.ui_data?.mode === 'prompt') {
      bindUiData.value = bindResult.ui_data
    } else if (bindResult?.binding_status === 'bound') {
      setTimeout(() => emit('close'), 600)
    }
  }
}

async function onChannelDelete(channelId) {
  await handleDeleteChannel(channelId)
}

async function onChannelRename(channelId, name) {
  await handleRenameChannel(channelId, name)
}

function onNavigateSession(sessionId) {
  emit('navigate-session', sessionId)
  emit('close')
}

async function onInitSubmit(params) {
  const channelId = initRequired.value?.channel_id || selectedInstance.value?.id
  if (!channelId) return
  const result = await handleInitialize(channelId, params)
  if (result?.init_status === 'ready') {
    const bindResult = await handleBind(props.sessionId, channelId)
    clearInitRequired()
    if (bindResult?.ui_data?.mode === 'prompt') {
      bindUiData.value = bindResult.ui_data
    } else if (bindResult?.binding_status === 'bound') {
      // Direct-mode binding (Lark, WeChat) — auto-close after brief success flash
      setTimeout(() => emit('close'), 600)
    }
  } else if (result?.ui_data?.prompt) {
    emit('prompt', result.ui_data.prompt)
    clearInitRequired()
    emit('close')
  } else if (result?.init_status === 'initializing' && result?.ui_data) {
    initRequired.value = {
      ...initRequired.value,
      init_status: result.init_status,
      ui_data: {
        ...initRequired.value?.ui_data,
        ...result.ui_data,
      },
    }
  }
}

function onInitBack() {
  clearInitRequired()
  selectedInstance.value = null
}

async function onPromptStart() {
  const prompt = bindUiData.value?.prompt
  if (!prompt) return
  const channelId = selectedInstance.value?.id || bindingState.value?.channel_id
  await handleComplete(props.sessionId, channelId)
  emit('prompt', prompt)
  emit('close')
}

function onQrComplete() {
  const fid = friendUserIdInput.value.trim()
  if (!fid) return
  const channelId = bindingState.value?.channel_id || selectedInstance.value?.id
  if (!channelId) return
  handleComplete(props.sessionId, channelId, { friend_user_id: fid })
}

function onUnbind() {
  handleUnbind(props.sessionId)
  selectedInstance.value = null
  bindUiData.value = null
}

async function onSyncContext() {
  clearSyncResult()
  const result = await handleSyncContext(props.sessionId)
  if (result && result.synced != null && !result.error) {
    setTimeout(() => emit('close'), 600)
  }
}

async function onSwitchChannel() {
  await handleUnbind(props.sessionId)
  selectedInstance.value = null
  bindUiData.value = null
}

function onBack() {
  selectedInstance.value = null
  bindUiData.value = null
  clearInitRequired()
}

function handleClose() {
  emit('close')
}

function handleOverlayClick(e) {
  if (e.target === e.currentTarget) handleClose()
}

function handleKeydown(e) {
  if (e.key === 'Escape') handleClose()
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div
        v-if="visible"
        class="dialog-overlay"
        @click="handleOverlayClick"
        role="dialog"
        aria-modal="true"
        aria-label="IM Integration"
      >
        <div class="dialog">
          <div class="dialog-header">
            <h2 class="dialog-title">IM Integration</h2>
            <button class="close-btn" @click="handleClose" aria-label="Close">&times;</button>
          </div>

          <Transition name="banner-slide" mode="out-in">
            <div v-if="error" :key="error" class="error-banner">{{ error }}</div>
          </Transition>

          <div v-if="loading && stage === 'pick'" class="loading-state">
            <div class="spinner"></div>
            <span>Loading...</span>
          </div>

          <Transition name="stage-fade" mode="out-in">
            <!-- Stage: Pick channel (two-level: type → instances) -->
            <div v-if="!loading && stage === 'pick'" key="pick" class="dialog-body">
              <ChannelPicker
                :channels="availableChannels"
                :current-session-id="sessionId"
                @select="onInstanceSelect"
                @create="onChannelCreate"
                @delete="onChannelDelete"
                @rename="onChannelRename"
                @navigate-session="onNavigateSession"
              />
            </div>

            <!-- Stage: Channel initialization -->
            <div v-else-if="stage === 'init'" key="init" class="dialog-body">
              <ChannelInitDialog
                :channel-type="initRequired?.channel_type || selectedInstance?.channel_type || ''"
                :display-name="initRequired?.display_name || selectedInstance?.display_name || ''"
                :init-mode="initRequired?.init_mode || 'credentials'"
                :init-fields="initRequired?.init_fields || []"
                :description="initRequired?.description || ''"
                :init-status="initRequired?.init_status || 'not_initialized'"
                :ui-data="initRequired?.ui_data || {}"
                :disabled="loading"
                @submit="onInitSubmit"
                @back="onInitBack"
              />
            </div>

            <!-- Stage: Prompt binder (after bind call, confirm before sending) -->
            <div v-else-if="stage === 'prompt-confirm'" key="prompt-confirm" class="dialog-body">
              <PromptBinder
                :channel-name="selectedInstance?.display_name || selectedInstance?.name || ''"
                :description="bindUiData?.description || ''"
                :prompt="bindUiData?.prompt || ''"
                :disabled="loading"
                @start="onPromptStart"
                @back="onBack"
              />
            </div>

            <!-- Stage: QR code binding in progress -->
            <div v-else-if="stage === 'qr-binding'" key="qr-binding" class="dialog-body">
              <div class="state-section">
                <button class="back-link" @click="onBack">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="15 18 9 12 15 6" />
                  </svg>
                  Back
                </button>
                <div class="qr-container">
                  <canvas ref="qrCanvas"></canvas>
                </div>
                <p class="state-desc">
                  Scan the QR code with your IM app to add this session as a friend.
                </p>
                <div class="state-info">
                  <span class="info-label">IM User ID:</span>
                  <span class="info-value">{{ bindingState?.im_user_id }}</span>
                </div>
                <div class="complete-section">
                  <p class="complete-hint">After scanning, enter the friend user ID to complete binding:</p>
                  <div class="complete-row">
                    <input
                      v-model="friendUserIdInput"
                      class="complete-input"
                      placeholder="Friend User ID"
                      @keydown.enter="onQrComplete"
                    />
                    <button
                      class="btn-primary btn-sm"
                      @click="onQrComplete"
                      :disabled="loading || !friendUserIdInput.trim()"
                    >
                      Complete
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Stage: Prompt binding in progress -->
            <div v-else-if="stage === 'prompt-binding'" key="prompt-binding" class="dialog-body">
              <div class="state-section">
                <div class="bound-badge binding-badge">
                  <div class="spinner-small"></div>
                  Binding...
                </div>
                <p class="state-desc">Channel binding is in progress.</p>
              </div>
            </div>

            <!-- Stage: Bound -->
            <div v-else-if="stage === 'bound'" key="bound" class="dialog-body">
              <div class="state-section">
                <div class="bound-badge">
                  <span class="bound-dot"></span>
                  Connected
                </div>
                <div class="state-info">
                  <span class="info-label">Channel:</span>
                  <span class="info-value">{{ bindingState?.channel_type }}</span>
                </div>
                <div v-if="bindingState?.channel_address" class="state-info">
                  <span class="info-label">Address:</span>
                  <span class="info-value">{{ bindingState.channel_address }}</span>
                </div>
                <div class="bound-actions">
                  <button class="btn-sync" @click="onSyncContext" :disabled="loading">
                    <template v-if="loading && syncResult == null">
                      <div class="spinner-small"></div>
                      Syncing...
                    </template>
                    <template v-else-if="syncResult?.synced != null">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"/>
                      </svg>
                      Synced ({{ syncResult.synced }})
                    </template>
                    <template v-else>Sync Context</template>
                  </button>
                  <button class="btn-switch" @click="onSwitchChannel" :disabled="loading">
                    Switch Channel
                  </button>
                  <button class="btn-danger" @click="onUnbind" :disabled="loading">
                    Unbind
                  </button>
                </div>
                <p v-if="syncResult?.error" class="sync-error">{{ syncResult.error }}</p>
              </div>
            </div>
          </Transition>

          <div class="dialog-footer">
            <span class="footer-hint">Session: {{ sessionId || 'N/A' }}</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ── Dialog enter/leave ── */
.dialog-fade-enter-active {
  transition: opacity 0.25s ease;
}
.dialog-fade-leave-active {
  transition: opacity 0.2s ease;
}
.dialog-fade-enter-active .dialog {
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.25s ease;
}
.dialog-fade-leave-active .dialog {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}
.dialog-fade-enter-from .dialog {
  transform: scale(0.95) translateY(8px);
  opacity: 0;
}
.dialog-fade-leave-to .dialog {
  transform: scale(0.97) translateY(4px);
  opacity: 0;
}

/* ── Stage content crossfade ── */
.stage-fade-enter-active {
  transition: opacity 0.2s ease 0.05s, transform 0.2s ease 0.05s;
}
.stage-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.stage-fade-enter-from {
  opacity: 0;
  transform: translateX(8px);
}
.stage-fade-leave-to {
  opacity: 0;
  transform: translateX(-8px);
}

/* ── Error banner slide ── */
.banner-slide-enter-active,
.banner-slide-leave-active {
  transition: opacity 0.2s ease, max-height 0.2s ease;
  overflow: hidden;
}
.banner-slide-enter-from,
.banner-slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.banner-slide-enter-to,
.banner-slide-leave-from {
  max-height: 60px;
}

.dialog-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-overlay);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
}

.dialog {
  width: 440px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  display: flex;
  flex-direction: column;
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.dialog-title {
  font-weight: 600;
  font-size: 16px;
  color: var(--text-primary);
}

.close-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 20px;
  cursor: pointer;
  transition: all 0.15s;
}

.close-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.error-banner {
  padding: 8px 20px;
  background: var(--red-dim);
  color: var(--red);
  font-size: 13px;
  flex-shrink: 0;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  color: var(--text-muted);
  font-size: 14px;
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.state-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.state-desc {
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
  line-height: 1.5;
  max-width: 320px;
}

.state-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  width: 100%;
  max-width: 320px;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
}

.info-label {
  color: var(--text-muted);
  flex-shrink: 0;
}

.info-value {
  font-family: var(--font-mono);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qr-container {
  padding: 12px;
  background: #ffffff;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}

.qr-container canvas {
  display: block;
}

.complete-section {
  width: 100%;
  max-width: 320px;
  margin-top: 4px;
}

.complete-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.complete-row {
  display: flex;
  gap: 8px;
}

.complete-input {
  flex: 1;
  padding: 6px 10px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  outline: none;
  transition: border-color var(--transition-fast);
}

.complete-input:focus {
  border-color: var(--accent);
}

.complete-input::placeholder {
  color: var(--text-muted);
}

.bound-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: var(--green-dim, rgba(52, 211, 153, 0.1));
  color: var(--green);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 600;
}

.binding-badge {
  background: var(--accent-dim);
  color: var(--accent);
}

.bound-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--green);
  animation: pulse 1.5s ease-in-out infinite;
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
  align-self: flex-start;
  transition: color 0.15s;
}

.back-link:hover {
  color: var(--text-primary);
}

.btn-primary {
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: var(--bg-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: filter 0.15s, transform 0.15s;
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.1);
}

.btn-primary:active:not(:disabled) {
  transform: scale(0.97);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 12px;
}

.btn-danger {
  padding: 8px 20px;
  border: 1px solid var(--red);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--red);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, transform 0.15s;
}

.btn-danger:hover:not(:disabled) {
  background: var(--red-dim);
}

.btn-danger:active:not(:disabled) {
  transform: scale(0.97);
}

.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.bound-actions {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}

.btn-switch {
  padding: 8px 20px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, transform 0.15s;
}

.btn-switch:hover:not(:disabled) {
  background: var(--accent);
  color: var(--text-on-accent);
}

.btn-switch:active:not(:disabled) {
  transform: scale(0.97);
}

.btn-switch:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-sync {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border: 1px solid var(--green);
  border-radius: var(--radius-sm);
  background: var(--green-dim, rgba(52, 211, 153, 0.1));
  color: var(--green);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s, color 0.2s, transform 0.15s;
}

.btn-sync:hover:not(:disabled) {
  background: var(--green);
  color: #fff;
}

.btn-sync:active:not(:disabled) {
  transform: scale(0.97);
}

.btn-sync:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sync-error {
  font-size: 12px;
  color: var(--red);
  text-align: center;
  margin: 0;
}

.dialog-footer {
  padding: 10px 20px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.footer-hint {
  font-size: 11px;
  color: var(--text-muted);
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@media (prefers-reduced-motion: reduce) {
  .dialog-fade-enter-active,
  .dialog-fade-leave-active,
  .dialog-fade-enter-active .dialog,
  .dialog-fade-leave-active .dialog,
  .stage-fade-enter-active,
  .stage-fade-leave-active,
  .banner-slide-enter-active,
  .banner-slide-leave-active {
    transition-duration: 0.01ms;
  }
  .bound-dot,
  .spinner,
  .spinner-small {
    animation-duration: 0.01ms;
  }
}
</style>
