<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useTimeout } from '@shared/lib/useTimeout'
import { deleteAgentTemplate, listAgentTemplates, listSystemAgents } from '../api/adminAgentApi'
import AgentTemplateForm from './AgentTemplateForm.vue'

const props = defineProps({
  page: { type: String, required: true, validator: value => ['system', 'custom'].includes(value) },
})
const emit = defineEmits(['dirty-change'])

const templates = ref([])
const systemCategories = ref([])
const loading = ref(false)
const error = ref('')
const query = ref('')
const showForm = ref(false)
const editingTemplate = ref(null)
const deletingId = ref('')
const success = ref('')
const { set: setTimer } = useTimeout()

function showSuccess(message) {
  success.value = message
  setTimer(() => { success.value = '' }, 2200)
}

const systemAgents = computed(() => systemCategories.value.flatMap(category =>
  (category.agents || [])
    .filter(agent => agent.source !== 'custom')
    .map(agent => ({ ...agent, categoryName: category.name })),
))

const filteredSystemAgents = computed(() => filterItems(systemAgents.value))
const filteredTemplates = computed(() => filterItems(templates.value))

function filterItems(items) {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return items
  return items.filter(item => [
    item.id,
    item.name,
    item.name_zh,
    item.name_en,
    item.description,
    item.description_zh,
    item.description_en,
    item.category,
    item.categoryName,
  ].some(value => String(value || '').toLocaleLowerCase().includes(keyword)))
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    if (props.page === 'system') {
      const result = await listSystemAgents()
      systemCategories.value = result.categories || []
    } else {
      templates.value = await listAgentTemplates()
    }
  } catch (loadError) {
    error.value = loadError.message || '加载 Agent 模板失败'
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
  try {
    deletingId.value = template.id
    await deleteAgentTemplate(template.id)
    await loadData()
    showSuccess('Agent 模板已删除')
  } catch (deleteError) {
    error.value = deleteError.message || '删除失败'
  } finally {
    deletingId.value = ''
  }
}

async function handleFormSaved() {
  showForm.value = false
  editingTemplate.value = null
  emit('dirty-change', false)
  await loadData()
  showSuccess('Agent 模板已保存')
}

watch(() => props.page, () => {
  query.value = ''
  showForm.value = false
  emit('dirty-change', false)
  loadData()
})

onMounted(loadData)
</script>

<template>
  <section class="agent-page">
    <header class="page-header">
      <div>
        <span class="eyebrow">AGENT TEMPLATES</span>
        <h1>{{ page === 'system' ? '系统 Agent' : '自定义 Agent' }}</h1>
        <p>{{ page === 'system' ? '检索并查看 Velpos 内置提供的默认 Agent。' : '管理由管理员扩展并存储在数据库中的 Agent。' }}</p>
      </div>
      <button v-if="page === 'custom' && !showForm" class="glass-btn primary" type="button" @click="handleCreate">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
        新增模板
      </button>
    </header>

    <AgentTemplateForm
      v-if="showForm"
      :template="editingTemplate"
      @saved="handleFormSaved"
      @cancel="showForm = false; editingTemplate = null; emit('dirty-change', false)"
      @dirty-change="emit('dirty-change', $event)"
    />

    <template v-else>
      <div v-if="success" class="success-state" role="status">{{ success }}</div>
      <div class="search-row">
        <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
        <input v-model="query" type="search" aria-label="搜索 Agent 模板" :placeholder="page === 'system' ? '搜索默认 Agent 名称、描述或分类' : '搜索自定义 Agent 名称、描述或分类'" />
        <button v-if="query" class="clear-search" type="button" aria-label="清除搜索" @click="query = ''">清除</button>
        <span>{{ page === 'system' ? filteredSystemAgents.length : filteredTemplates.length }} 项</span>
      </div>

      <div v-if="error" class="error-state" role="alert"><span>{{ error }}</span><button class="glass-btn sm" type="button" @click="loadData">重试</button></div>
      <div v-else-if="loading" class="loading-state">加载中...</div>

      <div v-else-if="page === 'system'" class="template-grid">
        <article v-for="agent in filteredSystemAgents" :key="agent.id" class="template-card">
          <div class="card-top">
            <span class="template-emoji">{{ agent.emoji || '✦' }}</span>
            <span class="source-badge">系统内置</span>
          </div>
          <h2>{{ agent.name }}</h2>
          <p>{{ agent.description || '暂无描述' }}</p>
          <div class="card-meta"><span>{{ agent.categoryName }}</span><code>{{ agent.id }}</code></div>
        </article>
        <div v-if="filteredSystemAgents.length === 0" class="empty-state">没有匹配的系统 Agent</div>
      </div>

      <div v-else class="template-list">
        <article v-for="template in filteredTemplates" :key="template.id" class="template-card custom-card">
          <div class="card-main">
            <span class="template-emoji">{{ template.emoji || '🤖' }}</span>
            <div>
              <h2>{{ template.name_zh || template.name_en }}</h2>
              <p>{{ template.description_zh || template.description_en || '暂无描述' }}</p>
              <div class="card-meta"><span>{{ template.category }}</span><code>{{ template.name_en }}</code></div>
            </div>
          </div>
          <div class="template-actions">
            <button class="glass-btn sm" type="button" :disabled="deletingId === template.id" @click="handleEdit(template)">编辑</button>
            <button class="glass-btn sm danger" type="button" :disabled="deletingId === template.id" @click="handleDelete(template)">{{ deletingId === template.id ? '删除中…' : '删除' }}</button>
          </div>
        </article>
        <div v-if="filteredTemplates.length === 0" class="empty-state">{{ templates.length ? '没有匹配的自定义 Agent' : '暂无自定义 Agent 模板' }}</div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.agent-page { max-width: 1080px; margin: 0 auto; }
