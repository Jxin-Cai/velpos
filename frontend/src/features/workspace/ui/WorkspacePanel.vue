<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import hljs from 'highlight.js/lib/common'
import { useGlobalHotkeys } from '../../../shared/lib/useGlobalHotkeys'
import { useWorkspace } from '../model/useWorkspace'

const props = defineProps({
  visible: { type: Boolean, required: true },
  project: { type: Object, default: null },
  vbRunning: { type: Boolean, default: false },
  vbMessage: { type: String, default: '' },
})

const emit = defineEmits(['close', 'apply-vb', 'width-change'])

const {
  files,
  selectedFile,
  selectedDiff,
  fileHistory,
  loading,
  reading,
  historyLoading,
  error,
  loadFiles,
  openFile,
  loadFileHistory,
  openHistoricalFile,
  clearSelection,
} = useWorkspace()

const changedOnly = ref(false)
const keyword = ref('')
const expandedDirs = ref(new Set())
const contentOpen = ref(false)
const contentFullscreen = ref(false)
const vbMode = ref(false)
const pendingSelection = ref(null)
const reviewComment = ref('')
const reviews = ref([])
const compareMode = ref(false)
const versionCursor = ref(0)
const versionContents = ref({})
const diffCursor = ref(-1)
const historyRows = ref([])
let historyTransitionTimer = null
let historyAnchorFrame = null

const projectId = computed(() => props.project?.id || '')
const fileLines = computed(() => (selectedFile.value?.content || '').split('\n'))
const canApplyVb = computed(() => selectedFile.value && reviews.value.length > 0 && !props.vbRunning)
const drawerWidth = computed(() => {
  if (!props.visible) return 0
  if (contentFullscreen.value) return 0
  return contentOpen.value ? 900 : 360
})

const treeRows = computed(() => flattenTree(buildTree(files.value), expandedDirs.value))
const versionNodes = computed(() => {
  if (!selectedFile.value) return []
  const currentLabel = selectedDiff.value?.patch ? 'Uncommitted' : 'Current'
  return [
    {
      ref: 'current',
      short_hash: currentLabel,
      author_name: '',
      message: selectedFile.value.path,
      current: true,
    },
    ...fileHistory.value.map((commit) => ({ ...commit, current: false })),
  ]
})
const activeVersion = computed(() => versionNodes.value[versionCursor.value] || null)
const compareFromNode = computed(() => {
  if (!versionNodes.value.length) return null
  if (versionCursor.value === 0) return versionNodes.value[1] || null
  return versionNodes.value[versionCursor.value - 1] || null
})
const compareToNode = computed(() => activeVersion.value)
const compareFromLines = computed(() => splitLines(getVersionContent(compareFromNode.value)))
const compareToLines = computed(() => splitLines(getVersionContent(compareToNode.value)))
const highlightedFileLines = computed(() => fileLines.value.map((line) => highlightLine(line, selectedFile.value?.path || '')))
const compareRows = computed(() => historyRows.value)
const diffRowIndexes = computed(() => compareRows.value
  .map((row, index) => (row.type === 'same' ? -1 : index))
  .filter((index) => index >= 0))
const compareToTitle = computed(() => formatVersionTitle(compareToNode.value, 'Current'))

watch(() => props.visible, (visible) => {
  emitWidth()
  if (visible && projectId.value) refreshFiles()
  if (!visible) {
    closeContent()
  }
})

watch(projectId, () => {
  if (props.visible && projectId.value) refreshFiles()
})

watch(drawerWidth, emitWidth)

function emitWidth() {
  emit('width-change', drawerWidth.value)
}

async function refreshFiles() {
  await loadFiles(projectId.value, { changedOnly: changedOnly.value, keyword: keyword.value })
}

async function selectFile(path) {
  await openFile(projectId.value, path)
  contentOpen.value = true
  vbMode.value = false
  compareMode.value = false
  versionCursor.value = 0
  versionContents.value = {}
  clearHistoryTransition()
  historyRows.value = []
  pendingSelection.value = null
  reviewComment.value = ''
  reviews.value = []
  emitWidth()
}

function closeContent() {
  contentOpen.value = false
  contentFullscreen.value = false
  compareMode.value = false
  versionCursor.value = 0
  versionContents.value = {}
  clearHistoryTransition()
  historyRows.value = []
  pendingSelection.value = null
  reviewComment.value = ''
  reviews.value = []
  clearSelection()
  emitWidth()
}

