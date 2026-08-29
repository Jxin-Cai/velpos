<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import EmojiPickerField from '@shared/ui/EmojiPickerField.vue'
import {
  createAgentTemplate,
  listClaudeMarketplacePlugins,
  listClaudeMarketplaces,
  updateAgentTemplate,
} from '../api/adminAgentApi'
import { listMcpServerEntries, listSkillEntries } from '../api/adminMarketApi'

const props = defineProps({ template: { type: Object, default: null } })
const emit = defineEmits(['saved', 'cancel', 'dirty-change'])

const form = ref({
  name_en: '', name_zh: '', description_en: '', description_zh: '',
  category: 'custom', emoji: '🤖', color: '#6366f1', prompt_en: '', prompt_zh: '',
})
const marketplaces = ref([])
const selectedMarketplaceName = ref('')
const availablePlugins = ref([])
const selectedPlugins = ref([])
const preservedLocalPlugins = ref([])
const configuredMarketplaces = ref([])
const pluginQuery = ref('')
const mcpEntries = ref([])
const skillEntries = ref([])
const selectedMcpIds = ref([])
const selectedSkillIds = ref([])
const mcpQuery = ref('')
const skillQuery = ref('')
const marketLoading = ref(false)
const pluginsLoading = ref(false)
const marketplacesLoading = ref(false)
const saving = ref(false)
const isEdit = ref(false)
const error = ref('')
const initialSnapshot = ref('')
let pluginLoadSequence = 0

const selectedMarketplace = computed(() => marketplaces.value.find(item => item.name === selectedMarketplaceName.value))
const filteredPlugins = computed(() => {
  const keyword = pluginQuery.value.trim().toLocaleLowerCase()
  if (!keyword) return availablePlugins.value
  return availablePlugins.value.filter(plugin => [plugin.name, plugin.key, plugin.description]
    .some(value => String(value || '').toLocaleLowerCase().includes(keyword)))
})

function filterMarketEntries(entries, keyword) {
  const normalized = keyword.trim().toLocaleLowerCase()
  if (!normalized) return entries
  return entries.filter(entry => [
    entry.name,
    entry.display_name,
    entry.description,
    entry.author,
    ...(entry.tags || []),
  ].some(value => String(value || '').toLocaleLowerCase().includes(normalized)))
}

const filteredMcpEntries = computed(() => filterMarketEntries(mcpEntries.value, mcpQuery.value))
const filteredSkillEntries = computed(() => filterMarketEntries(skillEntries.value, skillQuery.value))

function countMissingSelections(selectedIds, entries) {
  const knownIds = new Set(entries.map(entry => entry.id))
  return selectedIds.filter(id => !knownIds.has(id)).length
}

const missingMcpCount = computed(() => (marketLoading.value ? 0 : countMissingSelections(selectedMcpIds.value, mcpEntries.value)))
const missingSkillCount = computed(() => (marketLoading.value ? 0 : countMissingSelections(selectedSkillIds.value, skillEntries.value)))
const currentSnapshot = computed(() => JSON.stringify({
  form: { ...form.value, color: String(form.value.color || '').toLowerCase() },
  plugins: [...selectedPlugins.value].sort(),
  localPlugins: preservedLocalPlugins.value,
  mcpServerIds: [...selectedMcpIds.value].sort(),
  skillIds: [...selectedSkillIds.value].sort(),
}))
const isDirty = computed(() => Boolean(initialSnapshot.value) && currentSnapshot.value !== initialSnapshot.value)

async function loadPlugins(name) {
  const sequence = ++pluginLoadSequence
  availablePlugins.value = []
  if (!name) return
  pluginsLoading.value = true
  try {
    const plugins = await listClaudeMarketplacePlugins(name)
    if (sequence !== pluginLoadSequence) return
    availablePlugins.value = plugins.map(plugin => ({ ...plugin, key: `${plugin.name}@${plugin.marketplace || name}` }))
  } catch (loadError) {
    if (sequence !== pluginLoadSequence) return
    error.value = loadError.message || '读取市场插件失败'
  } finally {
    if (sequence === pluginLoadSequence) pluginsLoading.value = false
  }
}

watch(selectedMarketplaceName, (name) => {
  pluginQuery.value = ''
  loadPlugins(name)
})

watch(isDirty, value => emit('dirty-change', value), { immediate: true })

function handleBeforeUnload(event) {
  if (!isDirty.value) return
  event.preventDefault()
}

function requestCancel() {
  if (isDirty.value && !confirm('当前模板尚未保存，确定丢弃修改吗？')) return
  emit('dirty-change', false)
  emit('cancel')
}

onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  if (props.template) {
    isEdit.value = true
    form.value = {
      name_en: props.template.name_en || '', name_zh: props.template.name_zh || '',
      description_en: props.template.description_en || '', description_zh: props.template.description_zh || '',
      category: props.template.category || 'custom', emoji: props.template.emoji || '🤖',
      color: props.template.color || '#6366f1', prompt_en: props.template.prompt_en || '', prompt_zh: props.template.prompt_zh || '',
    }
    const config = props.template.plugins_config || {}
    configuredMarketplaces.value = [...(config.marketplaces || [])]
    selectedMarketplaceName.value = config.marketplaces?.[0]?.name || ''
    selectedPlugins.value = [...(config.plugins || [])]
    preservedLocalPlugins.value = [...(config.local_plugins || [])]
    selectedMcpIds.value = [...(config.mcp_server_ids || [])]
    selectedSkillIds.value = [...(config.skill_ids || [])]
  }
  await nextTick()
  initialSnapshot.value = currentSnapshot.value
  marketplacesLoading.value = true
  marketLoading.value = true
  loadMarketEntries()
  try {
    marketplaces.value = await listClaudeMarketplaces()
  } catch (loadError) {
    error.value = loadError.message || '读取本地 Claude Code 市场失败'
  } finally {
    marketplacesLoading.value = false
  }
})

async function loadMarketEntries() {
  try {
    const [mcpList, skillList] = await Promise.all([
      listMcpServerEntries({ onlyActive: true }),
      listSkillEntries({ onlyActive: true }),
    ])
    mcpEntries.value = mcpList || []
    skillEntries.value = skillList || []
  } catch (loadError) {
    error.value = loadError.message || '读取 MCP / Skill 市场失败'
  } finally {
    marketLoading.value = false
  }
}

onBeforeUnmount(() => window.removeEventListener('beforeunload', handleBeforeUnload))

