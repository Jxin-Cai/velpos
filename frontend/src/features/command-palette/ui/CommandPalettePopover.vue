<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  commands: {
    type: Array,
    default: () => [],
  },
  policyRows: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  searchQuery: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['select', 'close', 'update:searchQuery', 'policy-change'])

const popoverEl = ref(null)
const searchEl = ref(null)
const activeIndex = ref(0)
const manageMode = ref(false)

const filteredCommands = computed(() => {
  const q = props.searchQuery.toLowerCase()
  if (!q) return props.commands
  return props.commands.filter(
    c => c.name.toLowerCase().includes(q) || c.description.toLowerCase().includes(q)
  )
})

const filteredPolicyRows = computed(() => {
  const q = props.searchQuery.toLowerCase()
  if (!q) return props.policyRows
  return props.policyRows.filter(row => (
    row.command_name.toLowerCase().includes(q)
    || (row.description || '').toLowerCase().includes(q)
  ))
})

watch(() => props.visible, (val) => {
  if (val) {
    activeIndex.value = 0
    nextTick(() => searchEl.value?.focus())
  }
})

watch(() => props.searchQuery, () => {
  activeIndex.value = 0
})

function handleClickOutside(e) {
  if (props.visible && popoverEl.value && !popoverEl.value.contains(e.target)) {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('mousedown', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleClickOutside)
})

function handleKeydown(e) {
  const len = manageMode.value ? 0 : filteredCommands.value.length
  if (!len && e.key !== 'Escape') return

  // 如果有修饰键（全局快捷键），不处理，让事件传播到全局处理器
  const hasModifiers = e.ctrlKey || e.metaKey
  if (hasModifiers) {
    return // 不阻止事件，让全局快捷键处理器接管
  }

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value + 1) % len
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = (activeIndex.value - 1 + len) % len
  } else if (e.key === 'Enter') {
    e.preventDefault()
    selectItem(filteredCommands.value[activeIndex.value])
  } else if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  }
}

function selectItem(cmd) {
  if (cmd) {
    emit('select', cmd)
  }
}

function onSearchInput(e) {
  emit('update:searchQuery', e.target.value)
}
</script>

<template>
  <div v-if="visible" ref="popoverEl" class="cmd-popover" @keydown="handleKeydown">
    <div class="cmd-search-wrapper">
      <svg class="cmd-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
      <input
        ref="searchEl"
        class="cmd-search"
        :value="searchQuery"
        @input="onSearchInput"
        placeholder="Search commands..."
        type="text"
      />
      <button class="cmd-manage-btn" @click="manageMode = !manageMode">
        {{ manageMode ? 'Browse' : 'Manage' }}
      </button>
    </div>

    <div class="cmd-list">
      <div v-if="loading" class="cmd-loading">Loading commands...</div>
      <template v-else-if="manageMode">
        <div v-if="filteredPolicyRows.length === 0" class="cmd-empty">No commands found</div>
        <div
          v-for="row in filteredPolicyRows"
          :key="row.command_name + ':' + row.command_type"
          class="cmd-policy-item"
        >
          <div class="cmd-policy-main">
            <span class="cmd-name">/{{ row.command_name }}</span>
            <span class="cmd-tag" :class="row.command_type === 'prompt' ? 'cmd-tag--prompt' : 'cmd-tag--local'">
              {{ row.command_type === 'prompt' ? 'skill' : row.command_type }}
            </span>
            <span class="cmd-desc">{{ row.description || 'Policy override' }}</span>
          </div>
          <div class="cmd-policy-actions">
            <button
              class="cmd-policy-btn"
              :class="{ active: row.enabled }"
              @click="emit('policy-change', row, { enabled: !row.enabled })"
            >
              {{ row.enabled ? 'Enabled' : 'Disabled' }}
            </button>
            <button
              class="cmd-policy-btn"
              :class="{ active: row.visible }"
              @click="emit('policy-change', row, { visible: !row.visible })"
            >
              {{ row.visible ? 'Visible' : 'Hidden' }}
            </button>
          </div>
        </div>
      </template>
      <template v-else>
        <div v-if="filteredCommands.length === 0" class="cmd-empty">No commands found</div>
        <div
          v-else
          v-for="(cmd, index) in filteredCommands"
          :key="cmd.name"
          class="cmd-item"
          :class="{ 'cmd-item--active': index === activeIndex }"
          @click="selectItem(cmd)"
          @mouseenter="activeIndex = index"
        >
          <span class="cmd-name">/{{ cmd.name }}</span>
          <span v-if="cmd.type === 'prompt'" class="cmd-tag cmd-tag--prompt">skill</span>
          <span v-else-if="cmd.type === 'local' || cmd.type === 'local-jsx'" class="cmd-tag cmd-tag--local">built-in</span>
          <span class="cmd-desc">{{ cmd.description }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.cmd-popover {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  margin-bottom: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xl);
  max-height: 320px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 100;
}

.cmd-search-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}

.cmd-search-icon {
  color: var(--text-muted);
  flex-shrink: 0;
}

.cmd-search {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 13px;
  font-family: var(--font-sans);
}

.cmd-manage-btn {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  padding: 3px 8px;
  cursor: pointer;
}

.cmd-manage-btn:hover {
  color: var(--text-primary);
  border-color: var(--accent);
}

.cmd-search::placeholder {
  color: var(--text-muted);
}

.cmd-list {
  overflow-y: auto;
  padding: 4px;
}

.cmd-item {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.1s;
}

.cmd-item:hover,
.cmd-item--active {
  background: var(--bg-hover);
}

.cmd-name {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--accent);
  white-space: nowrap;
  flex-shrink: 0;
}

.cmd-tag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  white-space: nowrap;
  flex-shrink: 0;
}

.cmd-tag--prompt {
  color: var(--purple);
  background: var(--purple-dim);
}

.cmd-tag--local {
  color: var(--text-muted);
  background: var(--bg-tertiary);
}

.cmd-desc {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cmd-policy-item {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
}

.cmd-policy-item:hover {
  background: var(--bg-hover);
}

.cmd-policy-main {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.cmd-policy-actions {
  display: flex;
  gap: 6px;
  padding-left: 2px;
}

.cmd-policy-btn {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 11px;
  padding: 2px 7px;
  cursor: pointer;
}

.cmd-policy-btn.active {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-dim);
}

.cmd-loading,
.cmd-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
