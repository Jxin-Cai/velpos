<script setup>
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useSession } from '@entities/session'
import MessageItem from './MessageItem.vue'

const props = defineProps({
  messages: {
    type: Array,
    required: true,
  },
  hasMore: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['load-more', 'open-trace'])

const { currentSessionId, getTraceSpansFor } = useSession()

const traceSummaryByRun = computed(() => {
  const summaries = new Map()
  for (const span of getTraceSpansFor(currentSessionId.value)) {
    if (!span?.run_id) continue
    if (!summaries.has(span.run_id)) {
      summaries.set(span.run_id, {
        statuses: new Set(),
        spanCount: 0,
        toolCallCount: 0,
        subagentCount: 0,
        runningSubagentCount: 0,
      })
    }
    const summary = summaries.get(span.run_id)
    summary.statuses.add(span.status)
    summary.spanCount += 1
    if (span.span_type === 'tool_call') summary.toolCallCount += 1
    if (span.span_type === 'subagent') {
      summary.subagentCount += 1
      if (span.status === 'running') summary.runningSubagentCount += 1
    }
  }
  for (const summary of summaries.values()) {
    if (summary.statuses.has('running')) summary.status = 'running'
    else if (summary.statuses.has('failed')) summary.status = 'failed'
    else if (summary.statuses.has('cancelled')) summary.status = 'cancelled'
    else if (summary.statuses.has('denied')) summary.status = 'denied'
    else summary.status = 'completed'
    delete summary.statuses
  }
  return summaries
})

function traceRunIdFor(message) {
  if (message?.content?.run_id) return message.content.run_id
  const messageId = message?.content?.message_id
  if (!messageId) return ''
  const root = getTraceSpansFor(currentSessionId.value).find(span => (
    span.span_type === 'run' && span.metadata?.source_message_id === messageId
  ))
  return root?.run_id || ''
}

function traceSummaryFor(message) {
  const runId = traceRunIdFor(message)
  return runId ? (traceSummaryByRun.value.get(runId) || null) : null
}

const messagesContainer = ref(null)
const isNearBottom = ref(true)
const showScrollBtn = ref(false)
const loadingMore = ref(false)
const activeUserMessageIndex = ref(-1)

const userMessageMarkers = computed(() => props.messages
  .map((message, index) => ({ message, index }))
  .filter(({ message }) => message?.type === 'user')
  .map(({ message, index }) => ({
    index,
    key: message._id ?? message.id ?? `user-${index}`,
    preview: userMessagePreview(message),
  })))

const BOTTOM_THRESHOLD = 150

function checkNearBottom() {
  const el = messagesContainer.value
  if (!el) return
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  isNearBottom.value = distanceFromBottom < BOTTOM_THRESHOLD
  showScrollBtn.value = !isNearBottom.value
  updateActiveUserMessage()
}

function userMessagePreview(message) {
  const text = String(message?.content?.text || '')
    .replace(/\u001b\[[0-9;]*m/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (text) return text
  const attachments = message?.content?.attachments || []
  if (attachments.length) return attachments.map((item) => item.filename || item.name || 'attachment').join(', ')
  return 'User message'
}

function updateActiveUserMessage() {
  const container = messagesContainer.value
  if (!container || !userMessageMarkers.value.length) {
    activeUserMessageIndex.value = -1
    return
  }
  const readingLine = container.scrollTop + 32
  let active = userMessageMarkers.value[0].index
  for (const marker of userMessageMarkers.value) {
    const anchor = container.querySelector(`[data-message-index="${marker.index}"]`)
    if (anchor && anchor.offsetTop <= readingLine) active = marker.index
  }
  activeUserMessageIndex.value = active
}

function scrollToUserMessage(index) {
  const container = messagesContainer.value
  const anchor = container?.querySelector(`[data-message-index="${index}"]`)
  if (!container || !anchor) return
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  container.scrollTo({
    top: Math.max(0, anchor.offsetTop - 20),
    behavior: reducedMotion ? 'auto' : 'smooth',
  })
  activeUserMessageIndex.value = index
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

// Sentinel IntersectionObserver for loading more
let sentinelObserver = null
const sentinelEl = ref(null)

function setupSentinel() {
  if (!messagesContainer.value || !sentinelEl.value) return
  if (sentinelObserver) sentinelObserver.disconnect()
  sentinelObserver = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && props.hasMore && !loadingMore.value) {
        triggerLoadMore()
      }
    },
    { root: messagesContainer.value, threshold: 0, rootMargin: '300px 0px 0px 0px' }
  )
  sentinelObserver.observe(sentinelEl.value)
}

async function triggerLoadMore() {
  const el = messagesContainer.value
  if (!el) return
  loadingMore.value = true
  if (sentinelObserver) sentinelObserver.disconnect()
  const prevScrollHeight = el.scrollHeight
  emit('load-more')
  await nextTick()
  await nextTick()
  await new Promise(resolve => requestAnimationFrame(resolve))
  const newScrollHeight = el.scrollHeight
  if (newScrollHeight !== prevScrollHeight) {
    el.scrollTop += newScrollHeight - prevScrollHeight
  }
  loadingMore.value = false
  await nextTick()
  setupSentinel()
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

  setupSentinel()
  nextTick(updateActiveUserMessage)
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
  if (sentinelObserver) {
    sentinelObserver.disconnect()
    sentinelObserver = null
  }
})
</script>

