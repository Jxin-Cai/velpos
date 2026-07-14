<script setup>
import { ref, nextTick, watch, computed } from 'vue'
import { useUserPreferences } from '@shared/lib/useUserPreferences'
import { formatFileSize } from '@shared/lib/textParsers'

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  running: {
    type: Boolean,
    default: false,
  },
  canceling: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['send', 'cancel'])

const { shouldEnterSend, shouldCtrlEnterSend } = useUserPreferences()

const input = ref('')
const isComposing = ref(false)
const compositionEndedRecently = ref(false)
const pendingAttachments = ref([])
const hasDraft = computed(() => Boolean(input.value.trim() || pendingAttachments.value.length))
const primaryAction = computed(() => (props.running && !hasDraft.value ? 'stop' : 'send'))

// 动态生成placeholder文本
const placeholderText = computed(() => {
  if (props.canceling) return 'Stopping…'
  if (props.disabled) return 'Message unavailable'
  if (props.running) return 'Add a follow-up for the next turn…'

  const sendShortcut = shouldEnterSend() ? 'Enter' : 'Ctrl+Enter'
  const newLineShortcut = shouldEnterSend() ? 'Ctrl+Enter' : 'Enter'

  return `Send a message... (${sendShortcut} to send, ${newLineShortcut} for new line, paste or attach files)`
})

// 动态生成发送按钮的提示文本
const sendButtonTitle = computed(() => {
  if (props.canceling) return 'Stopping current task…'
  if (primaryAction.value === 'stop') return 'Stop current task (Esc)'
  const sendShortcut = shouldEnterSend() ? 'Enter' : 'Ctrl+Enter'
  return props.running
    ? `Queue follow-up (${sendShortcut})`
    : `Send message (${sendShortcut})`
})
const sendButtonLabel = computed(() => {
  if (props.canceling) return 'Stopping current task'
  if (primaryAction.value === 'stop') return 'Stop current task'
  return props.running ? 'Queue follow-up message' : 'Send message'
})
const inputEl = ref(null)
const fileInputEl = ref(null)

function autoResize() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

watch(input, () => {
  nextTick(autoResize)
})

function handleSend() {
  const text = input.value.trim()
  if ((!text && pendingAttachments.value.length === 0) || props.disabled) return

  if (pendingAttachments.value.length > 0) {
    emit('send', {
      text: text || 'Please review the attached files.',
      attachments: pendingAttachments.value.map(item => ({
        name: item.name,
        mime_type: item.mime_type,
        size: item.size,
        data: item.data,
      })),
    })
  } else {
    emit('send', text)
  }

  input.value = ''
  pendingAttachments.value = []
  nextTick(() => {
    autoResize()
    inputEl.value?.focus()
  })
}

function handlePrimaryAction() {
  if (props.canceling || props.disabled) return
  if (primaryAction.value === 'stop') {
    emit('cancel')
    return
  }
  handleSend()
}

function handleCompositionStart() {
  isComposing.value = true
}

function handleCompositionEnd() {
  isComposing.value = false
  // 标记最近刚结束输入法，避免keydown事件立即触发
  compositionEndedRecently.value = true
  // 50ms后清除标记，给keydown事件足够的时间窗口
  setTimeout(() => {
    compositionEndedRecently.value = false
  }, 50)
}

function handleKeydown(e) {
  if (e.key === 'Enter') {
    // During IME composition or just after composition, defer all Enter handling to browser default
    if (isComposing.value || compositionEndedRecently.value) {
      return
    }

    const hasCtrl = e.ctrlKey
    const hasCmd = e.metaKey
    const hasModifier = hasCtrl || hasCmd

    // 根据用户偏好决定行为
    if (shouldEnterSend() && !hasModifier) {
      // 模式1：Enter发送，Ctrl/Cmd+Enter换行
      // 只有单独按Enter时才发送
      e.preventDefault()
      handleSend()
    } else if (shouldCtrlEnterSend() && hasModifier) {
      // 模式2：Ctrl/Cmd+Enter发送，Enter换行
      // 只有按Ctrl/Cmd+Enter时才发送
      e.preventDefault()
      handleSend()
    } else if (hasModifier) {
      // Ctrl/Cmd+Enter 但当前模式不要求发送 -> 手动插入换行
      e.preventDefault()
      const start = inputEl.value.selectionStart
      const end = inputEl.value.selectionEnd
      const value = input.value
      input.value = value.slice(0, start) + '\n' + value.slice(end)
      nextTick(() => {
        inputEl.value.selectionStart = inputEl.value.selectionEnd = start + 1
        autoResize()
      })
    }
    // 其他情况：让浏览器默认处理（单独Enter在非enter-send模式下）
  }
}

