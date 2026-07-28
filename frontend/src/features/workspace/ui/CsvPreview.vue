<script setup>
import { computed } from 'vue'

const props = defineProps({
  content: { type: String, default: '' },
  zoom: { type: Number, default: 1 },
  truncated: { type: Boolean, default: false },
})

const parsed = computed(() => parseCsv(props.content))
const header = computed(() => parsed.value.rows[0] || [])
const body = computed(() => parsed.value.rows.slice(1))
const columns = computed(() => Array.from({ length: parsed.value.columnCount }, (_, index) => index))

function parseCsv(content) {
  const source = content.startsWith('\uFEFF') ? content.slice(1) : content
  const rows = []
  let row = []
  let cell = ''
  let inQuotes = false
  let endedWithSeparator = false

  for (let index = 0; index < source.length; index += 1) {
    const character = source[index]
    if (character === '"') {
      if (inQuotes && source[index + 1] === '"') {
        cell += '"'
        index += 1
      } else if (inQuotes) {
        inQuotes = false
      } else if (!cell) {
        inQuotes = true
      } else {
        cell += character
      }
      endedWithSeparator = false
    } else if (character === ',' && !inQuotes) {
      row.push(cell)
      cell = ''
      endedWithSeparator = false
    } else if ((character === '\n' || character === '\r') && !inQuotes) {
      if (character === '\r' && source[index + 1] === '\n') index += 1
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
      endedWithSeparator = true
    } else {
      cell += character
      endedWithSeparator = false
    }
  }

  if (source && (!endedWithSeparator || row.length || cell)) {
    row.push(cell)
    rows.push(row)
  }

  return {
    rows,
    hasUnclosedQuote: inQuotes,
    columnCount: rows.reduce((maximum, item) => Math.max(maximum, item.length), 0),
  }
}
</script>

<template>
  <div class="csv-preview">
    <div v-if="truncated" class="preview-warning">The file is truncated; only loaded rows are shown.</div>
    <div v-if="parsed.hasUnclosedQuote" class="preview-warning">An unclosed quote was detected. The table may be incomplete.</div>
    <div v-if="!header.length" class="preview-empty">CSV file is empty.</div>
    <div v-else class="csv-table-scroll">
      <table :style="{ fontSize: `${12 * zoom}px` }" aria-label="CSV preview">
        <thead>
          <tr>
            <th class="row-number" scope="col">#</th>
            <th v-for="column in columns" :key="column" scope="col">
              {{ header[column] || `Column ${column + 1}` }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in body" :key="rowIndex">
            <th class="row-number" scope="row">{{ rowIndex + 1 }}</th>
            <td v-for="column in columns" :key="column">{{ row[column] ?? '' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="header.length" class="csv-summary">{{ body.length }} rows · {{ parsed.columnCount }} columns</div>
  </div>
</template>

<style scoped>
.csv-preview {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px;
  background: var(--bg-secondary);
}

.csv-table-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
}

table {
  min-width: 100%;
  border-spacing: 0;
  border-collapse: separate;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

th,
td {
  max-width: 420px;
  padding: 7px 9px;
  border-right: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}

thead th {
  position: sticky;
  z-index: 2;
  top: 0;
  color: var(--text-primary);
  background: var(--layer-active);
  font-weight: 700;
  white-space: nowrap;
}

tbody tr:nth-child(even) > * {
  background: color-mix(in srgb, var(--bg-secondary) 65%, transparent);
}

.row-number {
  position: sticky;
  z-index: 1;
  left: 0;
  width: 1%;
  min-width: 42px;
  color: var(--text-muted);
  background: var(--bg-secondary);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

thead .row-number {
  z-index: 3;
}

.csv-summary {
  padding: 8px 2px 0;
  color: var(--text-muted);
  font-size: 11px;
  text-align: right;
}

.preview-warning,
.preview-empty {
  padding: 10px;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
