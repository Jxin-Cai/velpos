<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useTimeout } from '@shared/lib/useTimeout'
import {
  createMcpServerEntry,
  createSkillEntry,
  deleteMcpServerEntry,
  deleteSkillEntry,
  getSkillEntry,
  listMcpCategories,
  listMcpServerEntries,
  listSkillCategories,
  listSkillEntries,
  updateMcpServerEntry,
  updateSkillEntry,
} from '../api/adminMarketApi'

const props = defineProps({ kind: { type: String, required: true, validator: v => ['mcp', 'skill'].includes(v) } })
const emit = defineEmits(['dirty-change'])

const KIND_META = {
  mcp: {
    eyebrow: 'MCP MARKET',
    title: 'MCP 市场',
    intro: '管理可供 Agent 模板选用的 MCP Server，加载 Agent 时自动写入项目 .mcp.json。',
    entryLabel: 'MCP Server',
    defaultEmoji: '🔌',
    namePattern: /^[a-z0-9][a-z0-9._-]*$/,
    nameHint: '小写字母/数字开头，可含 . _ -（作为 .mcp.json 中的 server 键名）',
    api: {
      list: listMcpServerEntries,
      categories: listMcpCategories,
      create: createMcpServerEntry,
      update: updateMcpServerEntry,
      remove: deleteMcpServerEntry,
    },
  },
  skill: {
    eyebrow: 'SKILL MARKET',
    title: 'Skill 市场',
    intro: '管理可供 Agent 模板选用的 Skill，加载 Agent 时自动写入项目 .claude/skills/。',
    entryLabel: 'Skill',
    defaultEmoji: '🎯',
    namePattern: /^[a-z0-9][a-z0-9-]*$/,
    nameHint: '小写字母/数字开头，仅可含 -（兼作 skills 目录名）',
    api: {
      list: listSkillEntries,
      categories: listSkillCategories,
      create: createSkillEntry,
      update: updateSkillEntry,
      remove: deleteSkillEntry,
    },
  },
}

const TRANSPORT_OPTIONS = [
  { value: 'stdio', label: 'stdio · 本地进程' },
  { value: 'sse', label: 'sse · 远程 SSE' },
  { value: 'http', label: 'http · 远程 HTTP' },
]

const meta = computed(() => KIND_META[props.kind])
const isMcp = computed(() => props.kind === 'mcp')

const PAGE_SIZE = 12
const entries = ref([])
const categories = ref([])
const loading = ref(false)
const error = ref('')
const success = ref('')
const query = ref('')
const categoryFilter = ref('')
const currentPage = ref(1)
const deletingId = ref('')
const { set: setTimer } = useTimeout()

const showForm = ref(false)
const editingEntry = ref(null)
const saving = ref(false)
const formError = ref('')
const form = ref(emptyForm())
const initialSnapshot = ref('')

function emptyForm() {
  return {
    name: '',
    display_name: '',
    description: '',
    category: 'other',
    tagsText: '',
    transport: 'stdio',
    serverConfigText: '{\n  "command": "npx",\n  "args": ["-y", "@your/mcp-server"],\n  "env": {}\n}',
    content: '',
    repo_url: '',
    homepage_url: '',
    author: '',
    version: '',
    logo_emoji: KIND_META[props.kind].defaultEmoji,
    is_active: true,
  }
}

function showSuccess(message) {
  success.value = message
  setTimer(() => { success.value = '' }, 2200)
}

const categoryLabelById = computed(() => Object.fromEntries(categories.value.map(c => [c.id, c.name_zh || c.name_en || c.id])))

const filteredEntries = computed(() => {
  let result = entries.value
  const keyword = query.value.trim().toLocaleLowerCase()
  if (keyword) {
    result = result.filter(entry => [
      entry.name,
      entry.display_name,
      entry.description,
      entry.author,
      ...(entry.tags || []),
    ].some(value => String(value || '').toLocaleLowerCase().includes(keyword)))
  }
  if (categoryFilter.value) {
    result = result.filter(entry => entry.category === categoryFilter.value)
  }
  return result
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredEntries.value.length / PAGE_SIZE)))
const paginatedEntries = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return filteredEntries.value.slice(start, start + PAGE_SIZE)
})

watch([query, categoryFilter], () => { currentPage.value = 1 })
watch(totalPages, value => {
  if (currentPage.value > value) currentPage.value = value
})

const currentSnapshot = computed(() => JSON.stringify(form.value))
const isDirty = computed(() => showForm.value && Boolean(initialSnapshot.value) && currentSnapshot.value !== initialSnapshot.value)
watch(isDirty, value => emit('dirty-change', value), { immediate: true })

