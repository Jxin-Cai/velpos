<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { SearchAddon } from '@xterm/addon-search'
import { Unicode11Addon } from '@xterm/addon-unicode11'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { useDialogManager, useVisibleProxy, useEscapeToClose } from '@shared/lib/useDialogManager'

const props = defineProps({
  visible: { type: Boolean, required: true },
  projectDir: { type: String, default: '' },
  gitBranch: { type: String, default: '' },
})

const emit = defineEmits(['close', 'height-change'])

const { useDialog } = useDialogManager()
useDialog('terminal', useVisibleProxy(props, emit))
useEscapeToClose(() => props.visible, () => emit('close'))

const MIN_HEIGHT = 220
const DEFAULT_HEIGHT = 400
const drawerHeight = ref(Number.parseInt(localStorage.getItem('pf_terminal_height'), 10) || DEFAULT_HEIGHT)
const isMaximized = ref(false)
const searchVisible = ref(false)
const searchQuery = ref('')
const searchInputRef = ref(null)
const tabs = ref([createTab(1)])
const activeTabId = ref(tabs.value[0].id)
const terminalContainerRef = ref(null)
let nextTabNo = 2
let resizeObserver = null
let fitFrame = 0
let resizeOnMove = null
let resizeOnUp = null

const activeTab = computed(() => tabs.value.find(tab => tab.id === activeTabId.value) || tabs.value[0])
const activeStatus = computed(() => activeTab.value?.status || 'idle')
const terminalLocation = computed(() => {
  const cwd = activeTab.value?.cwd || props.projectDir || '~'
  return props.gitBranch ? `${cwd} · ${props.gitBranch}` : cwd
})
const dockHeight = computed(() => isMaximized.value ? 'calc(100vh - 58px)' : `${drawerHeight.value}px`)

function createTab(no) {
  return {
    id: `terminal-${Date.now()}-${no}`,
    title: `Terminal ${no}`,
    status: 'idle',
    terminalId: '',
    cwd: props.projectDir || '',
    shell: '',
    error: '',
    unread: false,
    ws: null,
    xterm: null,
    fitAddon: null,
    searchAddon: null,
  }
}

function terminalWsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = localStorage.getItem('velpos_auth_token')
  const query = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${protocol}//${window.location.host}/ws/terminal${query}`
}

function reportTabError(tab, message) {
  tab.error = message
  tab.status = 'error'
}

function sendInput(tab, data) {
  if (!tab) return
  if (tab.ws?.readyState !== WebSocket.OPEN) {
    reportTabError(tab, 'Terminal is disconnected. Reconnect to continue.')
    return
  }
  tab.ws.send(JSON.stringify({ action: 'input', data }))
}

function copySelection(tab) {
  const selection = tab.xterm?.getSelection()
  if (!selection) return
  navigator.clipboard.writeText(selection).catch(() => {
    reportTabError(tab, 'Clipboard access was denied by the browser.')
  })
}

function pasteClipboard(tab) {
  navigator.clipboard.readText()
    .then(text => sendInput(tab, text))
    .catch(() => reportTabError(tab, 'Clipboard access was denied by the browser.'))
}

function handleTerminalKey(tab, event) {
  const modifier = event.ctrlKey || event.metaKey
  if (modifier && event.shiftKey && event.code === 'KeyF') {
    openSearch()
    return false
  }
  if (modifier && event.shiftKey && event.code === 'KeyT') {
    addTab()
    return false
  }
  if (modifier && event.code === 'KeyK') {
    clearActiveTab()
    return false
  }
  if ((event.metaKey || (event.ctrlKey && event.shiftKey)) && event.code === 'KeyC' && tab.xterm?.hasSelection()) {
    copySelection(tab)
    return false
  }
  if ((event.metaKey || (event.ctrlKey && event.shiftKey)) && event.code === 'KeyV') {
    pasteClipboard(tab)
    return false
  }
  return true
}

