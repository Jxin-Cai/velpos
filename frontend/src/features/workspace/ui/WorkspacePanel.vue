<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { downloadWorkspaceSelection } from '@entities/project/api/projectApi'
import hljs from 'highlight.js/lib/common'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys'
import { useTimeout } from '@shared/lib/useTimeout'
import { escapeHtml } from '@shared/lib/escapeHtml'
import { cachedParse } from '@features/message-display'
import { useWorkspace } from '../model/useWorkspace'
import { getFilePreviewType, getFileRawUrl } from '../lib/fileTypes'
import ImagePreview from './ImagePreview.vue'
import PdfPreview from './PdfPreview.vue'
import ExcelPreview from './ExcelPreview.vue'
import PreviewControls from './PreviewControls.vue'
import CsvPreview from './CsvPreview.vue'
import HtmlPreview from './HtmlPreview.vue'
import JsonPreview from './JsonPreview.vue'
import MediaPreview from './MediaPreview.vue'

const props = defineProps({
  visible: { type: Boolean, required: true },
  project: { type: Object, default: null },
  initialPath: { type: String, default: '' },
  vbRunning: { type: Boolean, default: false },
  vbMessage: { type: String, default: '' },
})

const emit = defineEmits(['close', 'apply-vb'])

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
const fullscreenReviewOpen = ref(false)
const vbMode = ref(false)
const fileViewMode = ref('text')
const previewZoom = ref(1)
const pendingSelection = ref(null)
const reviewComment = ref('')
const reviews = ref([])
const selectionAnchorLine = ref(null)
const isSelectingLines = ref(false)
const compareMode = ref(false)
const versionCursor = ref(0)
const versionContents = ref({})
const diffCursor = ref(-1)
const historyRows = ref([])
const selectedNodeKeys = ref(new Set())
const lastSelectedRowIndex = ref(-1)
const exportLoading = ref(false)
const copyStatus = ref('')
let copyStatusTimer = null
let historyTransitionTimer = null
let historyAnchorFrame = null
const { set: setTimer, clear: clearTimerById } = useTimeout()

const projectId = computed(() => props.project?.id || '')
const fileLines = computed(() => (selectedFile.value?.content || '').split('\n'))
const currentReviews = computed(() => {
  const path = selectedFile.value?.path
  return path ? reviews.value.filter((review) => review.path === path) : []
})
const visibleReviews = computed(() => (
  contentFullscreen.value ? currentReviews.value : reviews.value
))
const canApplyVb = computed(() => selectedFile.value && currentReviews.value.length > 0 && !props.vbRunning)
const binaryPreviewType = computed(() => selectedFile.value ? getFilePreviewType(selectedFile.value.path) : null)
const binaryPreviewUrl = computed(() => {
  if (!selectedFile.value || !projectId.value) return ''
  return getFileRawUrl(projectId.value, selectedFile.value.path)
})
const currentFileDownloadUrl = computed(() => binaryPreviewUrl.value)
const isMarkdownFile = computed(() => {
  const path = selectedFile.value?.path || ''
  return /\.md(?:own)?$/i.test(path)
})
const fileExtension = computed(() => selectedFile.value?.path.split('.').pop()?.toLowerCase() || '')
const renderedPreviewType = computed(() => {
  if (isMarkdownFile.value) return 'markdown'
  if (fileExtension.value === 'json') return 'json'
  if (fileExtension.value === 'html' || fileExtension.value === 'htm') return 'html'
  if (fileExtension.value === 'csv') return 'csv'
  return ''
})
const hasRenderedPreview = computed(() => Boolean(renderedPreviewType.value))
const showRenderedPreview = computed(() => (
  fileViewMode.value === 'preview' && hasRenderedPreview.value && !compareMode.value
))
const renderedMarkdown = computed(() => (
  isMarkdownFile.value ? cachedParse(selectedFile.value?.content || '') : ''
))
const treeNodes = computed(() => buildTree(files.value))
const treeRows = computed(() => flattenTree(treeNodes.value, expandedDirs.value))
const selectedNodes = computed(() => collectSelectedNodes(treeNodes.value, selectedNodeKeys.value))
const selectedPaths = computed(() => selectedNodes.value.map((node) => node.path).filter(Boolean))
const hasWorkspaceSelection = computed(() => selectedPaths.value.length > 0)
const showBulkSelectionToolbar = computed(() => {
  if (!hasWorkspaceSelection.value) return false
  const onlyNode = selectedNodes.value.length === 1 ? selectedNodes.value[0] : null
  return !(
    onlyNode?.type === 'file'
    && onlyNode.path === selectedFile.value?.path
  )
})
const selectionSummary = computed(() => {
  const count = selectedPaths.value.length
  if (count === 0) return 'No selection'
  if (count === 1) return selectedPaths.value[0]
  return `${count} items selected`
})
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
  if (visible && projectId.value) refreshFilesAndOpenRequestedPath()
})

watch(projectId, (newProjectId, oldProjectId) => {
  if (newProjectId !== oldProjectId) {
    resetContentState()
    clearWorkspaceSelection()
    clearSelection()
    reviews.value = []
  }
  if (props.visible && newProjectId) refreshFilesAndOpenRequestedPath()
})

watch(() => props.initialPath, (path) => {
  if (props.visible && path) openRequestedPath(path)
})

watch(vbMode, (enabled) => {
  if (!enabled) cancelPendingReview()
})

async function refreshFiles() {
  await loadFiles(projectId.value, { changedOnly: changedOnly.value, keyword: keyword.value })
}

async function refreshFilesAndOpenRequestedPath() {
  await refreshFiles()
  if (props.initialPath) await openRequestedPath(props.initialPath)
}