function buildTree(fileList) {
  const root = { key: '', name: '', type: 'dir', children: [], depth: -1 }
  const dirs = new Map([['', root]])
  for (const file of fileList) {
    const parts = file.path.split('/').filter(Boolean)
    let currentPath = ''
    let parent = root
    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1
      currentPath = currentPath ? `${currentPath}/${part}` : part
      if (isFile) {
        parent.children.push({
          key: file.path,
          name: part,
          type: 'file',
          path: file.path,
          depth: index,
          is_changed: file.is_changed,
          git_status: file.git_status,
        })
      } else {
        let dir = dirs.get(currentPath)
        if (!dir) {
          dir = { key: currentPath, name: part, type: 'dir', path: currentPath, depth: index, children: [], is_changed: false }
          dirs.set(currentPath, dir)
          parent.children.push(dir)
        }
        if (file.is_changed) dir.is_changed = true
        parent = dir
      }
    })
  }
  sortTree(root)
  return root.children
}

function sortTree(node) {
  node.children?.sort((a, b) => {
    if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
    return a.name.localeCompare(b.name)
  })
  for (const child of node.children || []) {
    if (child.type === 'dir') sortTree(child)
  }
}

function flattenTree(nodes, expanded) {
  const rows = []
  function visit(node) {
    rows.push(node)
    if (node.type === 'dir' && expanded.has(node.key)) {
      for (const child of node.children) visit(child)
    }
  }
  for (const node of nodes) visit(node)
  return rows
}

function toggleDir(node) {
  const next = new Set(expandedDirs.value)
  if (next.has(node.key)) next.delete(node.key)
  else next.add(node.key)
  expandedDirs.value = next
}

function nearestLineNode(node) {
  let current = node?.nodeType === Node.TEXT_NODE ? node.parentElement : node
  while (current && current !== document.body) {
    if (current.dataset?.line) return current
    current = current.parentElement
  }
  return null
}

function handleCodeMouseUp() {
  if (!vbMode.value) return
  const selection = window.getSelection()
  const text = selection?.toString().trim()
  if (!selection || !text || selection.rangeCount === 0) return
  const range = selection.getRangeAt(0)
  const startEl = nearestLineNode(range.startContainer)
  const endEl = nearestLineNode(range.endContainer)
  if (!startEl || !endEl) return
  const start = Number(startEl.dataset.line)
  const end = Number(endEl.dataset.line)
  pendingSelection.value = {
    start_line: Math.min(start, end),
    end_line: Math.max(start, end),
    selected_text: text,
  }
  nextTick(() => document.querySelector('.vb-comment-input')?.focus())
}

function addSelectionReview() {
  const comment = reviewComment.value.trim()
  if (!pendingSelection.value || !comment) return
  reviews.value.push({ ...pendingSelection.value, comment })
  reviewComment.value = ''
  pendingSelection.value = null
  window.getSelection()?.removeAllRanges()
}

function removeReview(index) {
  reviews.value.splice(index, 1)
}

function applyVb() {
  if (!canApplyVb.value) return
  emit('apply-vb', {
    file_path: selectedFile.value.path,
    reviews: reviews.value,
    refresh: () => selectFile(selectedFile.value.path),
  })
}

async function toggleCompare() {
  compareMode.value = !compareMode.value
  if (!compareMode.value || !selectedFile.value) {
    clearHistoryTransition()
    historyRows.value = []
    return
  }
  versionCursor.value = 0
  versionContents.value = {}
  await loadFileHistory(projectId.value, selectedFile.value.path)
  await ensureCompareContent()
  setSettledHistoryRows()
}

async function selectVersion(index) {
  const next = Number(index)
  if (Number.isNaN(next) || next < 0 || next >= versionNodes.value.length || next === versionCursor.value) return
  const anchor = captureHistoryScrollAnchor()
  const previousContent = getVersionContent(activeVersion.value)
  versionCursor.value = next
  diffCursor.value = -1
  await ensureCompareContent()
  startHistoryTransition(previousContent, getVersionContent(activeVersion.value), anchor)
}

