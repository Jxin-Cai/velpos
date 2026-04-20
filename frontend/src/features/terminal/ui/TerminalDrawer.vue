<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useTerminal } from '../model/useTerminal'
import { useDialogManager } from '@shared/lib/useDialogManager'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
  projectDir: {
    type: String,
    default: '',
  },
  gitBranch: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['close'])

// 创建包装对象来管理可见性
const visibleWrapper = {
  get value() {
    return props.visible
  },
  set value(newValue) {
    if (!newValue) {
      emit('close')
    }
  }
}

const { useDialog } = useDialogManager()
useDialog('terminal', visibleWrapper)

const { entries, executing, error, runCommand, clearEntries } = useTerminal()

const commandInput = ref('')
const outputRef = ref(null)

// Resizable drawer
const drawerWidth = ref(parseInt(localStorage.getItem('pf_terminal_width')) || 480)
const isResizing = ref(false)
let _resizeOnMove = null
let _resizeOnUp = null

function startResize(e) {
  e.preventDefault()
  isResizing.value = true
  _resizeOnMove = (ev) => {
    const w = window.innerWidth - ev.clientX
    drawerWidth.value = Math.max(280, Math.min(w, window.innerWidth * 0.8))
  }
  _resizeOnUp = () => {
    isResizing.value = false
    localStorage.setItem('pf_terminal_width', drawerWidth.value)
    window.removeEventListener('mousemove', _resizeOnMove)
    window.removeEventListener('mouseup', _resizeOnUp)
    _resizeOnMove = null
    _resizeOnUp = null
  }
  window.addEventListener('mousemove', _resizeOnMove)
  window.addEventListener('mouseup', _resizeOnUp)
}

// Prompt string built from session's project dir + git branch
const promptStr = computed(() => {
  const dir = props.projectDir || '~'
  const branch = props.gitBranch
  if (branch) return `${dir} (${branch}) >`
  return `${dir} >`
})

watch(() => entries.value.length, () => {
  nextTick(() => {
    if (outputRef.value) {
      outputRef.value.scrollTop = outputRef.value.scrollHeight
    }
  })
})

watch(() => props.visible, (val) => {
  if (val) {
    nextTick(() => {
      const input = document.querySelector('.terminal-input')
      if (input) input.focus()
    })
  }
})

async function handleSubmit() {
  const cmd = commandInput.value.trim()
  if (!cmd || executing.value) return
  commandInput.value = ''
  await runCommand(cmd, props.projectDir || null)
}

function handleOverlayClick(e) {
  if (e.target === e.currentTarget) {
    emit('close')
  }
}

function handleKeydown(e) {
  if (e.key === 'Escape' && props.visible) {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  if (_resizeOnMove) {
    window.removeEventListener('mousemove', _resizeOnMove)
    window.removeEventListener('mouseup', _resizeOnUp)
    _resizeOnMove = null
    _resizeOnUp = null
  }
})
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="drawer-overlay" @click="handleOverlayClick">
      <transition name="slide">
        <div v-if="visible" class="drawer" :style="{ width: drawerWidth + 'px' }" @click.stop>
          <div class="resize-handle" @mousedown="startResize"></div>
          <div class="drawer-header">
            <h3 class="drawer-title">Terminal</h3>
            <button class="btn-clear" :disabled="executing" @click="clearEntries">Clear</button>
          </div>
          <!-- Project path banner -->
          <div class="terminal-env-banner" v-if="projectDir">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span class="env-cwd">{{ projectDir }}</span>
            <span v-if="gitBranch" class="env-branch">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="6" y1="3" x2="6" y2="15"/>
                <circle cx="18" cy="6" r="3"/>
                <circle cx="6" cy="18" r="3"/>
                <path d="M18 9a9 9 0 0 1-9 9"/>
              </svg>
              {{ gitBranch }}
            </span>
          </div>
          <div class="terminal-output" ref="outputRef">
            <div v-for="(entry, i) in entries" :key="i" class="terminal-entry">
              <div class="terminal-command">{{ promptStr }} {{ entry.command }}</div>
              <div v-if="entry.stdout" class="terminal-stdout">{{ entry.stdout }}</div>
              <div v-if="entry.stderr" class="terminal-stderr">{{ entry.stderr }}</div>
              <div class="terminal-meta">
                <span :class="entry.return_code === 0 ? 'rc-success' : 'rc-error'">
                  exit {{ entry.return_code }}
                </span>
                <span class="terminal-duration">{{ entry.duration_ms }}ms</span>
              </div>
            </div>
            <div v-if="!entries.length" class="terminal-empty">No commands executed yet</div>
          </div>
          <div class="terminal-input-area">
            <span class="terminal-prompt">{{ promptStr }}</span>
            <input
              class="terminal-input"
              v-model="commandInput"
              :disabled="executing"
              :placeholder="executing ? 'Executing...' : 'Type a command...'"
              @keydown.enter="handleSubmit"
              autofocus
            />
          </div>
        </div>
      </transition>
    </div>
  </Teleport>
</template>

<style scoped>
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-overlay);
  z-index: 100;
}

.drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  max-width: calc(100vw - 32px);
  background: var(--bg-secondary);
  border-left: 1px solid var(--border);
  box-shadow: var(--shadow-xl);
  display: flex;
  flex-direction: column;
}

.resize-handle {
  position: absolute;
  top: 0;
  left: -3px;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  z-index: 10;
}

.resize-handle:hover,
.resize-handle:active {
  background: var(--accent);
  opacity: 0.3;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 200ms ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}

.drawer-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.drawer-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.btn-clear {
  font-size: 11px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.btn-clear:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.btn-clear:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Env banner */
.terminal-env-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 12px;
  flex-shrink: 0;
  overflow-x: auto;
  white-space: nowrap;
  color: var(--text-secondary);
}

.env-cwd {
  color: var(--purple);
  font-weight: 500;
}

.env-branch {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--green);
  font-weight: 500;
  margin-left: 4px;
}

.terminal-output {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  background: var(--bg-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
}

.terminal-entry {
  margin-bottom: 12px;
}

.terminal-command {
  color: var(--green);
  font-weight: 500;
}

.terminal-stdout {
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-all;
}

.terminal-stderr {
  color: var(--red);
  white-space: pre-wrap;
  word-break: break-all;
}

.terminal-meta {
  margin-top: 2px;
  font-size: 10px;
  display: flex;
  gap: 8px;
}

.rc-success {
  color: var(--green);
}

.rc-error {
  color: var(--red);
}

.terminal-duration {
  color: var(--text-muted);
}

.terminal-empty {
  color: var(--text-muted);
  padding: 40px;
  text-align: center;
}

.terminal-input-area {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
  gap: 8px;
}

.terminal-prompt {
  color: var(--green);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.terminal-input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 13px;
  outline: none;
}

.terminal-input::placeholder {
  color: var(--text-muted);
}

@media (max-width: 768px) {
  .drawer {
    width: 100vw !important;
    max-width: 100vw;
  }
  .resize-handle {
    display: none;
  }
}
</style>
