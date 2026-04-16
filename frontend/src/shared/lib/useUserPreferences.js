import { ref, watch } from 'vue'

const ENTER_BEHAVIOR_KEY = 'pf_enter_behavior'
const ENTER_BEHAVIORS = ['enter-send', 'ctrl-enter-send']

function getStoredEnterBehavior() {
  try {
    const stored = localStorage.getItem(ENTER_BEHAVIOR_KEY)
    if (stored && ENTER_BEHAVIORS.includes(stored)) return stored
  } catch {}
  return 'enter-send' // 默认：Enter发送，Ctrl+Enter换行
}

const currentEnterBehavior = ref(getStoredEnterBehavior())

watch(currentEnterBehavior, (behavior) => {
  try {
    localStorage.setItem(ENTER_BEHAVIOR_KEY, behavior)
  } catch {}
})

export function useUserPreferences() {
  function setEnterBehavior(behavior) {
    if (ENTER_BEHAVIORS.includes(behavior)) {
      currentEnterBehavior.value = behavior
    }
  }

  function getEnterBehavior() {
    return currentEnterBehavior.value
  }

  // 判断Enter键是否应该发送消息
  function shouldEnterSend() {
    return currentEnterBehavior.value === 'enter-send'
  }

  // 判断Ctrl+Enter是否应该发送消息
  function shouldCtrlEnterSend() {
    return currentEnterBehavior.value === 'ctrl-enter-send'
  }

  return {
    enterBehavior: currentEnterBehavior,
    enterBehaviors: ENTER_BEHAVIORS,
    setEnterBehavior,
    getEnterBehavior,
    shouldEnterSend,
    shouldCtrlEnterSend,
  }
}
