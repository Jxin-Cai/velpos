<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { executeCommand } from '../api/terminalApi'
import { useDialogManager } from '@shared/lib/useDialogManager'

const props = defineProps({
  visible: { type: Boolean, required: true },
  projectDir: { type: String, default: '' },
  gitBranch: { type: String, default: '' },
})

const emit = defineEmits(['close', 'height-change'])

const visibleWrapper = {
  get value() {
    return props.visible
  },
  set value(newValue) {
    if (!newValue) emit('close')
  }
}

const { useDialog } = useDialogManager()
useDialog('terminal', visibleWrapper)

const drawerHeight = ref(parseInt(localStorage.getItem('pf_terminal_height')) || 360)
const tabs = ref([createTab(1)])
const activeTabId = ref(tabs.value[0].id)
const outputRef = ref(null)
let nextTabNo = 2
let _resizeOnMove = null
let _resizeOnUp = null

const activeTab = computed(() => tabs.value.find(tab => tab.id === activeTabId.value) || tabs.value[0])
const promptStr = computed(() => {
  const dir = props.projectDir || '~'
  return props.gitBranch ? `${dir} (${props.gitBranch}) >` : `${dir} >`
})

function createTab(no) {
  return {
    id: `terminal-${Date.now()}-${no}`,
    title: `term ${no}`,
    commandInput: '',
    entries: [],
    executing: false,
  }
}

function addTab() {
  const tab = createTab(nextTabNo++)
  tabs.value.push(tab)
  activeTabId.value = tab.id
  focusInput()
}

function closeTab(tabId) {
  if (tabs.value.length === 1) return
  const index = tabs.value.findIndex(tab => tab.id === tabId)
  tabs.value = tabs.value.filter(tab => tab.id !== tabId)
  if (activeTabId.value === tabId) {
    activeTabId.value = tabs.value[Math.max(index - 1, 0)]?.id || tabs.value[0].id
  }
}

function clearActiveTab() {
  if (activeTab.value?.executing) return
  activeTab.value.entries = []
}

function startResize(e) {
  e.preventDefault()
  _resizeOnMove = (ev) => {
    const h = window.innerHeight - ev.clientY
    drawerHeight.value = Math.max(220, Math.min(h, window.innerHeight * 0.75))
    emitHeight()
  }
  _resizeOnUp = () => {
    localStorage.setItem('pf_terminal_height', drawerHeight.value)
    window.removeEventListener('mousemove', _resizeOnMove)
    window.removeEventListener('mouseup', _resizeOnUp)
    _resizeOnMove = null
    _resizeOnUp = null
  }
  window.addEventListener('mousemove', _resizeOnMove)
  window.addEventListener('mouseup', _resizeOnUp)
}

async function handleSubmit() {
  const tab = activeTab.value
  const cmd = tab.commandInput.trim()
  if (!cmd || tab.executing) return
  tab.commandInput = ''
  tab.executing = true
  try {
    const result = await executeCommand(cmd, 30, props.projectDir || null)
    tab.entries.push({
      command: cmd,
      stdout: result.stdout || '',
      stderr: result.stderr || '',
      return_code: result.return_code,
      duration_ms: result.duration_ms,
    })
  } catch (err) {
    tab.entries.push({
      command: cmd,
      stdout: '',
      stderr: err.message || 'Command execution failed',
      return_code: -1,
      duration_ms: 0,
    })
  } finally {
    tab.executing = false
  }
}

function emitHeight() {
  emit('height-change', props.visible ? drawerHeight.value : 0)
}

function focusInput() {
  nextTick(() => document.querySelector('.terminal-input')?.focus())
}

function handleKeydown(e) {
  if (e.key === 'Escape' && props.visible) emit('close')
}

watch(() => props.visible, (val) => {
  emitHeight()
  if (val) focusInput()
})

watch(drawerHeight, emitHeight)
watch(() => activeTab.value?.entries.length, () => {
  nextTick(() => {
    if (outputRef.value) outputRef.value.scrollTop = outputRef.value.scrollHeight
  })
})

onMounted(() => document.addEventListener('keydown', handleKeydown))

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  emit('height-change', 0)
  if (_resizeOnMove) {
    window.removeEventListener('mousemove', _resizeOnMove)
    window.removeEventListener('mouseup', _resizeOnUp)
  }
})
</script>