function canMoveVersion(delta) {
  const next = versionCursor.value + delta
  return next >= 0 && next < versionNodes.value.length
}

function browseVersion(delta) {
  if (!canMoveVersion(delta)) return true
  selectVersion(versionCursor.value + delta)
  return false
}

function getVersionContent(node) {
  if (!node) return ''
  if (node.current) return selectedFile.value?.content || ''
  return versionContents.value[node.ref] || ''
}

async function ensureCompareContent() {
  await Promise.all([
    ensureVersionContent(compareFromNode.value),
    ensureVersionContent(compareToNode.value),
  ])
}

async function ensureVersionContent(node) {
  if (!node || node.current || !selectedFile.value) return
  if (Object.prototype.hasOwnProperty.call(versionContents.value, node.ref)) return
  const file = await openHistoricalFile(projectId.value, selectedFile.value.path, node.ref)
  versionContents.value = {
    ...versionContents.value,
    [node.ref]: file?.content || '',
  }
}

function clearHistoryTransition() {
  if (historyTransitionTimer) {
    clearTimeout(historyTransitionTimer)
    historyTransitionTimer = null
  }
  if (historyAnchorFrame) {
    cancelAnimationFrame(historyAnchorFrame)
    historyAnchorFrame = null
  }
}

function holdHistoryScrollAnchor(anchor, duration = 820) {
  if (!anchor) return
  const startedAt = performance.now()
  const tick = () => {
    restoreHistoryScrollAnchor(anchor)
    if (performance.now() - startedAt < duration) {
      historyAnchorFrame = requestAnimationFrame(tick)
    } else {
      historyAnchorFrame = null
    }
  }
  historyAnchorFrame = requestAnimationFrame(tick)
}

function setSettledHistoryRows() {
  historyRows.value = buildSettledHistoryRows(compareFromNode.value ? compareFromLines.value : [], compareToLines.value)
}

function startHistoryTransition(previousContent, nextContent, anchor) {
  clearHistoryTransition()
  const previousLines = splitLines(previousContent)
  const nextLines = splitLines(nextContent)
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  if (reducedMotion) {
    setSettledHistoryRows()
    nextTick(() => restoreHistoryScrollAnchor(anchor))
    return
  }

  historyRows.value = buildTransitionHistoryRows(previousLines, nextLines)
  nextTick(() => {
    restoreHistoryScrollAnchor(anchor)
    holdHistoryScrollAnchor(anchor)
  })
  historyTransitionTimer = setTimeout(() => {
    historyTransitionTimer = null
    setSettledHistoryRows()
    nextTick(() => restoreHistoryScrollAnchor(anchor))
  }, 820)
}

function handleKeydown(event) {
  if (event.key === 'Escape' && props.visible) {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  clearHistoryTransition()
})

function formatVersionTitle(node, fallback) {
  if (!node) return fallback
  if (node.current) return node.short_hash
  const author = node.author_name ? ` · ${node.author_name}` : ''
  return `${node.short_hash}${author}`
}

function isEditableTarget(target) {
  const element = target instanceof Element ? target : null
  if (!element) return false
  return Boolean(element.closest('input, textarea, select, [contenteditable="true"]'))
}

useGlobalHotkeys({
  keys: ['ArrowLeft', 'ArrowRight'],
  priority: 20,
  condition: () => props.visible && contentOpen.value && compareMode.value && selectedFile.value && !selectedFile.value.is_binary,
  handler: (event) => {
    if (isEditableTarget(event.target)) return true
    return event.key === 'ArrowRight' ? browseVersion(1) : browseVersion(-1)
  },
})

function splitLines(content) {
  return (content || '').split('\n')
}

function buildSettledHistoryRows(before, after) {
  const changedLines = new Set()
  if (before.length) {
    for (const row of buildSideBySideDiff(before, after)) {
      if (row.type !== 'same' && row.afterLineNo) changedLines.add(row.afterLineNo)
    }
  }
  return after.map((line, index) => {
    const lineNo = index + 1
    const type = changedLines.has(lineNo) ? 'added' : 'same'
    return createDiffRow(type, '', line, null, lineNo, 'stable')
  })
}

function buildTransitionHistoryRows(before, after) {
  return buildSideBySideDiff(before, after).map((row) => ({
    ...row,
    phase: row.type === 'added' ? 'entering' : row.type === 'removed' ? 'leaving' : 'stable',
  }))
}