function createXterm(tab) {
  if (tab.xterm) return
  const xterm = new Terminal({
    allowProposedApi: true,
    cursorBlink: true,
    cursorStyle: 'bar',
    fontSize: 13,
    lineHeight: 1.18,
    letterSpacing: 0,
    fontFamily: 'var(--font-mono), "SFMono-Regular", Consolas, "Liberation Mono", monospace',
    theme: {
      background: '#0b0e14',
      foreground: '#d8dee9',
      cursor: '#7aa2f7',
      cursorAccent: '#0b0e14',
      selectionBackground: '#33467c99',
      black: '#11151c', red: '#f7768e', green: '#9ece6a', yellow: '#e0af68',
      blue: '#7aa2f7', magenta: '#bb9af7', cyan: '#7dcfff', white: '#c0caf5',
      brightBlack: '#565f89', brightRed: '#ff899d', brightGreen: '#b9f27c', brightYellow: '#ff9e64',
      brightBlue: '#8db0ff', brightMagenta: '#c7a9ff', brightCyan: '#a4daff', brightWhite: '#ffffff',
    },
    minimumContrastRatio: 4.5,
    convertEol: false,
    scrollback: 20000,
    smoothScrollDuration: 120,
    macOptionIsMeta: true,
    rightClickSelectsWord: true,
  })
  const fitAddon = new FitAddon()
  const searchAddon = new SearchAddon()
  xterm.loadAddon(fitAddon)
  xterm.loadAddon(searchAddon)
  xterm.loadAddon(new Unicode11Addon())
  xterm.loadAddon(new WebLinksAddon((_event, uri) => {
    window.open(uri, '_blank', 'noopener,noreferrer')
  }))
  xterm.unicode.activeVersion = '11'
  xterm.attachCustomKeyEventHandler(event => handleTerminalKey(tab, event))
  tab.xterm = xterm
  tab.fitAddon = fitAddon
  tab.searchAddon = searchAddon

  xterm.onData(data => sendInput(tab, data))
  xterm.onResize(({ cols, rows }) => {
    if (tab.ws?.readyState === WebSocket.OPEN && tab.status === 'connected') {
      tab.ws.send(JSON.stringify({ action: 'resize', cols, rows }))
    }
  })
  xterm.onTitleChange(title => {
    const cleanTitle = title.trim()
    if (cleanTitle) tab.title = cleanTitle.length > 32 ? `${cleanTitle.slice(0, 29)}…` : cleanTitle
  })
}

function mountXterm(tab) {
  if (!terminalContainerRef.value || !tab.xterm || tab.xterm.element) return
  const wrapper = document.createElement('div')
  wrapper.className = 'xterm-tab-wrapper'
  wrapper.dataset.tabId = tab.id
  wrapper.hidden = tab.id !== activeTabId.value
  terminalContainerRef.value.appendChild(wrapper)
  tab.xterm.open(wrapper)
  scheduleFit()
}

function connectTab(tab) {
  if (!props.visible || tab.ws?.readyState === WebSocket.OPEN || tab.ws?.readyState === WebSocket.CONNECTING) return
  tab.status = 'connecting'
  tab.error = ''
  createXterm(tab)

  const ws = new WebSocket(terminalWsUrl())
  tab.ws = ws
  ws.onopen = () => {
    scheduleFit()
    ws.send(JSON.stringify({
      cwd: tab.cwd || props.projectDir || null,
      cols: tab.xterm?.cols || 80,
      rows: tab.xterm?.rows || 24,
    }))
  }
  ws.onmessage = event => {
    let message
    try {
      message = JSON.parse(event.data)
    } catch {
      reportTabError(tab, 'The terminal server sent an invalid response.')
      return
    }
    if (message.event === 'ready') {
      tab.status = 'connected'
      tab.terminalId = message.terminal_id || ''
      tab.cwd = message.cwd || tab.cwd
      tab.shell = message.shell || ''
      tab.error = ''
      nextTick(() => tab.xterm?.focus())
    } else if (message.event === 'output') {
      tab.xterm?.write(message.data || '')
      if (tab.id !== activeTabId.value) tab.unread = true
    } else if (message.event === 'closed') {
      tab.status = 'closed'
    } else if (message.event === 'error') {
      reportTabError(tab, message.message || 'Unable to start the terminal.')
    }
  }
  ws.onerror = () => {
    if (tab.ws === ws) reportTabError(tab, 'Unable to connect to the terminal server.')
  }
  ws.onclose = () => {
    if (tab.ws !== ws) return
    if (tab.status !== 'error') tab.status = 'closed'
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
    scheduleFit(true)
  })
}