function handleBeforeUnload(event) {
  if (!isDirty.value) return
  event.preventDefault()
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const [entryList, categoryList] = await Promise.all([
      meta.value.api.list(),
      meta.value.api.categories(),
    ])
    entries.value = entryList || []
    categories.value = categoryList || []
  } catch (loadError) {
    error.value = loadError.message || `加载${meta.value.entryLabel}列表失败`
  } finally {
    loading.value = false
  }
}

function handleCreate() {
  editingEntry.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
  initialSnapshot.value = JSON.stringify(form.value)
}

async function handleEdit(entry) {
  formError.value = ''
  let detail = entry
  if (!isMcp.value) {
    try {
      detail = await getSkillEntry(entry.id)
    } catch (loadError) {
      error.value = loadError.message || '读取 Skill 详情失败'
      return
    }
  }
  editingEntry.value = detail
  form.value = {
    name: detail.name || '',
    display_name: detail.display_name || '',
    description: detail.description || '',
    category: detail.category || 'other',
    tagsText: (detail.tags || []).join(', '),
    transport: detail.transport || 'stdio',
    serverConfigText: isMcp.value ? JSON.stringify(detail.server_config || {}, null, 2) : emptyForm().serverConfigText,
    content: detail.content || '',
    repo_url: detail.repo_url || '',
    homepage_url: detail.homepage_url || '',
    author: detail.author || '',
    version: detail.version || '',
    logo_emoji: detail.logo_emoji || meta.value.defaultEmoji,
    is_active: detail.is_active !== false,
  }
  showForm.value = true
  initialSnapshot.value = JSON.stringify(form.value)
}

function requestCancel() {
  if (isDirty.value && !confirm(`当前${meta.value.entryLabel}尚未保存，确定丢弃修改吗？`)) return
  showForm.value = false
  editingEntry.value = null
  initialSnapshot.value = ''
  emit('dirty-change', false)
}

function buildPayload() {
  const name = form.value.name.trim()
  if (!name || !form.value.display_name.trim()) {
    formError.value = '标识名和显示名称为必填项'
    return null
  }
  if (!meta.value.namePattern.test(name)) {
    formError.value = `标识名格式不合法：${meta.value.nameHint}`
    return null
  }
  const tags = form.value.tagsText.split(/[,，\s]+/).map(tag => tag.trim()).filter(Boolean).slice(0, 16)
  const payload = {
    name,
    display_name: form.value.display_name.trim(),
    description: form.value.description.trim(),
    category: form.value.category,
    tags,
    repo_url: form.value.repo_url.trim(),
    author: form.value.author.trim(),
    version: form.value.version.trim(),
    logo_emoji: form.value.logo_emoji.trim() || meta.value.defaultEmoji,
    is_active: form.value.is_active,
  }
  if (isMcp.value) {
    let serverConfig
    try {
      serverConfig = JSON.parse(form.value.serverConfigText)
    } catch {
      formError.value = '连接配置不是合法的 JSON'
      return null
    }
    if (!serverConfig || typeof serverConfig !== 'object' || Array.isArray(serverConfig)) {
      formError.value = '连接配置必须是 JSON 对象'
      return null
    }
    if (form.value.transport === 'stdio' && !String(serverConfig.command || '').trim()) {
      formError.value = 'stdio 类型需要在连接配置中提供 command 字段'
      return null
    }
    if (form.value.transport !== 'stdio' && !String(serverConfig.url || '').trim()) {
      formError.value = `${form.value.transport} 类型需要在连接配置中提供 url 字段`
      return null
    }
    payload.transport = form.value.transport
    payload.server_config = serverConfig
    payload.homepage_url = form.value.homepage_url.trim()
  } else {
    if (!form.value.content.trim()) {
      formError.value = 'SKILL.md 内容为必填项'
      return null
    }
    payload.content = form.value.content
  }
  return payload
}

