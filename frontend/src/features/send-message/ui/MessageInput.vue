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

// 动态生成placeholder文本
const placeholderText = computed(() => {
  if (props.disabled) return 'Waiting for Claude to finish...'
  if (props.running) return 'Send follow-up (queued until Claude finishes)...'

  const sendShortcut = shouldEnterSend() ? 'Enter' : 'Ctrl+Enter'
  const newLineShortcut = shouldEnterSend() ? 'Ctrl+Enter' : 'Enter'

  return `Send a message... (${sendShortcut} to send, ${newLineShortcut} for new line, paste images with Ctrl+V)`
})

// 动态生成发送按钮的提示文本
const sendButtonTitle = computed(() => {
  const sendShortcut = shouldEnterSend() ? 'Enter' : 'Ctrl+Enter'
  return `Send message (${sendShortcut})`
})
const inputEl = ref(null)
const pendingImages = ref([]) // [{ data: base64, media_type: 'image/png', preview: dataUrl }]

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
  if ((!text && pendingImages.value.length === 0) || props.disabled) return

  if (pendingImages.value.length > 0) {
    emit('send', {
      text: text || 'Please look at the attached image(s).',
      images: pendingImages.value.map(img => ({ data: img.data, media_type: img.media_type })),
    })
  } else {
    emit('send', text)
  }

  input.value = ''
  pendingImages.value = []
  nextTick(() => {
    autoResize()
    inputEl.value?.focus()
  })
}

function handleKeydown(e) {
  if (e.key === 'Enter') {
    const hasCtrl = e.ctrlKey || e.metaKey

    // 根据用户偏好决定行为
    if (shouldEnterSend() && !hasCtrl) {
      // Enter发送，Ctrl+Enter换行
      e.preventDefault()
      handleSend()
    } else if (shouldCtrlEnterSend() && hasCtrl) {
      // Ctrl+Enter发送，Enter换行
      e.preventDefault()
      handleSend()
    }
    // 其他情况：默认的换行行为
  }
}

function handlePaste(e) {
  const items = e.clipboardData?.items
  if (!items) return

  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      const file = item.getAsFile()
      if (file) addImageFile(file)
      return
    }
  }
}

function handleDrop(e) {
  e.preventDefault()
  const files = e.dataTransfer?.files
  if (!files) return
  for (const file of files) {
    if (file.type.startsWith('image/')) {
      addImageFile(file)
    }
  }
}

function handleDragover(e) {
  e.preventDefault()
}

function addImageFile(file) {
  const reader = new FileReader()
  reader.onload = () => {
    const dataUrl = reader.result
    // Extract base64 data after the comma
    const base64 = dataUrl.split(',')[1]
    pendingImages.value.push({
      data: base64,
      media_type: file.type || 'image/png',
      preview: dataUrl,
    })
  }
  reader.readAsDataURL(file)
}

function addImage(base64, mediaType) {
  const preview = `data:${mediaType};base64,${base64}`
  pendingImages.value.push({ data: base64, media_type: mediaType, preview })
}

function removeImage(index) {
  pendingImages.value.splice(index, 1)
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
  // If clicking on the input area (but not on the send button or image remove buttons), focus the input
  const isSendBtn = e.target.closest('.send-btn')
  const isRemoveBtn = e.target.closest('.image-remove')

  if (!isSendBtn && !isRemoveBtn && !props.disabled) {
    inputEl.value?.focus()
  }
}

defineExpose({ setInput, addImage, appendText })
</script>

<template>
  <div class="input-area" @drop="handleDrop" @dragover="handleDragover" @click="handleAreaClick">
    <!-- Image previews -->
    <div v-if="pendingImages.length > 0" class="image-previews">
      <div v-for="(img, i) in pendingImages" :key="i" class="image-thumb">
        <img :src="img.preview" alt="Pending image" />
        <button class="image-remove" @click="removeImage(i)" title="Remove image">
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
    <button
      class="send-btn"
      :disabled="(!input.trim() && pendingImages.length === 0) || disabled"
      :title="sendButtonTitle"
      @click="handleSend"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="22" y1="2" x2="11" y2="13"/>
        <polygon points="22 2 15 22 11 13 2 9 22 2"/>
      </svg>
    </button>
  </div>
</template>

<style scoped>
.input-area {
  display: flex;
  flex-direction: column;
  gap: 0;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  margin: 0 16px;
  transition:
    border-color var(--transition-fast),
    background var(--transition-base),
    box-shadow var(--transition-fast);
  cursor: text;
}

.input-area:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}

.image-previews {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 8px;
}

.image-thumb {
  position: relative;
  width: 60px;
  height: 60px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  border: 1px solid var(--border);
  cursor: default;
}

.image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.image-thumb:hover .image-remove {
  opacity: 1;
}

.input-field {
  flex: none;
  background: none;
  border: none;
  outline: none;
  box-shadow: none;
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  min-height: 24px;
  max-height: 50vh;
  overflow-y: auto;
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

.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: var(--text-on-accent);
  cursor: pointer;
  transition:
    filter var(--transition-fast),
    transform var(--transition-spring),
    box-shadow var(--transition-fast);
  flex-shrink: 0;
  box-shadow: var(--shadow-sm);
  align-self: flex-end;
  cursor: pointer;
}

.send-btn:hover:not(:disabled) {
  filter: brightness(1.1);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md), var(--shadow-glow);
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