function buildSideBySideDiff(before, after) {
  if (before.length * after.length > 1000000) return buildSequentialDiff(before, after)
  const rows = []
  const dp = Array.from({ length: before.length + 1 }, () => new Uint32Array(after.length + 1))

  for (let i = before.length - 1; i >= 0; i -= 1) {
    for (let j = after.length - 1; j >= 0; j -= 1) {
      dp[i][j] = before[i] === after[j]
        ? dp[i + 1][j + 1] + 1
        : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }

  let i = 0
  let j = 0
  while (i < before.length && j < after.length) {
    if (before[i] === after[j]) {
      rows.push(createDiffRow('same', before[i], after[j], i + 1, j + 1))
      i += 1
      j += 1
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      rows.push(createDiffRow('removed', before[i], '', i + 1, null))
      i += 1
    } else {
      rows.push(createDiffRow('added', '', after[j], null, j + 1))
      j += 1
    }
  }

  while (i < before.length) {
    rows.push(createDiffRow('removed', before[i], '', i + 1, null))
    i += 1
  }
  while (j < after.length) {
    rows.push(createDiffRow('added', '', after[j], null, j + 1))
    j += 1
  }

  return rows
}

function buildSequentialDiff(before, after) {
  const rows = []
  const max = Math.max(before.length, after.length)
  for (let index = 0; index < max; index += 1) {
    const beforeLine = before[index]
    const afterLine = after[index]
    if (beforeLine === afterLine) {
      rows.push(createDiffRow('same', beforeLine || '', afterLine || '', index + 1, index + 1))
    } else {
      if (beforeLine !== undefined) rows.push(createDiffRow('removed', beforeLine, '', index + 1, null))
      if (afterLine !== undefined) rows.push(createDiffRow('added', '', afterLine, null, index + 1))
    }
  }
  return rows
}

function createDiffRow(type, beforeLine, afterLine, beforeLineNo, afterLineNo, phase = 'stable') {
  const source = `${type}:${beforeLineNo || 0}:${afterLineNo || 0}:${beforeLine}:${afterLine}`
  const displayLine = afterLineNo ? afterLine : beforeLine
  const displayLineNo = afterLineNo || beforeLineNo
  return {
    id: `${type}-${beforeLineNo || 0}-${afterLineNo || 0}-${hashString(source)}`,
    type,
    phase,
    beforeLine,
    afterLine,
    beforeLineNo,
    afterLineNo,
    displayLine,
    displayLineNo,
  }
}

function hashString(value) {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) - hash + value.charCodeAt(index)) | 0
  }
  return Math.abs(hash).toString(36)
}

const languageByExtension = {
  js: 'javascript',
  jsx: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  vue: 'xml',
  py: 'python',
  json: 'json',
  md: 'markdown',
  css: 'css',
  scss: 'scss',
  html: 'xml',
  htm: 'xml',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  go: 'go',
  java: 'java',
  rs: 'rust',
  yaml: 'yaml',
  yml: 'yaml',
  sql: 'sql',
  xml: 'xml',
}

function languageForPath(path) {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  return languageByExtension[ext] || ''
}

function highlightLine(line, path) {
  const value = line || ' '
  const language = languageForPath(path)
  try {
    if (language && hljs.getLanguage(language)) {
      return hljs.highlight(value, { language, ignoreIllegals: true }).value
    }
  } catch {
    return escapeHtml(value)
  }
  return escapeHtml(value)
}

