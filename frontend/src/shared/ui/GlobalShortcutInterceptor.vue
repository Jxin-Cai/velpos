<script setup>
import { useSession } from '@entities/session'
import { useProject } from '@entities/project'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys'
import { useDialogManager } from '@shared/lib/useDialogManager'
import { inject, nextTick } from 'vue'

const { status, currentSessionId, sessions, setCurrentSessionId } = useSession()
const { projects } = useProject()
const connections = inject('wsConnections', null)
const switchSession = inject('switchSession', null)
const { closeTopmostDialog, hasOpenDialogs } = useDialogManager()

// ==================== Session 导航逻辑 ====================

/**
 * 构建扁平化的可导航 session 列表
 * 规则：
 * 1. 只包含未折叠项目中的 session
 * 2. 只纳入 velpos 管理的 session（有 project_id）
 * 3. 按照项目在侧边栏中的实际顺序展开（置顶项目在前）
 * 4. 每个项目内的 sessions 按 SessionSidebar 的排序规则
 */
function getFlattenedSessionList() {
  if (!sessions.value?.length || !projects.value?.length) return []

  const collapsedProjects = getCollapsedProjectIds()
  const pinnedProjectIds = getPinnedProjectIds()

  // 过滤出纳入 velpos 管理的 sessions（有 project_id）
  const managedSessions = sessions.value.filter(s => !!s.project_id)

  // 按 session_id 分组
  const sessionsByProject = {}
  for (const session of managedSessions) {
    if (!sessionsByProject[session.project_id]) {
      sessionsByProject[session.project_id] = []
    }
    sessionsByProject[session.project_id].push(session)
  }

  // 对每个项目内的 sessions 排序（遵循 SessionSidebar 的逻辑）
  for (const list of Object.values(sessionsByProject)) {
    list.sort((a, b) => {
      // Running sessions always come first
      const aRunning = a.status === 'running' ? 1 : 0
      const bRunning = b.status === 'running' ? 1 : 0
      if (aRunning !== bRunning) return bRunning - aRunning
      // Then by updated_time (most recent first)
      const timeA = a.updated_time ? new Date(a.updated_time).getTime() : 0
      const timeB = b.updated_time ? new Date(b.updated_time).getTime() : 0
      return timeB - timeA
    })
  }

  // 分离置顶和非置顶项目
  const pinnedProjects = []
  const unpinnedProjects = []

  for (const project of projects.value) {
    if (pinnedProjectIds.has(project.id)) {
      pinnedProjects.push(project)
    } else {
      unpinnedProjects.push(project)
    }
  }

  // 构建扁平列表：置顶项目在前，然后是非置顶项目
  const flattenedList = []

  for (const project of [...pinnedProjects, ...unpinnedProjects]) {
    // 跳过折叠的项目
    if (collapsedProjects.includes(project.id)) continue

    // 获取该项目中的 sessions
    const projectSessions = sessionsByProject[project.id] || []

    // 添加到扁平列表
    for (const session of projectSessions) {
      flattenedList.push(session)
    }
  }

  return flattenedList
}

/**
 * 获取置顶的项目 ID 列表
 */
function getPinnedProjectIds() {
  try {
    const stored = localStorage.getItem('pf_pinned_projects')
    return stored ? new Set(JSON.parse(stored)) : new Set()
  } catch {
    return new Set()
  }
}

/**
 * 从 localStorage 获取折叠的项目 ID 列表
 */
function getCollapsedProjectIds() {
  try {
    const stored = localStorage.getItem('pf_collapsed_groups')
    return stored ? JSON.parse(stored) : []
  } catch {
    return []
  }
}

/**
 * 查找当前 session 在扁平列表中的位置
 * 如果当前 session 不在导航列表中（比如是未管理的紫色session），返回 -1
 */
