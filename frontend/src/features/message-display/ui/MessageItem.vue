<script setup>
import { ref, shallowRef, watch, onMounted, nextTick, inject } from 'vue'
import { cachedParse } from '../lib/markdownConfig'
import { buildSystemMessageBlock } from '../lib/systemMessageBlock'
import { visibleUserText } from '../lib/userMessageText'
import AssistantBlock from './AssistantBlock.vue'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolUseBlock from './ToolUseBlock.vue'
import ToolResultBlock from './ToolResultBlock.vue'
import ResultBlock from './ResultBlock.vue'
import SystemBlock from './SystemBlock.vue'
import UserChoiceBlock from './UserChoiceBlock.vue'
import PermissionRequestBlock from './PermissionRequestBlock.vue'
import TodoProgressBlock from './TodoProgressBlock.vue'
import ArtifactBlock from './ArtifactBlock.vue'
import MessageAttachmentCard from './MessageAttachmentCard.vue'
import { TraceButton } from '@features/trace-viewer'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
  traceRunId: { type: String, default: '' },
  traceSummary: { type: Object, default: null },
  interactiveAnswered: { type: Boolean, default: false },
  projectId: { type: String, default: '' },
  sessionId: { type: String, default: '' },
  presentation: { type: String, default: 'standard' },
})

const emit = defineEmits(['open-trace', 'open-file', 'interactive-answered'])

const wsConnection = inject('wsConnection')

const interactiveError = ref('')

function handleInteractiveResponse(data) {
  if (props.interactiveAnswered) return
  if (wsConnection?.value && wsConnection.value.send({ action: 'user_response', data })) {
    emit('interactive-answered', data)
    interactiveError.value = ''
    return
  }
  interactiveError.value = 'Connection lost. Reopen this session and try again.'
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

const renderedBlocks = shallowRef([])

watch(
  () => props.message,
  (msg) => {
    if (!msg) { renderedBlocks.value = []; return }

    const content = msg.content || {}

    if (msg.type === 'user') {
      renderedBlocks.value = [{
        type: 'user',
        html: cachedParse(visibleUserText(content)),
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
        type: content.is_error ? 'result' : 'text',
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

    if (msg.type === 'error') {
      renderedBlocks.value = [{
        type: 'result',
        html: cachedParse(content.text || content.message || 'Unknown error'),
        meta: { is_error: true },
      }]
      return
    }

    if (msg.type === 'artifact') {
      renderedBlocks.value = [{
        type: 'artifact',
        ...content,
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
      if (content.is_error || content.error) {
        renderedBlocks.value = [{
          type: 'result',
          html: cachedParse(content.message || content.error || 'Unknown error'),
          meta: { is_error: true },
        }]
        return
      }
      const block = buildSystemMessageBlock(content)
      renderedBlocks.value = [{
        ...block,
        html: block.markdown ? cachedParse(block.markdown) : '',
      }]
      return
    }

    if (msg.type === 'interactive') {
      if (content.interaction_type === 'user_choice') {
        renderedBlocks.value = [{
          type: 'user_choice',
          input: { questions: content.questions },
          tool_name: content.tool_name,
          answers: content.interaction_response?.answers || content.answers || {},
        }]
        return
      }
      if (content.interaction_type === 'permission') {
        renderedBlocks.value = [{ type: 'permission', tool_name: content.tool_name, tool_input: content.tool_input }]
        return
      }
    }

    renderedBlocks.value = []
  },
  { immediate: true },
)

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
      emit('open-file', filePath)
    }
  }
}
</script>

<template>
  <div
    class="message-item"
    :class="[`type-${message.type}`, `presentation-${presentation}`]"
    @click="handleDelegatedClick"
  >
    <div v-if="presentation === 'final'" class="final-answer-label">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" aria-hidden="true">
        <path d="m5 12 4 4L19 6" />
      </svg>
      <span>Final answer</span>
    </div>
    <template v-for="(block, i) in renderedBlocks" :key="i">
      <!-- User message -->
      <div v-if="block.type === 'user'" class="msg-user" :class="{ 'msg-user--selected': isUserMsgSelected }">
        <div class="user-actions">
          <button
            type="button"
            class="user-marker"
            @click.stop="handleUserMarkerClick"
            title="Click to select message text"
            aria-label="选择该用户消息文本"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </button>
          <TraceButton
            :run-id="traceRunId"
            :summary="traceSummary"
            @open-trace="emit('open-trace', $event)"
          />
        </div>
        <div class="user-content">
          <div
            ref="userTextEl"
            class="user-text markdown-body"
            :class="{ 'user-text-collapsed': isUserMsgOverflow && !isUserMsgExpanded }"
            v-html="block.html"
          ></div>
          <div v-if="block.attachments?.length" class="user-attachments">
            <MessageAttachmentCard
              v-for="attachment in block.attachments"
              :key="attachment.id || attachment.filename"
              :attachment="attachment"
              :project-id="projectId"
              :session-id="sessionId"
              @open-file="emit('open-file', $event)"
            />
          </div>
          <button
            v-if="isUserMsgOverflow"
            type="button"
            class="user-expand-btn"
            :aria-expanded="isUserMsgExpanded"
            @click.stop="isUserMsgExpanded = !isUserMsgExpanded"
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
      <ArtifactBlock
        v-else-if="['artifact', 'attachment', 'file', 'image', 'output_file'].includes(block.type)"
        :block="block"
        @open-file="emit('open-file', $event)"
      />
      <SystemBlock
        v-else-if="block.type === 'system'"
        :content="block.text"
        :html="block.html"
      />
      <UserChoiceBlock
        v-else-if="block.type === 'user_choice'"
        :block="block"
        :answered="interactiveAnswered"
        @answer="handleInteractiveResponse"
      />
      <PermissionRequestBlock
        v-else-if="block.type === 'permission'"
        :block="block"
        :answered="interactiveAnswered"
        @respond="handleInteractiveResponse"
      />
    </template>
    <p v-if="interactiveError" class="interactive-error" role="alert">
      {{ interactiveError }}
    </p>
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

.message-item.presentation-final {
  margin-top: 14px;
  padding: 18px clamp(16px, 2vw, 24px);
  border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--border-subtle));
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--bg-secondary) 88%, var(--accent-dim));
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.08);
}

.final-answer-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.final-answer-label svg {
  flex: 0 0 auto;
}

.msg-user {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.user-actions {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
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

.user-marker:focus-visible,
.user-expand-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
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
  gap: 8px;
  margin-top: 10px;
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

.interactive-error {
  margin: 8px 0 0;
  color: var(--danger, #ef5b5b);
  font-size: 12px;
  line-height: 1.4;
}
</style>