<template>
  <div class="messages-shell">
    <nav v-if="userMessageMarkers.length" class="conversation-rail" aria-label="User prompts in this conversation">
      <button
        v-for="marker in userMessageMarkers"
        :key="marker.key"
        class="conversation-marker"
        :class="{ active: activeUserMessageIndex === marker.index }"
        :aria-label="`Jump to prompt: ${marker.preview}`"
        @click="scrollToUserMessage(marker.index)"
      >
        <span class="marker-dash" aria-hidden="true"></span>
        <span class="marker-tooltip" role="tooltip">
          <span>{{ marker.preview }}</span>
        </span>
      </button>
    </nav>
    <div ref="messagesContainer" class="messages-area" @scroll="handleScroll">
      <div class="messages-content">
        <div ref="sentinelEl" class="load-more-sentinel">
          <div v-if="loadingMore" class="load-more-indicator">Loading...</div>
        </div>
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
        <div
          v-for="(msg, index) in messages"
          :key="msg._id ?? msg.id ?? index"
          class="message-anchor"
          :data-message-index="index"
        >
          <MessageItem
            :message="msg"
            :trace-run-id="traceRunIdFor(msg)"
            :trace-summary="traceSummaryFor(msg)"
            @open-trace="emit('open-trace', $event)"
          />
        </div>
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

.conversation-rail {
  position: absolute;
  top: calc(50% - clamp(150px, 17vh, 190px));
  left: 8px;
  z-index: 32;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  width: 22px;
  padding: 4px 0;
}

.conversation-marker {
  position: relative;
  flex: 0 0 auto;
  width: 22px;
  height: 7px;
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.marker-dash {
  position: absolute;
  top: 3px;
  left: 7px;
  width: 8px;
  height: 1.5px;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.56;
  transition: width var(--transition-fast), opacity var(--transition-fast), transform var(--transition-fast);
}

.conversation-marker:hover,
.conversation-marker:focus-visible,
.conversation-marker.active {
  color: var(--accent);
}

.conversation-marker:hover .marker-dash,
.conversation-marker:focus-visible .marker-dash,
.conversation-marker.active .marker-dash {
  width: 14px;
  opacity: 1;
  transform: translateX(-3px);
}

.conversation-marker:focus-visible {
  outline: 1px solid var(--accent);
  outline-offset: 2px;
  border-radius: 3px;
}

.marker-tooltip {
  position: absolute;
  top: 50%;
  left: 25px;
  width: min(288px, calc(100vw - 68px));
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--bg-secondary);
  box-shadow: var(--shadow-md);
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.45;
  text-align: left;
  opacity: 0;
  visibility: hidden;
  transform: translate(3px, -50%);
  transition: opacity var(--transition-fast), transform var(--transition-fast), visibility var(--transition-fast);
}

.marker-tooltip span {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
}

.conversation-marker:hover .marker-tooltip,
.conversation-marker:focus-visible .marker-tooltip {
  opacity: 1;
  visibility: visible;
  transform: translate(0, -50%);
}

.message-anchor {
  scroll-margin-top: 20px;
}

.load-more-sentinel {
  height: 1px;
  width: 100%;
}

.load-more-indicator {
  text-align: center;
  padding: 12px 0;
  font-size: 12px;
  color: var(--text-muted);
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  overflow-anchor: none;
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
  padding: 0 clamp(34px, 3vw, 44px);
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
