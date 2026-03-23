import { ref, watch, computed } from 'vue'
import { useTheme } from './useTheme'

const BRIGHTNESS_KEY = 'pf_eyecare_brightness'
const WARMTH_KEY = 'pf_eyecare_warmth'

const DEFAULT_BRIGHTNESS = 100
const DEFAULT_WARMTH = 0

function loadValue(key, fallback) {
  try {
    const v = localStorage.getItem(key)
    if (v !== null) {
      const n = Number(v)
      if (!Number.isNaN(n)) return n
    }
  } catch {}
  return fallback
}

const brightness = ref(loadValue(BRIGHTNESS_KEY, DEFAULT_BRIGHTNESS))
const warmth = ref(loadValue(WARMTH_KEY, DEFAULT_WARMTH))

function applyFilter() {
  const el = document.documentElement
  const b = brightness.value / 100
  const w = warmth.value / 100
  const s = w * 0.35
  const sat = 1 + w * 0.15

  // No filter needed when both at defaults
  if (brightness.value === 100 && warmth.value === 0) {
    el.style.removeProperty('filter')
    return
  }

  el.style.filter = `brightness(${b}) sepia(${s}) saturate(${sat})`
}

// Module-level watchers — run once, not per useEyeCare() call
const { theme } = useTheme()

watch(brightness, (v) => {
  try { localStorage.setItem(BRIGHTNESS_KEY, v) } catch {}
  applyFilter()
})

watch(warmth, (v) => {
  try { localStorage.setItem(WARMTH_KEY, v) } catch {}
  applyFilter()
})

// Re-apply on theme change (filter persists across themes)
watch(theme, () => {
  applyFilter()
}, { immediate: true })

export function useEyeCare() {
  const isActive = computed(() => brightness.value !== DEFAULT_BRIGHTNESS || warmth.value !== DEFAULT_WARMTH)

  function reset() {
    brightness.value = DEFAULT_BRIGHTNESS
    warmth.value = DEFAULT_WARMTH
  }

  return {
    brightness,
    warmth,
    isActive,
    reset,
  }
}
