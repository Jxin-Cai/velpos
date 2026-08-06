<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useTimeout } from '@shared/lib/useTimeout'
import { deleteAgentTemplate, listAgentTemplates, listSystemAgents } from '../api/adminAgentApi'
import AgentTemplateForm from './AgentTemplateForm.vue'

const emit = defineEmits(['dirty-change'])

const PAGE_SIZE = 20
const activeTab = ref('system')
const templates = ref([])
const systemCategories = ref([])
const loading = ref(false)
const error = ref('')
const query = ref('')
const categoryFilter = ref('')
const currentPage = ref(1)
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

const allCategories = computed(() => {
  if (activeTab.value === 'system') {
    const names = [...new Set(systemAgents.value.map(a => a.categoryName).filter(Boolean))]
    return names.sort()
  }
  const names = [...new Set(templates.value.map(t => t.category).filter(Boolean))]
  return names.sort()
})

const filteredItems = computed(() => {
  const items = activeTab.value === 'system' ? systemAgents.value : templates.value
  let result = items

  const keyword = query.value.trim().toLocaleLowerCase()
  if (keyword) {
    result = result.filter(item => [
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

  if (categoryFilter.value) {
    const cat = categoryFilter.value
    result = result.filter(item =>
      (item.categoryName || item.category || '') === cat,
    )
  }

  return result
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredItems.value.length / PAGE_SIZE)))
const paginatedItems = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return filteredItems.value.slice(start, start + PAGE_SIZE)
})

watch([query, categoryFilter, activeTab], () => { currentPage.value = 1 })

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const [sysResult, customResult] = await Promise.all([
      listSystemAgents(),
      listAgentTemplates(),
    ])
    systemCategories.value = sysResult.categories || []
    templates.value = customResult
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
    templates.value = templates.value.filter(t => t.id !== template.id)
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

function switchTab(tab) {
  if (tab === activeTab.value) return
  activeTab.value = tab
  query.value = ''
  categoryFilter.value = ''
  showForm.value = false
  emit('dirty-change', false)
}

onMounted(loadData)
</script>

<template>
  <section class="agent-page">
    <header class="page-header">
      <div>
        <span class="eyebrow">AGENT TEMPLATES</span>
        <h1>Agent 模板</h1>
        <p>管理系统内置与自定义 Agent 模板。</p>
      </div>
    </header>

    <div class="tab-bar">
      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === 'system' }"
        @click="switchTab('system')"
      >系统 Agent</button>
      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === 'custom' }"
        @click="switchTab('custom')"
      >自定义 Agent</button>
    </div>

    <AgentTemplateForm
      v-if="showForm"
      :template="editingTemplate"
      @saved="handleFormSaved"
      @cancel="showForm = false; editingTemplate = null; emit('dirty-change', false)"
      @dirty-change="emit('dirty-change', $event)"
    />

    <template v-else>
      <div v-if="success" class="success-state" role="status">{{ success }}</div>
      <div class="toolbar">
        <div class="search-row">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
          <input v-model="query" type="search" aria-label="搜索 Agent 模板" placeholder="搜索名称、描述或分类" />
          <button v-if="query" class="clear-search" type="button" aria-label="清除搜索" @click="query = ''">清除</button>
        </div>
        <select v-if="allCategories.length > 0" v-model="categoryFilter" class="category-select" aria-label="按分类筛选">
          <option value="">全部分类</option>
          <option v-for="cat in allCategories" :key="cat" :value="cat">{{ cat }}</option>
        </select>
        <button v-if="activeTab === 'custom'" class="glass-btn primary" type="button" @click="handleCreate">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          新增模板
        </button>
      </div>

      <div class="result-count">共 {{ filteredItems.length }} 项</div>

      <div v-if="error" class="error-state" role="alert"><span>{{ error }}</span><button class="glass-btn sm" type="button" @click="loadData">重试</button></div>
      <div v-else-if="loading" class="loading-state">加载中...</div>

      <div v-else-if="activeTab === 'system'" class="template-grid">
        <article v-for="agent in paginatedItems" :key="agent.id" class="template-card">
          <div class="card-top">
            <span class="template-emoji">{{ agent.emoji || '✦' }}</span>
            <span class="source-badge">系统内置</span>
          </div>
          <h2>{{ agent.name }}</h2>
          <p>{{ agent.description || '暂无描述' }}</p>
          <div class="card-meta"><span>{{ agent.categoryName }}</span><code>{{ agent.id }}</code></div>
        </article>
        <div v-if="paginatedItems.length === 0" class="empty-state">没有匹配的系统 Agent</div>
      </div>

      <div v-else class="template-list">
        <article v-for="template in paginatedItems" :key="template.id" class="template-card custom-card">
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
        <div v-if="paginatedItems.length === 0" class="empty-state">{{ templates.length ? '没有匹配的自定义 Agent' : '暂无自定义 Agent 模板' }}</div>
      </div>

      <nav v-if="totalPages > 1" class="pagination" aria-label="分页导航">
        <button
          type="button"
          class="page-btn"
          :disabled="currentPage <= 1"
          @click="currentPage--"
        >上一页</button>
        <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
        <button
          type="button"
          class="page-btn"
          :disabled="currentPage >= totalPages"
          @click="currentPage++"
        >下一页</button>
      </nav>
    </template>
  </section>
