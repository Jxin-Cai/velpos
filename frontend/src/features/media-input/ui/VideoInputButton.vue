<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useVideoInput } from '../model/useVideoInput'

const props = defineProps({
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['capture'])

const { isCapturing, supported, startCapture, stopCapture, captureFrame } = useVideoInput()
const videoEl = ref(null)
const showPreview = ref(false)

const isDisabled = computed(() => (!supported.value || props.disabled) && !isCapturing.value)

async function handleToggle() {
  if (isCapturing.value) {
    stopCapture()
    showPreview.value = false
  } else {
    const stream = await startCapture()
    if (stream) {
      showPreview.value = true
      await nextTick()
      if (videoEl.value) {
        videoEl.value.srcObject = stream
      }
    }
  }
}

function handleCapture() {
  const frame = captureFrame(videoEl.value)
  if (frame) {
    emit('capture', frame)
  }
}

// 监听全局快捷键触发的 camera 切换
async function handleGlobalToggle() {
  if (!isDisabled.value) {
    await handleToggle()
  }
}

onMounted(() => {
  window.addEventListener('vp-camera-toggle-global', handleGlobalToggle)
})

onBeforeUnmount(() => {
  window.removeEventListener('vp-camera-toggle-global', handleGlobalToggle)
  stopCapture()
})
</script>

<template>
  <div class="video-input-wrapper">
    <button
      class="toolbar-btn"
      :class="{ 'toolbar-btn--active': isCapturing }"
      :disabled="isDisabled"
      :title="!supported ? 'Camera not supported' : isCapturing ? 'Stop camera' : 'Start camera'"
      @click="handleToggle"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="23 7 16 12 23 17 23 7"/>
        <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
      </svg>
      <span class="toolbar-btn-label">{{ isCapturing ? 'Close' : 'Camera' }}</span>
    </button>

    <div v-if="showPreview && isCapturing" class="video-preview-popup">
      <video ref="videoEl" autoplay muted playsinline class="video-preview"></video>
      <button class="capture-btn" @click="handleCapture" title="Capture frame">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <circle cx="12" cy="12" r="4"/>
        </svg>
        Capture
      </button>
    </div>
  </div>
</template>

<style scoped>
.video-input-wrapper {
  position: relative;
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
  transition: color var(--transition-fast), background var(--transition-fast), border-color var(--transition-fast);
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
.toolbar-btn--active {
  color: var(--accent);
  background: var(--accent-dim);
  border-color: var(--accent);
}
.toolbar-btn-label {
  font-weight: 500;
}

.video-preview-popup {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  z-index: 60;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xl);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.video-preview {
  width: 240px;
  height: 180px;
  border-radius: var(--radius-sm);
  background: black;
  object-fit: cover;
}

.capture-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  background: var(--accent);
  color: var(--text-on-accent);
  border: none;
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: filter var(--transition-fast);
  font-family: var(--font-sans);
}
.capture-btn:hover {
  filter: brightness(1.1);
}
</style>
