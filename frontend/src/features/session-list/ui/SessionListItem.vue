<script setup>
import { ref, computed, nextTick, onBeforeUnmount } from 'vue'

const props = defineProps({
  session: {
    type: Object,
    required: true,
  },
  active: {
    type: Boolean,
    default: false,
  },
  selectable: {
    type: Boolean,
    default: false,
  },
  selected: {
    type: Boolean,
    default: false,
  },
  pinned: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['select', 'delete', 'rename', 'toggle-select', 'toggle-pin'])

const isClaudeCode = computed(() => props.session.source === 'claude-code')

const showDeleteConfirm = ref(false)
const editing = ref(false)
const editName = ref('')
const editInput = ref(null)
const copySuccess = ref(false)
let confirmTimer = null
let copyTimer = null

function requestDelete() {
  showDeleteConfirm.value = true
  clearTimeout(confirmTimer)
  confirmTimer = setTimeout(() => {
    showDeleteConfirm.value = false
  }, 3000)
}

function confirmDelete() {
  clearTimeout(confirmTimer)
  showDeleteConfirm.value = false
  emit('delete', props.session.session_id)
}

function cancelDelete() {
  clearTimeout(confirmTimer)
  showDeleteConfirm.value = false
}

function getShortId(id) {
  return id ? id.substring(0, 8) : ''
}

const displayName = computed(() => {
  return props.session.name || getShortId(props.session.session_id)
})

const modelShortName = computed(() => {
  const m = props.session.model || ''
  if (m.includes('sonnet')) return 'Sonnet'
  if (m.includes('opus')) return 'Opus'
  if (m.includes('haiku')) return 'Haiku'
  // Take last segment after last hyphen for unknown models
  const parts = m.split('-')
  return parts.length > 1 ? parts.slice(-2).join('-') : m
})

const isActive = computed(() => {
  return props.session.status === 'running'
})

const statusLabel = computed(() => {
  return isActive.value ? 'Active' : 'Inactive'
})

const formattedTime = computed(() => {
  const t = props.session.updated_time
  if (!t) return ''
  const d = new Date(t)
  const now = new Date()
  const diffMs = now - d
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  if (diffDay < 7) return `${diffDay}d ago`
  return d.toLocaleDateString()
})

function getStatusClass(status) {
  if (status === 'running') return 'status-running'
  if (status === 'error') return 'status-error'
  return 'status-idle'
}

const statusDotClass = computed(() => {
  if (isClaudeCode.value) return 'status-claude'
  if (props.session.status === 'running') return 'status-running'
  if (props.session.status === 'error') return 'status-error'
  return 'status-idle'
})

const imChannelLabel = computed(() => {
  const ct = props.session.im_binding?.channel_type || ''
  const labels = { lark: 'Lark', openim: 'IM', qq: 'QQ', weixin: 'WeChat' }
  return labels[ct] || ct
})

function startEditing() {
  editing.value = true
  editName.value = displayName.value
  nextTick(() => {
    editInput.value?.focus()
    editInput.value?.select()
  })
}

function submitRename() {
  const trimmed = editName.value.trim()
  editing.value = false
  if (trimmed && trimmed !== (props.session.name || '')) {
    emit('rename', { sessionId: props.session.session_id, name: trimmed })
  }
}

function cancelEditing() {
  editing.value = false
}

async function copySessionId() {
  try {
    await navigator.clipboard.writeText(props.session.session_id)
    copySuccess.value = true
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => {
      copySuccess.value = false
    }, 1500)
  } catch (err) {
    console.error('Failed to copy session ID:', err)
  }
}

onBeforeUnmount(() => {
  clearTimeout(confirmTimer)
  clearTimeout(copyTimer)
})
</script>

