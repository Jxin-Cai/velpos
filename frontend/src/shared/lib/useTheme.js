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

// A page restored from the back-forward cache can bring back an older DOM
// attribute without re-evaluating this module. Re-apply the reactive source of
// truth whenever the document becomes active again.
window.addEventListener('pageshow', () => {
  applyTheme(currentTheme.value)
})

// Keep open tabs consistent when another tab changes the saved preference.
window.addEventListener('storage', (event) => {
  if (event.key === THEME_KEY && event.newValue && THEMES.includes(event.newValue)) {
    currentTheme.value = event.newValue
  }
})

export function useTheme() {
  function setTheme(theme) {
    if (THEMES.includes(theme)) {
      currentTheme.value = theme
    }
  }

  return {
    theme: currentTheme,
    themes: THEMES,
    setTheme,
  }
}
