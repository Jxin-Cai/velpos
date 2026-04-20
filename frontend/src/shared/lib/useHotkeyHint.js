import { ref } from 'vue'

// 全局状态：是否按住了 Cmd/Ctrl 键
const isModifierPressed = ref(false)

let keydownHandler = null
let keyupHandler = null

export function useHotkeyHint() {
  /**
   * 开始监听 Cmd/Ctrl 键
   */
  function startListening() {
    if (keydownHandler && keyupHandler) return // 已经在监听

    keydownHandler = (event) => {
      if (event.key === 'Meta' || event.key === 'Control') {
        isModifierPressed.value = true
      }
    }

    keyupHandler = (event) => {
      if (event.key === 'Meta' || event.key === 'Control') {
        isModifierPressed.value = false
      }
    }

    window.addEventListener('keydown', keydownHandler)
    window.addEventListener('keyup', keyupHandler)
  }

  /**
   * 停止监听 Cmd/Ctrl 键
   */
  function stopListening() {
    if (keydownHandler) {
      window.removeEventListener('keydown', keydownHandler)
      keydownHandler = null
    }
    if (keyupHandler) {
      window.removeEventListener('keyup', keyupHandler)
      keyupHandler = null
    }
    isModifierPressed.value = false
  }

  return {
    isModifierPressed,
    startListening,
    stopListening
  }
}