function escapeHtml(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function captureHistoryScrollAnchor() {
  const container = document.querySelector('.history-code-view')
  if (!container) return null
  const rows = [...container.querySelectorAll('.history-line[data-display-line]')]
  const viewportTop = container.getBoundingClientRect().top
  const row = rows.find((item) => item.getBoundingClientRect().bottom >= viewportTop + 1) || rows[0]
  if (!row) return { scrollTop: container.scrollTop }
  return {
    line: Number(row.dataset.displayLine),
    offset: Math.max(0, row.getBoundingClientRect().top - viewportTop),
    scrollTop: container.scrollTop,
  }
}

function restoreHistoryScrollAnchor(anchor) {
  const container = document.querySelector('.history-code-view')
  if (!container || !anchor) return
  if (!anchor.line) {
    container.scrollTop = anchor.scrollTop || 0
    return
  }
  const rows = [...container.querySelectorAll('.history-line[data-display-line]')]
  const exact = rows.find((row) => Number(row.dataset.displayLine) === anchor.line)
  const next = rows.find((row) => Number(row.dataset.displayLine) > anchor.line)
  const target = exact || next || rows.at(-1)
  if (!target) return
  container.scrollTop = target.offsetTop - anchor.offset
}

function nextDifference() {
  const rows = diffRowIndexes.value
  if (!rows.length) return
  const next = rows.find((index) => index > diffCursor.value) ?? rows[0]
  diffCursor.value = next
  nextTick(() => {
    document.querySelector(`.history-line[data-diff-row="${next}"]`)?.scrollIntoView({ block: 'center' })
  })
}
</script>

<template>
  <Teleport to="body">
    <Transition name="workspace-slide">
      <aside v-if="visible" class="workspace-drawer" role="dialog" aria-label="Workspace files">
        <header class="workspace-header">
          <div>
            <h2>Workspace</h2>
            <p>{{ project?.dir_path || 'No project selected' }}</p>
          </div>
          <button class="icon-btn" aria-label="Close workspace" @click="$emit('close')">×</button>
        </header>

        <div class="workspace-filters">
          <label class="changed-toggle">
            <input v-model="changedOnly" type="checkbox" @change="refreshFiles" />
            Changed only
          </label>
          <input v-model="keyword" class="file-search" placeholder="Search files" @keydown.enter="refreshFiles" />
          <button class="secondary-btn" :disabled="loading" @click="refreshFiles">Refresh</button>
        </div>

        <div v-if="loading" class="workspace-empty">Loading files...</div>
        <div v-else-if="error" class="workspace-error">{{ error }}</div>
        <div v-else-if="!treeRows.length" class="workspace-empty">No files</div>
        <div v-else class="tree-list">
          <button
            v-for="node in treeRows"
            :key="node.key"
            class="tree-row"
            :class="{ active: selectedFile?.path === node.path, changed: node.is_changed }"
            :style="{ paddingLeft: `${12 + node.depth * 14}px` }"
            @click="node.type === 'dir' ? toggleDir(node) : selectFile(node.path)"
          >
            <span v-if="node.type === 'dir'" class="tree-caret">{{ expandedDirs.has(node.key) ? '▾' : '▸' }}</span>
            <span v-else class="tree-caret"></span>
            <span class="tree-icon">{{ node.type === 'dir' ? 'dir' : 'file' }}</span>
            <span class="tree-name">{{ node.name }}</span>
            <span v-if="node.git_status" class="file-status">{{ node.git_status }}</span>
          </button>
        </div>
      </aside>
    </Transition>

    <Transition name="content-slide">
      <section
        v-if="contentOpen && selectedFile"
        class="file-content-panel"
        :class="{ fullscreen: contentFullscreen }"
        aria-label="File content"
      >
        <header class="viewer-header">
          <div>
            <strong>{{ selectedFile.path }}</strong>
            <span>{{ selectedFile.size }} bytes</span>
            <span v-if="selectedFile.truncated">truncated</span>
            <span v-if="selectedFile.is_binary">binary</span>
          </div>
          <div class="viewer-actions">
            <button class="secondary-btn" :class="{ active: compareMode }" :disabled="selectedFile.is_binary" @click="toggleCompare">History</button>
            <button class="secondary-btn" :class="{ active: vbMode }" :disabled="selectedFile.is_binary" @click="vbMode = !vbMode">VB</button>
            <button class="icon-btn small-icon" :aria-label="contentFullscreen ? 'Shrink file' : 'Fullscreen file'" @click="contentFullscreen = !contentFullscreen">
              <svg v-if="!contentFullscreen" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 5h5v5"/>
                <path d="M19 5l-7 7"/>
                <path d="M10 19H5v-5"/>
                <path d="M5 19l7-7"/>
              </svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 12l7-7"/>
                <path d="M14 5h5v5"/>
                <path d="M12 12l-7 7"/>
                <path d="M10 19H5v-5"/>
              </svg>
            </button>
            <button class="icon-btn" aria-label="Close file" @click="closeContent">×</button>
          </div>
        </header>

        <div v-if="reading" class="workspace-empty viewer-empty">Reading file...</div>
        <div v-else-if="selectedFile.is_binary" class="workspace-empty viewer-empty">Binary file cannot be previewed.</div>
        <template v-else>
          <div v-if="compareMode" class="compare-shell">
            <div class="compare-toolbar">
              <div class="history-track" aria-label="File version history">
                <button
                  v-for="(node, index) in versionNodes"
                  :key="node.ref"
                  class="history-node"
                  :class="{ current: node.current, active: versionCursor === index }"
                  @click="selectVersion(index)"
                >
                  <strong>{{ node.short_hash }}</strong>
                  <small>{{ node.current ? 'current' : node.author_name }}</small>
                </button>
              </div>
              <div class="history-keys">
                <button class="key-hint" :disabled="!canMoveVersion(-1)" @click="browseVersion(-1)">← newer</button>
                <button class="key-hint" :disabled="!canMoveVersion(1)" @click="browseVersion(1)">older →</button>
              </div>
              <button class="secondary-btn" :disabled="!diffRowIndexes.length" @click="nextDifference">
                Next diff
              </button>
              <span v-if="activeVersion">Viewing {{ compareToTitle }}</span>
              <span v-else>{{ historyLoading ? 'Loading history...' : 'No history' }}</span>
            </div>
            <div class="compare-view">
              <div class="history-code-view">
                <div class="pane-title">{{ compareToTitle }}</div>
                <div class="history-lines">
                  <div
                    v-for="(row, index) in compareRows"
                    :key="row.id"
                    class="history-line"
                    :class="[row.type, row.phase, { 'current-diff': diffCursor === index }]"
                    :data-diff-row="index"
                    :data-display-line="row.displayLineNo || null"
                  >
                    <span class="line-no">{{ row.displayLineNo || '' }}</span>
                    <pre v-html="highlightLine(row.displayLine, selectedFile.path)"></pre>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="code-view" @mouseup="handleCodeMouseUp">
            <div v-for="(line, index) in highlightedFileLines" :key="index" class="code-line" :data-line="index + 1">
              <span class="line-no">{{ index + 1 }}</span>
              <pre v-html="line"></pre>
            </div>
          </div>

          <section v-if="selectedDiff?.patch && !compareMode" class="diff-box">
            <div class="diff-title">Diff</div>
            <pre>{{ selectedDiff.patch }}</pre>
          </section>

          <section v-if="vbMode" class="vb-panel">
            <div v-if="pendingSelection" class="selection-card">
              <span>L{{ pendingSelection.start_line }}-{{ pendingSelection.end_line }}</span>
              <blockquote>{{ pendingSelection.selected_text }}</blockquote>
              <textarea v-model="reviewComment" class="vb-comment-input" placeholder="给选中的内容写评语"></textarea>
              <button class="secondary-btn" @click="addSelectionReview">Add review</button>
            </div>
            <div v-else class="selection-hint">鼠标选中文件内容后写评语。</div>
            <div class="review-list">
              <div v-for="(review, index) in reviews" :key="index" class="review-item">
                <span>L{{ review.start_line }}-{{ review.end_line }}</span>
                <p>{{ review.comment }}</p>
                <button @click="removeReview(index)">Remove</button>
              </div>
            </div>
            <div class="vb-actions">
              <span>{{ vbMessage }}</span>
              <button class="primary-btn" :disabled="!canApplyVb" @click="applyVb">
                {{ vbRunning ? 'VB running...' : 'Start VB' }}
              </button>
            </div>
          </section>
        </template>
      </section>
    </Transition>
  </Teleport>
</template>

<style scoped>
.workspace-drawer {
  position: fixed;
  top: 48px;
  right: 0;
  bottom: 0;
  z-index: 70;
  width: 360px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--glass-border);
  background: var(--glass-bg-strong);
  box-shadow: var(--shadow-glass);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.file-content-panel {
  position: fixed;
  top: 48px;
  right: 360px;
  bottom: 0;
  z-index: 69;
  width: 540px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--glass-border);
  background: var(--glass-bg-strong);
  box-shadow: var(--shadow-glass);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.file-content-panel.fullscreen {
  top: 0;
  right: 0;
  z-index: 120;
  width: 100vw;
  height: 100vh;
}

.workspace-header,
.viewer-header,
.vb-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.workspace-header,
.viewer-header {
  padding: 14px 16px;
  border-bottom: 1px solid var(--glass-border);
  background: var(--layer-glass);
  flex-shrink: 0;
}

.workspace-header h2 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary);
}

