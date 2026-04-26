<script setup>
import { ref, shallowRef, watch, onMounted, nextTick, inject } from 'vue'
import { configuredMarked } from '../lib/markdownConfig'
import { openPath } from '@features/terminal'
import AssistantBlock from './AssistantBlock.vue'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolUseBlock from './ToolUseBlock.vue'
import ToolResultBlock from './ToolResultBlock.vue'
import ResultBlock from './ResultBlock.vue'
import SystemBlock from './SystemBlock.vue'
import UserChoiceBlock from './UserChoiceBlock.vue'
import PermissionRequestBlock from './PermissionRequestBlock.vue'
import TodoProgressBlock from './TodoProgressBlock.vue'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['select-user'])

const wsConnection = inject('wsConnection')

// Track whether interactive messages have been answered
const interactiveAnswered = ref(false)

function handleChoiceAnswer(data) {
  if (interactiveAnswered.value) return
  interactiveAnswered.value = true
  if (wsConnection?.value) {
    wsConnection.value.send({ action: 'user_response', data })
  }
}

function handlePermissionRespond(data) {
  if (interactiveAnswered.value) return
  interactiveAnswered.value = true
  if (wsConnection?.value) {
    wsConnection.value.send({ action: 'user_response', data })
  }
}

// User message collapse state
const userTextEl = ref(null)
const isUserMsgExpanded = ref(false)
const isUserMsgOverflow = ref(false)
const isUserMsgSelected = ref(false)
const USER_MSG_MAX_HEIGHT = 144 // ~6 lines at 24px line-height

onMounted(() => {
  nextTick(() => {
    if (userTextEl.value && userTextEl.value.scrollHeight > USER_MSG_MAX_HEIGHT) {
      isUserMsgOverflow.value = true
    }
  })
})

function handleUserMarkerClick() {
  if (!userTextEl.value) return
  // Select the user message text content
  const range = document.createRange()
  range.selectNodeContents(userTextEl.value)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(range)
  isUserMsgSelected.value = true
}

// Markdown parse cache: keyed by text content to avoid re-parsing unchanged blocks
const _mdCache = new Map()
function cachedParse(text) {
  if (!text) return ''
  const cached = _mdCache.get(text)
  if (cached) return cached
  const html = configuredMarked(text)
  // Keep cache bounded
  if (_mdCache.size > 500) {
    const firstKey = _mdCache.keys().next().value
    _mdCache.delete(firstKey)
  }
  _mdCache.set(text, html)
  return html
}

const renderedBlocks = shallowRef([])

watch(
  () => props.message,
  (msg) => {
    if (!msg) { renderedBlocks.value = []; return }

    const content = msg.content || {}

    if (msg.type === 'user') {
      renderedBlocks.value = [{
        type: 'user',
        html: cachedParse(content.text || ''),
        attachments: content.attachments || [],
      }]
      return
    }

    if (msg.type === 'assistant') {
      const blocks = content.blocks || []
      renderedBlocks.value = blocks.map((block) => {
        if (block.type === 'text') {
          return { ...block, html: cachedParse(block.text || '') }
        }
        if (block.type === 'thinking') {
          return { ...block }
        }
        // Convert TodoWrite tool_use into visual todo_progress block
        if (block.type === 'tool_use' && block.name === 'TodoWrite' && block.input?.todos) {
          return {
            type: 'todo_progress',
            todos: block.input.todos.map(t => ({
              subject: t.subject || t.content || '',
              status: t.status || 'pending',
              description: t.description || '',
              activeForm: t.activeForm || '',
            })),
          }
        }
        return block
      })
      return
    }

    if (msg.type === 'result') {
      renderedBlocks.value = [{
        type: 'result',
        html: content.text ? cachedParse(content.text) : '',
        meta: {
          duration: content.duration_ms,
          turns: content.num_turns,
          usage: content.usage,
          is_error: content.is_error,
        },
      }]
      return
    }

    if (msg.type === 'tool_result') {
      renderedBlocks.value = (content.results || []).map((r) => ({
        type: 'tool_result',
        tool_use_id: r.tool_use_id,
        content: r.content,
        is_error: r.is_error,
      }))
      return
    }

    if (msg.type === 'system') {
      const subtype = content.subtype || ''
      let text = subtype
      if (content.description) text += `: ${content.description}`
      if (content.status) text += ` [${content.status}]`
      if (content.summary) text += ` - ${content.summary}`
      if (content.last_tool_name) text += ` (${content.last_tool_name})`
      renderedBlocks.value = [{ type: 'system', text: text || JSON.stringify(content) }]
      return
    }

    if (msg.type === 'interactive') {
      if (content.interaction_type === 'user_choice') {
        renderedBlocks.value = [{ type: 'user_choice', input: { questions: content.questions }, tool_name: content.tool_name }]
        return
      }
      if (content.interaction_type === 'permission') {
        renderedBlocks.value = [{ type: 'permission', tool_name: content.tool_name, tool_input: content.tool_input }]
        return
      }
    }

    renderedBlocks.value = []
  },
  { immediate: true, deep: true },
)

function attachmentHref(attachment) {
  if (!attachment?.id) return '#'
  return `/api/attachments/${encodeURIComponent(attachment.id)}/download`
}

function attachmentName(attachment) {
  return attachment?.filename || attachment?.name || 'attachment'
}

