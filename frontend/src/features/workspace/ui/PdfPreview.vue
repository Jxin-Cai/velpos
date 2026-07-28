<script setup>
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'
import { useCancellableAsync } from '@shared/lib/useCancellableAsync'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.mjs',
  import.meta.url
).href

const props = defineProps({
  src: { type: String, required: true },
  zoom: { type: Number, default: 1 },
})

const containerEl = ref(null)
const loading = ref(true)
const error = ref('')
const pageCount = ref(0)
const currentPage = ref(1)

let pdfDoc = null
let renderTask = null
const loadTracker = useCancellableAsync()

async function loadPdf() {
  const version = loadTracker.start()
  loading.value = true
  error.value = ''
  try {
    const doc = await pdfjsLib.getDocument(props.src).promise
    if (!loadTracker.isCurrent(version)) {
      doc.destroy()
      return
    }
    if (pdfDoc) pdfDoc.destroy()
    pdfDoc = doc
    pageCount.value = pdfDoc.numPages
    currentPage.value = 1
  } catch (e) {
    if (!loadTracker.isCurrent(version)) return
    error.value = e.message || 'Failed to load PDF'
  } finally {
    if (loadTracker.isCurrent(version)) loading.value = false
  }
  if (loadTracker.isCurrent(version) && pdfDoc) {
    await nextTick()
    await renderPage(1)
  }
}

async function renderPage(num) {
  if (!pdfDoc || !containerEl.value) return
  if (renderTask) {
    renderTask.cancel()
    renderTask = null
  }

  const page = await pdfDoc.getPage(num)
  const viewport = page.getViewport({ scale: 1.5 * props.zoom })

  let canvas = containerEl.value.querySelector('canvas')
  if (!canvas) {
    canvas = document.createElement('canvas')
    containerEl.value.appendChild(canvas)
  }
  canvas.width = viewport.width
  canvas.height = viewport.height

  const ctx = canvas.getContext('2d')
  renderTask = page.render({ canvasContext: ctx, viewport })
  try {
    await renderTask.promise
  } catch (e) {
    if (e.name !== 'RenderingCancelledException') throw e
  }
  renderTask = null
}

function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value--
    renderPage(currentPage.value)
  }
}

function nextPage() {
  if (currentPage.value < pageCount.value) {
    currentPage.value++
    renderPage(currentPage.value)
  }
}

watch(() => props.src, loadPdf, { immediate: true })
watch(() => props.zoom, () => renderPage(currentPage.value))

onBeforeUnmount(() => {
  if (renderTask) renderTask.cancel()
  if (pdfDoc) pdfDoc.destroy()
})
</script>

<template>
  <div class="pdf-preview">
    <div class="pdf-toolbar">
      <button class="page-btn" :disabled="currentPage <= 1" @click="prevPage">‹</button>
      <span class="page-info">{{ currentPage }} / {{ pageCount }}</span>
      <button class="page-btn" :disabled="currentPage >= pageCount" @click="nextPage">›</button>
    </div>
    <div v-if="loading" class="pdf-status">Loading PDF...</div>
    <div v-else-if="error" class="pdf-status pdf-error">{{ error }}</div>
    <div v-else ref="containerEl" class="pdf-canvas-container"></div>
  </div>
</template>

<style scoped>
.pdf-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.pdf-toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.page-btn {
  width: 28px;
  height: 24px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--layer-glass);
  color: var(--text-secondary);
  font-size: 16px;
  cursor: pointer;
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.page-btn:not(:disabled):hover {
  background: var(--layer-active);
  color: var(--text-primary);
}

.page-info {
  font-size: 12px;
  color: var(--text-muted);
}

.pdf-status {
  padding: 24px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}

.pdf-error {
  color: var(--color-error, #e53935);
}

.pdf-canvas-container {
  flex: 1;
  overflow: auto;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 16px;
  background: var(--layer-base);
}

.pdf-canvas-container canvas {
  max-width: 100%;
  height: auto;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
}
</style>