</template>

<style scoped>
.agent-page { max-width: 1080px; margin: 0 auto; }
.page-header { margin-bottom: 20px; }
.eyebrow { color: var(--accent); font-size: 9px; font-weight: 700; letter-spacing: .14em; }
.page-header h1 { margin: 4px 0 7px; font-size: 24px; letter-spacing: -.025em; }
.page-header p { margin: 0; color: var(--text-muted); font-size: 13px; }

.tab-bar { display: flex; gap: 0; margin-bottom: 20px; border-bottom: 1px solid var(--border-subtle); }
.tab-btn { position: relative; padding: 10px 18px; border: 0; background: transparent; color: var(--text-secondary); font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; transition: color .16s; }
.tab-btn:hover { color: var(--text-primary); }
.tab-btn.active { color: var(--accent); font-weight: 600; }
.tab-btn.active::after { content: ''; position: absolute; left: 0; right: 0; bottom: -1px; height: 2px; background: var(--accent); border-radius: 2px 2px 0 0; }

.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.search-row { display: flex; align-items: center; gap: 9px; flex: 1; min-width: 200px; padding: 0 12px; border: 1px solid var(--border-subtle); border-radius: 9px; background: var(--layer-base); }
.search-row:focus-within { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
.search-row svg { width: 17px; fill: none; stroke: var(--text-muted); stroke-width: 1.8; flex-shrink: 0; }
.search-row input { min-width: 0; flex: 1; padding: 10px 0; border: 0; outline: 0; background: transparent; color: var(--text-primary); font: inherit; font-size: 13px; }
.clear-search { padding: 4px 7px; border: 0; border-radius: 5px; background: transparent; color: var(--text-muted); font-size: 11px; cursor: pointer; }.clear-search:hover, .clear-search:focus-visible { background: var(--layer-active); color: var(--text-primary); outline: none; }

.category-select { padding: 8px 12px; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--layer-base); color: var(--text-primary); font: inherit; font-size: 12px; cursor: pointer; outline: none; }
.category-select:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }

.result-count { margin-bottom: 14px; color: var(--text-muted); font-size: 11px; }

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

.pagination { display: flex; align-items: center; justify-content: center; gap: 16px; margin-top: 24px; padding: 12px 0; }
.page-btn { padding: 7px 14px; border: 1px solid var(--border-subtle); border-radius: 7px; background: var(--layer-base); color: var(--text-secondary); font: inherit; font-size: 12px; cursor: pointer; transition: border-color .16s, color .16s, background .16s; }
.page-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }
.page-btn:disabled { opacity: .4; cursor: not-allowed; }
.page-info { color: var(--text-muted); font-size: 12px; }

@media (max-width: 640px) { .toolbar { flex-direction: column; align-items: stretch; } .search-row { min-width: 0; } .custom-card { align-items: stretch; flex-direction: column; } .template-actions { align-self: flex-end; } }
</style>