<template>
  <div
    class="session-item"
    :class="{ active, 'is-claude-code': isClaudeCode, 'is-selected': selected, 'is-pinned': pinned }"
    @click="selectable ? emit('toggle-select', session.session_id) : emit('select', session.session_id)"
    role="button"
    tabindex="0"
    :aria-label="'Session ' + getShortId(session.session_id)"
    @keydown.enter="selectable ? emit('toggle-select', session.session_id) : emit('select', session.session_id)"
  >
    <Transition name="confirm-swap" mode="out-in">
    <div v-if="!showDeleteConfirm" key="normal">
      <div class="session-main">
        <label v-if="selectable" class="select-checkbox" @click.stop>
          <input
            type="checkbox"
            :checked="selected"
            @change="emit('toggle-select', session.session_id)"
          />
          <span class="checkbox-mark"></span>
        </label>
        <span
          v-else
          class="status-dot"
          :class="statusDotClass"
          :aria-label="isClaudeCode ? 'claude-code' : (session.status || 'idle')"
        ></span>
        <template v-if="editing && !isClaudeCode">
          <input
            ref="editInput"
            v-model="editName"
            class="rename-input"
            @click.stop
            @keydown.enter.stop="submitRename"
            @keydown.escape.stop="cancelEditing"
            @blur="submitRename"
            placeholder="Session name"
          />
        </template>
        <template v-else>
          <span class="session-name" @dblclick.stop="!isClaudeCode && startEditing()">
            {{ displayName }}
          </span>
          <span class="action-buttons">
            <button
              class="pin-btn"
              :class="{ pinned }"
              @click.stop="emit('toggle-pin', session.session_id)"
              :aria-label="pinned ? 'Unpin session' : 'Pin session'"
              :title="pinned ? 'Unpin' : 'Pin'"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="17" x2="12" y2="22"/>
                <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z"/>
              </svg>
            </button>
            <button
              class="copy-btn"
              @click.stop="copySessionId"
              :class="{ 'copy-success': copySuccess }"
              aria-label="Copy session ID"
              title="Copy session ID"
            >
              <svg v-if="!copySuccess" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </button>
            <button
              class="delete-btn"
              @click.stop="requestDelete"
              aria-label="Delete session"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </span>
        </template>
      </div>
      <div class="session-meta">
        <span v-if="session.im_binding" class="im-badge" :title="'IM: ' + session.im_binding.channel_type">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          {{ imChannelLabel }}
        </span>
        <span v-if="formattedTime" class="session-time">{{ formattedTime }}</span>
      </div>
    </div>

    <div v-else key="confirm">
      <div class="delete-confirm" @click.stop>
        <span class="confirm-text">Delete?</span>
        <button class="confirm-yes" @click.stop="confirmDelete">Yes</button>
        <button class="confirm-no" @click.stop="cancelDelete">No</button>
      </div>
    </div>
    </Transition>
  </div>
</template>

<style scoped>
.session-item {
  padding: 10px 12px;
  cursor: pointer;
  border-left: 3px solid transparent;
  min-height: 48px;
  box-sizing: border-box;
  transition:
    background 200ms cubic-bezier(0.4, 0, 0.2, 1),
    border-color 200ms cubic-bezier(0.4, 0, 0.2, 1),
    box-shadow var(--transition-fast);
  position: relative;
}

.session-item::after {
  content: '';
  position: absolute;
  left: 0;
  top: 4px;
  bottom: 4px;
  width: 3px;
  background: var(--accent);
  border-radius: 0 2px 2px 0;
  transform: scaleY(0);
  transition: transform 150ms cubic-bezier(0.4, 0, 0.2, 1);
}

.session-item:hover {
  background: var(--bg-hover);
}

.session-item:active {
  background: var(--bg-hover);
  transform: scale(0.995);
  transition-duration: 100ms;
}

.session-item.active {
  background: var(--accent-dim);
}

.session-item.active::after {
  transform: scaleY(1);
}

.session-item.active .session-name {
  color: var(--text-primary);
}

.session-item.is-claude-code:hover {
  background: var(--bg-hover);
}

.session-item:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.session-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-idle {
  background: var(--green);
}