function projectRelativePath(path) {
  const value = String(path || '').replace(/\\/g, '/')
  const root = String(props.project?.dir_path || '').replace(/\\/g, '/').replace(/\/+$/, '')
  if (root && value.startsWith(`${root}/`)) return value.slice(root.length + 1)
  return value.replace(/^\.?\//, '')
}

async function openRequestedPath(path) {
  const relativePath = projectRelativePath(path)
  if (!relativePath) return
  const parts = relativePath.split('/').filter(Boolean)
  const nextExpanded = new Set(expandedDirs.value)
  for (let index = 1; index < parts.length; index += 1) {
    nextExpanded.add(parts.slice(0, index).join('/'))
  }
  expandedDirs.value = nextExpanded
  await selectFile(relativePath)
}

async function selectFile(path) {
  await openFile(projectId.value, path)
  contentOpen.value = true
  vbMode.value = false
  fileViewMode.value = 'text'
  previewZoom.value = 1
  compareMode.value = false
  versionCursor.value = 0
  versionContents.value = {}
  clearHistoryTransition()
  historyRows.value = []
  pendingSelection.value = null
  reviewComment.value = ''
  selectionAnchorLine.value = null
}

async function openFileFullscreen(path) {
  await selectFile(path)
  contentFullscreen.value = true
}

function setSelectedNodeKeys(keys) {
  selectedNodeKeys.value = new Set(keys)
}

function handleTreeRowClick(node, index, event) {
  const currentKeys = selectedNodeKeys.value
  if (event.shiftKey && lastSelectedRowIndex.value >= 0) {
    const start = Math.min(lastSelectedRowIndex.value, index)
    const end = Math.max(lastSelectedRowIndex.value, index)
    const next = new Set(currentKeys)
    for (let i = start; i <= end; i += 1) {
      const row = treeRows.value[i]
      if (row?.path) next.add(row.key)
    }
    setSelectedNodeKeys(next)
  } else if (event.metaKey || event.ctrlKey) {
    const next = new Set(currentKeys)
    if (next.has(node.key)) next.delete(node.key)
    else next.add(node.key)
    setSelectedNodeKeys(next)
    lastSelectedRowIndex.value = index
  } else {
    setSelectedNodeKeys(node.path ? [node.key] : [])
    lastSelectedRowIndex.value = index
  }

  if (node.type === 'dir' && !event.shiftKey && !event.metaKey && !event.ctrlKey) {
    toggleDir(node)
  }
  if (node.type === 'file' && !event.shiftKey && !event.metaKey && !event.ctrlKey) {
    selectFile(node.path)
  }
}

function clearWorkspaceSelection() {
  setSelectedNodeKeys([])
  lastSelectedRowIndex.value = -1
}

function selectedAbsolutePaths() {
  const root = (props.project?.dir_path || '').replace(/\/$/, '')
  return selectedPaths.value.map((path) => (root ? `${root}/${path}` : path))
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`
}

function showCopyStatus(message) {
  copyStatus.value = message
  if (copyStatusTimer) clearTimerById(copyStatusTimer)
  copyStatusTimer = setTimer(() => { copyStatus.value = ''; copyStatusTimer = null }, 1600)
}

async function copyText(text, message) {
  if (text === null || text === undefined) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      try {
        textarea.value = text
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
      } finally {
        textarea.remove()
      }
    }
    showCopyStatus(message)
  } catch (e) {
    showCopyStatus(e.message || 'Copy failed')
  }
}

async function copyCurrentFile() {
  if (selectedFile.value?.is_binary) return
  await copyText(selectedFile.value?.content ?? '', 'File contents copied')
}

async function copySelectedPaths() {
  await copyText(selectedAbsolutePaths().join('\n'), 'Paths copied')
}

async function copySelectedCpCommand() {
  const sources = selectedAbsolutePaths().map(shellQuote).join(' ')
  await copyText(`cp -R ${sources} ./`, 'cp command copied')
}

function closeSelectionMenu(event) {
  event.currentTarget.closest('details')?.removeAttribute('open')
}

async function downloadSelectionZip() {
  if (!projectId.value || !hasWorkspaceSelection.value || exportLoading.value) return
  exportLoading.value = true
  try {
    await downloadWorkspaceSelection(projectId.value, selectedPaths.value)
  } catch (e) {
    showCopyStatus(e.message || 'Export failed')
  } finally {
    exportLoading.value = false
  }
}

function resetContentState() {
  contentOpen.value = false
  contentFullscreen.value = false
  fullscreenReviewOpen.value = false
  compareMode.value = false
  fileViewMode.value = 'text'
  previewZoom.value = 1
  versionCursor.value = 0
  versionContents.value = {}
  clearHistoryTransition()
  historyRows.value = []
  pendingSelection.value = null
  reviewComment.value = ''
  selectionAnchorLine.value = null
}

function closeContent() {
  resetContentState()
  clearSelection()
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

function collectSelectedNodes(nodes, keys) {
  const selected = []
  function visit(node) {
    if (keys.has(node.key) && node.path) selected.push(node)
    for (const child of node.children || []) visit(child)
  }
  for (const node of nodes) visit(node)
  return selected
}

function toggleDir(node) {
  const next = new Set(expandedDirs.value)
  if (next.has(node.key)) next.delete(node.key)
  else next.add(node.key)
  expandedDirs.value = next
}

function collapseAllDirectories() {
  expandedDirs.value = new Set()
}

function fileIconKind(path) {
  const extension = String(path || '').split('.').pop()?.toLowerCase() || ''
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'avif'].includes(extension)) return 'image'
  if (['mp3', 'wav', 'ogg', 'm4a', 'mp4', 'webm', 'mov'].includes(extension)) return 'media'
  if (['zip', 'tar', 'gz', 'rar', '7z'].includes(extension)) return 'archive'
  if (['json', 'csv', 'xls', 'xlsx'].includes(extension)) return 'data'
  if (['md', 'txt', 'pdf', 'doc', 'docx'].includes(extension)) return 'document'
  if ([
    'js', 'jsx', 'ts', 'tsx', 'vue', 'py', 'java', 'go', 'rs', 'rb', 'php',
    'css', 'scss', 'sh', 'sql', 'xml', 'yaml', 'yml', 'html',
  ].includes(extension)) return 'code'
  return 'file'
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
  setPendingSelection(start, end, text)
}

function setPendingSelection(start, end, selectedText = '', shouldFocus = true) {
  const startLine = Math.max(1, Math.min(Number(start), Number(end)))
  const endLine = Math.min(fileLines.value.length, Math.max(Number(start), Number(end)))
  pendingSelection.value = {
    start_line: startLine,
    end_line: endLine,
    selected_text: selectedText || fileLines.value.slice(startLine - 1, endLine).join('\n'),
  }
  if (shouldFocus) nextTick(() => document.querySelector('.review-composer .vb-comment-input')?.focus())
}

function handleLinePointerDown(line, event) {
  if (!vbMode.value || event.button !== 0) return
  event.preventDefault()
  const anchor = event.shiftKey && selectionAnchorLine.value ? selectionAnchorLine.value : line
  if (!event.shiftKey) selectionAnchorLine.value = line
  isSelectingLines.value = true
  setPendingSelection(anchor, line, '', false)
}

function handleLineClick(line, event) {
  if (!vbMode.value || event.detail !== 0) return
  const anchor = event.shiftKey && selectionAnchorLine.value ? selectionAnchorLine.value : line
  if (!event.shiftKey) selectionAnchorLine.value = line
  setPendingSelection(anchor, line)
}

function handleLinePointerEnter(line) {
  if (!vbMode.value || !isSelectingLines.value || !selectionAnchorLine.value) return
  setPendingSelection(selectionAnchorLine.value, line, '', false)
}

function stopLineSelection() {
  const shouldFocus = isSelectingLines.value
  isSelectingLines.value = false
  if (shouldFocus) nextTick(() => document.querySelector('.review-composer .vb-comment-input')?.focus())
}

function isPendingLine(line) {
  const selection = pendingSelection.value
  return Boolean(selection && line >= selection.start_line && line <= selection.end_line)
}

function reviewsOnLine(line) {
  return currentReviews.value.filter((review) => line >= review.start_line && line <= review.end_line)
}

function reviewsEndingAt(line) {
  return currentReviews.value.filter((review) => review.end_line === line)
}

function cancelPendingReview() {
  pendingSelection.value = null
  reviewComment.value = ''
  isSelectingLines.value = false
  window.getSelection()?.removeAllRanges()
}

function handleReviewComposerKeydown(event) {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    event.preventDefault()
    addSelectionReview()
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    cancelPendingReview()
  }
}

function addSelectionReview() {
  const comment = reviewComment.value.trim()
  if (!pendingSelection.value || !comment || !selectedFile.value) return
  reviews.value.push({
    id: `${selectedFile.value.path}:${pendingSelection.value.start_line}:${pendingSelection.value.end_line}:${Date.now()}`,
    path: selectedFile.value.path,
    ...pendingSelection.value,
    comment,
  })
  cancelPendingReview()
}

function removeReview(review) {
  reviews.value = reviews.value.filter((item) => item.id !== review.id)
}

function clearCurrentReviews() {
  const path = selectedFile.value?.path
  if (!path) return
  reviews.value = reviews.value.filter((review) => review.path !== path)
}

async function focusReview(review) {
  if (selectedFile.value?.path !== review.path) {
    await selectFile(review.path)
  }
  fileViewMode.value = 'review'
  vbMode.value = true
  await nextTick()
  document.querySelector(`.code-line[data-line="${review.end_line}"]`)?.scrollIntoView({
    behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    block: 'center',
  })
}

function setFileViewMode(mode) {
  fileViewMode.value = mode
  vbMode.value = mode === 'review'
  compareMode.value = false
  cancelPendingReview()
}

function zoomOut() {
  previewZoom.value = Math.max(0.5, previewZoom.value - 0.25)
}

function zoomIn() {
  previewZoom.value = Math.min(2, previewZoom.value + 0.25)
}

function resetZoom() {
  previewZoom.value = 1
}

function toggleContentFullscreen() {
  contentFullscreen.value = !contentFullscreen.value
  fullscreenReviewOpen.value = false
}

function toggleFullscreenReview(event) {
  fullscreenReviewOpen.value = !fullscreenReviewOpen.value
  if (!fullscreenReviewOpen.value) {
    event.currentTarget?.blur()
  }
}

function applyVb() {
  if (!canApplyVb.value) return
  emit('apply-vb', {
    file_path: selectedFile.value.path,
    reviews: currentReviews.value.map(({ start_line, end_line, selected_text, comment }) => ({
      start_line,
      end_line,
      selected_text,
      comment,
    })),
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
    clearTimerById(historyTransitionTimer)
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
  historyTransitionTimer = setTimer(() => {
    historyTransitionTimer = null
    setSettledHistoryRows()
    nextTick(() => restoreHistoryScrollAnchor(anchor))
  }, 820)
}

function handleKeydown(event) {
  if (!props.visible) return
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'c' && hasWorkspaceSelection.value) {
    if (isEditableTarget(event.target) || window.getSelection()?.toString()) return
    event.preventDefault()
    copySelectedPaths().catch(() => {})
    return
  }
  if (event.key === 'Escape') {
    if (pendingSelection.value) {
      cancelPendingReview()
      return
    }
    if (contentFullscreen.value) {
      contentFullscreen.value = false
      fullscreenReviewOpen.value = false
      return
    }
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('pointerup', stopLineSelection)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('pointerup', stopLineSelection)
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

import { splitLines, buildSideBySideDiff, createDiffRow } from '@shared/lib/diff'

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
      <div v-if="visible" class="workspace-backdrop" @mousedown.self="$emit('close')">
        <section class="workspace-workbench" role="dialog" aria-modal="true" aria-label="Project files">
          <header class="workspace-workbench-header">
            <div class="workspace-workbench-title">
              <span class="workspace-title-icon" aria-hidden="true">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>
                  <path d="M3 10h18"/>
                </svg>
              </span>
              <div>
                <h2>Project files</h2>
                <p>{{ project?.dir_path || 'No project selected' }}</p>
              </div>
            </div>
            <div class="workspace-workbench-actions">
              <span>CLAUDE.md and .claude are hidden</span>
              <button class="icon-btn" aria-label="Close project files" @click="$emit('close')">×</button>
            </div>
          </header>

          <div class="workspace-workbench-body">
            <aside class="workspace-drawer" aria-label="Project file tree">

        <div class="explorer-header">
          <div>
            <strong>Files</strong>
            <span>{{ files.length }}</span>
          </div>
          <div class="explorer-actions">
            <button
              type="button"
              class="explorer-icon-btn"
              aria-label="Collapse all folders"
              title="Collapse all"
              :disabled="expandedDirs.size === 0"
              @click="collapseAllDirectories"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path d="M4 7h6l2 2h8v9H4z"/><path d="m9 13 3 3 3-3"/>
              </svg>
            </button>
            <button
              type="button"
              class="explorer-icon-btn"
              aria-label="Refresh files"
              title="Refresh"
              :disabled="loading"
              @click="refreshFiles"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path d="M20 11a8 8 0 1 0 2 5"/><path d="M20 4v7h-7"/>
              </svg>
            </button>
          </div>
        </div>
        <div class="workspace-filters">
          <label class="file-search-wrap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>
            </svg>
            <span class="sr-only">Search files</span>
            <input v-model="keyword" class="file-search" placeholder="Filter files" @keydown.enter="refreshFiles" />
          </label>
          <label class="changed-toggle">
            <input v-model="changedOnly" type="checkbox" @change="refreshFiles" />
            <span>Changed files</span>
          </label>
        </div>

        <div v-if="showBulkSelectionToolbar" class="selection-toolbar">
          <span class="selection-summary" :title="selectionSummary">{{ selectionSummary }}</span>
          <div class="selection-actions">
            <button class="selection-download-btn" :disabled="exportLoading" @click="downloadSelectionZip">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>
              </svg>
              {{ exportLoading ? 'Preparing…' : 'Download' }}
            </button>
            <details class="selection-more-menu">
              <summary class="explorer-icon-btn" aria-label="More file actions" title="More actions">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/>
                </svg>
              </summary>
              <div class="selection-menu-popover">
                <button type="button" @click="closeSelectionMenu($event); copySelectedPaths()">Copy path</button>
                <button type="button" @click="closeSelectionMenu($event); copySelectedCpCommand()">Copy cp command</button>
                <span>Downloads are packaged as ZIP</span>
              </div>
            </details>
            <button class="icon-btn small-icon" aria-label="Clear selection" @click="clearWorkspaceSelection">×</button>
          </div>
          <span v-if="copyStatus" class="copy-status">{{ copyStatus }}</span>
        </div>

        <div v-if="loading" class="workspace-empty">Loading files...</div>
        <div v-else-if="error" class="workspace-error">{{ error }}</div>
        <div v-else-if="!treeRows.length" class="workspace-empty">No files</div>
        <div v-else class="tree-list" title="Use Cmd/Ctrl-click or Shift-click to select multiple items">
          <button
            v-for="(node, index) in treeRows"
            :key="node.key"
            class="tree-row"
            :class="{ active: selectedFile?.path === node.path, selected: selectedNodeKeys.has(node.key), changed: node.is_changed }"
            :style="{ '--tree-depth': node.depth, paddingLeft: `${10 + node.depth * 16}px` }"
            :aria-expanded="node.type === 'dir' ? expandedDirs.has(node.key) : undefined"
            :aria-current="selectedFile?.path === node.path ? 'true' : undefined"
            @click="handleTreeRowClick(node, index, $event)"
          >
            <span v-if="node.type === 'dir'" class="tree-caret" aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <path :d="expandedDirs.has(node.key) ? 'm6 9 6 6 6-6' : 'm9 18 6-6-6-6'"/>
              </svg>
            </span>
            <span v-else class="tree-caret"></span>
            <span class="tree-icon" :class="node.type === 'file' ? `file-kind-${fileIconKind(node.path)}` : 'file-kind-folder'" aria-hidden="true">
              <svg v-if="node.type === 'dir'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                <path :d="expandedDirs.has(node.key) ? 'M3 8h7l2 2h9l-2 9H5L3 8Z' : 'M3 6h7l2 2h9v11H3V6Z'"/>
              </svg>
              <svg v-else-if="fileIconKind(node.path) === 'code'" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <path d="m8 9-4 3 4 3m8-6 4 3-4 3M14 5l-4 14"/>
              </svg>
              <svg v-else-if="fileIconKind(node.path) === 'image'" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m4 17 5-5 4 4 3-3 4 4"/>
              </svg>
              <svg v-else-if="fileIconKind(node.path) === 'data'" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/>
              </svg>
              <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>
              </svg>
            </span>
            <span class="tree-name">{{ node.name }}</span>
            <span v-if="node.git_status" class="file-status">{{ node.git_status }}</span>
            <span
              v-if="node.type === 'file'"
              class="tree-fullscreen-btn"
              role="button"
              tabindex="-1"
              aria-label="Open in fullscreen"
              title="全屏打开"
              @click.stop="openFileFullscreen(node.path)"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3"/>
              </svg>
            </span>
          </button>
        </div>
            </aside>

      <section
        v-if="selectedFile"
        v-show="contentOpen"
        class="file-content-panel"
        :class="{ fullscreen: contentFullscreen }"
        aria-label="File content"
      >
        <header class="viewer-header">
          <div class="viewer-file-identity">
            <span class="viewer-file-icon" :class="`file-kind-${fileIconKind(selectedFile.path)}`" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>
              </svg>
            </span>
            <div>
              <strong :title="selectedFile.path">{{ selectedFile.path }}</strong>
              <div class="viewer-file-meta">
                <span>{{ selectedFile.size.toLocaleString() }} bytes</span>
                <span>{{ fileExtension.toUpperCase() || 'FILE' }}</span>
                <span v-if="selectedFile.truncated" class="viewer-file-warning">Truncated</span>
                <span v-if="selectedFile.is_binary">Binary</span>
              </div>
            </div>
          </div>
          <div class="viewer-actions">
            <span v-if="copyStatus" class="viewer-copy-status" role="status">{{ copyStatus }}</span>
            <div v-if="!selectedFile.is_binary" class="viewer-mode-toggle" role="group" aria-label="File view mode">
              <button
                class="secondary-btn"
                :class="{ active: fileViewMode === 'text' && !compareMode }"
                @click="setFileViewMode('text')"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                  <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>
                </svg>
                Text
              </button>
              <button
                class="secondary-btn"
                :class="{ active: fileViewMode === 'review' && !compareMode }"
                @click="setFileViewMode('review')"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                  <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/>
                </svg>
                Select lines
              </button>
              <button
                v-if="hasRenderedPreview"
                class="secondary-btn"
                :class="{ active: fileViewMode === 'preview' && !compareMode }"
                @click="setFileViewMode('preview')"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                  <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>
                </svg>
                Preview
              </button>
            </div>
            <button
              v-if="!selectedFile.is_binary"
              type="button"
              class="viewer-icon-action viewer-text-action"
              aria-label="Copy file contents"
              title="Copy file contents"
              @click="copyCurrentFile"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <rect x="9" y="9" width="11" height="11" rx="2"/><path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3"/>
              </svg>
              <span>Copy</span>
            </button>
            <a
              :href="currentFileDownloadUrl"
              :download="selectedFile.path.split('/').pop()"
              class="viewer-icon-action viewer-text-action"
              aria-label="Download current file"
              title="Download file"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>
              </svg>
              <span>Download</span>
            </a>
            <button class="secondary-btn" :class="{ active: compareMode }" :disabled="selectedFile.is_binary" @click="toggleCompare">History</button>
            <PreviewControls
              :zoom="previewZoom"
              :fullscreen="contentFullscreen"
              @zoom-out="zoomOut"
              @zoom-reset="resetZoom"
              @zoom-in="zoomIn"
              @toggle-fullscreen="toggleContentFullscreen"
            />
            <button class="icon-btn" aria-label="Close file" @click="closeContent">×</button>
          </div>
        </header>

        <div v-if="reading" class="workspace-empty viewer-empty">Reading file...</div>
        <template v-else-if="selectedFile.is_binary">
          <ImagePreview v-if="binaryPreviewType === 'image'" :src="binaryPreviewUrl" :path="selectedFile.path" :zoom="previewZoom" />
          <PdfPreview v-else-if="binaryPreviewType === 'pdf'" :src="binaryPreviewUrl" :zoom="previewZoom" />
          <ExcelPreview v-else-if="binaryPreviewType === 'excel'" :src="binaryPreviewUrl" :zoom="previewZoom" />
          <MediaPreview
            v-else-if="binaryPreviewType === 'video' || binaryPreviewType === 'audio'"
            :src="binaryPreviewUrl"
            :path="selectedFile.path"
            :type="binaryPreviewType"
            :zoom="previewZoom"
          />
          <div v-else class="workspace-empty viewer-empty">Binary file cannot be previewed.</div>
        </template>
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
          <div v-else-if="showRenderedPreview" class="rendered-preview-shell">
            <div class="preview-review-guide">
              <span>{{ renderedPreviewType === 'html' ? 'Interactive preview · use the page naturally, or switch modes to review its source.' : 'Rendered preview · switch to line selection to add comments.' }}</span>
              <button class="secondary-btn" @click="setFileViewMode('review')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                  <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4 4h10a4 4 0 0 1 4 4z"/>
                </svg>
                Select lines
              </button>
            </div>
            <article
              v-if="renderedPreviewType === 'markdown'"
              class="markdown-file-preview markdown-body"
              :style="{ zoom: previewZoom }"
              v-html="renderedMarkdown"
            ></article>
            <JsonPreview v-else-if="renderedPreviewType === 'json'" :content="selectedFile.content" :zoom="previewZoom" />
            <HtmlPreview
              v-else-if="renderedPreviewType === 'html'"
              :content="selectedFile.content"
              :zoom="previewZoom"
              :truncated="selectedFile.truncated"
            />
            <CsvPreview
              v-else-if="renderedPreviewType === 'csv'"
              :content="selectedFile.content"
              :zoom="previewZoom"
              :truncated="selectedFile.truncated"
            />
          </div>
          <div v-else class="code-view" :class="{ 'review-mode': vbMode }" :style="{ fontSize: `${12.5 * previewZoom}px` }" @mouseup="handleCodeMouseUp">
            <div v-if="vbMode" class="review-mode-banner">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L8 18l-4 1 1-4Z"/></svg>
              <span>Select lines to leave a comment</span>
              <kbd>⌘ Enter</kbd>
            </div>
            <template v-for="(line, index) in highlightedFileLines" :key="index">
              <div
                class="code-line"
                :class="{
                  'pending-line': isPendingLine(index + 1),
                  'reviewed-line': reviewsOnLine(index + 1).length,
                }"
                :data-line="index + 1"
                @pointerenter="handleLinePointerEnter(index + 1)"
              >
                <button
                  class="line-no line-no-button"
                  :class="{ selectable: vbMode }"
                  :aria-label="vbMode ? `Select line ${index + 1}` : `Line ${index + 1}`"
                  :tabindex="vbMode ? 0 : -1"
                  @pointerdown="handleLinePointerDown(index + 1, $event)"
                  @click="handleLineClick(index + 1, $event)"
                >{{ index + 1 }}</button>
                <pre v-html="line"></pre>
                <span v-if="reviewsEndingAt(index + 1).length" class="line-review-dot" :title="`${reviewsEndingAt(index + 1).length} review comment(s)`">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/>
                  </svg>
                </span>
              </div>
              <div v-if="pendingSelection?.end_line === index + 1" class="review-composer" @mouseup.stop>
                <div class="review-composer-heading">
                  <span>Comment on {{ pendingSelection.start_line === pendingSelection.end_line ? `line ${pendingSelection.start_line}` : `lines ${pendingSelection.start_line}–${pendingSelection.end_line}` }}</span>
                  <button aria-label="Cancel comment" title="Cancel" @click.stop="cancelPendingReview">×</button>
                </div>
                <textarea
                  v-model="reviewComment"
                  class="vb-comment-input"
                  rows="3"
                  placeholder="Describe what Codex should change…"
                  @keydown="handleReviewComposerKeydown"
                ></textarea>
                <div class="review-composer-actions">
                  <span>⌘ Enter to add</span>
                  <button class="primary-btn" :disabled="!reviewComment.trim()" @click.stop="addSelectionReview">Add comment</button>
                </div>
              </div>
            </template>
          </div>

          <section v-if="selectedDiff?.patch && !compareMode && fileViewMode !== 'preview'" class="diff-box">
            <div class="diff-title">Diff</div>
            <pre>{{ selectedDiff.patch }}</pre>
          </section>

        </template>
      </section>
      <section v-else class="file-content-panel file-welcome-panel" aria-label="File preview">
        <div class="file-welcome-icon" aria-hidden="true">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/>
            <path d="M14 2v6h6M8 13h8M8 17h5"/>
          </svg>
        </div>
        <h3>Select a file to preview</h3>
        <p>Browse project files, preview media and documents, inspect history, or leave grouped review comments.</p>
      </section>
      <aside
        class="workspace-review-panel"
        :class="{
          'fullscreen-review-rail': contentFullscreen,
          'fullscreen-review-open': contentFullscreen && fullscreenReviewOpen,
        }"
        :aria-label="contentFullscreen ? 'Current file review comments' : 'Review comments'"
      >
        <button
          v-if="contentFullscreen"
          type="button"
          class="fullscreen-review-handle"
          :aria-expanded="fullscreenReviewOpen"
          aria-label="Toggle current file review comments"
          @click="toggleFullscreenReview"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/>
          </svg>
          <span>{{ currentReviews.length }}</span>
        </button>
        <div class="workspace-review-panel-content">
        <header class="workspace-review-header">
          <div>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/>
            </svg>
            <strong>{{ contentFullscreen ? 'Current file comments' : 'Review comments' }}</strong>
          </div>
          <span>{{ visibleReviews.length }}</span>
        </header>
        <div class="workspace-review-list">
          <div v-if="!visibleReviews.length" class="workspace-review-empty">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
              <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4 4h10a4 4 0 0 1 4 4z"/>
            </svg>
            <p>No comments yet</p>
            <span>Select one or more source lines and describe the change you want.</span>
          </div>
          <article
            v-for="review in visibleReviews"
            :key="review.id"
            class="workspace-review-card"
            :class="{ active: review.path === selectedFile?.path }"
            tabindex="0"
            @click="focusReview(review)"
            @keydown.enter.prevent="focusReview(review)"
            @keydown.space.prevent="focusReview(review)"
          >
            <div>
              <strong :title="review.path">{{ review.path }}</strong>
              <button
                type="button"
                :aria-label="`Remove review for ${review.path}`"
                @click.stop="removeReview(review)"
              >×</button>
            </div>
            <span>{{ review.start_line === review.end_line ? `L${review.start_line}` : `L${review.start_line}–${review.end_line}` }}</span>
            <p>{{ review.comment }}</p>
          </article>
        </div>
        <footer class="workspace-review-actions">
          <div>
            <span>{{ selectedFile ? `${currentReviews.length} on current file` : 'Select a file' }}</span>
            <button v-if="currentReviews.length" class="text-btn" @click="clearCurrentReviews">Clear current</button>
          </div>
          <span v-if="vbMessage" class="review-status">{{ vbMessage }}</span>
          <button class="primary-btn" :disabled="!canApplyVb" @click="applyVb">
            {{ vbRunning ? 'Applying changes…' : currentReviews.length ? `Apply ${currentReviews.length} comment${currentReviews.length === 1 ? '' : 's'}` : 'Apply current comments' }}
          </button>
        </footer>
        </div>
      </aside>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.workspace-backdrop {
  position: fixed;
  inset: 0;
  z-index: 110;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28px;
  background: color-mix(in srgb, var(--bg-primary) 58%, transparent);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.workspace-workbench {
  width: min(1420px, calc(100vw - 56px));
  height: min(820px, calc(100vh - 56px));
  min-height: 480px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--glass-border);
  border-radius: 14px;
  background: var(--bg-primary);
  box-shadow: 0 24px 72px rgba(0, 0, 0, 0.34);
}

.workspace-workbench-header {
  min-height: 58px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
}

.workspace-workbench-title,
.workspace-workbench-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.workspace-title-icon {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--accent);
  background: var(--bg-primary);
}

.workspace-workbench-header h2,
.workspace-workbench-header p {
  margin: 0;
}

.workspace-workbench-header h2 {
  color: var(--text-primary);
  font-size: 14px;
}

.workspace-workbench-header p,
.workspace-workbench-actions > span {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-workbench-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 252px minmax(0, 1fr) 264px;
}

.workspace-drawer {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
}

.file-content-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

.file-content-panel:not(.fullscreen) {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--border-subtle) 54%, transparent);
}

.rendered-preview-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--layer-base);
}

.preview-review-guide {
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-muted);
  background: color-mix(in srgb, var(--bg-secondary) 88%, var(--bg-primary));
  font-size: 11px;
  line-height: 1.4;
}

.preview-review-guide .secondary-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 30px;
}

.workspace-review-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
}

.workspace-review-panel-content {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
}

.fullscreen-review-handle {
  display: none;
}

.workspace-review-header,
.workspace-review-header > div,
.workspace-review-actions > div {
  display: flex;
  align-items: center;
}

.workspace-review-header {
  min-height: 48px;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
}

.workspace-review-header > div {
  gap: 7px;
}

.workspace-review-header > span {
  min-width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: var(--text-secondary);
  background: var(--layer-active);
  font: 600 11px/1 var(--font-mono);
}

.workspace-review-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px;
}

.workspace-review-empty {
  display: grid;
  justify-items: center;
  padding: 32px 10px;
  color: var(--text-muted);
  text-align: center;
}

.workspace-review-empty p {
  margin: 9px 0 4px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.workspace-review-empty span {
  font-size: 11px;
  line-height: 1.5;
}

.workspace-review-card {
  margin-bottom: 7px;
  padding: 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  outline: none;
  background: var(--bg-primary);
  cursor: pointer;
  transition: border-color var(--transition-fast), background var(--transition-fast), box-shadow var(--transition-fast);
}

.workspace-review-card:hover,
.workspace-review-card:focus-visible,
.workspace-review-card.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 5%, var(--bg-primary));
}

.workspace-review-card:focus-visible,
.workspace-review-card.active {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 14%, transparent);
}

.workspace-review-card > div {
  display: flex;
  align-items: center;
  gap: 5px;
}

.workspace-review-card strong {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font: 600 10px/1.4 var(--font-mono);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-review-card > div button {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  background: transparent;
  cursor: pointer;
  font-size: 18px;
}

.workspace-review-card > div button:hover,
.workspace-review-card > div button:focus-visible {
  color: var(--red);
  background: var(--layer-active);
  outline: none;
}

.workspace-review-card > span {
  display: inline-block;
  margin-top: 6px;
  padding: 2px 5px;
  border-radius: 4px;
  color: var(--accent);
  background: var(--accent-dim);
  font: 10px/1.2 var(--font-mono);
}

.workspace-review-card p {
  margin: 7px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.workspace-review-actions {
  display: grid;
  gap: 7px;
  padding: 10px;
  border-top: 1px solid var(--border-subtle);
}

.workspace-review-actions > div {
  justify-content: space-between;
  gap: 8px;
  color: var(--text-muted);
  font-size: 11px;
}

.workspace-review-actions .primary-btn {
  width: 100%;
  min-height: 34px;
}

.review-status {
  color: var(--text-muted);
  font-size: 11px;
}

.file-content-panel.fullscreen {
  position: fixed;
  top: 0;
  bottom: 0;
  right: 0;
  left: 0;
  z-index: 120;
  width: 100vw;
  height: 100vh;
}

.file-content-panel.fullscreen ~ .workspace-review-panel {
  position: fixed;
  top: 53px;
  right: 0;
  bottom: 0;
  z-index: 121;
  width: min(320px, 100vw);
  display: flex;
  flex-direction: row;
  border-top: 0;
  border-left: 1px solid var(--border-subtle);
  box-shadow: -12px 0 32px rgb(0 0 0 / 16%);
  transform: translateX(calc(100% - 32px));
  transition: transform 170ms ease;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.file-content-panel.fullscreen ~ .workspace-review-panel:focus-within,
.file-content-panel.fullscreen ~ .workspace-review-panel.fullscreen-review-open {
  transform: translateX(0);
}

@media (hover: hover) {
  .file-content-panel.fullscreen ~ .workspace-review-panel:hover {
    transform: translateX(0);
  }
}

.file-content-panel.fullscreen ~ .workspace-review-panel .fullscreen-review-handle {
  width: 32px;
  min-width: 32px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  flex-direction: column;
  padding: 0;
  border: 0;
  color: white;
  background: #27272a;
  cursor: pointer;
}

.file-content-panel.fullscreen ~ .workspace-review-panel .fullscreen-review-handle span {
  font: 700 9px/1 var(--font-mono);
}

.file-content-panel.fullscreen ~ .workspace-review-panel .fullscreen-review-handle:focus-visible {
  position: relative;
  z-index: 1;
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.file-content-panel.fullscreen ~ .workspace-review-panel .workspace-review-list {
  display: block;
}

.file-content-panel.fullscreen ~ .workspace-review-panel .workspace-review-card {
  width: auto;
}

.file-welcome-panel {
  align-items: center;
  justify-content: center;
  padding: 32px;
  text-align: center;
  color: var(--text-secondary);
}

.file-welcome-panel h3 {
  margin: 14px 0 6px;
  color: var(--text-primary);
  font-size: 15px;
}

.file-welcome-panel p {
  max-width: 460px;
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
}

.file-welcome-icon {
  width: 48px;
  height: 48px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  color: var(--accent);
  background: var(--bg-secondary);
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

.viewer-header {
  min-height: 62px;
  padding: 10px 12px 10px 14px;
  border-bottom-color: var(--border-subtle);
  background: color-mix(in srgb, var(--bg-secondary) 88%, var(--bg-primary));
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

.viewer-file-identity {
  min-width: 150px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.viewer-file-identity > div {
  min-width: 0;
}

.viewer-file-icon {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-secondary);
  background: var(--bg-primary);
  box-shadow: var(--shadow-sm);
  margin: 0;
}

.viewer-file-icon.file-kind-code { color: var(--purple); }
.viewer-file-icon.file-kind-image { color: var(--green); }
.viewer-file-icon.file-kind-data { color: var(--yellow); }

.viewer-header strong {
  color: var(--text-primary);
  display: block;
  max-width: 360px;
  overflow: hidden;
  font: 600 12px/1.35 var(--font-mono);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.viewer-file-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 4px;
}

.viewer-file-meta span {
  margin: 0;
  padding: 1px 5px;
  border-radius: 4px;
  color: var(--text-muted);
  background: var(--layer-active);
  font: 9px/1.45 var(--font-mono);
}

.viewer-file-meta .viewer-file-warning {
  color: var(--yellow);
  background: color-mix(in srgb, var(--yellow) 10%, transparent);
}

.viewer-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.viewer-mode-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--bg-primary);
}

.viewer-mode-toggle .secondary-btn {
  min-height: 26px;
  padding: 3px 8px;
  border-color: transparent;
  font-size: 11px;
}

.viewer-mode-toggle .secondary-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.review-mode-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.review-button-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--accent);
  color: var(--text-on-accent);
  font: 600 10px/1 var(--font-mono);
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

.explorer-header {
  min-height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 8px 5px 12px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  background: var(--bg-secondary);
}

.explorer-header > div,
.explorer-actions {
  display: flex;
  align-items: center;
  gap: 7px;
}

.explorer-header strong {
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.explorer-header span {
  min-width: 20px;
  padding: 2px 6px;
  border-radius: 999px;
  color: var(--text-muted);
  background: var(--layer-active);
  font: 10px/1.4 var(--font-mono);
  text-align: center;
}

.explorer-icon-btn,
.viewer-icon-action {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  background: transparent;
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast), border-color var(--transition-fast);
}

.explorer-icon-btn:hover:not(:disabled),
.explorer-icon-btn:focus-visible,
.viewer-icon-action:hover,
.viewer-icon-action:focus-visible {
  border-color: var(--border);
  outline: none;
  color: var(--text-primary);
  background: var(--layer-active);
}

.explorer-icon-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.workspace-filters {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px;
  border-bottom: 1px solid var(--glass-border);
  background: color-mix(in srgb, var(--glass-bg) 44%, transparent);
  flex-shrink: 0;
}

.changed-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 7px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}

.changed-toggle input {
  width: 13px;
  height: 13px;
  margin: 0;
  accent-color: var(--accent);
}

.file-search-wrap {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  background: var(--bg-primary);
}

.file-search-wrap:focus-within {
  border-color: var(--accent);
  box-shadow: var(--ring);
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

.file-search {
  min-width: 0;
  height: 28px;
  padding: 0;
  border: 0;
  background: transparent;
  box-shadow: none;
  font-size: 11px;
}

.selection-toolbar {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--glass-border);
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  flex-shrink: 0;
}

.selection-summary {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
}

.selection-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.selection-download-btn {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 9px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  color: var(--accent);
  background: var(--accent-dim);
  cursor: pointer;
  font-size: 11px;
}

.selection-download-btn:disabled {
  opacity: 0.55;
  cursor: wait;
}

.selection-more-menu {
  position: relative;
}

.selection-more-menu > summary {
  list-style: none;
}

.selection-more-menu > summary::-webkit-details-marker {
  display: none;
}

.selection-menu-popover {
  position: absolute;
  top: calc(100% + 5px);
  left: 0;
  z-index: 20;
  width: 176px;
  display: grid;
  gap: 2px;
  padding: 5px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--dialog-surface);
  box-shadow: var(--dialog-shadow);
}

.selection-menu-popover button {
  min-height: 32px;
  padding: 0 8px;
  border: 0;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  background: transparent;
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.selection-menu-popover button:hover,
.selection-menu-popover button:focus-visible {
  outline: none;
  color: var(--text-primary);
  background: var(--layer-active);
}

.selection-menu-popover span {
  padding: 5px 8px 3px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 10px;
}

.copy-status {
  color: var(--accent);
  font-size: 11px;
}

.tree-list {
  flex: 1;
  overflow: auto;
  padding: 5px 6px 10px;
}

.tree-row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-height: 30px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
  padding-right: 8px;
  position: relative;
  transition: color var(--transition-fast), background var(--transition-fast), border-color var(--transition-fast);
}

.tree-row:hover {
  background: var(--layer-active);
  color: var(--text-primary);
}

.tree-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.tree-row.active {
  border-color: color-mix(in srgb, var(--accent) 28%, transparent);
  background: color-mix(in srgb, var(--accent) 9%, transparent);
  color: var(--text-primary);
}

.tree-row.selected {
  background: color-mix(in srgb, var(--accent) 7%, var(--layer-active));
  color: var(--text-primary);
}

.tree-row.selected {
  box-shadow: inset 2px 0 0 var(--accent);
}

.tree-row.changed .tree-name {
  color: var(--accent);
}

.tree-caret {
  width: 13px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  flex-shrink: 0;
}

.tree-icon {
  width: 17px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  flex-shrink: 0;
}

.tree-icon.file-kind-folder { color: var(--accent); }
.tree-icon.file-kind-code { color: var(--purple); }
.tree-icon.file-kind-image { color: var(--green); }
.tree-icon.file-kind-data { color: var(--yellow); }

.tree-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 12px;
}

.file-status {
  min-width: 17px;
  padding: 1px 4px;
  border-radius: 4px;
  color: var(--yellow);
  background: color-mix(in srgb, var(--yellow) 9%, transparent);
  font: 600 9px/1.4 var(--font-mono);
  text-align: center;
}

.tree-fullscreen-btn {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  opacity: 0;
  cursor: pointer;
  transition: opacity var(--transition-fast), color var(--transition-fast), background var(--transition-fast);
}

.tree-row:hover .tree-fullscreen-btn {
  opacity: 1;
}

.tree-fullscreen-btn:hover {
  color: var(--accent);
  background: var(--layer-active);
}

.viewer-icon-action {
  flex-shrink: 0;
  text-decoration: none;
}

.viewer-text-action {
  width: auto;
  gap: 5px;
  padding: 0 8px;
  font-size: 11px;
}

.viewer-copy-status {
  max-width: 132px;
  overflow: hidden;
  color: var(--accent);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.code-view {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--bg-primary);
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 20px;
}

.markdown-file-preview {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 24px 28px 48px;
  color: var(--text-primary);
  background: var(--bg-primary);
}

.markdown-file-preview :deep(pre) {
  overflow-x: auto;
}

.markdown-file-preview :deep(img) {
  max-width: 100%;
  height: auto;
}

.markdown-file-preview :deep(a) {
  color: var(--accent);
}

.review-mode-banner {
  position: sticky;
  top: 0;
  z-index: 6;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 5px 10px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font: 11px/1.4 var(--font-sans);
}

.review-mode-banner svg {
  color: var(--accent);
  flex-shrink: 0;
}

.review-mode-banner kbd {
  margin-left: auto;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font: 10px/1.2 var(--font-mono);
  white-space: nowrap;
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
  grid-template-columns: 48px minmax(max-content, 1fr) 26px;
  min-width: max-content;
  min-height: 20px;
  transition: background var(--transition-fast);
}

.code-view.review-mode .code-line:hover {
  background: color-mix(in srgb, var(--text-primary) 4%, transparent);
}

.code-line.pending-line {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.code-line.reviewed-line:not(.pending-line) {
  background: color-mix(in srgb, var(--purple) 5%, transparent);
}

.line-no {
  border: 0;
  color: var(--text-muted);
  text-align: right;
  padding: 0 9px 0 0;
  user-select: none;
}

.line-no-button {
  width: 100%;
  border: 0;
  background: transparent;
  font: inherit;
  cursor: default;
}

.line-no-button.selectable {
  color: var(--text-secondary);
  cursor: crosshair;
}

.line-no-button.selectable:hover,
.line-no-button.selectable:focus-visible {
  color: var(--accent);
  outline: none;
}

.code-line.pending-line .line-no-button,
.code-line.reviewed-line .line-no-button {
  color: var(--accent);
}

.line-review-dot {
  position: sticky;
  right: 4px;
  align-self: center;
  justify-self: center;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 18px;
  border: 0;
  border-radius: 6px;
  background: var(--purple);
  color: var(--text-on-accent);
}

.code-line pre,
.diff-box pre,
.history-line pre {
  margin: 0;
  white-space: pre;
  padding: 0 12px 0 8px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  font: inherit;
  line-height: inherit;
}

.code-line pre,
.history-line pre {
  overflow: visible;
}

.code-line pre {
  user-select: text;
  -webkit-user-select: text;
  cursor: text;
}

.code-line pre::selection,
.code-line pre :deep(*)::selection {
  background: color-mix(in srgb, var(--accent) 28%, transparent);
}

.review-composer {
  position: sticky;
  left: 56px;
  z-index: 5;
  display: grid;
  gap: 6px;
  width: min(460px, calc(100vw - 456px));
  margin: 5px 12px 10px 50px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-secondary);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.14);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.review-composer:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-dim), 0 8px 22px rgba(0, 0, 0, 0.16);
}

.file-content-panel.fullscreen .review-composer {
  width: min(560px, calc(100vw - 96px));
}

.review-composer-heading,
.review-composer-actions,
.review-queue-heading,
.review-queue-heading > div {
  display: flex;
  align-items: center;
}

.review-composer-heading,
.review-composer-actions,
.review-queue-heading {
  justify-content: space-between;
  gap: 12px;
}

.review-composer-heading > span {
  color: var(--text-secondary);
  font: 500 11px/1.3 var(--font-sans);
}

.review-composer-heading button,
.text-btn {
  border: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.review-composer-heading button {
  width: 26px;
  height: 26px;
  font-size: 18px;
}

.review-composer textarea {
  width: 100%;
  resize: vertical;
  min-height: 58px;
  padding: 5px 6px;
  border: 0;
  border-radius: 0;
  outline: none;
  background: transparent;
  color: var(--text-primary);
  font: 12px/1.5 var(--font-sans);
}

.review-composer textarea:focus {
  box-shadow: none;
}

.review-composer-actions > span {
  color: var(--text-muted);
  font-size: 10px;
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
  border-top: 1px solid var(--border-subtle);
  padding: 10px 12px;
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.review-queue-heading > div {
  gap: 8px;
}

.review-queue-heading strong {
  color: var(--text-primary);
  font-size: 12px;
}

.review-queue-heading span {
  color: var(--text-muted);
  font-size: 11px;
}

.text-btn {
  min-height: 28px;
  padding: 0 4px;
  font-size: 11px;
}

.text-btn:hover,
.text-btn:focus-visible {
  color: var(--accent);
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
  gap: 0;
  margin-top: 6px;
  max-height: 150px;
  overflow: auto;
}

.review-item {
  display: grid;
  grid-template-columns: 80px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 7px 0;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
}

.review-item:hover {
  background: transparent;
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
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  font-size: 17px;
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
.workspace-slide-leave-active {
  transition: opacity 160ms ease;
}

.workspace-slide-enter-from,
.workspace-slide-leave-to {
  opacity: 0;
}

.workspace-slide-enter-active .workspace-workbench,
.workspace-slide-leave-active .workspace-workbench {
  transition: transform 240ms cubic-bezier(0.22, 1, 0.36, 1), opacity 160ms ease;
}

.workspace-slide-enter-from .workspace-workbench,
.workspace-slide-leave-to .workspace-workbench {
  transform: translateY(10px) scale(0.985);
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .file-content-panel.fullscreen ~ .workspace-review-panel {
    transition: none;
  }

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

@media (max-width: 1180px) {
  .workspace-workbench-body {
    grid-template-columns: minmax(190px, 30vw) minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) minmax(140px, 22vh);
  }

  .workspace-review-panel {
    grid-column: 1 / -1;
    grid-row: 2;
    border-top: 1px solid var(--border-subtle);
    border-left: 0;
  }

  .workspace-review-list {
    display: flex;
    gap: 8px;
    padding: 8px;
  }

  .workspace-review-card {
    width: 240px;
    flex: 0 0 auto;
    margin: 0;
  }

  .workspace-review-empty {
    width: 100%;
    padding: 12px;
  }

  .workspace-review-actions {
    grid-template-columns: 1fr auto;
    align-items: center;
  }

  .workspace-review-actions .primary-btn {
    width: auto;
    min-width: 180px;
  }
}

@media (max-width: 900px) {
  .workspace-backdrop {
    padding: 0;
  }

  .workspace-workbench {
    width: 100vw;
    height: 100vh;
    border: 0;
    border-radius: 0;
  }

  .workspace-workbench-actions > span {
    display: none;
  }

  .review-composer,
  .file-content-panel.fullscreen .review-composer {
    width: calc(100vw - 88px);
  }

  .viewer-text-action {
    width: 30px;
    padding: 0;
  }

  .viewer-text-action span {
    display: none;
  }

  .viewer-header strong {
    max-width: 240px;
  }
}

@media (max-width: 620px) {
  .file-content-panel.fullscreen {
    right: 0;
    width: 100vw;
  }

  .workspace-workbench-body {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) 170px;
  }

  .workspace-drawer,
  .file-content-panel {
    position: relative;
    grid-column: 1;
    grid-row: 1;
  }

  .file-content-panel {
    z-index: 2;
  }

  .workspace-review-panel {
    grid-column: 1;
    grid-row: 2;
  }

  .workspace-review-actions {
    display: none;
  }

  .workspace-review-header {
    min-height: 36px;
  }

  .file-welcome-panel {
    display: none;
  }

  .viewer-header {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .viewer-actions {
    width: 100%;
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .viewer-file-identity {
    width: calc(100% - 40px);
  }

  .viewer-header strong {
    max-width: calc(100vw - 92px);
  }
}
</style>
