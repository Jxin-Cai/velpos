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
  loading: {
    type: Boolean,
    default: false,
  },
  searchQuery: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['select', 'close', 'update:searchQuery'])

const popoverEl = ref(null)
const searchEl = ref(null)
const activeIndex = ref(0)

const filteredCommands = computed(() => {
  const q = props.searchQuery.toLowerCase()
  if (!q) return props.commands
  return props.commands.filter(
    c => c.name.toLowerCase().includes(q) || c.description.toLowerCase().includes(q)
  )
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
  const len = filteredCommands.value.length
  if (!len) return

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
    </div>

    <div class="cmd-list">
      <div v-if="loading" class="cmd-loading">Loading commands...</div>
      <div v-else-if="filteredCommands.length === 0" class="cmd-empty">No commands found</div>
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

.cmd-loading,
.cmd-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