function addTab() {
  const tab = createTab(nextTabNo++)
  tabs.value.push(tab)
  activeTabId.value = tab.id
}

function closeTabConnection(tab) {
  if (!tab) return
  const ws = tab.ws
  tab.ws = null
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action: 'close' }))
  ws?.close()
  const wrapper = tab.xterm?.element?.closest('.xterm-tab-wrapper')
  tab.xterm?.dispose()
  wrapper?.remove()
  tab.xterm = null
  tab.fitAddon = null
  tab.searchAddon = null
}

function closeTab(tabId) {
  const index = tabs.value.findIndex(tab => tab.id === tabId)
  if (index < 0) return
  closeTabConnection(tabs.value[index])
  tabs.value.splice(index, 1)
  if (tabs.value.length === 0) {
    const replacement = createTab(nextTabNo++)
    tabs.value.push(replacement)
  }
  if (activeTabId.value === tabId) {
    activeTabId.value = tabs.value[Math.min(index, tabs.value.length - 1)].id
  }
}

function reconnectActiveTab() {
  const tab = activeTab.value
  if (!tab) return
  tab.ws?.close()
  tab.ws = null
  tab.xterm?.writeln('\r\n\x1b[2m— starting a new shell —\x1b[0m')
  connectTab(tab)
}

function clearActiveTab() {
  activeTab.value?.xterm?.clear()
  activeTab.value?.xterm?.focus()
}

function scheduleFit(focus = false) {
  window.cancelAnimationFrame(fitFrame)
  fitFrame = window.requestAnimationFrame(() => {
    const tab = activeTab.value
    if (props.visible && tab?.fitAddon && tab.xterm?.element) {
      tab.fitAddon.fit()
      if (focus) tab.xterm.focus()
    }
  })
}

function openSearch() {
  searchVisible.value = true
  nextTick(() => {
    searchInputRef.value?.focus()
    searchInputRef.value?.select()
  })
}

function closeSearch() {
  searchVisible.value = false
  activeTab.value?.searchAddon?.clearDecorations()
  activeTab.value?.xterm?.focus()
}

function findInTerminal(previous = false) {
  if (!searchQuery.value) return
  const options = { caseSensitive: false, wholeWord: false, regex: false, incremental: true }
  if (previous) activeTab.value?.searchAddon?.findPrevious(searchQuery.value, options)
  else activeTab.value?.searchAddon?.findNext(searchQuery.value, options)
}

function toggleMaximize() {
  isMaximized.value = !isMaximized.value
  emitHeight()
  nextTick(() => scheduleFit(true))
}

function startResize(event) {
  if (isMaximized.value) return
  event.preventDefault()
  resizeOnMove = ev => {
    drawerHeight.value = Math.max(MIN_HEIGHT, Math.min(window.innerHeight - ev.clientY, window.innerHeight * 0.85))
  }
  resizeOnUp = () => {
    localStorage.setItem('pf_terminal_height', String(Math.round(drawerHeight.value)))
    window.removeEventListener('pointermove', resizeOnMove)
    window.removeEventListener('pointerup', resizeOnUp)
    resizeOnMove = null
    resizeOnUp = null
    scheduleFit()
  }
  window.addEventListener('pointermove', resizeOnMove)
  window.addEventListener('pointerup', resizeOnUp)
}

