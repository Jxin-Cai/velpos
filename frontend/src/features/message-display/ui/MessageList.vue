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

onMounted(() => {
  const el = messagesContainer.value
  if (!el) return

  observer = new MutationObserver(() => {
    if (isNearBottom.value) {
      requestAnimationFrame(() => scrollToBottom())
    }
  })
  observer.observe(el, { childList: true, subtree: true, characterData: true })
})

onBeforeUnmount(() => {
  if (observer) {
    observer.disconnect()
    observer = null
  }
})
</script>

<template>
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
    <button
      v-if="showScrollBtn"
      class="scroll-bottom-btn"
      @click="scrollToBottom"
      title="Scroll to bottom"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>
  </div>
</template>

<style scoped>
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  position: relative;
}

.messages-content {
  width: 100%;
  margin: 0;
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
  color: var(--text-muted);
}

.empty-icon {
  color: var(--accent);
  opacity: 0.5;
  margin-bottom: 8px;
}

.empty-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-secondary);
}

.empty-desc {
  font-size: 13px;
}

.scroll-bottom-btn {
  position: sticky;
  bottom: 12px;
  align-self: center;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  box-shadow: var(--shadow-md);
  transition: all var(--transition-fast);
  z-index: 10;
}

.scroll-bottom-btn:hover {
  background: var(--bg-hover);
  color: var(--accent);
  border-color: var(--accent);
  box-shadow: var(--shadow-lg);
}
</style>