.status-running {
  background: var(--yellow, #f59e0b);
  animation: pulse 1.5s ease-in-out infinite;
}

.status-error {
  background: var(--red);
}

.status-claude {
  background: var(--purple, #a78bfa);
}

.source-tag {
  font-size: 9px;
  font-weight: 600;
  padding: 0 4px;
  border-radius: 3px;
  background: var(--purple-dim);
  color: var(--purple);
  flex-shrink: 0;
  letter-spacing: 0.5px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.session-name {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-secondary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  transition: color var(--transition-fast);
}

.rename-input {
  flex: 1;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--bg-input);
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  padding: 1px 6px;
  outline: none;
}

.action-buttons {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  width: 0;
  overflow: hidden;
  transition: opacity 0.15s, width 0.15s;
  margin-left: 4px;
}

.session-item:hover .action-buttons {
  opacity: 1;
  width: 68px;
}

.pin-btn,
.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  padding: 0;
}

.pin-btn:hover,
.pin-btn.pinned {
  background: var(--accent-dim);
  color: var(--accent);
}

.session-item.is-pinned .session-name {
  color: var(--text-primary);
}

.session-item.is-pinned .status-dot {
  box-shadow: 0 0 0 2px var(--accent), 0 0 0 5px var(--accent-dim);
}

.copy-btn:hover {
  background: var(--accent-dim);
  color: var(--accent);
}

.copy-btn.copy-success {
  color: var(--green);
}

.copy-btn.copy-success:hover {
  background: var(--green-dim);
}

.delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  padding: 0;
}

.delete-btn:hover {
  background: var(--red-dim);
  color: var(--red);
}

.session-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  padding-left: 16px;
  font-size: 11px;
  color: var(--text-muted);
}

.session-status {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  white-space: nowrap;
}

.session-model {
  font-size: 10px;
  font-family: var(--font-mono);
  padding: 1px 5px;
  border-radius: 6px;
  background: var(--accent-dim);
  color: var(--accent);
  white-space: nowrap;
  max-width: 70px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-status.active {
  background: var(--green-dim);
  color: var(--green);
}

.session-time {
  white-space: nowrap;
}

.im-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 6px;
  background: var(--blue-dim, rgba(59, 130, 246, 0.1));
  color: var(--blue, #3b82f6);
  white-space: nowrap;
}

.session-branch {
  font-size: 10px;
  font-family: var(--font-mono);
  padding: 1px 5px;
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  white-space: nowrap;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Delete confirmation */
.delete-confirm {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 26px;
}

.confirm-text {
  font-size: 13px;
  color: var(--text-secondary);
  flex: 1;
}

.confirm-yes,
.confirm-no {
  border: none;
  border-radius: var(--radius-sm);
  padding: 2px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.confirm-yes {
  background: var(--red-dim);
  color: var(--red);
}

.confirm-yes:hover {
  background: var(--red-dim);
  filter: brightness(1.3);
}

.confirm-no {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.confirm-no:hover {
  background: var(--bg-hover);
}

/* Selection mode */
.session-item.is-selected {
  background: var(--accent-dim);
}

.select-checkbox {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  cursor: pointer;
  position: relative;
}

.select-checkbox input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.checkbox-mark {
  width: 14px;
  height: 14px;
  border: 1.5px solid var(--text-muted);
  border-radius: 3px;
  transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  display: flex;
  align-items: center;
  justify-content: center;
}

.select-checkbox input:checked + .checkbox-mark {
  background: var(--accent);
  border-color: var(--accent);
  transform: scale(1.1);
}

.select-checkbox input:checked + .checkbox-mark::after {
  content: '';
  width: 4px;
  height: 7px;
  border: solid var(--text-on-accent);
  border-width: 0 2px 2px 0;
  transform: rotate(45deg) translateY(-1px);
}

.select-checkbox:active .checkbox-mark {
  transform: scale(0.85);
  transition-duration: 0.1s;
}

/* Confirm swap transition */
.confirm-swap-enter-active,
.confirm-swap-leave-active {
  transition: opacity 120ms var(--ease-smooth);
}
.confirm-swap-enter-from,
.confirm-swap-leave-to {
  opacity: 0;
}
</style>