function handlePaste(e) {
  const items = e.clipboardData?.items
  if (!items) return

  for (const item of items) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) {
        e.preventDefault()
        addAttachmentFile(file)
        return
      }
    }
  }
}

function handleDrop(e) {
  e.preventDefault()
  const files = e.dataTransfer?.files
  if (!files) return
  for (const file of files) {
    addAttachmentFile(file)
  }
}

function handleDragover(e) {
  e.preventDefault()
}

function handleFileSelect(e) {
  const files = e.target.files
  if (!files) return
  for (const file of files) {
    addAttachmentFile(file)
  }
  e.target.value = ''
}

function addAttachmentFile(file) {
  const reader = new FileReader()
  reader.onload = () => {
    const dataUrl = reader.result
    const base64 = dataUrl.split(',')[1]
    pendingAttachments.value.push({
      name: file.name || 'attachment',
      data: base64,
      mime_type: file.type || 'application/octet-stream',
      size: file.size || 0,
      preview: file.type?.startsWith('image/') ? dataUrl : '',
    })
  }
  reader.readAsDataURL(file)
}

function addImage(base64, mediaType) {
  const preview = `data:${mediaType};base64,${base64}`
  pendingAttachments.value.push({
    name: `image-${Date.now()}.png`,
    data: base64,
    mime_type: mediaType,
    size: 0,
    preview,
  })
}

function removeAttachment(index) {
  pendingAttachments.value.splice(index, 1)
}

function formatSize(size) {
  return formatFileSize(size)
}

function setInput(text) {
  input.value = text
  nextTick(() => {
    autoResize()
    inputEl.value?.focus()
  })
}

function appendText(text) {
  input.value += text
  nextTick(() => {
    autoResize()
    inputEl.value?.focus()
  })
}

function handleAreaClick(e) {
  // If clicking on the input area (but not on controls), focus the input
  const isControl = e.target.closest('.primary-action-btn, .attach-btn, .attachment-remove, .attachment-thumb, .attachment-file, input[type="file"]')

  if (!isControl && !props.disabled) {
    inputEl.value?.focus()
  }
}

function openFilePicker() {
  fileInputEl.value?.click()
}

function clearAttachments() {
  pendingAttachments.value = []
}

defineExpose({ setInput, addImage, appendText, clearAttachments })
</script>

<template>
  <div class="input-area" @drop="handleDrop" @dragover="handleDragover" @click="handleAreaClick">
    <div v-if="pendingAttachments.length > 0" class="attachment-previews">
      <div
        v-for="(item, i) in pendingAttachments"
        :key="i"
        :class="item.preview ? 'attachment-thumb' : 'attachment-file'"
      >
        <img v-if="item.preview" :src="item.preview" :alt="item.name" />
        <div v-else class="attachment-file-main">
          <span class="attachment-icon">FILE</span>
          <span class="attachment-name">{{ item.name }}</span>
          <span class="attachment-size">{{ formatSize(item.size) }}</span>
        </div>
        <button type="button" class="attachment-remove" @click="removeAttachment(i)" title="Remove attachment" aria-label="Remove attachment">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>
    <textarea
      ref="inputEl"
      v-model="input"
      @keydown="handleKeydown"
      @compositionstart="handleCompositionStart"
      @compositionend="handleCompositionEnd"
      @paste="handlePaste"
      :placeholder="placeholderText"
      :disabled="disabled"
      rows="1"
      class="input-field"
      autocomplete="off"
      autocorrect="off"
      autocapitalize="off"
      spellcheck="false"
    ></textarea>
    <div class="input-actions">
      <input
        ref="fileInputEl"
        type="file"
        multiple
        class="file-input"
        @change="handleFileSelect"
      />
      <button
        type="button"
        class="attach-btn"
        :disabled="disabled"
        data-tooltip="Attach files"
        title="Attach files"
        aria-label="Attach files"
        @click.stop="openFilePicker"
      >
        +
      </button>
      <button
        type="button"
        class="primary-action-btn"
        :class="{
          'primary-action-btn--stop': primaryAction === 'stop',
          'primary-action-btn--canceling': canceling,
        }"
        :disabled="disabled || canceling || (primaryAction === 'send' && !hasDraft)"
        :data-tooltip="sendButtonTitle"
        :title="sendButtonTitle"
        :aria-label="sendButtonLabel"
        @click.stop="handlePrimaryAction"
      >
        <svg v-if="primaryAction === 'stop'" class="stop-icon" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" />
        </svg>
        <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 19V5" />
          <path d="m6 11 6-6 6 6" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.input-area {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0;
  background: color-mix(in srgb, var(--glass-bg) 46%, transparent);
  border: 1px solid color-mix(in srgb, var(--glass-border) 72%, transparent);
  border-radius: var(--radius-lg);
  padding: 9px 86px 9px 14px;
  margin: 0;
  min-height: 46px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.13), inset 0 1px 0 var(--glass-highlight);
  backdrop-filter: blur(calc(var(--glass-blur) * 1.05)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(calc(var(--glass-blur) * 1.05)) saturate(var(--glass-saturate));
  transition:
    border-color var(--transition-fast),
    background var(--transition-base),
    box-shadow var(--transition-fast),
    transform var(--transition-fast);
  cursor: text;
}