function findCurrentIndex(flattenedList) {
  const currentId = currentSessionId.value
  if (!currentId) return -1

  // 只在可导航的 session 列表中查找
  return flattenedList.findIndex(s => s.session_id === currentId)
}

/**
 * 切换到上一个 session
 */
function navigatePrevious() {
  const list = getFlattenedSessionList()

  if (list.length === 0) return

  const currentIndex = findCurrentIndex(list)

  // 如果当前 session 不在导航列表中（比如当前是未管理的紫色session）
  // 选择列表中的第一个 session
  if (currentIndex === -1) {
    const firstSession = list[0]
    switchToAndScroll(firstSession.session_id)
    return
  }

  // 计算上一个 session 的索引，循环到末尾
  const prevIndex = currentIndex - 1
  const targetIndex = prevIndex < 0 ? list.length - 1 : prevIndex

  const targetSession = list[targetIndex]
  switchToAndScroll(targetSession.session_id)
}

/**
 * 切换到下一个 session
 */
function navigateNext() {
  const list = getFlattenedSessionList()

  if (list.length === 0) return

  const currentIndex = findCurrentIndex(list)

  // 如果当前 session 不在导航列表中（比如当前是未管理的紫色session）
  // 选择列表中的第一个 session
  if (currentIndex === -1) {
    const firstSession = list[0]
    switchToAndScroll(firstSession.session_id)
    return
  }

  // 计算下一个 session 的索引，循环到开头
  const nextIndex = currentIndex + 1
  const targetIndex = nextIndex >= list.length ? 0 : nextIndex

  const targetSession = list[targetIndex]
  switchToAndScroll(targetSession.session_id)
}

/**
 * 切换 session 并滚动到视图
 */
function switchToAndScroll(sessionId) {
  if (switchSession) {
    switchSession(sessionId)
  } else if (setCurrentSessionId) {
    setCurrentSessionId(sessionId)
  }

  // 触发滚动事件
  nextTick(() => {
    window.dispatchEvent(new CustomEvent('vp-scroll-to-session', { detail: { sessionId } }))
  })
}

// ==================== 全局快捷键注册 ====================

// ESC: 关闭弹窗 > 取消运行中的查询 > 阻止浏览器默认行为
useGlobalHotkeys({
  keys: 'Escape',
  handler: (event) => {
    // 如果有弹窗打开，让弹窗自己的 ESC 处理逻辑去处理
    // 我们什么都不做，直接返回 true 让事件继续传播
    if (hasOpenDialogs()) {
      return true // 让弹窗的原生事件处理
    }

    // 没有弹窗时，处理取消查询
    const isRunning = status.value === 'running'
    if (isRunning && currentSessionId.value && connections) {
      // 取消正在运行的查询
      const connection = connections.get(currentSessionId.value)
      if (connection && connection.getReadyState() === WebSocket.OPEN) {
        connection.send({ action: 'cancel' })
        return false // 阻止默认行为和事件传播
      }
    }

    // 阻止 ESC 键传播到浏览器
    return false
  },
  priority: 5 // 最低优先级，让弹窗可以优先处理
})

// Cmd/Ctrl + 上箭头: 上一个 session
useGlobalHotkeys({
  keys: ['Ctrl+ArrowUp', 'Cmd+ArrowUp'],
  handler: () => {
    navigatePrevious()
    return true
  },
  priority: 100
})

// Cmd/Ctrl + 下箭头: 下一个 session
useGlobalHotkeys({
  keys: ['Ctrl+ArrowDown', 'Cmd+ArrowDown'],
  handler: () => {
    navigateNext()
    return true
  },
  priority: 100
})

// Cmd/Ctrl + K: 语音输入切换
useGlobalHotkeys({
  keys: ['Ctrl+K', 'Cmd+K'],
  handler: () => {
    window.dispatchEvent(new CustomEvent('vp-voice-toggle-global'))
    return false
  },
  priority: 100
})
</script>

<template>
  <!-- 无 UI 组件 -->
</template>