async function handleSubmit() {
  formError.value = ''
  const payload = buildPayload()
  if (!payload) return
  saving.value = true
  try {
    if (editingEntry.value) await meta.value.api.update(editingEntry.value.id, payload)
    else await meta.value.api.create(payload)
    showForm.value = false
    editingEntry.value = null
    initialSnapshot.value = ''
    emit('dirty-change', false)
    await loadData()
    showSuccess(`${meta.value.entryLabel} 已保存`)
  } catch (saveError) {
    formError.value = saveError.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function handleDelete(entry) {
  if (!confirm(`确定删除 ${meta.value.entryLabel}「${entry.display_name || entry.name}」？删除后引用它的 Agent 模板将不再安装该项。`)) return
  try {
    deletingId.value = entry.id
    await meta.value.api.remove(entry.id)
    entries.value = entries.value.filter(item => item.id !== entry.id)
    showSuccess(`${meta.value.entryLabel} 已删除`)
  } catch (deleteError) {
    error.value = deleteError.message || '删除失败'
  } finally {
    deletingId.value = ''
  }
}

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  loadData()
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', handleBeforeUnload))
</script>

<template>
  <section class="market-page">
    <header class="page-header">
      <div>
        <span class="eyebrow">{{ meta.eyebrow }}</span>
        <h1>{{ meta.title }}</h1>
        <p>{{ meta.intro }}</p>
      </div>
    </header>

    <form v-if="showForm" class="entry-form" @submit.prevent="handleSubmit">
      <header class="form-header">
        <h2>{{ editingEntry ? `编辑 ${meta.entryLabel}` : `新增 ${meta.entryLabel}` }}</h2>
        <button class="glass-btn" type="button" @click="requestCancel">返回列表</button>
      </header>
      <div v-if="formError" class="form-error" role="alert">{{ formError }}</div>

      <div class="form-section">
        <h3>基础信息</h3>
        <div class="form-grid">
          <label><span>标识名 *</span><input v-model="form.name" type="text" required autocomplete="off" :placeholder="isMcp ? '例：github' : '例：pdf-report'" /><small>{{ meta.nameHint }}</small></label>
          <label><span>显示名称 *</span><input v-model="form.display_name" type="text" required autocomplete="off" :placeholder="isMcp ? '例：GitHub' : '例：PDF 报告生成'" /></label>
          <label class="span-2"><span>描述</span><input v-model="form.description" type="text" placeholder="一句话说明用途，便于检索" /></label>
          <label><span>分类</span>
            <select v-model="form.category">
              <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name_zh || cat.name_en }}</option>
            </select>
          </label>
          <label><span>标签（逗号分隔，最多 16 个）</span><input v-model="form.tagsText" type="text" placeholder="例：git, vcs" /></label>
          <div class="compact-fields">
            <label><span>Logo Emoji</span><input v-model="form.logo_emoji" class="emoji-input" /></label>
            <label><span>版本</span><input v-model="form.version" type="text" placeholder="例：1.0.0" /></label>
            <label class="checkbox-field"><input v-model="form.is_active" type="checkbox" /><span>上架（可被 Agent 模板选用）</span></label>
          </div>
          <label><span>作者</span><input v-model="form.author" type="text" placeholder="例：Anthropic" /></label>
          <label><span>仓库地址</span><input v-model="form.repo_url" type="url" placeholder="https://github.com/..." /></label>
          <label v-if="isMcp"><span>主页地址</span><input v-model="form.homepage_url" type="url" placeholder="https://..." /></label>
        </div>
      </div>

      <div v-if="isMcp" class="form-section">
        <h3>连接配置</h3>
        <label><span>传输类型</span>
          <select v-model="form.transport">
            <option v-for="option in TRANSPORT_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>
        <label><span>Server 配置（JSON）*</span>
          <textarea v-model="form.serverConfigText" rows="8" spellcheck="false" required></textarea>
          <small>{{ form.transport === 'stdio' ? '需包含 command，可选 args / env' : '需包含 url，可选 headers' }}</small>
        </label>
      </div>

      <div v-else class="form-section">
        <h3>SKILL.md 内容</h3>
        <label><span>完整内容（含 frontmatter）*</span>
          <textarea v-model="form.content" rows="14" spellcheck="false" required placeholder="---&#10;name: pdf-report&#10;description: ...&#10;---&#10;&#10;技能说明..."></textarea>
          <small>frontmatter 中的 name 建议与标识名一致，加载 Agent 时将写入项目 .claude/skills/&lt;标识名&gt;/SKILL.md</small>
        </label>
      </div>

      <footer class="form-actions">
        <span v-if="isDirty" class="dirty-hint">有未保存的修改</span>
        <button class="glass-btn" type="button" @click="requestCancel">取消</button>
        <button class="glass-btn primary" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
      </footer>
    </form>

    <template v-else>
      <div v-if="success" class="success-state" role="status">{{ success }}</div>
      <div class="toolbar">
        <div class="search-row">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
          <input v-model="query" type="search" :aria-label="`搜索 ${meta.entryLabel}`" placeholder="搜索名称、描述、作者或标签" />
          <button v-if="query" class="clear-search" type="button" aria-label="清除搜索" @click="query = ''">清除</button>
        </div>
        <select v-model="categoryFilter" class="category-select" aria-label="按分类筛选">
          <option value="">全部分类</option>
          <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name_zh || cat.name_en }}</option>
        </select>
        <button class="glass-btn primary" type="button" @click="handleCreate">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          新增 {{ meta.entryLabel }}
        </button>
      </div>

      <div class="result-count">共 {{ filteredEntries.length }} 项</div>

      <div v-if="error" class="error-state" role="alert"><span>{{ error }}</span><button class="glass-btn sm" type="button" @click="loadData">重试</button></div>
      <div v-else-if="loading" class="loading-state">加载中...</div>

      <div v-else class="entry-grid">
        <article v-for="entry in paginatedEntries" :key="entry.id" class="entry-card" :class="{ inactive: !entry.is_active }">
          <div class="card-top">
            <span class="entry-emoji">{{ entry.logo_emoji || meta.defaultEmoji }}</span>
            <div class="badge-row">
              <span v-if="isMcp" class="transport-badge">{{ entry.transport }}</span>
              <span v-if="!entry.is_active" class="inactive-badge">已下架</span>
            </div>
          </div>
          <h2>{{ entry.display_name }}</h2>
          <p>{{ entry.description || '暂无描述' }}</p>
          <div v-if="(entry.tags || []).length" class="tag-row">
            <span v-for="tag in entry.tags" :key="tag" class="tag-chip">{{ tag }}</span>
          </div>
          <div class="card-meta">
            <span>{{ categoryLabelById[entry.category] || entry.category }}</span>
            <span v-if="entry.author">{{ entry.author }}</span>
            <span v-if="entry.version">v{{ entry.version }}</span>
            <code>{{ entry.name }}</code>
          </div>
          <div class="card-footer">
            <a v-if="entry.repo_url" class="repo-link" :href="entry.repo_url" target="_blank" rel="noopener noreferrer">仓库</a>
            <div class="entry-actions">
              <button class="glass-btn sm" type="button" :disabled="deletingId === entry.id" @click="handleEdit(entry)">编辑</button>
              <button class="glass-btn sm danger" type="button" :disabled="deletingId === entry.id" @click="handleDelete(entry)">{{ deletingId === entry.id ? '删除中…' : '删除' }}</button>
            </div>
          </div>
        </article>
        <div v-if="paginatedEntries.length === 0" class="empty-state">{{ entries.length ? `没有匹配的 ${meta.entryLabel}` : `暂无 ${meta.entryLabel}，点击右上角新增` }}</div>
      </div>

      <nav v-if="totalPages > 1" class="pagination" aria-label="分页导航">
        <button type="button" class="page-btn" :disabled="currentPage <= 1" @click="currentPage--">上一页</button>
        <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
        <button type="button" class="page-btn" :disabled="currentPage >= totalPages" @click="currentPage++">下一页</button>
      </nav>
    </template>
  </section>