function attachmentSize(attachment) {
  const n = Number(attachment?.size_bytes || attachment?.size || 0)
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  if (n >= 1024) return `${Math.round(n / 1024)} KB`
  return `${n} B`
}

// Event delegation for code copy buttons and file path links
function handleDelegatedClick(e) {
  // Handle code copy button
  const btn = e.target.closest('.code-copy-btn')
  if (btn) {
    e.stopPropagation()
    const wrapper = btn.closest('.code-block-wrapper')
    if (!wrapper) return
    const code = wrapper.querySelector('pre code')
    if (!code) return
    navigator.clipboard.writeText(code.textContent || '').then(() => {
      btn.classList.add('copied')
      setTimeout(() => btn.classList.remove('copied'), 1500)
    }).catch(() => {})
    return
  }

  // Handle file path link
  const fileLink = e.target.closest('.file-path-link')
  if (fileLink) {
    e.preventDefault()
    e.stopPropagation()
    const filePath = fileLink.getAttribute('data-file-path')
    if (filePath) {
      openPath(filePath).catch(() => {})
    }
  }
}
</script>

<template>
  <div class="message-item" :class="`type-${message.type}`" @click="handleDelegatedClick">
    <template v-for="(block, i) in renderedBlocks" :key="i">
      <!-- User message -->
      <div v-if="block.type === 'user'" class="msg-user" :class="{ 'msg-user--selected': isUserMsgSelected }">
        <button
          class="user-marker"
          @click.stop="handleUserMarkerClick"
          title="Click to select message text"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
        </button>
        <div class="user-content">
          <div
            ref="userTextEl"
            class="user-text markdown-body"
            :class="{ 'user-text-collapsed': isUserMsgOverflow && !isUserMsgExpanded }"
            v-html="block.html"
          ></div>
          <div v-if="block.attachments?.length" class="user-attachments">
            <a
              v-for="attachment in block.attachments"
              :key="attachment.id || attachment.filename"
              class="user-attachment"
              :href="attachmentHref(attachment)"
              target="_blank"
              rel="noreferrer"
              :title="attachmentName(attachment)"
            >
              <span class="user-attachment-icon">FILE</span>
              <span class="user-attachment-name">{{ attachmentName(attachment) }}</span>
              <span class="user-attachment-size">{{ attachmentSize(attachment) }}</span>
            </a>
          </div>
          <button
            v-if="isUserMsgOverflow"
            class="user-expand-btn"
            @click="isUserMsgExpanded = !isUserMsgExpanded"
          >
            {{ isUserMsgExpanded ? 'Show less' : 'Show more' }}
          </button>
        </div>
      </div>
      <AssistantBlock
        v-else-if="block.type === 'text'"
        :block="block"
      />
      <ThinkingBlock
        v-else-if="block.type === 'thinking'"
        :block="block"
      />
      <TodoProgressBlock
        v-else-if="block.type === 'todo_progress'"
        :todos="block.todos"
      />
      <ToolUseBlock
        v-else-if="block.type === 'tool_use'"
        :block="block"
      />
      <ToolResultBlock
        v-else-if="block.type === 'tool_result'"
        :result="block"
      />
      <ResultBlock
        v-else-if="block.type === 'result'"
        :result="block"
      />
      <SystemBlock
        v-else-if="block.type === 'system'"
        :content="block.text"
      />
      <UserChoiceBlock
        v-else-if="block.type === 'user_choice'"
        :block="block"
        :answered="interactiveAnswered"
        @answer="handleChoiceAnswer"
      />
      <PermissionRequestBlock
        v-else-if="block.type === 'permission'"
        :block="block"
        :answered="interactiveAnswered"
        @respond="handlePermissionRespond"
      />
    </template>
  </div>
</template>

<style scoped>
.message-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.message-item.type-user {
  margin-top: 20px;
}

.message-item.type-assistant {
  margin-top: 4px;
}

.message-item.type-result {
  margin-top: 4px;
  margin-bottom: 8px;
}

.message-item.type-tool_result {
  margin-top: 0;
}

.msg-user {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.user-marker {
  flex-shrink: 0;
  color: var(--accent);
  margin-top: 2px;
  display: flex;
  align-items: center;
  background: none;
  border: none;
  padding: 2px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast), color var(--transition-fast);
}

.user-marker:hover {
  background: var(--accent-dim);
  color: var(--accent);
}

.msg-user--selected .user-marker {
  background: var(--accent-dim);
}

.user-content {
  flex: 1;
  min-width: 0;
}

.user-text {
  line-height: 1.6;
  word-break: break-word;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
}

.user-text-collapsed {
  max-height: 144px;
  overflow: hidden;
  mask-image: linear-gradient(to bottom, black 60%, transparent 100%);
  -webkit-mask-image: linear-gradient(to bottom, black 60%, transparent 100%);
}

.user-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.user-attachment {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 260px;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 12px;
}

.user-attachment:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.user-attachment-icon {
  flex-shrink: 0;
  color: var(--accent);
  font-size: 10px;
  font-weight: 700;
}

.user-attachment-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-attachment-size {
  flex-shrink: 0;
  color: var(--text-muted);
}

.user-expand-btn {
  display: block;
  background: none;
  border: none;
  color: var(--accent);
  font-size: 11px;
  cursor: pointer;
  padding: 4px 0 0;
  font-family: var(--font-sans);
}

.user-expand-btn:hover {
  text-decoration: underline;
}
</style>