<template>
  <transition name="terminal-dock">
    <section
      v-if="visible"
      class="terminal-dock"
      :style="{ height: drawerHeight + 'px' }"
      aria-label="Terminal drawer"
    >
      <div class="resize-handle" @mousedown="startResize"></div>
      <div class="terminal-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="terminal-tab"
          :class="{ active: tab.id === activeTabId }"
          @click="activeTabId = tab.id"
        >
          <span>{{ tab.title }}</span>
          <span v-if="tab.executing" class="tab-running"></span>
          <button class="tab-close" :disabled="tabs.length === 1" @click.stop="closeTab(tab.id)">×</button>
        </button>
        <button class="tab-add" title="New terminal" aria-label="New terminal" @click="addTab">+</button>
        <button class="btn-clear" :disabled="activeTab?.executing" @click="clearActiveTab">Clear</button>
        <button class="btn-close" aria-label="Close terminal" @click="$emit('close')">×</button>
      </div>
      <div class="terminal-env-banner" v-if="projectDir">
        <span class="env-cwd">{{ projectDir }}</span>
        <span v-if="gitBranch" class="env-branch">{{ gitBranch }}</span>
      </div>
      <div class="terminal-output" ref="outputRef">
        <div v-for="(entry, i) in activeTab.entries" :key="i" class="terminal-entry">
          <div class="terminal-command">{{ promptStr }} {{ entry.command }}</div>
          <div v-if="entry.stdout" class="terminal-stdout">{{ entry.stdout }}</div>
          <div v-if="entry.stderr" class="terminal-stderr">{{ entry.stderr }}</div>
          <div class="terminal-meta">
            <span :class="entry.return_code === 0 ? 'rc-success' : 'rc-error'">exit {{ entry.return_code }}</span>
            <span class="terminal-duration">{{ entry.duration_ms }}ms</span>
          </div>
        </div>
        <div v-if="!activeTab.entries.length" class="terminal-empty">No commands executed in this terminal yet</div>
      </div>
      <div class="terminal-input-area">
        <span class="terminal-prompt">{{ promptStr }}</span>
        <input
          class="terminal-input"
          v-model="activeTab.commandInput"
          :disabled="activeTab.executing"
          :placeholder="activeTab.executing ? 'Executing...' : 'Type a command...'"
          @keydown.enter="handleSubmit"
        />
      </div>
    </section>
  </transition>
</template>

<style scoped>
.terminal-dock {
  position: fixed;
  left: 280px;
  right: 24px;
  bottom: 0;
  z-index: 80;
  display: flex;
  flex-direction: column;
  max-height: 75vh;
  min-height: 220px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-bottom: none;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  box-shadow: var(--shadow-xl);
  overflow: hidden;
}

.resize-handle {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 8px;
  cursor: row-resize;
  z-index: 10;
}

.resize-handle:hover,
.resize-handle:active {
  background: var(--accent);
  opacity: 0.35;
}

.terminal-dock-enter-active,
.terminal-dock-leave-active {
  transition: transform 360ms cubic-bezier(0.22, 1, 0.36, 1), opacity 220ms ease;
}

.terminal-dock-enter-from,
.terminal-dock-leave-to {
  transform: translateY(105%);
  opacity: 0.2;
}

.terminal-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px 8px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.terminal-tab,
.tab-add,
.btn-clear,
.btn-close {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast);
}

.terminal-tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 8px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.terminal-tab.active,
.terminal-tab:hover,
.tab-add:hover,
.btn-clear:hover:not(:disabled),
.btn-close:hover {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}

.tab-running {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: var(--yellow);
  animation: pulse 1.2s ease-in-out infinite;
}

.tab-close {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  padding: 0 2px;
}

.tab-close:disabled {
  opacity: 0.25;
  cursor: not-allowed;
}

.tab-add,
.btn-close {
  width: 26px;
  height: 26px;
}

.btn-clear {
  margin-left: auto;
  padding: 5px 9px;
  font-size: 11px;
}

.btn-clear:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.terminal-env-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 16px;
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: nowrap;
}

.env-cwd { color: var(--purple); font-weight: 500; }
.env-branch { color: var(--green); font-weight: 500; }

.terminal-output {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  background: var(--bg-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
}

.terminal-entry { margin-bottom: 12px; }
.terminal-command { color: var(--green); font-weight: 500; }
.terminal-stdout,
.terminal-stderr { white-space: pre-wrap; word-break: break-all; }
.terminal-stdout { color: var(--text-primary); }
.terminal-stderr { color: var(--red); }
.terminal-meta { margin-top: 2px; font-size: 10px; display: flex; gap: 8px; }
.rc-success { color: var(--green); }
.rc-error { color: var(--red); }
.terminal-duration,
.terminal-empty { color: var(--text-muted); }
.terminal-empty { padding: 40px; text-align: center; }

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

.terminal-input::placeholder { color: var(--text-muted); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

@media (max-width: 768px) {
  .terminal-dock {
    left: 0;
    right: 0;
    border-left: none;
    border-right: none;
    border-radius: var(--radius-md) var(--radius-md) 0 0;
  }
}
</style>