async function handleSubmit() {
  error.value = ''
  if (['name_en', 'name_zh', 'prompt_en', 'prompt_zh'].some(key => !form.value[key]?.trim())) {
    error.value = '中英文名称和 Prompt 均为必填项'
    document.querySelector('.agent-form input:invalid, .agent-form textarea:invalid')?.focus()
    return
  }

  const selectedMarketNames = new Set(selectedPlugins.value.map(key => key.split('@').at(-1)).filter(Boolean))
  const marketplaceConfigs = [...selectedMarketNames].map(name =>
    marketplaces.value.find(item => item.name === name)
      || configuredMarketplaces.value.find(item => item.name === name),
  ).filter(Boolean).map(item => ({ name: item.name, source: item.source }))
  const pluginsConfig = marketplaceConfigs.length || selectedPlugins.value.length || preservedLocalPlugins.value.length
    || selectedMcpIds.value.length || selectedSkillIds.value.length
    ? {
        marketplaces: marketplaceConfigs,
        plugins: [...selectedPlugins.value],
        local_plugins: [...preservedLocalPlugins.value],
        mcp_server_ids: [...selectedMcpIds.value],
        skill_ids: [...selectedSkillIds.value],
      }
    : null

  saving.value = true
  try {
    const payload = { ...form.value, plugins_config: pluginsConfig }
    if (isEdit.value) await updateAgentTemplate(props.template.id, payload)
    else await createAgentTemplate(payload)
    emit('dirty-change', false)
    emit('saved')
  } catch (saveError) {
    error.value = saveError.message || '保存失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form class="agent-form" @submit.prevent="handleSubmit">
    <header class="form-header">
      <div><span class="eyebrow">CUSTOM AGENT</span><h2>{{ isEdit ? '编辑 Agent 模板' : '新增 Agent 模板' }}</h2></div>
      <button class="glass-btn" type="button" @click="requestCancel">返回列表</button>
    </header>
    <div v-if="error" class="form-error" role="alert">{{ error }}</div>

    <section class="form-section">
      <h3>基础信息</h3>
      <div class="form-grid">
        <label><span>名称（中文）*</span><input v-model="form.name_zh" type="text" required autocomplete="off" placeholder="例：代码审查助手" /></label>
        <label><span>名称（英文）*</span><input v-model="form.name_en" type="text" required autocomplete="off" placeholder="e.g. Code Review Assistant" /></label>
        <label><span>描述（中文）</span><input v-model="form.description_zh" type="text" placeholder="简短描述" /></label>
        <label><span>描述（英文）</span><input v-model="form.description_en" type="text" placeholder="Short description" /></label>
        <label><span>分类</span><input v-model="form.category" type="text" placeholder="例：development" /></label>
        <div class="compact-fields"><label><span>Emoji</span><EmojiPickerField v-model="form.emoji" fallback="🤖" /></label><label><span>颜色</span><input v-model="form.color" type="color" class="color-input" /></label></div>
      </div>
    </section>

    <section class="form-section">
      <h3>系统提示词</h3>
      <label><span>Prompt（中文）*</span><textarea v-model="form.prompt_zh" rows="8" required placeholder="Agent 系统提示词（中文）"></textarea></label>
      <label><span>Prompt（英文）*</span><textarea v-model="form.prompt_en" rows="8" required placeholder="Agent system prompt (English)"></textarea></label>
    </section>

    <section class="form-section">
      <div class="section-heading"><div><h3>Claude Code 插件</h3><p>从本机 Claude Code 已加载的市场中选择插件。</p></div></div>
      <label><span>插件市场</span>
        <select v-model="selectedMarketplaceName">
          <option v-if="marketplacesLoading" value="">正在读取市场…</option>
          <option value="">不使用市场插件</option>
          <option v-if="selectedMarketplaceName && !selectedMarketplace" :value="selectedMarketplaceName">{{ selectedMarketplaceName }} · 市场当前不可用</option>
          <option v-for="marketplace in marketplaces" :key="marketplace.name" :value="marketplace.name">{{ marketplace.name }} · {{ marketplace.source }}</option>
        </select>
      </label>
      <div v-if="selectedMarketplaceName" class="plugin-browser">
        <div class="plugin-search"><input v-model="pluginQuery" type="search" aria-label="搜索市场插件" placeholder="搜索插件名称或描述"/><span>共已选 {{ selectedPlugins.length }}</span></div>
        <div v-if="pluginsLoading" class="plugin-empty">正在读取本地市场…</div>
        <div v-else-if="!filteredPlugins.length" class="plugin-empty">该市场未发现可安装插件，请先在 Claude Code 配置中刷新市场。</div>
        <div v-else class="plugin-grid">
          <label v-for="plugin in filteredPlugins" :key="plugin.key" class="plugin-card">
            <input v-model="selectedPlugins" type="checkbox" :value="plugin.key" />
            <span><strong>{{ plugin.name }}</strong><small>{{ plugin.description || '暂无描述' }}</small><code>{{ plugin.key }}</code></span>
          </label>
        </div>
      </div>
      <p v-else-if="!marketplaces.length" class="plugin-empty">尚未配置本地市场，请先前往“Claude Code 配置”添加市场。</p>
      <p v-if="preservedLocalPlugins.length" class="preserved-note">该模板还保留 {{ preservedLocalPlugins.length }} 个随 Agent 提供的本地插件。</p>
    </section>

    <section class="form-section">
      <div class="section-heading"><div><h3>MCP Server（可多选）</h3><p>从 MCP 市场选择，加载 Agent 时自动写入项目 .mcp.json。</p></div></div>
      <div class="plugin-search"><input v-model="mcpQuery" type="search" aria-label="搜索 MCP Server" placeholder="搜索名称、描述、作者或标签"/><span>共已选 {{ selectedMcpIds.length }}</span></div>
      <div v-if="marketLoading" class="plugin-empty">正在读取 MCP 市场…</div>
      <div v-else-if="!mcpEntries.length" class="plugin-empty">MCP 市场暂无已上架条目，请先前往「MCP 市场」新增。</div>
      <div v-else-if="!filteredMcpEntries.length" class="plugin-empty">没有匹配的 MCP Server。</div>
      <div v-else class="plugin-grid">
        <label v-for="entry in filteredMcpEntries" :key="entry.id" class="plugin-card">
          <input v-model="selectedMcpIds" type="checkbox" :value="entry.id" />
          <span><strong>{{ entry.logo_emoji }} {{ entry.display_name }}</strong><small>{{ entry.description || '暂无描述' }}</small><code>{{ entry.name }} · {{ entry.transport }}</code></span>
        </label>
      </div>
      <p v-if="missingMcpCount" class="missing-note">已选的 {{ missingMcpCount }} 个 MCP Server 当前不在市场列表中（可能已删除），保存后将继续保留其配置。</p>
    </section>

    <section class="form-section">
      <div class="section-heading"><div><h3>Skill（可多选）</h3><p>从 Skill 市场选择，加载 Agent 时自动写入项目 .claude/skills/。</p></div></div>
      <div class="plugin-search"><input v-model="skillQuery" type="search" aria-label="搜索 Skill" placeholder="搜索名称、描述、作者或标签"/><span>共已选 {{ selectedSkillIds.length }}</span></div>
      <div v-if="marketLoading" class="plugin-empty">正在读取 Skill 市场…</div>
      <div v-else-if="!skillEntries.length" class="plugin-empty">Skill 市场暂无已上架条目，请先前往「Skill 市场」新增。</div>
      <div v-else-if="!filteredSkillEntries.length" class="plugin-empty">没有匹配的 Skill。</div>
      <div v-else class="plugin-grid">
        <label v-for="entry in filteredSkillEntries" :key="entry.id" class="plugin-card">
          <input v-model="selectedSkillIds" type="checkbox" :value="entry.id" />
          <span><strong>{{ entry.logo_emoji }} {{ entry.display_name }}</strong><small>{{ entry.description || '暂无描述' }}</small><code>{{ entry.name }}</code></span>
        </label>
      </div>
      <p v-if="missingSkillCount" class="missing-note">已选的 {{ missingSkillCount }} 个 Skill 当前不在市场列表中（可能已删除），保存后将继续保留其配置。</p>
    </section>

    <footer class="form-actions"><span v-if="isDirty" class="dirty-hint">有未保存的修改</span><button class="glass-btn" type="button" @click="requestCancel">取消</button><button class="glass-btn primary" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存模板' }}</button></footer>
  </form>
</template>

<style scoped>
.agent-form { max-width: 960px; margin: 0 auto; }
.form-header, .section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.form-header { margin-bottom: 20px; }
.eyebrow { color: var(--accent); font-size: 9px; font-weight: 700; letter-spacing: .14em; }
.form-header h2 { margin: 4px 0 0; font-size: 22px; }
.form-section { margin-bottom: 14px; padding: 20px; border: 1px solid var(--border-subtle); border-radius: 12px; background: var(--glass-bg); }
.form-section h3 { margin: 0 0 16px; font-size: 14px; }
.section-heading h3 { margin-bottom: 4px; }.section-heading p { margin: 0 0 16px; color: var(--text-muted); font-size: 12px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
label { display: flex; flex-direction: column; gap: 6px; margin-bottom: 13px; color: var(--text-secondary); font-size: 11px; }
input, textarea, select { width: 100%; padding: 9px 11px; border: 1px solid var(--border-subtle); border-radius: 8px; outline: 0; background: var(--layer-base); color: var(--text-primary); font: inherit; font-size: 13px; }
textarea { resize: vertical; line-height: 1.5; } input:focus, textarea:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
.compact-fields { display: flex; gap: 14px; }.color-input { width: 48px; height: 37px; padding: 3px; }
.form-error { margin-bottom: 14px; padding: 10px 12px; border-radius: 8px; background: var(--red-dim); color: var(--red); font-size: 12px; }
.plugin-browser { margin-top: 12px; }.plugin-search { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }.plugin-search span { flex: 0 0 auto; color: var(--text-muted); font-size: 11px; }
.plugin-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 8px; max-height: 320px; overflow-y: auto; }
.plugin-card { display: flex; flex-direction: row; align-items: flex-start; gap: 9px; margin: 0; padding: 11px; border: 1px solid var(--border-subtle); border-radius: 8px; cursor: pointer; }.plugin-card:has(input:checked) { border-color: var(--accent); background: var(--accent-dim); }.plugin-card input { width: auto; margin-top: 2px; box-shadow: none; }.plugin-card span { display: flex; min-width: 0; flex-direction: column; gap: 4px; }.plugin-card strong { color: var(--text-primary); font-size: 12px; }.plugin-card small { color: var(--text-muted); line-height: 1.35; }.plugin-card code { overflow: hidden; color: var(--text-muted); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.plugin-empty { padding: 24px; border: 1px dashed var(--border-subtle); border-radius: 8px; color: var(--text-muted); font-size: 12px; text-align: center; }
.missing-note { margin: 10px 0 0; color: var(--text-muted); font-size: 12px; }
.preserved-note { margin: 10px 0 0; color: var(--text-muted); font-size: 11px; }
.form-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding-top: 6px; }
.dirty-hint { margin-right: auto; color: var(--text-muted); font-size: 11px; }
@media (max-width: 700px) { .form-grid { grid-template-columns: 1fr; }.plugin-grid { grid-template-columns: 1fr; } }
@media (max-width: 700px) { input, textarea, select { font-size: 16px; }.form-section { padding: 16px; }.form-header { align-items: stretch; flex-direction: column; }.form-actions { position: sticky; bottom: 0; z-index: 2; margin: 0 -14px -20px; padding: 12px 14px; border-top: 1px solid var(--border-subtle); background: var(--layer-workspace); } }
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
</style>
