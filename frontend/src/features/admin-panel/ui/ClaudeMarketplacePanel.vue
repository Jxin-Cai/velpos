<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useTimeout } from '@shared/lib/useTimeout'
import {
  addClaudeMarketplace,
  listClaudeMarketplaces,
  refreshClaudeMarketplace,
  removeClaudeMarketplace,
} from '../api/adminAgentApi'

const marketplaces = ref([])
const loading = ref(false)
const operating = ref('')
const showForm = ref(false)
const source = ref('')
const token = ref('')
const error = ref('')
const success = ref('')
const refreshTokens = reactive({})
const { set: setTimer } = useTimeout()
const emit = defineEmits(['dirty-change'])
const isDirty = computed(() => Boolean(
  (showForm.value && (source.value || token.value))
  || Object.values(refreshTokens).some(Boolean),
))
watch(isDirty, value => emit('dirty-change', value), { immediate: true })

function showSuccess(message) {
  success.value = message
  setTimer(() => { success.value = '' }, 2200)
}

function toggleForm() {
  if (showForm.value) {
    if ((source.value || token.value) && !confirm('市场信息尚未提交，确定取消吗？')) return
    source.value = ''
    token.value = ''
  }
  showForm.value = !showForm.value
}

async function loadMarketplaces(showLoading = true) {
  if (showLoading) loading.value = true
  error.value = ''
  try {
    marketplaces.value = (await listClaudeMarketplaces()).sort((left, right) => left.name.localeCompare(right.name))
  } catch (err) {
    error.value = err.message || '市场加载失败'
  } finally {
    if (showLoading) loading.value = false
  }
}

async function handleAdd() {
  if (!source.value.trim()) return
  operating.value = 'add'
  error.value = ''
  try {
    await addClaudeMarketplace(source.value.trim(), token.value.trim())
    source.value = ''
    token.value = ''
    showForm.value = false
    await loadMarketplaces(false)
    showSuccess('插件市场已添加并完成首次加载')
  } catch (err) {
    error.value = err.message || '添加市场失败'
  } finally {
    operating.value = ''
  }
}

async function handleRefresh(marketplace) {
  operating.value = marketplace.name
  error.value = ''
  try {
    await refreshClaudeMarketplace(marketplace.name, refreshTokens[marketplace.name] || '')
    refreshTokens[marketplace.name] = ''
    await loadMarketplaces(false)
    showSuccess(`已刷新市场「${marketplace.name}」`)
  } catch (err) {
    error.value = err.message || '刷新市场失败'
  } finally {
    operating.value = ''
  }
}

async function handleRemove(marketplace) {
  if (!confirm(`确认移除市场「${marketplace.name}」？`)) return
  operating.value = marketplace.name
  try {
    await removeClaudeMarketplace(marketplace.name)
    delete refreshTokens[marketplace.name]
    await loadMarketplaces(false)
    showSuccess(`已移除市场「${marketplace.name}」`)
  } catch (err) {
    error.value = err.message || '移除市场失败'
  } finally {
    operating.value = ''
  }
}

onMounted(loadMarketplaces)
</script>

