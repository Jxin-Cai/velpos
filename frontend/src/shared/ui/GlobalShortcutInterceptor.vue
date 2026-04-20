<script setup>
import { useSession } from '@entities/session'
import { useProject } from '@entities/project'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys'
import { inject } from 'vue'

/**
 * GlobalShortcutInterceptor
 * 全局快捷键拦截组件
 *
 * 功能：
 * - 使用 useGlobalHotkeys 系统注册全局快捷键
 * - ESC键：当session运行时取消查询，否则放行
 * - Ctrl/Cmd + Alt + 上下方向键：在session列表中跨项目循环跳转
 * - 可扩展其他全局快捷键逻辑
 */

const { status, currentSessionId, sessions, setCurrentSessionId } = useSession()
const { projects } = useProject()

// 从App.vue中注入连接池和切换session函数
const connections = inject('wsConnections', null)
const switchSession = inject('switchSession', null)

// 注册全局ESC键快捷键
useGlobalHotkeys({
  keys: 'Escape',
  handler: (event) => {
    const isRunning = status.value === 'running'

    if (isRunning && currentSessionId.value && connections) {
      // 取消正在运行的查询
      const connection = connections.get(currentSessionId.value)
      if (connection && connection.getReadyState() === WebSocket.OPEN) {
        connection.send({ action: 'cancel' })
        return false // 阻止默认行为和事件传播
      }
    }
    // 如果没有运行，返回true让事件继续传播（浏览器默认行为）
    return true
  },
  priority: 10 // 给一个适中的优先级，让组件可以覆盖
})

// Session导航功能
/**
 * 构建session列表，按项目分组并排序
 * 返回格式: [{ project: {...}, sessions: [...] }]
 */
function buildSessionNavigationList() {
  if (!projects.value || !sessions.value) return []

  return projects.value.map(project => ({
    project,
    sessions: sessions.value.filter(s => s.project_id === project.id)
  })).filter(group => group.sessions.length > 0)
}

/**
 * 在session列表中导航到上一个
 * 支持跨项目跳转：从第一个项目的第一个session跳转到最后一个项目的最后一个session
 */
function navigateToPreviousSession() {
  const navigationList = buildSessionNavigationList()
  if (navigationList.length === 0) return

  const currentId = currentSessionId.value
  if (!currentId) {
    // 如果没有当前session，选择最后一个session
    const lastGroup = navigationList[navigationList.length - 1]
    const lastSession = lastGroup.sessions[lastGroup.sessions.length - 1]
    switchToSession(lastSession.session_id)
    return
  }

  // 查找当前session的位置
  let currentGroupIndex = -1
  let currentSessionIndex = -1

  for (let i = 0; i < navigationList.length; i++) {
    const sessionIndex = navigationList[i].sessions.findIndex(s => s.session_id === currentId)
    if (sessionIndex !== -1) {
      currentGroupIndex = i
      currentSessionIndex = sessionIndex
      break
    }
  }

  if (currentGroupIndex === -1) {
    // 当前session不在列表中，选择最后一个session
    const lastGroup = navigationList[navigationList.length - 1]
    const lastSession = lastGroup.sessions[lastGroup.sessions.length - 1]
    switchToSession(lastSession.session_id)
    return
  }

  // 计算上一个session的位置
  let prevGroupIndex = currentGroupIndex
  let prevSessionIndex = currentSessionIndex - 1

  // 如果当前是项目的第一个session，跳转到上一个项目的最后一个session
  if (prevSessionIndex < 0) {
    prevGroupIndex = currentGroupIndex - 1
    // 如果当前是第一个项目的第一个session，循环到最后一个项目
    if (prevGroupIndex < 0) {
      prevGroupIndex = navigationList.length - 1
    }
    prevSessionIndex = navigationList[prevGroupIndex].sessions.length - 1
  }

  const prevSession = navigationList[prevGroupIndex].sessions[prevSessionIndex]
  switchToSession(prevSession.session_id)
}

/**
 * 在session列表中导航到下一个
 * 支持跨项目跳转：从最后一个项目的最后一个session跳转到第一个项目的第一个session
 */
function navigateToNextSession() {
  const navigationList = buildSessionNavigationList()
  if (navigationList.length === 0) return

  const currentId = currentSessionId.value
  if (!currentId) {
    // 如果没有当前session，选择第一个session
    const firstGroup = navigationList[0]
    const firstSession = firstGroup.sessions[0]
    switchToSession(firstSession.session_id)
    return
  }

  // 查找当前session的位置
  let currentGroupIndex = -1
  let currentSessionIndex = -1

  for (let i = 0; i < navigationList.length; i++) {
    const sessionIndex = navigationList[i].sessions.findIndex(s => s.session_id === currentId)
    if (sessionIndex !== -1) {
      currentGroupIndex = i
      currentSessionIndex = sessionIndex
      break
    }
  }

  if (currentGroupIndex === -1) {
    // 当前session不在列表中，选择第一个session
    const firstGroup = navigationList[0]
    const firstSession = firstGroup.sessions[0]
    switchToSession(firstSession.session_id)
    return
  }

  // 计算下一个session的位置
  let nextGroupIndex = currentGroupIndex
  let nextSessionIndex = currentSessionIndex + 1

  // 如果当前是项目的最后一个session，跳转到下一个项目的第一个session
  if (nextSessionIndex >= navigationList[nextGroupIndex].sessions.length) {
    nextGroupIndex = currentGroupIndex + 1
    // 如果当前是最后一个项目的最后一个session，循环到第一个项目
    if (nextGroupIndex >= navigationList.length) {
      nextGroupIndex = 0
    }
    nextSessionIndex = 0
  }

  const nextSession = navigationList[nextGroupIndex].sessions[nextSessionIndex]
  switchToSession(nextSession.session_id)
}

/**
 * 切换到指定session
 */
function switchToSession(sessionId) {
  if (switchSession) {
    switchSession(sessionId)
  } else if (setCurrentSessionId) {
    setCurrentSessionId(sessionId)
  }
}

// 注册全局session导航快捷键
// Mac: Cmd + Option + 上/下方向键
// Windows/Linux: Ctrl + Alt + 上/下方向键
useGlobalHotkeys({
  keys: ['Ctrl+Alt+ArrowUp', 'Cmd+Option+ArrowUp'],
  handler: () => {
    navigateToPreviousSession()
    return false // 阻止默认行为
  },
  priority: 10
})

useGlobalHotkeys({
  keys: ['Ctrl+Alt+ArrowDown', 'Cmd+Option+ArrowDown'],
  handler: () => {
    navigateToNextSession()
    return false // 阻止默认行为
  },
  priority: 10
})
</script>

<template>
  <!-- 这是一个无UI的组件，只处理全局快捷键 -->
</template>
