<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useTheme } from '@shared/lib/useTheme'
import { useEyeCare } from '@shared/lib/useEyeCare'

const { theme, setTheme } = useTheme()
const { brightness, warmth, isActive: eyeCareActive, reset: resetEyeCare } = useEyeCare()

const showPanel = ref(false)
const panelRef = ref(null)
const switcherRef = ref(null)

const themeOptions = [
  { value: 'dark', label: 'Dark', icon: 'moon' },
  { value: 'light', label: 'Light', icon: 'sun' },
  { value: 'sepia', label: '护眼', icon: 'eye' },
]

function handleThemeClick(opt) {
  if (opt.value === theme.value) {
    showPanel.value = !showPanel.value
  } else {
    setTheme(opt.value)
    showPanel.value = false
  }
}

function onClickOutside(e) {
  if (
    showPanel.value &&
    panelRef.value && !panelRef.value.contains(e.target) &&
    switcherRef.value && !switcherRef.value.contains(e.target)
  ) {
    showPanel.value = false
  }
}

function onKeydown(e) {
  if (e.key === 'Escape' && showPanel.value) {
    showPanel.value = false
  }
}

onMounted(() => {
  document.addEventListener('mousedown', onClickOutside)
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onClickOutside)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="theme-switcher-wrap" ref="switcherRef">
    <div class="theme-switcher" role="radiogroup" aria-label="Theme">
      <button
        v-for="opt in themeOptions"
        :key="opt.value"
        class="theme-btn"
        :class="{ active: theme === opt.value }"
        :aria-checked="theme === opt.value"
        :title="opt.label"
        role="radio"
        @click="handleThemeClick(opt)"
      >
        <!-- Moon icon (Dark) -->
        <svg v-if="opt.icon === 'moon'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
        <!-- Sun icon (Light) -->
        <svg v-if="opt.icon === 'sun'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"/>
          <line x1="12" y1="1" x2="12" y2="3"/>
          <line x1="12" y1="21" x2="12" y2="23"/>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
          <line x1="1" y1="12" x2="3" y2="12"/>
          <line x1="21" y1="12" x2="23" y2="12"/>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </svg>
        <!-- Eye icon (Eye-care / Sepia) -->
        <svg v-if="opt.icon === 'eye'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
          <circle cx="12" cy="12" r="3"/>
        </svg>
      </button>
    </div>

    <!-- Eye-care adjustment panel -->
    <Transition name="eyecare-panel">
      <div v-if="showPanel" class="eyecare-panel" ref="panelRef">
        <div class="panel-row">
          <svg class="row-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
          </svg>
          <input
            type="range"
            class="slider"
            :value="brightness"
            @input="brightness = Number($event.target.value)"
            min="60"
            max="100"
            step="1"
            aria-label="亮度"
          />
          <svg class="row-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
          </svg>
        </div>

        <div class="panel-row">
          <span class="row-label">冷</span>
          <input
            type="range"
            class="slider slider-warmth"
            :value="warmth"
            @input="warmth = Number($event.target.value)"
            min="0"
            max="100"
            step="1"
            aria-label="色温"
          />
          <span class="row-label">暖</span>
        </div>

        <button class="reset-btn" @click="resetEyeCare">重置</button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.theme-switcher-wrap {
  position: relative;
}

.theme-switcher {
  display: flex;
  align-items: center;
  gap: 2px;
  background: color-mix(in srgb, var(--glass-bg) 36%, transparent);
  border-radius: var(--radius-md);
  padding: 2px;
  border: 1px solid color-mix(in srgb, var(--glass-border) 70%, transparent);
  backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(calc(var(--glass-blur) * 0.8)) saturate(var(--glass-saturate));
}

.theme-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 24px;
  border: none;
  border-radius: calc(var(--radius-md) - 2px);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition:
    color var(--transition-fast),
    background var(--transition-fast),
    box-shadow var(--transition-fast),
    transform var(--transition-spring);
}

.theme-btn:hover:not(.active) {
  color: var(--accent);
  background: var(--layer-active);
}

.theme-btn.active {
  color: var(--accent);
  background: var(--layer-active);
  box-shadow: var(--shadow-sm);
}

/* Eye-care panel */
.eyecare-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 200px;
  padding: 12px;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-glass);
  display: flex;
  flex-direction: column;
  gap: 10px;
  z-index: 60;
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.panel-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.row-icon {
  flex-shrink: 0;
  color: var(--text-muted);
}

.row-label {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-muted);
  width: 14px;
  text-align: center;
  user-select: none;
}

/* Custom range slider */
.slider {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 4px;
  border-radius: 2px;
  background: var(--border);
  outline: none;
  cursor: pointer;
}

.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--bg-secondary);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: transform var(--transition-fast);
}

.slider::-webkit-slider-thumb:hover {
  transform: scale(1.15);
}

.slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--bg-secondary);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
}

.slider-warmth {
  background: linear-gradient(to right, #b8cfe0, #e8c88a);
}

.reset-btn {
  align-self: center;
  font-size: 11px;
  color: var(--text-muted);
  background: color-mix(in srgb, var(--glass-bg) 36%, transparent);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  padding: 3px 14px;
  cursor: pointer;
  transition:
    color var(--transition-fast),
    border-color var(--transition-fast),
    background var(--transition-fast),
    box-shadow var(--transition-fast);
}

.reset-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--layer-active);
  box-shadow: var(--shadow-sm);
}

/* Panel transition */
.eyecare-panel-enter-active,
.eyecare-panel-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
}

.eyecare-panel-enter-from,
.eyecare-panel-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