.page-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 24px; }
.eyebrow { color: var(--accent); font-size: 9px; font-weight: 700; letter-spacing: .14em; }
.page-header h1 { margin: 4px 0 7px; font-size: 24px; letter-spacing: -.025em; }
.page-header p { margin: 0; color: var(--text-muted); font-size: 13px; }
.search-row { display: flex; align-items: center; gap: 9px; margin-bottom: 18px; padding: 0 12px; border: 1px solid var(--border-subtle); border-radius: 9px; background: var(--layer-base); }
.search-row:focus-within { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
.search-row svg { width: 17px; fill: none; stroke: var(--text-muted); stroke-width: 1.8; }
.search-row input { min-width: 0; flex: 1; padding: 10px 0; border: 0; outline: 0; background: transparent; color: var(--text-primary); font: inherit; font-size: 13px; }
.search-row span { color: var(--text-muted); font-size: 11px; }
.clear-search { padding: 4px 7px; border: 0; border-radius: 5px; background: transparent; color: var(--text-muted); font-size: 11px; cursor: pointer; }.clear-search:hover, .clear-search:focus-visible { background: var(--layer-active); color: var(--text-primary); outline: none; }
.template-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 12px; }
.template-list { display: flex; flex-direction: column; gap: 10px; }
.template-card { min-width: 0; padding: 17px; border: 1px solid var(--border-subtle); border-radius: 11px; background: var(--glass-bg); transition: transform .16s, border-color .16s; }
.template-card:hover { transform: translateY(-1px); border-color: var(--border); }
.card-top, .card-main, .custom-card { display: flex; align-items: center; }
.card-top { justify-content: space-between; }
.card-main { min-width: 0; gap: 13px; }
.custom-card { justify-content: space-between; gap: 20px; }
.template-emoji { display: grid; place-items: center; width: 35px; height: 35px; flex: 0 0 auto; border-radius: 9px; background: var(--accent-dim); font-size: 18px; }
.source-badge { padding: 3px 7px; border-radius: 5px; background: var(--accent-dim); color: var(--accent); font-size: 10px; }
.template-card h2 { margin: 13px 0 6px; font-size: 14px; }
.card-main h2 { margin-top: 0; }
.template-card p { min-height: 34px; margin: 0 0 12px; color: var(--text-muted); font-size: 12px; line-height: 1.45; }
.card-main p { min-height: auto; }
.card-meta { display: flex; align-items: center; gap: 8px; color: var(--text-secondary); font-size: 10px; }
.card-meta code { min-width: 0; overflow: hidden; color: var(--text-muted); text-overflow: ellipsis; white-space: nowrap; }
.template-actions { display: flex; flex: 0 0 auto; gap: 6px; }
.loading-state, .empty-state, .error-state { grid-column: 1 / -1; padding: 46px 12px; color: var(--text-muted); font-size: 13px; text-align: center; }
.error-state { display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--red); }
.success-state { margin-bottom: 14px; padding: 10px 12px; border-radius: 8px; background: var(--green-dim); color: var(--green); font-size: 12px; }
@media (max-width: 640px) { .page-header, .custom-card { align-items: stretch; flex-direction: column; } .template-actions { align-self: flex-end; } }
</style>