function resizeWithKeyboard(event) {
  if (!['ArrowUp', 'ArrowDown'].includes(event.key) || isMaximized.value) return
  event.preventDefault()
  drawerHeight.value = Math.max(MIN_HEIGHT, Math.min(drawerHeight.value + (event.key === 'ArrowUp' ? 24 : -24), window.innerHeight * 0.85))
  localStorage.setItem('pf_terminal_height', String(Math.round(drawerHeight.value)))
}

function emitHeight() {
  emit('height-change', props.visible ? (isMaximized.value ? window.innerHeight - 58 : drawerHeight.value) : 0)
}

function handleGlobalShortcut(event) {
  if (!props.visible) return
  if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.code === 'KeyF') {
    event.preventDefault()
    openSearch()
  }
}

watch(() => props.visible, value => {
  emitHeight()
  if (value) ensureActiveTerminal()
})

watch(activeTabId, newId => {
  terminalContainerRef.value?.querySelectorAll('.xterm-tab-wrapper').forEach(wrapper => {
    wrapper.hidden = wrapper.dataset.tabId !== newId
  })
  const tab = activeTab.value
  if (tab) tab.unread = false
  if (props.visible) nextTick(() => ensureActiveTerminal())
})

watch(drawerHeight, () => {
  emitHeight()
  scheduleFit()
})

onMounted(() => {
  emitHeight()
  resizeObserver = new ResizeObserver(() => scheduleFit())
  if (terminalContainerRef.value) resizeObserver.observe(terminalContainerRef.value)
  window.addEventListener('keydown', handleGlobalShortcut)
  if (props.visible) ensureActiveTerminal()
})

onBeforeUnmount(() => {
  emit('height-change', 0)
  resizeObserver?.disconnect()
  window.cancelAnimationFrame(fitFrame)
  window.removeEventListener('keydown', handleGlobalShortcut)
  if (resizeOnMove) {
    window.removeEventListener('pointermove', resizeOnMove)
    window.removeEventListener('pointerup', resizeOnUp)
  }
  tabs.value.forEach(closeTabConnection)
})
</script>

