import { onMounted, onUnmounted, reactive } from 'vue'

/**
 * Global hotkey registry
 * Allows components to register hotkeys with priority
 * Local (component-level) hotkeys take precedence over global ones
 */
const hotkeyRegistry = reactive(new Map())

/**
 * Normalize key combination to a standardized string
 * Examples: 'Ctrl+K', 'Cmd+K', 'Escape', 'Ctrl+Shift+K'
 */
function normalizeKeyCombo(event) {
  const parts = []

  if (event.ctrlKey) parts.push('Ctrl')
  if (event.metaKey) parts.push('Cmd')
  if (event.shiftKey) parts.push('Shift')
  if (event.altKey) parts.push('Alt')

  // Handle special keys
  const specialKeys = [
    'Escape', 'Enter', 'Tab', 'Backspace', 'Delete',
    'Insert', 'Home', 'End', 'PageUp', 'PageDown',
    'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
    'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12'
  ]

  if (specialKeys.includes(event.key)) {
    parts.push(event.key)
  } else if (event.key.length === 1) {
    // Regular character key
    parts.push(event.key.toUpperCase())
  }

  return parts.join('+')
}

/**
 * Generate a unique ID for hotkey handlers
 */
function generateHotkeyId() {
  return `hotkey_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

/**
 * Normalize hotkey string to standard format
 */
function normalizeHotkeyString(key) {
  return key
    .replace(/ctrl\+/gi, 'Ctrl+')
    .replace(/cmd\+/gi, 'Cmd+')
    .replace(/meta\+/gi, 'Cmd+')
    .replace(/shift\+/gi, 'Shift+')
    .replace(/alt\+/gi, 'Alt+')
    .replace(/option\+/gi, 'Alt+') // Mac上的Option键映射为Alt
}

/**
 * Global hotkey handler
 * Processes keyboard events and dispatches to registered handlers
 */
function handleGlobalKeydown(event) {
  const combo = normalizeKeyCombo(event)

  // Find all handlers for this key combination
  const handlers = hotkeyRegistry.get(combo)
  if (!handlers || handlers.length === 0) return

  // Sort by priority (higher priority first)
  const sortedHandlers = [...handlers].sort((a, b) => b.priority - a.priority)

  // Execute handlers and check if any wants to handle the event
  let hasHandler = false
  for (const handler of sortedHandlers) {
    const result = handler.callback(event)
    // If callback returns anything other than true, it means the handler processed the event
    if (result !== true) {
      hasHandler = true
      event.preventDefault()
      event.stopPropagation()
      event.stopImmediatePropagation() // 阻止其他同级别监听器（包括原生DOM事件）
      break
    }
    // If callback returns true, the handler explicitly wants to ignore this event
    // Continue to next handler or let the event pass through
  }

  // If no handler processed the event, let it continue naturally
  // without any intervention from the global hotkey system
  if (!hasHandler) {
    // Don't prevent default or stop propagation - let the event continue
    return
  }
}

/**
 * Composable for registering global hotkeys
 * @param {Object} options - Hotkey configuration
 * @param {string|string[]} options.keys - Key combination(s) to listen for
 * @param {Function} options.handler - Callback function when hotkey is triggered
 * @param {number} options.priority - Handler priority (default: 0, higher values take precedence)
 * @param {Function} options.condition - Optional function to determine if hotkey should be active
 * @returns {Object} - Control object with unregister method
 */
export function useGlobalHotkeys({ keys, handler, priority = 0, condition = null }) {
  let keyList = Array.isArray(keys) ? keys : [keys]
  const handlerIds = []

  const registerHandler = () => {
    for (const key of keyList) {
      const normalizedKey = normalizeHotkeyString(key)

      if (!hotkeyRegistry.has(normalizedKey)) {
        hotkeyRegistry.set(normalizedKey, [])
      }

      const handlerId = generateHotkeyId()
      hotkeyRegistry.get(normalizedKey).push({
        id: handlerId,
        callback: (event) => {
          if (condition && !condition()) {
            return true
          }
          return handler(event)
        },
        priority,
      })

      handlerIds.push({ key: normalizedKey, id: handlerId })
    }
  }

  const unregisterHandler = () => {
    for (const { key, id } of handlerIds) {
      const handlers = hotkeyRegistry.get(key)
      if (handlers) {
        const index = handlers.findIndex(h => h.id === id)
        if (index !== -1) {
          handlers.splice(index, 1)
        }
        // Clean up empty arrays
        if (handlers.length === 0) {
          hotkeyRegistry.delete(key)
        }
      }
    }
  }

  onMounted(() => {
    // Initialize global listener if not already present
    if (hotkeyRegistry.size === 0) {
      window.addEventListener('keydown', handleGlobalKeydown)
    }
    registerHandler()
  })

  onUnmounted(() => {
    unregisterHandler()
    // Remove global listener if no more handlers
    if (hotkeyRegistry.size === 0) {
      window.removeEventListener('keydown', handleGlobalKeydown)
    }
  })

  return {
    unregister: unregisterHandler,
    reregister: (newKeys) => {
      unregisterHandler()
      keyList = Array.isArray(newKeys) ? newKeys : [newKeys]
      registerHandler()
    },
  }
}

/**
 * Composable for components that need to block global hotkeys
 * Creates a "local" hotkey scope that takes precedence over global handlers
 * @param {string|string[]} keys - Key combination(s) to intercept
 * @param {Function} handler - Local handler function
 * @returns {Object} - Control object
 */
export function useLocalHotkeys(keys, handler) {
  return useGlobalHotkeys({
    keys,
    handler: (event) => {
      handler(event)
      return false // Block propagation to lower priority handlers
    },
    priority: 100, // Local hotkeys always have higher priority
  })
}