<template>
  <section class="market-section">
    <div class="market-header">
      <div>
        <p class="eyebrow">PLUGIN MARKETPLACES</p>
        <h2>Claude Code 插件市场</h2>
        <p>读取本机 Claude Code 已配置的市场。Token 仅用于本次拉取，不会返回到前端。</p>
      </div>
      <button class="glass-btn primary" type="button" :aria-expanded="showForm" aria-controls="marketplace-add-form" @click="toggleForm">
        {{ showForm ? '取消' : '添加市场' }}
      </button>
    </div>

    <div v-if="error" class="notice error" role="alert"><span>{{ error }}</span><button class="glass-btn sm" type="button" @click="loadMarketplaces">重试</button></div>
    <div v-if="success" class="notice success" role="status">{{ success }}</div>

    <form v-if="showForm" id="marketplace-add-form" class="market-form" @submit.prevent="handleAdd">
      <label>
        <span>市场地址 / Host</span>
        <input v-model.trim="source" required autofocus autocomplete="off" placeholder="owner/repository 或 https://git.example.com/group/repo.git" />
      </label>
      <label>
        <span>访问 Token（可选）</span>
        <input v-model.trim="token" type="password" autocomplete="off" placeholder="用于私有市场拉取" />
      </label>
      <button class="glass-btn primary" type="submit" :disabled="Boolean(operating) || !source">
        {{ operating === 'add' ? '添加中…' : '添加并加载' }}
      </button>
    </form>

    <div v-if="loading" class="empty">正在读取本地 Claude Code 市场…</div>
    <div v-else-if="!marketplaces.length" class="empty">暂无插件市场，请先添加市场。</div>
    <div v-else class="market-grid">
      <article v-for="marketplace in marketplaces" :key="marketplace.name" class="market-card">
        <div class="market-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 9h18l-1-5H4L3 9Z"/><path d="M5 9v11h14V9"/><path d="M9 20v-6h6v6"/></svg>
        </div>
        <div class="market-info">
          <strong>{{ marketplace.name }}</strong>
          <span>{{ marketplace.source || '本地市场' }}</span>
        </div>
        <input
          v-model.trim="refreshTokens[marketplace.name]"
          class="refresh-token"
          type="password"
          autocomplete="off"
          aria-label="刷新市场使用的访问 Token"
          placeholder="刷新 Token（私有市场可选）"
        />
        <div class="market-actions">
          <button class="glass-btn sm" type="button" :disabled="Boolean(operating)" @click="handleRefresh(marketplace)">{{ operating === marketplace.name ? '刷新中…' : '刷新' }}</button>
          <button class="glass-btn sm danger" type="button" :disabled="Boolean(operating)" @click="handleRemove(marketplace)">移除</button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.market-section { padding: 24px; border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); background: var(--glass-bg); }
.market-header { display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:20px; }
.eyebrow { margin:0 0 6px; color:var(--accent); font-size:10px; font-weight:700; letter-spacing:.14em; }
h2 { margin:0; color:var(--text-primary); font-size:18px; }
.market-header p:last-child { margin:6px 0 0; color:var(--text-muted); font-size:13px; }
.market-form { display:grid; grid-template-columns:minmax(220px,1fr) minmax(220px,1fr) auto; gap:12px; align-items:end; padding:16px; margin-bottom:16px; border:1px solid var(--border); border-radius:var(--radius-md); background:var(--layer-base); }
label { display:flex; flex-direction:column; gap:6px; color:var(--text-secondary); font-size:12px; }
input { min-height:40px; padding:0 12px; border:1px solid var(--border); border-radius:var(--radius-md); background:var(--layer-workspace); color:var(--text-primary); }
input:focus-visible { border-color:var(--accent); outline:2px solid var(--accent-dim); outline-offset:1px; }
.market-grid { display:grid; gap:10px; }
.market-card { display:grid; grid-template-columns:40px minmax(0,1fr) minmax(180px, .7fr) auto; align-items:center; gap:12px; padding:14px; border:1px solid var(--border-subtle); border-radius:var(--radius-md); background:var(--layer-base); }
.market-icon { display:grid; place-items:center; width:40px; height:40px; border-radius:10px; color:var(--accent); background:var(--accent-dim); }
.market-icon svg { width:20px; height:20px; }
.market-info { display:flex; flex-direction:column; min-width:0; gap:4px; }
.market-info strong { color:var(--text-primary); font-size:13px; }
.market-info span { overflow:hidden; text-overflow:ellipsis; color:var(--text-muted); font-size:12px; white-space:nowrap; }
.market-actions { display:flex; gap:8px; }
.refresh-token { min-width:0; }
.empty { padding:30px; text-align:center; color:var(--text-muted); border:1px dashed var(--border); border-radius:var(--radius-md); }
.notice { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:12px; padding:10px 12px; border-radius:var(--radius-md); font-size:13px; }.notice.error { color:var(--red); background:var(--red-dim); }.notice.success { color:var(--green); background:var(--green-dim); }
@media (max-width: 900px) { .market-form { grid-template-columns:1fr; } .market-header { flex-direction:column; } .market-card { grid-template-columns:40px 1fr; } .refresh-token, .market-actions { grid-column:1 / -1; width:100%; } .market-actions .glass-btn { min-height:44px; flex:1; } input { font-size:16px; } }
</style>
