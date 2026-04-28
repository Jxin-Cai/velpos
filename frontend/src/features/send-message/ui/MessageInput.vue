<script setup>
import { ref, nextTick, watch, computed } from 'vue'
import { useUserPreferences } from '@shared/lib/useUserPreferences'

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  running: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['send'])

const { shouldEnterSend, shouldCtrlEnterSend } = useUserPreferences()

const input = ref('')
const isComposing = ref(false)
const compositionEndedRecently = ref(false)

// 动态生成placeholder文本
const placeholderText = computed(() => {
  if (props.disabled) return 'Waiting for Claude to finish...'
  if (props.running) return 'Send follow-up (queued until Claude finishes)...'

  const sendShortcut = shouldEnterSend() ? 'Enter' : 'Ctrl+Enter'
  const newLineShortcut = shouldEnterSend() ? 'Ctrl+Enter' : 'Enter'

  return `Send a message... (${sendShortcut} to send, ${newLineShortcut} for new line, paste or attach files)`
})

// 动态生成发送按钮的提示文本
const sendButtonTitle = computed(() => {
  const sendShortcut = shouldEnterSend() ? 'Enter' : 'Ctrl+Enter'
  return `Send message (${sendShortcut})`
})
const inputEl = ref(null)
const fileInputEl = ref(null)
const pendingAttachments = ref([])

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
  const n = Number(size) || 0
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  if (n >= 1024) return `${Math.round(n / 1024)} KB`
  return `${n} B`
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
  const isControl = e.target.closest('.send-btn, .attach-btn, .attachment-remove, .attachment-thumb, .attachment-file, input[type="file"]')

  if (!isControl && !props.disabled) {
    inputEl.value?.focus()
  }
}

function openFilePicker() {
  fileInputEl.value?.click()
}

defineExpose({ setInput, addImage, appendText })
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
        <button class="attachment-remove" @click="removeAttachment(i)" title="Remove attachment" aria-label="Remove attachment">
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
        class="attach-btn"
        :disabled="disabled"
        title="Attach files"
        aria-label="Attach files"
        @click.stop="openFilePicker"
      >
        +
      </button>
      <button
        class="send-btn"
        :disabled="(!input.trim() && pendingAttachments.length === 0) || disabled"
        :title="sendButtonTitle"
        aria-label="Send message"
        @click="handleSend"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="22" y1="2" x2="11" y2="13"/>
          <polygon points="22 2 15 22 11 13 2 9 22 2"/>
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
}

.input-field:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-field::placeholder {
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
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

.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--accent), var(--purple));
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

.send-btn:hover:not(:disabled) {
  filter: brightness(1.08);
  transform: translateY(-1px);
  box-shadow: var(--shadow-lg), var(--shadow-glow);
}

.send-btn:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: var(--shadow-xs);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