</template>

<style scoped>
.market-page { max-width: 1080px; margin: 0 auto; }
.page-header { margin-bottom: 20px; }
.eyebrow { color: var(--accent); font-size: 9px; font-weight: 700; letter-spacing: .14em; }
.page-header h1 { margin: 4px 0 7px; font-size: 24px; letter-spacing: -.025em; }
.page-header p { margin: 0; color: var(--text-muted); font-size: 13px; }

.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.search-row { display: flex; align-items: center; gap: 9px; flex: 1; min-width: 200px; padding: 0 12px; border: 1px solid var(--border-subtle); border-radius: 9px; background: var(--layer-base); }
.search-row:focus-within { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
.search-row svg { width: 17px; fill: none; stroke: var(--text-muted); stroke-width: 1.8; flex-shrink: 0; }
.search-row input { min-width: 0; flex: 1; padding: 10px 0; border: 0; outline: 0; background: transparent; color: var(--text-primary); font: inherit; font-size: 13px; }
.clear-search { padding: 4px 7px; border: 0; border-radius: 5px; background: transparent; color: var(--text-muted); font-size: 11px; cursor: pointer; }
.clear-search:hover, .clear-search:focus-visible { background: var(--layer-active); color: var(--text-primary); outline: none; }
.category-select { padding: 8px 12px; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--layer-base); color: var(--text-primary); font: inherit; font-size: 12px; cursor: pointer; outline: none; }
.category-select:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
.result-count { margin-bottom: 14px; color: var(--text-muted); font-size: 11px; }

