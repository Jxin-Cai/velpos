<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import MessageItem from './MessageItem.vue'

const props = defineProps({
  messages: {
    type: Array,
    required: true,
  },
})

const messagesContainer = ref(null)
const isNearBottom = ref(true)
const showScrollBtn = ref(false)

const BOTTOM_THRESHOLD = 150

function checkNearBottom() {
  const el = messagesContainer.value
  if (!el) return
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  isNearBottom.value = distanceFromBottom < BOTTOM_THRESHOLD
  showScrollBtn.value = !isNearBottom.value
}

function scrollToBottom() {
  const el = messagesContainer.value
  if (!el) return
  el.scrollTop = el.scrollHeight
  isNearBottom.value = true
  showScrollBtn.value = false
}

function handleScroll() {
  checkNearBottom()
}

// Auto-scroll when new messages arrive and user is near bottom
watch(() => props.messages.length, () => {
  if (isNearBottom.value) {
    nextTick(scrollToBottom)
  }
})

// MutationObserver for streaming content changes (DOM updates without message count change)
let observer = null
let scrollRafId = null

onMounted(() => {
  const el = messagesContainer.value
  if (!el) return

  observer = new MutationObserver(() => {
    if (isNearBottom.value && !scrollRafId) {
      scrollRafId = requestAnimationFrame(() => {
        scrollRafId = null
        scrollToBottom()
      })
    }
  })
  observer.observe(el, { childList: true, subtree: true, characterData: true })
})

onBeforeUnmount(() => {
  if (observer) {
    observer.disconnect()
    observer = null
  }
  if (scrollRafId) {
    cancelAnimationFrame(scrollRafId)
    scrollRafId = null
  }
})
</script>

<template>
  <div class="messages-shell">
    <div ref="messagesContainer" class="messages-area" @scroll="handleScroll">
      <div class="messages-content">
        <div v-if="messages.length === 0" class="empty-state">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div class="empty-title">Velpos</div>
          <div class="empty-desc">Send a prompt to start interacting with Claude Code</div>
        </div>
        <MessageItem
          v-for="msg in messages"
          :key="msg._id ?? msg.id"
          :message="msg"
        />
        <slot name="footer"></slot>
      </div>
    </div>
    <button
      v-if="showScrollBtn"
      class="scroll-bottom-btn"
      @click="scrollToBottom"
      title="Scroll to bottom"
      aria-label="Scroll to bottom"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>
  </div>
</template>

<style scoped>
.messages-shell {
  flex: 1;
  min-height: 0;
  position: relative;
  display: flex;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0 clamp(300px, 34vh, 380px);
  display: flex;
  flex-direction: column;
  position: relative;
  background:
    radial-gradient(circle at 50% 0%, var(--accent-dim), transparent 26%),
    transparent;
  scroll-padding-bottom: clamp(300px, 34vh, 380px);
}

.messages-content {
  width: 100%;
  margin: 0;
  padding: 0 clamp(18px, 2.4vw, 32px);
  display: flex;
  flex-direction: column;
  gap: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin: auto;
  gap: 12px;
  min-height: 42vh;
  padding: 32px;
  color: var(--text-muted);
  text-align: center;
}

.empty-icon {
  width: 76px;
  height: 76px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
  background: var(--layer-active);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-active);
  opacity: 0.86;
  margin-bottom: 8px;
}

.empty-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.empty-desc {
  max-width: 360px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.scroll-bottom-btn {
  position: absolute;
  left: 50%;
  bottom: calc(clamp(300px, 34vh, 380px) - 46px);
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--touch-target);
  min-width: var(--touch-target);
  height: var(--touch-target);
  min-height: var(--touch-target);
  padding: 0;
  box-sizing: border-box;
  border-radius: 999px;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  color: var(--text-secondary);
  cursor: pointer;
  box-shadow: var(--shadow-glass);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
  z-index: 30;
}

.scroll-bottom-btn:hover {
  background: var(--layer-active);
  color: var(--accent);
  border-color: var(--accent);
  box-shadow: var(--shadow-active);
  transform: translateX(-50%) translateY(-1px);
}
</style>