.workspace-header p,
.viewer-header span,
.selection-hint {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.viewer-header strong {
  color: var(--text-primary);
  display: block;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.viewer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon-btn {
  width: 32px;
  height: 32px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--glass-bg) 36%, transparent);
  color: var(--text-secondary);
  font-size: 22px;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.icon-btn:hover,
.secondary-btn:hover:not(:disabled) {
  background: var(--layer-active);
  border-color: var(--accent);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.workspace-filters {
  display: grid;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--glass-border);
  background: color-mix(in srgb, var(--glass-bg) 44%, transparent);
  flex-shrink: 0;
}

.changed-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.file-search,
.selection-card textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  padding: 7px 9px;
  outline: none;
}

.tree-list {
  flex: 1;
  overflow: auto;
  padding: 6px 0;
}

.tree-row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-height: 28px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
  padding-right: 10px;
}

.tree-row:hover,
.tree-row.active {
  background: var(--layer-active);
  color: var(--text-primary);
}

.tree-row.changed .tree-name {
  color: var(--accent);
}

.tree-caret {
  width: 12px;
  color: var(--text-muted);
}

.tree-icon,
.file-status {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.tree-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 12px;
}

.file-status { color: var(--yellow); }

.code-view {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--bg-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.55;
}

.compare-shell {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.55;
}