.entry-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.entry-card { display: flex; min-width: 0; flex-direction: column; padding: 17px; border: 1px solid var(--border-subtle); border-radius: 11px; background: var(--glass-bg); transition: transform .16s, border-color .16s; }
.entry-card:hover { transform: translateY(-1px); border-color: var(--border); }
.entry-card.inactive { opacity: .65; }
.card-top { display: flex; align-items: center; justify-content: space-between; }
.badge-row { display: flex; gap: 6px; }
.entry-emoji { display: grid; place-items: center; width: 35px; height: 35px; flex: 0 0 auto; border-radius: 9px; background: var(--accent-dim); font-size: 18px; }
.transport-badge { padding: 3px 7px; border-radius: 5px; background: var(--accent-dim); color: var(--accent); font-size: 10px; text-transform: uppercase; }
.inactive-badge { padding: 3px 7px; border-radius: 5px; background: var(--layer-active); color: var(--text-muted); font-size: 10px; }
.entry-card h2 { margin: 13px 0 6px; font-size: 14px; }
.entry-card p { min-height: 34px; margin: 0 0 10px; color: var(--text-muted); font-size: 12px; line-height: 1.45; }
.tag-row { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 10px; }
.tag-chip { padding: 2px 7px; border: 1px solid var(--border-subtle); border-radius: 999px; color: var(--text-secondary); font-size: 10px; }
.card-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 12px; color: var(--text-secondary); font-size: 10px; }
.card-meta code { min-width: 0; overflow: hidden; color: var(--text-muted); text-overflow: ellipsis; white-space: nowrap; }
.card-footer { display: flex; align-items: center; justify-content: space-between; margin-top: auto; gap: 8px; }
.repo-link { color: var(--accent); font-size: 11px; text-decoration: none; }
.repo-link:hover { text-decoration: underline; }
.entry-actions { display: flex; gap: 6px; margin-left: auto; }
.loading-state, .empty-state, .error-state { grid-column: 1 / -1; padding: 46px 12px; color: var(--text-muted); font-size: 13px; text-align: center; }
.error-state { display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--red); }
.success-state { margin-bottom: 14px; padding: 10px 12px; border-radius: 8px; background: var(--green-dim); color: var(--green); font-size: 12px; }

.pagination { display: flex; align-items: center; justify-content: center; gap: 16px; margin-top: 24px; padding: 12px 0; }
.page-btn { padding: 7px 14px; border: 1px solid var(--border-subtle); border-radius: 7px; background: var(--layer-base); color: var(--text-secondary); font: inherit; font-size: 12px; cursor: pointer; transition: border-color .16s, color .16s, background .16s; }
.page-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }
.page-btn:disabled { opacity: .4; cursor: not-allowed; }
.page-info { color: var(--text-muted); font-size: 12px; }

.entry-form { max-width: 960px; }
.form-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 20px; }
.form-header h2 { margin: 0; font-size: 20px; }
.form-section { margin-bottom: 14px; padding: 20px; border: 1px solid var(--border-subtle); border-radius: 12px; background: var(--glass-bg); }
.form-section h3 { margin: 0 0 16px; font-size: 14px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 14px; }
.span-2 { grid-column: 1 / -1; }
label { display: flex; flex-direction: column; gap: 6px; margin-bottom: 0; color: var(--text-secondary); font-size: 11px; }
label small { color: var(--text-muted); font-size: 10px; }
input, textarea, select { width: 100%; padding: 9px 11px; border: 1px solid var(--border-subtle); border-radius: 8px; outline: 0; background: var(--layer-base); color: var(--text-primary); font: inherit; font-size: 13px; }
textarea { resize: vertical; line-height: 1.5; font-family: var(--font-mono, monospace); }
input:focus, textarea:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
.compact-fields { display: flex; align-items: flex-end; gap: 14px; }
.emoji-input { width: 70px; }
.checkbox-field { flex-direction: row; align-items: center; gap: 8px; padding-bottom: 9px; }
.checkbox-field input { width: auto; box-shadow: none; }
.form-error { margin-bottom: 14px; padding: 10px 12px; border-radius: 8px; background: var(--red-dim); color: var(--red); font-size: 12px; }
.form-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding-top: 6px; }
.dirty-hint { margin-right: auto; color: var(--text-muted); font-size: 11px; }

@media (max-width: 700px) {
  .toolbar { flex-direction: column; align-items: stretch; }
  .search-row { min-width: 0; }
  .form-grid { grid-template-columns: 1fr; }
  .compact-fields { flex-wrap: wrap; }
  input, textarea, select { font-size: 16px; }
  .form-section { padding: 16px; }
}
@media (prefers-reduced-motion: reduce) { .entry-card, .page-btn { transition: none; } }
</style>
