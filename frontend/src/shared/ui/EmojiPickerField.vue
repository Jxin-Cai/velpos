<script setup>
import { nextTick, ref } from 'vue'
import { useClickOutside } from '@shared/lib/useClickOutside'

defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  fallback: {
    type: String,
    default: '🎯',
  },
})

const emit = defineEmits(['update:modelValue'])

const EMOJI_OPTIONS = [
  '🔌', '🎯', '🤖', '🧠', '⚡', '🔥', '🚀', '🛠️',
  '🔧', '⚙️', '📦', '📚', '📄', '📝', '📊', '📈',
  '🗂️', '💾', '🔍', '🌐', '🌍', '💬', '📧', '🔔',
  '🔒', '🔑', '🛡️', '🧪', '🎨', '🖼️', '🎬', '🎵',
  '📷', '🗺️', '☁️', '💰', '📅', '⏰', '✅', '💡',
  '🐙', '🐍', '🕸️', '🧩', '🏷️', '📡', '🖥️', '📱',
]

const PANEL_WIDTH = 292
const PANEL_HEIGHT = 250

const isOpen = ref(false)
const wrapperRef = ref(null)
const panelStyle = ref({})

function positionPanel() {
  const el = wrapperRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const spaceBelow = window.innerHeight - rect.bottom
  const top = spaceBelow >= PANEL_HEIGHT + 8 || spaceBelow >= rect.top
    ? rect.bottom + 4
    : rect.top - PANEL_HEIGHT - 4
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - PANEL_WIDTH - 8))
  panelStyle.value = {
    position: 'fixed',
    top: `${top}px`,
    left: `${left}px`,
    width: `${PANEL_WIDTH}px`,
    zIndex: 9999,
  }
}

function toggle() {
  if (isOpen.value) {
    isOpen.value = false
    return
  }
  isOpen.value = true
  nextTick(() => positionPanel())
}

function select(emoji) {
  emit('update:modelValue', emoji)
  isOpen.value = false
}

useClickOutside(wrapperRef, () => { isOpen.value = false }, { event: 'click' })
</script>

<template>
  <div ref="wrapperRef" class="emoji-picker" @click.stop>
    <button
      class="emoji-picker-trigger"
      :class="{ active: isOpen }"
      type="button"
      aria-haspopup="listbox"
      :aria-expanded="isOpen"
      @click="toggle"
    >
      <span class="emoji-picker-current">{{ modelValue || fallback }}</span>
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
    </button>
    <Teleport to="body">
      <Transition name="dropdown-fade">
        <div v-if="isOpen" class="emoji-picker-menu" :style="panelStyle" role="listbox">
          <button
            v-for="emoji in EMOJI_OPTIONS"
            :key="emoji"
            class="emoji-picker-option"
            :class="{ selected: modelValue === emoji }"
            type="button"
            role="option"
            :aria-selected="modelValue === emoji"
            @click="select(emoji)"
          >
            {{ emoji }}
          </button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.emoji-picker {
  position: relative;
  flex-shrink: 0;
}

.emoji-picker-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid var(--border-subtle, var(--border));
  border-radius: 8px;
  background: var(--layer-base, var(--bg-tertiary));
  color: var(--text-secondary);
  font: inherit;
  cursor: pointer;
  transition: border-color .16s, background .16s;
}

.emoji-picker-trigger:hover {
  border-color: var(--accent);
}

.emoji-picker-trigger.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-dim);
}

.emoji-picker-trigger svg {
  transition: transform 150ms cubic-bezier(0.4, 0, 0.2, 1);
}

.emoji-picker-trigger.active svg {
  transform: rotate(180deg);
}

.emoji-picker-current {
  font-size: 17px;
  line-height: 1;
}
</style>

<style>
/* Unscoped for Teleported panel */
.emoji-picker-menu {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 2px;
  padding: 8px;
  border: 1px solid var(--border, rgba(128, 128, 128, .3));
  border-radius: 10px;
  background: var(--bg-secondary, var(--glass-bg));
  box-shadow: var(--shadow-lg, 0 12px 32px rgba(0, 0, 0, .35));
}

.emoji-picker-option {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
  transition: background .12s;
}

.emoji-picker-option:hover,
.emoji-picker-option:focus-visible {
  background: var(--bg-hover, var(--layer-active));
  outline: none;
}

.emoji-picker-option.selected {
  background: var(--accent-dim);
  box-shadow: inset 0 0 0 1px var(--accent);
}
</style>
