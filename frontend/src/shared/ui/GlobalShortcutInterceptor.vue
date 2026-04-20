<script setup>
import { useSession } from '@entities/session'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys'
import { inject } from 'vue'

/**
 * GlobalShortcutInterceptor
 * 全局快捷键拦截组件
 *
 * 功能：
 * - 使用 useGlobalHotkeys 系统注册全局快捷键
 * - ESC键：当session运行时取消查询，否则放行
 * - 可扩展其他全局快捷键逻辑
 */

const { status, currentSessionId } = useSession()

// 从App.vue中注入连接池
const connections = inject('wsConnections', null)

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
</script>

<template>
  <!-- 这是一个无UI的组件，只处理全局快捷键 -->
</template>
