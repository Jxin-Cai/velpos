<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import QRCode from 'qrcode'

const props = defineProps({
  channelType: { type: String, required: true },
  displayName: { type: String, default: '' },
  initMode: { type: String, default: 'credentials' },
  initFields: { type: Array, default: () => [] },
  description: { type: String, default: '' },
  initStatus: { type: String, default: 'not_initialized' },
  uiData: { type: Object, default: () => ({}) },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['submit', 'back'])

const formValues = ref({})
const qrCanvas = ref(null)
const isCredentialsMode = computed(() => props.initMode === 'credentials')
const isQrMode = computed(() => props.initMode === 'qr_login')
const isPromptMode = computed(() => props.initMode === 'prompt')
const hasVerificationUrl = computed(() => !!props.uiData?.verification_url)
const hasQrImage = computed(() => !!props.uiData?.qr_code_url)

// Generate QR code from verification_url (e.g. Lark OAuth device flow)
watch(() => props.uiData?.verification_url, async (url) => {
  if (!url) return
  await nextTick()
  if (qrCanvas.value) {
    try {
      await QRCode.toCanvas(qrCanvas.value, url, {
        width: 200,
        margin: 2,
        color: { dark: '#000000', light: '#ffffff' },
      })
    } catch { /* QR render failed silently */ }
  }
}, { immediate: true })

function onSubmit() {
  emit('submit', { ...formValues.value })
}

function onPollQr() {
  emit('submit', { step: 'poll', qrcode: props.uiData?.qrcode || '' })
}

const FIELD_LABELS = {
  app_id: 'App ID',
  app_secret: 'App Secret',
  api_addr: 'API Address',
  ws_addr: 'WebSocket Address',
  admin_secret: 'Admin Secret',
  admin_user_id: 'Admin User ID',
  bot_token: 'Bot Token',
}

const STATUS_TEXT = {
  wait: 'Waiting for scan...',
  waiting: 'Waiting for scan...',
  scaned: 'Scanned, confirm on phone',
  scanned: 'Scanned, confirm on phone',
}

function fieldLabel(field) {
  return FIELD_LABELS[field] || field
}

function loginStatusText(status) {
  return STATUS_TEXT[status] || status
}

function loginStatusClass(status) {
  if (status === 'scaned' || status === 'scanned') return 'status-scanned'
  return 'status-waiting'
}

// ── Auto-polling for QR login ──
const pollTimer = ref(null)
const isAutoPolling = ref(false)

watch([
  () => props.uiData?.verification_url,
  () => props.uiData?.qr_code_url,
  () => props.uiData?.qrcode,
], ([verifyUrl, qrImgUrl, qrcode]) => {
  stopAutoPoll()
  if ((verifyUrl || qrImgUrl) && qrcode) {
    startAutoPoll()
  }
}, { immediate: true })

function startAutoPoll() {
  if (pollTimer.value) return
  isAutoPolling.value = true
  pollTimer.value = setInterval(() => {
    if (props.disabled) return
    onPollQr()
  }, 2500)
}

function stopAutoPoll() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
  isAutoPolling.value = false
}

onBeforeUnmount(() => stopAutoPoll())

const pollStatusText = computed(() => {
  const status = props.uiData?.login_status
  if (status === 'scaned' || status === 'scanned') return 'Scanned — confirm on your device'
  return 'Waiting for scan...'
})
</script>