.code-line {
  display: grid;
  grid-template-columns: 52px 1fr;
  min-width: max-content;
}

.code-line:hover {
  background: var(--bg-hover);
}

.line-no {
  border-right: 1px solid var(--border-subtle);
  color: var(--text-muted);
  text-align: right;
  padding: 0 10px;
  user-select: none;
}

.code-line pre,
.diff-box pre,
.history-line pre {
  margin: 0;
  white-space: pre;
  padding: 0 12px;
}

.code-line pre :deep(.hljs-keyword),
.history-line pre :deep(.hljs-keyword),
.code-line pre :deep(.hljs-selector-tag),
.history-line pre :deep(.hljs-selector-tag),
.code-line pre :deep(.hljs-title.function_),
.history-line pre :deep(.hljs-title.function_) {
  color: #c678dd;
}

.code-line pre :deep(.hljs-string),
.history-line pre :deep(.hljs-string),
.code-line pre :deep(.hljs-attr),
.history-line pre :deep(.hljs-attr) {
  color: #98c379;
}

.code-line pre :deep(.hljs-number),
.history-line pre :deep(.hljs-number),
.code-line pre :deep(.hljs-literal),
.history-line pre :deep(.hljs-literal) {
  color: #d19a66;
}

.code-line pre :deep(.hljs-comment),
.history-line pre :deep(.hljs-comment) {
  color: var(--text-muted);
  font-style: italic;
}

.code-line pre :deep(.hljs-built_in),
.history-line pre :deep(.hljs-built_in),
.code-line pre :deep(.hljs-type),
.history-line pre :deep(.hljs-type),
.code-line pre :deep(.hljs-name),
.history-line pre :deep(.hljs-name) {
  color: #61afef;
}

.diff-box {
  max-height: 160px;
  overflow: auto;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
}

