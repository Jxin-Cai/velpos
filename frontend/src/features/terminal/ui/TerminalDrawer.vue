<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
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
const terminalContainerRef = ref(null)
let nextTabNo = 2
let resizeOnMove = null
let resizeOnUp = null

const activeTab = computed(() => tabs.value.find(tab => tab.id === activeTabId.value) || tabs.value[0])
const activeStatus = computed(() => activeTab.value?.status || 'idle')
const terminalLocation = computed(() => {
  const cwd = activeTab.value?.cwd || props.projectDir || '~'
  return props.gitBranch ? `${cwd} (${props.gitBranch})` : cwd
})

function createTab(no) {
  return {
    id: `terminal-${Date.now()}-${no}`,
    title: `term ${no}`,
    status: 'idle',
    terminalId: '',
    cwd: props.projectDir || '',
    shell: '',
    ws: null,
    xterm: null,
    fitAddon: null,
  }
}

function terminalWsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/terminal`
}

function createXterm(tab) {
  if (tab.xterm) return
  const xterm = new Terminal({
    cursorBlink: true,
    fontSize: 12,
    fontFamily: 'var(--font-mono), Menlo, Monaco, "Courier New", monospace',
    theme: {
      background: '#090d14',
      foreground: '#d6deeb',
      cursor: '#d6deeb',
    },
    convertEol: false,
    scrollback: 10000,
  })
  const fitAddon = new FitAddon()
  xterm.loadAddon(fitAddon)
  tab.xterm = xterm
  tab.fitAddon = fitAddon

  xterm.onData((data) => {
    sendInput(tab, data)
  })

  xterm.onResize(({ cols, rows }) => {
    if (tab.ws?.readyState === WebSocket.OPEN) {
      tab.ws.send(JSON.stringify({ action: 'resize', cols, rows }))
    }
  })
}

function mountXterm(tab) {
  if (!terminalContainerRef.value || !tab.xterm) return
  if (tab.xterm.element) return
  const wrapper = document.createElement('div')
  wrapper.className = 'xterm-tab-wrapper'
  wrapper.style.height = '100%'
  wrapper.style.display = tab.id === activeTabId.value ? '' : 'none'
  wrapper.dataset.tabId = tab.id
  terminalContainerRef.value.appendChild(wrapper)
  tab.xterm.open(wrapper)
  nextTick(() => tab.fitAddon?.fit())
}

function connectTab(tab) {
  if (!props.visible || tab.ws?.readyState === WebSocket.OPEN || tab.ws?.readyState === WebSocket.CONNECTING) return
  tab.status = 'connecting'

  createXterm(tab)

  const ws = new WebSocket(terminalWsUrl())
  tab.ws = ws

  ws.onopen = () => {
    const fitAddon = tab.fitAddon
    let cols = 80, rows = 24
    if (fitAddon && tab.xterm?.element) {
      fitAddon.fit()
      cols = tab.xterm.cols
      rows = tab.xterm.rows
    }
    ws.send(JSON.stringify({ cwd: props.projectDir || null, cols, rows }))
  }
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    if (message.event === 'ready') {
      tab.status = 'connected'
      tab.terminalId = message.terminal_id || ''
      tab.cwd = message.cwd || tab.cwd
      tab.shell = message.shell || ''
      return
    }
    if (message.event === 'output') {
      tab.xterm?.write(message.data || '')
      return
    }
    if (message.event === 'closed') {
      tab.status = 'closed'
    }
  }
  ws.onerror = () => {
    tab.status = 'error'
  }
  ws.onclose = () => {
    tab.status = tab.status === 'error' ? 'error' : 'closed'
    tab.ws = null
  }
}

function ensureActiveTerminal() {
  const tab = activeTab.value
  if (!tab) return
  createXterm(tab)
  nextTick(() => {
    mountXterm(tab)
    connectTab(tab)
    nextTick(() => {
      tab.fitAddon?.fit()
      tab.xterm?.focus()
    })
  })
}

function addTab() {
  const tab = createTab(nextTabNo++)
  tabs.value.push(tab)
  activeTabId.value = tab.id
  nextTick(() => ensureActiveTerminal())
}

function closeTabConnection(tab) {
  if (tab?.ws?.readyState === WebSocket.OPEN) {
    tab.ws.send(JSON.stringify({ action: 'close' }))
  }
  tab?.ws?.close()
  if (tab?.xterm?.element) {
    const wrapper = tab.xterm.element.closest('.xterm-tab-wrapper')
    tab.xterm.dispose()
    wrapper?.remove()
  }
  tab.xterm = null
  tab.fitAddon = null
}

function closeTab(tabId) {
  if (tabs.value.length === 1) return
  const index = tabs.value.findIndex(tab => tab.id === tabId)
  const tab = tabs.value[index]
  closeTabConnection(tab)
  tabs.value = tabs.value.filter(item => item.id !== tabId)
  if (activeTabId.value === tabId) {
    activeTabId.value = tabs.value[Math.max(index - 1, 0)]?.id || tabs.value[0].id
  }
}

function clearActiveTab() {
  activeTab.value?.xterm?.clear()
}

function sendInput(tab, data) {
  if (!tab) return
  if (tab.ws?.readyState !== WebSocket.OPEN) {
    connectTab(tab)
    return
  }
  tab.ws.send(JSON.stringify({ action: 'input', data }))
}

function fitTerminal() {
  const tab = activeTab.value
  if (tab?.fitAddon && tab.xterm?.element) {
    tab.fitAddon.fit()
  }
}

function startResize(e) {
  e.preventDefault()
  resizeOnMove = (ev) => {
    const h = window.innerHeight - ev.clientY
    drawerHeight.value = Math.max(220, Math.min(h, window.innerHeight * 0.75))
    emitHeight()
    fitTerminal()
  }
  resizeOnUp = () => {
    localStorage.setItem('pf_terminal_height', drawerHeight.value)
    window.removeEventListener('mousemove', resizeOnMove)
    window.removeEventListener('mouseup', resizeOnUp)
    resizeOnMove = null
    resizeOnUp = null
    fitTerminal()
  }
  window.addEventListener('mousemove', resizeOnMove)
  window.addEventListener('mouseup', resizeOnUp)
}

function emitHeight() {
  emit('height-change', props.visible ? drawerHeight.value : 0)
}

function handleKeydown(e) {
  if (e.key === 'Escape' && props.visible) emit('close')
}

watch(() => props.visible, (val) => {
  emitHeight()
  if (val) ensureActiveTerminal()
})

watch(activeTabId, (newId, oldId) => {
  if (terminalContainerRef.value) {
    const wrappers = terminalContainerRef.value.querySelectorAll('.xterm-tab-wrapper')
    wrappers.forEach(w => {
      w.style.display = w.dataset.tabId === newId ? '' : 'none'
    })
  }
  if (props.visible) {
    nextTick(() => {
      const tab = activeTab.value
      if (tab?.xterm?.element) {
        tab.fitAddon?.fit()
        tab.xterm.focus()
      } else {
        ensureActiveTerminal()
      }
    })
  }
})

watch(drawerHeight, () => {
  emitHeight()
  nextTick(() => fitTerminal())
})

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  emitHeight()
  if (props.visible) ensureActiveTerminal()
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  emit('height-change', 0)
  if (resizeOnMove) {
    window.removeEventListener('mousemove', resizeOnMove)
    window.removeEventListener('mouseup', resizeOnUp)
  }
  for (const tab of tabs.value) {
    closeTabConnection(tab)
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
          <span v-if="tab.status === 'connecting'" class="tab-running"></span>
          <span v-else class="tab-status" :class="`status-${tab.status}`"></span>
          <button class="tab-close" :disabled="tabs.length === 1" @click.stop="closeTab(tab.id)">×</button>
        </button>
        <button class="tab-add" title="New terminal" aria-label="New terminal" @click="addTab">+</button>
        <button class="btn-clear" @click="clearActiveTab">Clear</button>
        <button class="btn-close" aria-label="Close terminal" @click="$emit('close')">×</button>
      </div>
      <div class="terminal-env-banner">
        <span class="env-cwd">{{ terminalLocation }}</span>
        <span v-if="activeTab?.shell" class="env-shell">{{ activeTab.shell }}</span>
        <span class="env-status" :class="`status-text-${activeStatus}`">{{ activeStatus }}</span>
      </div>
      <div ref="terminalContainerRef" class="terminal-container"></div>
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
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-bottom: none;
  border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  box-shadow: var(--shadow-glass);
  overflow: hidden;
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
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
  transition: transform var(--transition-enter), opacity var(--transition-enter);
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
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass-bg);
  box-shadow: inset 0 1px 0 var(--glass-highlight);
  flex-shrink: 0;
}

.terminal-tab,
.tab-add,
.btn-clear,
.btn-close {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--layer-glass);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast);
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
.btn-clear:hover,
.btn-close:hover {
  background: var(--layer-active);
  border-color: var(--accent);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.tab-running,
.tab-status {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  flex-shrink: 0;
}

.tab-running {
  background: var(--status-warning);
  box-shadow: 0 0 12px var(--status-warning-bg);
  animation: pulse 1.6s ease-in-out infinite;
}

.status-connected { background: var(--green); }
.status-closed { background: var(--text-muted); }
.status-error { background: var(--red); }
.status-idle { background: var(--text-muted); }

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

.terminal-env-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 16px;
  background: var(--layer-glass);
  border-bottom: 1px solid var(--glass-border);
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: nowrap;
}

.env-cwd { color: var(--purple); font-weight: 500; }
.env-shell { color: var(--green); }
.env-status { margin-left: auto; }
.status-text-error { color: var(--red); }
.status-text-connected { color: var(--green); }

.terminal-container {
  flex: 1;
  min-height: 0;
  background: #090d14;
  padding: 4px;
}

.terminal-container :deep(.xterm) {
  height: 100%;
}

.terminal-container :deep(.xterm-viewport) {
  overflow-y: auto !important;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.45; transform: scale(0.82); }
}
</style>
