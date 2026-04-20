<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'

const props = defineProps({
  modelValue: {
    type: [String, Number],
    default: '',
  },
  options: {
    type: Array,
    required: true,
    // [{ value, label }]
  },
  displayMap: {
    type: Object,
    default: null,
  },
  placeholder: {
    type: String,
    default: 'Select...',
  },
})

const emit = defineEmits(['update:modelValue'])

const isOpen = ref(false)
const openUpward = ref(false)
const wrapperRef = ref(null)

const selectedLabel = (() => {
  if (props.displayMap && props.displayMap[props.modelValue]) {
    return props.displayMap[props.modelValue]
  }
  const opt = props.options.find(o => o.value === props.modelValue)
  return opt ? opt.label : props.placeholder
})()

function getLabel() {
  if (props.displayMap && props.displayMap[props.modelValue]) {
    return props.displayMap[props.modelValue]
  }
  const opt = props.options.find(o => o.value === props.modelValue)
  return opt ? opt.label : props.placeholder
}

function toggle() {
  if (isOpen.value) {
    isOpen.value = false
    return
  }
  // Check if near bottom of viewport
  const el = wrapperRef.value
  if (el) {
    const rect = el.getBoundingClientRect()
    const spaceBelow = window.innerHeight - rect.bottom
    const menuHeight = props.options.length * 36 + 8
    openUpward.value = spaceBelow < menuHeight && rect.top > menuHeight
  }
  isOpen.value = true
}

function select(value) {
  emit('update:modelValue', value)
  isOpen.value = false
}

function onClickOutside(e) {
  if (wrapperRef.value && !wrapperRef.value.contains(e.target)) {
    isOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onClickOutside)
})
</script>

<template>
  <div ref="wrapperRef" class="custom-select" @click.stop>
    <button class="custom-select-trigger" :class="{ active: isOpen }" @click="toggle">
      <span class="custom-select-text">{{ getLabel() }}</span>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
    </button>
    <Transition name="dropdown-fade">
      <div v-if="isOpen" class="custom-select-menu" :class="{ 'custom-select-menu--up': openUpward }">
        <button
          v-for="opt in options"
          :key="opt.value"
          class="custom-select-option"
          :class="{ selected: modelValue === opt.value }"
          @click="select(opt.value)"
        >
          {{ opt.label }}
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.custom-select {
  position: relative;
  flex-shrink: 0;
}

.custom-select-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 13px;
  font-family: var(--font-sans);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.custom-select-trigger:hover {
  border-color: var(--accent);
  background: var(--bg-hover);
}

.custom-select-trigger.active {
  border-color: var(--accent);
  background: var(--accent-dim);
  color: var(--accent);
}

.custom-select-trigger svg {
  transition: transform 150ms cubic-bezier(0.4, 0, 0.2, 1);
}

.custom-select-trigger.active svg {
  transform: rotate(180deg);
}

.custom-select-text {
  font-weight: 500;
}

.custom-select-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 100;
  min-width: 200px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lg);
  padding: 4px;
}

.custom-select-menu--up {
  top: auto;
  bottom: calc(100% + 4px);
}

.custom-select-option {
  display: block;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-family: var(--font-sans);
  text-align: left;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
  white-space: nowrap;
}

.custom-select-option:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.custom-select-option.selected {
  color: var(--accent);
  font-weight: 600;
  background: var(--accent-dim);
}
</style>