<template>
  <transition name="terminal-dock">
    <section
      v-show="visible"
      class="terminal-dock"
      :class="{ maximized: isMaximized }"
      :style="{ height: dockHeight }"
      aria-label="Integrated terminal"
    >
      <div
        class="resize-handle"
        role="separator"
        aria-label="Resize terminal"
        aria-orientation="horizontal"
        tabindex="0"
        @pointerdown="startResize"
        @keydown="resizeWithKeyboard"
      ></div>

      <div class="terminal-toolbar">
        <div class="terminal-tabs" role="tablist" aria-label="Terminal sessions">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            class="terminal-tab"
            :class="{ active: tab.id === activeTabId }"
            role="tab"
            :aria-selected="tab.id === activeTabId"
            :tabindex="tab.id === activeTabId ? 0 : -1"
            @click="activeTabId = tab.id"
          >
            <span class="tab-status" :class="`status-${tab.status}`" aria-hidden="true"></span>
            <span class="tab-title">{{ tab.title }}</span>
            <span v-if="tab.unread" class="tab-unread" title="New output"></span>
            <span
              class="tab-close"
              role="button"
              tabindex="0"
              aria-label="Close terminal"
              @click.stop="closeTab(tab.id)"
              @keydown.enter.stop="closeTab(tab.id)"
            >×</span>
          </button>
          <button class="icon-button tab-add" title="New terminal (⌘/Ctrl+Shift+T)" aria-label="New terminal" @click="addTab">+</button>
        </div>

        <div class="terminal-actions">
          <button class="icon-button" title="Search (⌘/Ctrl+Shift+F)" aria-label="Search terminal" @click="openSearch">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
          </button>
          <button class="icon-button" title="Clear (⌘/Ctrl+K)" aria-label="Clear terminal" @click="clearActiveTab">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14"/></svg>
          </button>
          <button class="icon-button" :title="isMaximized ? 'Restore' : 'Maximize'" :aria-label="isMaximized ? 'Restore terminal' : 'Maximize terminal'" @click="toggleMaximize">
            <svg v-if="!isMaximized" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5m13-5h5v5M8 21H3v-5m13 5h5v-5"/></svg>
            <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3v5H3m13-5v5h5M8 21v-5H3m13 5v-5h5"/></svg>
          </button>
          <button class="icon-button" title="Hide terminal" aria-label="Hide terminal" @click="emit('close')">×</button>
        </div>
      </div>

      <div v-if="searchVisible" class="terminal-search" role="search">
        <input
          ref="searchInputRef"
          v-model="searchQuery"
          aria-label="Search terminal output"
          placeholder="Search terminal output"
          @input="findInTerminal(false)"
          @keydown.enter.prevent="findInTerminal($event.shiftKey)"
          @keydown.esc.prevent="closeSearch"
        />
        <button aria-label="Previous match" title="Previous match" @click="findInTerminal(true)">↑</button>
        <button aria-label="Next match" title="Next match" @click="findInTerminal(false)">↓</button>
        <button aria-label="Close search" title="Close search" @click="closeSearch">×</button>
      </div>

      <div class="terminal-context">
        <span class="env-cwd" :title="terminalLocation">{{ terminalLocation }}</span>
        <span v-if="activeTab?.shell" class="env-shell">{{ activeTab.shell.split('/').pop() }}</span>
        <span class="env-status" :class="`status-text-${activeStatus}`">{{ activeStatus }}</span>
        <button v-if="['closed', 'error'].includes(activeStatus)" class="reconnect-button" @click="reconnectActiveTab">Reconnect</button>
      </div>
      <div v-if="activeTab?.error" class="terminal-error" role="alert">{{ activeTab.error }}</div>
      <div ref="terminalContainerRef" class="terminal-container" @click="activeTab?.xterm?.focus()"></div>
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
  max-height: 85vh;
  min-height: 220px;
  color: #d8dee9;
  background: #0b0e14;
  border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--glass-border));
  border-bottom: none;
  border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  box-shadow: 0 -16px 50px rgb(0 0 0 / 24%);
  overflow: hidden;
}

.terminal-dock.maximized {
  left: 0;
  right: 0;
  max-height: calc(100vh - 58px);
  border-radius: 0;
}

.resize-handle {
  position: absolute;
  inset: 0 0 auto;
  height: 7px;
  cursor: row-resize;
  z-index: 10;
}

.resize-handle::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 50%;
  width: 42px;
  height: 2px;
  border-radius: 2px;
  background: #596579;
  transform: translateX(-50%);
  transition: width 160ms ease, background 160ms ease;
}

.resize-handle:hover::after,
.resize-handle:focus-visible::after {
  width: 64px;
  background: #7aa2f7;
}

.resize-handle:focus-visible,
.terminal-tab:focus-visible,
.icon-button:focus-visible,
.terminal-search button:focus-visible,
.terminal-search input:focus-visible,
.reconnect-button:focus-visible {
  outline: 2px solid #7aa2f7;
  outline-offset: -2px;
}

.terminal-dock-enter-active,
.terminal-dock-leave-active { transition: transform 180ms ease, opacity 180ms ease; }
.terminal-dock-enter-from,
.terminal-dock-leave-to { transform: translateY(100%); opacity: 0; }

.terminal-toolbar {
  display: flex;
  align-items: center;
  min-height: 42px;
  padding: 7px 8px 5px;
  gap: 8px;
  background: #11151c;
  border-bottom: 1px solid #242b38;
  flex-shrink: 0;
}

.terminal-tabs {
  display: flex;
  align-items: center;
  gap: 3px;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}
.terminal-tabs::-webkit-scrollbar { display: none; }