.diff-title,
.pane-title {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.vb-panel {
  border-top: 1px solid var(--border);
  padding: 12px;
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.selection-card {
  display: grid;
  gap: 8px;
}

.selection-card span,
.review-item span {
  font-family: var(--font-mono);
  color: var(--accent);
  font-size: 12px;
}

.selection-card blockquote {
  margin: 0;
  max-height: 72px;
  overflow: auto;
  padding: 8px;
  border-left: 3px solid var(--accent);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 12px;
}

.review-list {
  display: grid;
  gap: 6px;
  margin-top: 10px;
  max-height: 120px;
  overflow: auto;
}

.review-item {
  display: grid;
  grid-template-columns: 80px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
}

.review-item p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.review-item button {
  border: none;
  background: transparent;
  color: var(--red);
  cursor: pointer;
}

.vb-actions {
  margin-top: 10px;
  color: var(--text-muted);
  font-size: 12px;
}

.compare-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 12px;
  flex-shrink: 0;
  overflow: hidden;
}

.compare-toolbar label {
  display: flex;
  align-items: center;
  gap: 8px;
}

.compare-view {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.history-code-view {
  height: 100%;
  overflow: auto;
  background: var(--bg-primary);
}

.small-icon {
  font-size: 15px;
}

.history-track {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 180px;
  max-width: 340px;
  overflow-x: auto;
}

.history-node {
  display: grid;
  gap: 1px;
  min-width: 74px;
  padding: 5px 7px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  text-align: left;
}

.history-node strong,
.history-node small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-node.current {
  border-color: var(--accent);
  color: var(--accent);
}

.history-keys {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.key-hint {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-muted);
  font-size: 11px;
  padding: 4px 6px;
  cursor: pointer;
}

.key-hint:disabled {
  opacity: 0.45;
  cursor: default;
}

.history-node.active {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--text-primary);
}

.history-lines {
  min-width: max-content;
}

.history-line {
  display: grid;
  grid-template-columns: 52px 1fr;
  min-width: max-content;
  min-height: 18px;
  overflow: hidden;
  border-left: 3px solid transparent;
  transform-origin: left center;
  will-change: transform, opacity, max-height;
}

.history-line.added {
  background: rgba(34, 197, 94, 0.12);
  border-left-color: var(--green, #22c55e);
}

.history-line.removed {
  background: rgba(239, 68, 68, 0.12);
  border-left-color: var(--red, #ef4444);
}

.history-line.removed pre {
  text-decoration: line-through;
  opacity: 0.72;
}

.history-line.changed {
  background: rgba(234, 179, 8, 0.11);
}

.history-line.current-diff {
  outline: 1px solid var(--accent);
  outline-offset: -1px;
}

.history-line.entering {
  animation: history-line-enter 780ms cubic-bezier(0.16, 1.18, 0.3, 1) both;
  box-shadow: inset 6px 0 0 rgba(34, 197, 94, 0.42), 0 8px 24px rgba(34, 197, 94, 0.12);
}

.history-line.leaving {
  animation: history-line-leave 780ms cubic-bezier(0.4, 0, 0.2, 1) both;
  box-shadow: inset 6px 0 0 rgba(239, 68, 68, 0.42), 0 8px 24px rgba(239, 68, 68, 0.12);
}

@keyframes history-line-enter {
  0% {
    max-height: 0;
    opacity: 0;
    transform: translate3d(160px, 0, 0) scale(0.985);
  }
  42% {
    max-height: 28px;
    opacity: 0.48;
    transform: translate3d(160px, 0, 0) scale(0.985);
  }
  100% {
    max-height: 28px;
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
}

@keyframes history-line-leave {
  0% {
    max-height: 28px;
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
  48% {
    max-height: 28px;
    opacity: 0.52;
    transform: translate3d(-150px, 0, 0) scale(0.985);
  }
  100% {
    max-height: 0;
    opacity: 0;
    transform: translate3d(-180px, 0, 0) scale(0.98);
  }
}

.secondary-btn,
.primary-btn {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

.secondary-btn.active,
.primary-btn {
  border-color: var(--accent);
  background: var(--accent-dim);
  color: var(--accent);
}

.secondary-btn:disabled,
.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.workspace-empty,
.workspace-error {
  padding: 24px;
  color: var(--text-muted);
  text-align: center;
}

.workspace-error { color: var(--red); }
.viewer-empty { margin: auto; }

.workspace-slide-enter-active,
.workspace-slide-leave-active,
.content-slide-enter-active,
.content-slide-leave-active {
  transition: transform 240ms cubic-bezier(0.22, 1, 0.36, 1), opacity 160ms ease;
}

.workspace-slide-enter-from,
.workspace-slide-leave-to,
.content-slide-enter-from,
.content-slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .history-line.entering,
  .history-line.leaving,
  .workspace-slide-enter-active,
  .workspace-slide-leave-active,
  .content-slide-enter-active,
  .content-slide-leave-active {
    transition: none;
    animation: none;
  }
}

@media (max-width: 900px) {
  .workspace-drawer,
  .file-content-panel {
    top: 48px;
    right: 0;
    width: 100vw;
  }
}
</style>