.input-area:focus-within {
  background: color-mix(in srgb, var(--glass-bg) 64%, transparent);
  border-color: var(--accent);
  box-shadow: var(--shadow-active), 0 14px 34px rgba(0, 0, 0, 0.16), inset 0 1px 0 var(--glass-highlight);
}

.attachment-previews {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 8px;
}

.attachment-thumb {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--glass-border);
  background: var(--layer-glass);
  box-shadow: var(--shadow-sm);
  cursor: default;
}

.attachment-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.attachment-file {
  position: relative;
  max-width: 240px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--layer-glass);
  padding: 9px 30px 9px 10px;
  box-shadow: var(--shadow-xs);
  cursor: default;
}

.attachment-file-main {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.attachment-icon {
  flex-shrink: 0;
  color: var(--accent);
  font-size: 10px;
  font-weight: 700;
}

.attachment-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
  font-size: 12px;
}

.attachment-size {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 11px;
}

.attachment-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--glass-bg-strong);
  color: var(--text-primary);
  border: 1px solid var(--glass-border);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  box-shadow: var(--shadow-sm);
  transition: opacity var(--transition-fast), background var(--transition-fast), color var(--transition-fast);
}

.attachment-thumb:hover .attachment-remove,
.attachment-file:hover .attachment-remove,
.attachment-remove:focus-visible {
  opacity: 1;
}

.input-field {
  flex: none;
  width: 100%;
  background: none;
  border: none;
  outline: none;
  box-shadow: none;
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.45;
  resize: none;
  min-height: 24px;
  max-height: 38vh;
  overflow-y: auto;
  padding-right: 4px;
}

.input-field::placeholder {
  color: var(--text-muted);
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}

.input-field:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-actions {
  position: absolute;
  right: 8px;
  bottom: 7px;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
}

.file-input {
  display: none;
}

.attach-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  height: 32px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--layer-glass);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.attach-btn:hover:not(:disabled) {
  background: var(--layer-active);
  border-color: var(--accent);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.attach-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.primary-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 50%;
  background: var(--accent);
  color: var(--text-on-accent);
  cursor: pointer;
  transition:
    filter var(--transition-fast),
    transform var(--transition-fast),
    box-shadow var(--transition-fast),
    opacity var(--transition-fast);
  flex-shrink: 0;
  box-shadow: var(--shadow-md), var(--shadow-glow);
  align-self: flex-end;
}

:global([data-theme="dark"]) .input-area {
  background: var(--bg-input);
  border-color: var(--border);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.24);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

:global([data-theme="dark"]) .input-area:focus-within {
  background: var(--bg-input);
  border-color: #494949;
  box-shadow: 0 0 0 1px var(--border-subtle), 0 10px 28px rgba(0, 0, 0, 0.28);
}

:global([data-theme="dark"]) .attach-btn {
  background: transparent;
  border-color: transparent;
}

:global([data-theme="dark"]) .primary-action-btn {
  border-color: transparent;
  box-shadow: none;
}

.primary-action-btn:hover:not(:disabled) {
  filter: brightness(1.08);
  transform: translateY(-1px);
  box-shadow: var(--shadow-lg), var(--shadow-glow);
}

.primary-action-btn:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: var(--shadow-xs);
}

.primary-action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.primary-action-btn--stop {
  background: var(--text-primary);
  border-color: color-mix(in srgb, var(--text-primary) 72%, transparent);
  color: var(--layer-base);
  box-shadow: var(--shadow-sm);
}

.primary-action-btn--stop:hover:not(:disabled) {
  filter: none;
  background: color-mix(in srgb, var(--text-primary) 88%, var(--text-secondary));
  box-shadow: var(--shadow-md);
}

.primary-action-btn--canceling .stop-icon {
  animation: stop-pulse 900ms ease-in-out infinite;
}

.primary-action-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

@keyframes stop-pulse {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .primary-action-btn,
  .primary-action-btn--canceling .stop-icon {
    animation: none;
    transition: none;
  }
}

@media (pointer: coarse) {
  .input-area {
    padding-right: 108px;
    min-height: 58px;
  }

  .attach-btn,
  .primary-action-btn {
    min-width: 44px;
    width: 44px;
    height: 44px;
  }
}
</style>