.terminal-tab,
.icon-button,
.terminal-search button,
.reconnect-button {
  border: 0;
  background: transparent;
  color: #8993a4;
  cursor: pointer;
  transition: color 160ms ease, background 160ms ease;
}

.terminal-tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 92px;
  max-width: 210px;
  height: 29px;
  padding: 0 7px;
  border-radius: 5px;
  font: 12px/1 var(--font-mono);
}
.terminal-tab:hover { background: #1a202b; color: #c3cad6; }
.terminal-tab.active { background: #242c3a; color: #f2f4f8; }
.tab-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.tab-status,
.tab-unread {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #596579;
  flex: 0 0 auto;
}
.status-connecting { background: #e0af68; animation: pulse 1.3s ease-in-out infinite; }
.status-connected { background: #9ece6a; }
.status-error { background: #f7768e; }
.status-closed { background: #596579; }
.tab-unread { margin-left: auto; background: #7aa2f7; box-shadow: 0 0 7px #7aa2f7; }
.tab-close { padding: 3px; border-radius: 3px; color: #8993a4; font-size: 15px; }
.tab-close:hover { background: #394255; color: #fff; }

.terminal-actions { display: flex; align-items: center; gap: 2px; margin-left: auto; }
.icon-button { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 5px; flex: 0 0 auto; }
.icon-button:hover { color: #fff; background: #242c3a; }
.icon-button svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.tab-add { font-size: 20px; line-height: 1; }

.terminal-search {
  position: absolute;
  z-index: 12;
  top: 48px;
  right: 12px;
  display: flex;
  align-items: center;
  padding: 4px;
  border: 1px solid #394255;
  border-radius: 7px;
  background: #171c26;
  box-shadow: 0 8px 28px rgb(0 0 0 / 42%);
}
.terminal-search input {
  width: min(260px, 45vw);
  height: 30px;
  padding: 0 9px;
  border: 0;
  border-radius: 4px;
  outline: none;
  color: #e5e9f0;
  background: #0b0e14;
  font: 12px var(--font-mono);
}
.terminal-search button { width: 30px; height: 30px; border-radius: 4px; font-size: 15px; }
.terminal-search button:hover { color: #fff; background: #2b3444; }

.terminal-context {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 28px;
  padding: 0 12px;
  border-bottom: 1px solid #202632;
  background: #0e1219;
  color: #8993a4;
  font: 11px/1 var(--font-mono);
  white-space: nowrap;
}
.env-cwd { color: #a9b7d0; overflow: hidden; text-overflow: ellipsis; }
.env-shell { color: #9ece6a; }
.env-status { margin-left: auto; text-transform: capitalize; }
.status-text-connected { color: #9ece6a; }
.status-text-error { color: #f7768e; }
.reconnect-button { padding: 4px 7px; border-radius: 4px; color: #8db0ff; font: inherit; }
.reconnect-button:hover { background: #242c3a; }

.terminal-error {
  padding: 7px 12px;
  background: #351923;
  border-bottom: 1px solid #6f293b;
  color: #ff9aac;
  font: 12px/1.3 var(--font-mono);
}

.terminal-container { flex: 1; min-height: 0; padding: 7px 8px 6px; background: #0b0e14; }
.terminal-container :deep(.xterm-tab-wrapper) { width: 100%; height: 100%; }
.terminal-container :deep(.xterm-tab-wrapper[hidden]) { display: none; }
.terminal-container :deep(.xterm) { height: 100%; }
.terminal-container :deep(.xterm-viewport) { overflow-y: auto !important; scrollbar-color: #394255 transparent; }

@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }

@media (max-width: 820px) {
  .terminal-dock { left: 0; right: 0; max-height: 80vh; border-radius: var(--radius-lg) var(--radius-lg) 0 0; }
  .terminal-context { padding-inline: 9px; }
  .env-shell { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .terminal-dock-enter-active,
  .terminal-dock-leave-active,
  .resize-handle::after,
  .terminal-tab,
  .icon-button { transition: none; }
  .status-connecting { animation: none; }
}
</style>
