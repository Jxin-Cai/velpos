import { ref, watch } from 'vue'

const THEME_KEY = 'pf_theme'
const THEMES = ['dark', 'light', 'sepia']

function getStoredTheme() {
  try {
    const stored = localStorage.getItem(THEME_KEY)
    if (stored && THEMES.includes(stored)) return stored
  } catch {}
  return 'dark'
}

const currentTheme = ref(getStoredTheme())

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme)
}

// Apply on first load
applyTheme(currentTheme.value)

watch(currentTheme, (theme) => {
  applyTheme(theme)
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {}
})

export function useTheme() {
  function setTheme(theme) {
    if (THEMES.includes(theme)) {
      currentTheme.value = theme
    }
  }

  function cycleTheme() {
    const idx = THEMES.indexOf(currentTheme.value)
    const next = THEMES[(idx + 1) % THEMES.length]
    currentTheme.value = next
  }

  return {
    theme: currentTheme,
    themes: THEMES,
    setTheme,
    cycleTheme,
  }
}
