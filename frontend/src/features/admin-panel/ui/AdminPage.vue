<script setup>
import { ref } from 'vue'
import AgentTemplateTab from './AgentTemplateTab.vue'
import UserManagementTab from './UserManagementTab.vue'
import { SettingsDialog } from '@features/settings-manager'
import { GitManagerDialog } from '@features/git-manager'

const emit = defineEmits(['close'])

const tabs = [
  { key: 'agents', label: 'Agent 模板' },
  { key: 'users', label: '用户管理' },
  { key: 'settings', label: 'CC 配置' },
  { key: 'git', label: 'Git 配置' },
]

const activeTab = ref('agents')
const settingsVisible = ref(false)
const gitVisible = ref(false)

function selectTab(tab) {
  activeTab.value = tab.key
  if (tab.key === 'settings') settingsVisible.value = true
  if (tab.key === 'git') gitVisible.value = true
}
</script>

<template>
  <div class="admin-page">
    <header class="admin-header">
      <div class="admin-header-left">
        <button class="glass-btn" @click="emit('close')" title="返回">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
        <h1 class="admin-title">管理面板</h1>
      </div>
      <nav class="admin-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="admin-tab"
          :class="{ active: activeTab === tab.key }"
          @click="selectTab(tab)"
        >
          {{ tab.label }}
        </button>
      </nav>
    </header>
    <main class="admin-body">
      <AgentTemplateTab v-if="activeTab === 'agents'" />
      <UserManagementTab v-else-if="activeTab === 'users'" />
      <div v-else-if="activeTab === 'settings'" class="admin-launcher">
        <p>管理 Claude Code 设置、模型渠道和认证配置。</p>
        <button class="glass-btn primary" @click="settingsVisible = true">打开 CC 配置</button>
      </div>
      <div v-else-if="activeTab === 'git'" class="admin-launcher">
        <p>管理全局 Git 身份和 SSH 密钥。</p>
        <button class="glass-btn primary" @click="gitVisible = true">打开 Git 配置</button>
      </div>
    </main>
    <SettingsDialog :visible="settingsVisible" @close="settingsVisible = false" />
    <GitManagerDialog :visible="gitVisible" @close="gitVisible = false" />
  </div>
</template>

<style scoped>
.admin-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--layer-workspace);
}

.admin-header {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.admin-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.admin-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.admin-tabs {
  display: flex;
  gap: 4px;
}

.admin-tab {
  padding: 6px 14px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.admin-tab:hover {
  background: var(--layer-active);
  color: var(--text-primary);
}

.admin-tab.active {
  background: var(--accent-dim);
  color: var(--accent);
}

.admin-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.admin-launcher {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--text-muted);
  font-size: 14px;
  flex-direction: column;
  gap: 12px;
}
</style>