<template>
  <div class="channel-init">
    <button class="back-link" @click="emit('back')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 18 9 12 15 6" />
      </svg>
      Back
    </button>

    <div class="init-header">
      <h3 class="init-title">Initialize {{ displayName || channelType }}</h3>
      <p v-if="description" class="init-desc">{{ description }}</p>
    </div>

    <!-- Credentials mode -->
    <template v-if="isCredentialsMode">
      <div class="form-fields">
        <div v-for="field in initFields" :key="field" class="form-field">
          <label class="field-label">{{ fieldLabel(field) }}</label>
          <input
            v-model="formValues[field]"
            class="field-input"
            :type="field.includes('secret') || field.includes('token') ? 'password' : 'text'"
            :placeholder="fieldLabel(field)"
          />
        </div>
      </div>
      <button
        class="btn-init"
        :disabled="disabled"
        @click="onSubmit"
      >
        Initialize
      </button>
    </template>

    <!-- QR login mode -->
    <template v-else-if="isQrMode">
      <!-- QR from verification URL (e.g. Lark — generate QR from URL) -->
      <div v-if="hasVerificationUrl" class="qr-section">
        <div class="qr-container">
          <canvas ref="qrCanvas"></canvas>
        </div>
        <a
          :href="uiData.verification_url"
          target="_blank"
          rel="noopener"
          class="verify-link"
        >
          Or open verification link
        </a>
        <div class="poll-status">
          <div class="poll-indicator" :class="loginStatusClass(uiData?.login_status)">
            <div class="spinner-tiny"></div>
            <span>{{ pollStatusText }}</span>
          </div>
        </div>
        <button v-if="!isAutoPolling" class="btn-init" :disabled="disabled" @click="onPollQr">
          Check Status
        </button>
      </div>
      <!-- QR from image data (e.g. WeChat — base64 image) -->
      <div v-else-if="hasQrImage" class="qr-section">
        <div class="qr-container">
          <img :src="uiData.qr_code_url" alt="QR Code" class="qr-image" />
        </div>
        <p class="qr-hint">Scan with WeChat to connect</p>
        <div class="poll-status">
          <div class="poll-indicator" :class="loginStatusClass(uiData?.login_status)">
            <div class="spinner-tiny"></div>
            <span>{{ pollStatusText }}</span>
          </div>
        </div>
        <button v-if="!isAutoPolling" class="btn-init" :disabled="disabled" @click="onPollQr">
          Check Status
        </button>
      </div>
      <!-- No QR yet — start button -->
      <div v-else class="qr-section">
        <button class="btn-init" :disabled="disabled" @click="$emit('submit', { step: 'start' })">
          Get QR Code
        </button>
      </div>
    </template>

    <!-- Prompt-based init mode (e.g. Lark — sends setup prompt to Claude session) -->
    <template v-else-if="isPromptMode">
      <div class="prompt-section">
        <p class="prompt-hint">
          This will send setup instructions to your Claude session.
          Follow the prompts to complete initialization (including QR scan if required).
        </p>
        <button class="btn-init" :disabled="disabled" @click="$emit('submit', { step: 'start' })">
          Start Setup
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.channel-init {
  display: flex;
  flex-direction: column;
  gap: 16px;
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

.init-header {
  text-align: center;
}

.init-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px;
}

.init-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.form-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

.field-input {
  padding: 8px 10px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 13px;
  outline: none;
  transition: border-color var(--transition-fast);
}

.field-input:focus {
  border-color: var(--accent);
}

.field-input::placeholder {
  color: var(--text-muted);
}

.btn-init {
  align-self: center;
  padding: 8px 28px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-init:hover:not(:disabled) {
  background: var(--accent);
  color: var(--text-on-accent);
}

.btn-init:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.qr-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.qr-container {
  padding: 12px;
  background: #ffffff;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}

.qr-image {
  display: block;
  width: 200px;
  height: 200px;
}

.qr-hint {
  font-size: 13px;
  color: var(--text-secondary);
}

.verify-link {
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
  transition: opacity 0.15s;
}

.verify-link:hover {
  opacity: 0.8;
  text-decoration: underline;
}

.prompt-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.prompt-hint {
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
  line-height: 1.6;
  max-width: 320px;
}

.login-status {
  margin-top: 4px;
}

.status-badge {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: var(--radius-sm);
}

.status-waiting {
  background: var(--yellow-dim, rgba(245, 158, 11, 0.1));
  color: var(--yellow, #f59e0b);
}

.status-scanned {
  background: var(--green-dim, rgba(52, 211, 153, 0.1));
  color: var(--green);
}

.poll-status {
  margin-top: 4px;
}

.poll-indicator {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  background: var(--yellow-dim, rgba(245, 158, 11, 0.1));
  color: var(--yellow, #f59e0b);
  transition: background 0.3s, color 0.3s;
}

.poll-indicator.status-scanned {
  background: var(--green-dim, rgba(52, 211, 153, 0.1));
  color: var(--green);
}

.spinner-tiny {
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  opacity: 0.7;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
