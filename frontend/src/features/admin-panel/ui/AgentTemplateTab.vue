<script setup>
import { ref, onMounted } from 'vue'
import { listAgentTemplates, deleteAgentTemplate } from '../api/adminAgentApi'
import AgentTemplateForm from './AgentTemplateForm.vue'

const templates = ref([])
const loading = ref(false)
const showForm = ref(false)
const editingTemplate = ref(null)

async function loadTemplates() {
  loading.value = true
  try {
    templates.value = await listAgentTemplates()
  } finally {
    loading.value = false
  }
}

function handleCreate() {
  editingTemplate.value = null
  showForm.value = true
}

function handleEdit(template) {
  editingTemplate.value = template
  showForm.value = true
}

async function handleDelete(template) {
  if (!confirm(`确定删除 Agent 模板「${template.name_zh || template.name_en}」？`)) return
  await deleteAgentTemplate(template.id)
  await loadTemplates()
}

function handleFormSaved() {
  showForm.value = false
  editingTemplate.value = null
  loadTemplates()
}

function handleFormCancel() {
  showForm.value = false
  editingTemplate.value = null
}

onMounted(loadTemplates)
</script>

<template>
  <div class="agent-template-tab">
    <div class="tab-header">
      <h2 class="tab-title">自定义 Agent 模板</h2>
      <button class="glass-btn primary" @click="handleCreate">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="5" x2="12" y2="19"/>
          <line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        新增模板
      </button>
    </div>

    <AgentTemplateForm
      v-if="showForm"
      :template="editingTemplate"
      @saved="handleFormSaved"
      @cancel="handleFormCancel"
    />

    <div v-else-if="loading" class="loading-state">加载中...</div>

    <div v-else-if="templates.length === 0" class="empty-state">
      <p>暂无自定义 Agent 模板</p>
    </div>

    <div v-else class="template-list">
      <div
        v-for="tpl in templates"
        :key="tpl.id"
        class="template-card"
      >
        <div class="template-card-header">
          <span class="template-emoji">{{ tpl.emoji || '🤖' }}</span>
          <div class="template-info">
            <div class="template-name">{{ tpl.name_zh || tpl.name_en }}</div>
            <div class="template-desc">{{ tpl.description_zh || tpl.description_en }}</div>
          </div>
          <span class="template-category">{{ tpl.category }}</span>
        </div>
        <div class="template-actions">
          <button class="glass-btn sm" @click="handleEdit(tpl)">编辑</button>
          <button class="glass-btn sm danger" @click="handleDelete(tpl)">删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-template-tab {
  max-width: 900px;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.tab-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.loading-state,
.empty-state {
  color: var(--text-muted);
  font-size: 14px;
  padding: 40px 0;
  text-align: center;
}

.template-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.template-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  transition: background var(--transition-fast), border-color var(--transition-fast);
}

.template-card:hover {
  background: var(--layer-active);
  border-color: var(--border);
}

.template-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.template-emoji {
  font-size: 20px;
  flex-shrink: 0;
}

.template-info {
  flex: 1;
  min-width: 0;
}

.template-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.template-desc {
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.template-category {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--accent-dim);
  color: var(--accent);
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.template-actions {
  display: flex;
  gap: 6px;
  margin-left: 16px;
}
</style>
