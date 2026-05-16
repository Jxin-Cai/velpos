<script setup>
import { ref, watch } from 'vue'
import * as XLSX from 'xlsx'

const props = defineProps({
  src: { type: String, required: true },
})

const loading = ref(true)
const error = ref('')
const sheets = ref([])
const activeSheet = ref(0)
const rows = ref([])
const headers = ref([])
let loadVersion = 0

async function loadExcel() {
  const version = ++loadVersion
  loading.value = true
  error.value = ''
  sheets.value = []
  rows.value = []
  headers.value = []
  try {
    const response = await fetch(props.src)
    if (version !== loadVersion) return
    const buffer = await response.arrayBuffer()
    if (version !== loadVersion) return
    const workbook = XLSX.read(buffer, { type: 'array' })
    workbookCache = workbook
    sheets.value = workbook.SheetNames
    activeSheet.value = 0
    parseSheet(workbook, 0)
  } catch (e) {
    if (version !== loadVersion) return
    error.value = e.message || 'Failed to load file'
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

function parseSheet(workbook, index) {
  const name = sheets.value[index]
  if (!name) return
  const sheet = workbook.Sheets[name]
  const json = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' })
  if (json.length > 0) {
    headers.value = json[0].map((h, i) => h || `Col ${i + 1}`)
    rows.value = json.slice(1, 501)
  } else {
    headers.value = []
    rows.value = []
  }
}

let workbookCache = null

async function switchSheet(index) {
  activeSheet.value = index
  if (!workbookCache) {
    const response = await fetch(props.src)
    const buffer = await response.arrayBuffer()
    workbookCache = XLSX.read(buffer, { type: 'array' })
  }
  parseSheet(workbookCache, index)
}

watch(() => props.src, async () => {
  workbookCache = null
  await loadExcel()
}, { immediate: true })
</script>

<template>
  <div class="excel-preview">
    <div v-if="sheets.length > 1" class="sheet-tabs">
      <button
        v-for="(name, index) in sheets"
        :key="name"
        class="sheet-tab"
        :class="{ active: activeSheet === index }"
        @click="switchSheet(index)"
      >
        {{ name }}
      </button>
    </div>
    <div v-if="loading" class="excel-status">Loading...</div>
    <div v-else-if="error" class="excel-status excel-error">{{ error }}</div>
    <div v-else-if="rows.length === 0" class="excel-status">Empty sheet</div>
    <div v-else class="table-container">
      <table>
        <thead>
          <tr>
            <th v-for="(h, i) in headers" :key="i">{{ h }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, ri) in rows" :key="ri">
            <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.excel-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.sheet-tabs {
  display: flex;
  gap: 0;
  padding: 0 8px;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
  overflow-x: auto;
}

.sheet-tab {
  padding: 6px 12px;
  border: none;
  border-bottom: 2px solid transparent;
  background: none;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

.sheet-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.sheet-tab:hover:not(.active) {
  color: var(--text-primary);
}

.excel-status {
  padding: 24px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}

.excel-error {
  color: var(--color-error, #e53935);
}

.table-container {
  flex: 1;
  overflow: auto;
}

table {
  border-collapse: collapse;
  font-size: 12px;
  min-width: 100%;
}

th, td {
  border: 1px solid var(--glass-border);
  padding: 4px 8px;
  text-align: left;
  white-space: nowrap;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
}

th {
  position: sticky;
  top: 0;
  background: var(--layer-glass);
  color: var(--text-primary);
  font-weight: 600;
  z-index: 1;
}

td {
  color: var(--text-secondary);
}

tr:hover td {
  background: var(--layer-hover);
}
</style>
