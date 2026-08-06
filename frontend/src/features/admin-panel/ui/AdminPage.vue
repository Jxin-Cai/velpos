<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { currentUser } from '@shared/lib/authStore'
import AppLogo from '@shared/ui/AppLogo.vue'
import ThemeSwitcher from '@shared/ui/ThemeSwitcher.vue'
import UserIdentity from '@shared/ui/UserIdentity.vue'
import { SettingsDialog } from '@features/settings-manager'
import { GitManagerDialog } from '@features/git-manager'
import AgentTemplateTab from './AgentTemplateTab.vue'
import ClaudeMarketplacePanel from './ClaudeMarketplacePanel.vue'
import UserManagementTab from './UserManagementTab.vue'

const emit = defineEmits(['close', 'logout', 'dirty-change'])

const sections = [
  {
    label: '管理',
    items: [
      { key: 'agents', label: 'Agent 模板', icon: 'bot' },
    ],
  },
  {
    label: '开发工具',
    items: [
      { key: 'claude-code', label: 'Claude Code 配置', icon: 'terminal' },
      { key: 'git', label: 'Git 配置', icon: 'git' },
    ],
  },
  {
    label: '权限',
    items: [{ key: 'users', label: '用户管理', icon: 'users' }],
  },
]

const validPages = new Set(sections.flatMap(section => section.items).map(item => item.key))
const requestedPage = new URLSearchParams(window.location.search).get('adminPage')
const activePage = ref(validPages.has(requestedPage) ? requestedPage : 'agents')
const visitedPages = reactive(new Set([activePage.value]))
const mainRef = ref(null)
const agentFormDirty = ref(false)
const claudeSettingsDirty = ref(false)
const marketplaceDirty = ref(false)
const gitDirty = ref(false)
const hasUnsavedChanges = computed(() => agentFormDirty.value || claudeSettingsDirty.value || marketplaceDirty.value || gitDirty.value)
const pageTitle = computed(() => sections.flatMap(section => section.items).find(item => item.key === activePage.value)?.label || '')
const previousDocumentTitle = document.title

function canLeaveCurrentPage() {
  return !hasUnsavedChanges.value || confirm('管理后台中有尚未保存的配置，确定离开并丢弃修改吗？')
}

function selectPage(page, { history = true } = {}) {
  if (!validPages.has(page) || page === activePage.value) return
  activePage.value = page
  visitedPages.add(page)
  if (history) {
    const url = new URL(window.location.href)
    url.searchParams.set('surface', 'admin')
    url.searchParams.set('adminPage', page)
    window.history.pushState({}, '', url)
  }
  nextTick(() => mainRef.value?.focus({ preventScroll: true }))
}

function handleClose() {
  if (canLeaveCurrentPage()) emit('close')
}

function handleLogout() {
  if (canLeaveCurrentPage()) emit('logout')
}

function handlePopState() {
  const page = new URLSearchParams(window.location.search).get('adminPage')
  const normalizedPage = validPages.has(page) ? page : 'agents'
  selectPage(normalizedPage, { history: false })
}

function handleBeforeUnload(event) {
  if (!hasUnsavedChanges.value) return
  event.preventDefault()
}

onMounted(() => {
  window.addEventListener('popstate', handlePopState)
  window.addEventListener('beforeunload', handleBeforeUnload)
  if (!validPages.has(requestedPage)) {
    const url = new URL(window.location.href)
    url.searchParams.set('adminPage', activePage.value)
    window.history.replaceState({}, '', url)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('popstate', handlePopState)
  window.removeEventListener('beforeunload', handleBeforeUnload)
  document.title = previousDocumentTitle
})
watch(hasUnsavedChanges, value => emit('dirty-change', value), { immediate: true })
watch(pageTitle, value => { document.title = `${value} · Velpos 管理后台` }, { immediate: true })
</script>

<template>
  <div class="admin-app">
    <header class="admin-topbar">
      <div class="brand-area">
        <AppLogo prefix="admin" />
        <span class="surface-badge">管理后台</span>
      </div>
      <div class="topbar-actions">
        <button class="front-switch" type="button" @click="handleClose">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/>
          </svg>
          返回工作台
        </button>
        <ThemeSwitcher />
        <UserIdentity :user="currentUser" @logout="handleLogout" />
      </div>
    </header>

    <div class="admin-shell">
      <aside class="admin-sidebar" aria-label="后台配置导航">
        <div class="sidebar-heading">
          <span>ADMIN</span>
          <strong>配置中心</strong>
        </div>
        <nav>
          <section v-for="section in sections" :key="section.label" class="nav-section">
            <h2>{{ section.label }}</h2>
            <button
              v-for="item in section.items"
              :key="item.key"
              class="nav-item"
              :class="{ active: activePage === item.key }"
              type="button"
              :aria-current="activePage === item.key ? 'page' : undefined"
              :aria-label="item.label"
              :title="item.label"
              @click="selectPage(item.key)"
            >
              <svg v-if="item.icon === 'bot'" viewBox="0 0 24 24"><rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8"/></svg>
              <svg v-else-if="item.icon === 'terminal'" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/></svg>
              <svg v-else-if="item.icon === 'git'" viewBox="0 0 24 24"><circle cx="6" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><circle cx="6" cy="18" r="2"/><path d="M6 8v8M8 6h4a6 6 0 0 1 6 6v4"/></svg>
              <svg v-else viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
              <span>{{ item.label }}</span>
              <i
                v-if="(item.key === 'agents' && agentFormDirty) || (item.key === 'claude-code' && (claudeSettingsDirty || marketplaceDirty)) || (item.key === 'git' && gitDirty)"
                class="unsaved-dot"
                aria-label="有未保存修改"
              ></i>
            </button>
          </section>
        </nav>
        <div class="sidebar-footer">仅管理员可访问</div>
      </aside>

      <main ref="mainRef" class="admin-content" tabindex="-1">
        <div class="page-context">
          <span>管理后台 / {{ pageTitle }}</span>
        </div>
        <AgentTemplateTab v-if="visitedPages.has('agents')" v-show="activePage === 'agents'" @dirty-change="agentFormDirty = $event" />
        <div v-if="visitedPages.has('claude-code')" v-show="activePage === 'claude-code'" class="stacked-pages">
          <SettingsDialog :visible="true" embedded @dirty-change="claudeSettingsDirty = $event" />
          <ClaudeMarketplacePanel @dirty-change="marketplaceDirty = $event" />
        </div>
        <div v-if="visitedPages.has('git')" v-show="activePage === 'git'">
          <GitManagerDialog :visible="true" embedded @dirty-change="gitDirty = $event" />
        </div>
        <UserManagementTab v-if="visitedPages.has('users')" v-show="activePage === 'users'" />
      </main>
    </div>
  </div>
</template>

<style scoped>
.admin-app { display: flex; flex-direction: column; width: 100%; height: 100vh; background: var(--layer-workspace); color: var(--text-primary); }
.admin-topbar { display: flex; align-items: center; justify-content: space-between; min-height: 58px; padding: 0 22px; border-bottom: 1px solid var(--border-subtle); background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)); }
.brand-area, .topbar-actions { display: flex; align-items: center; gap: 12px; }
.surface-badge { padding: 3px 8px; border: 1px solid var(--border-subtle); border-radius: 6px; color: var(--text-secondary); font-size: 11px; font-weight: 600; }
.front-switch { display: flex; align-items: center; min-height: 36px; gap: 7px; padding: 7px 10px; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: transparent; color: var(--text-secondary); font: inherit; font-size: 12px; cursor: pointer; }
.front-switch:hover, .front-switch:focus-visible { border-color: var(--border); background: var(--layer-active); color: var(--text-primary); outline: none; }
.admin-shell { display: flex; min-height: 0; flex: 1; }
.admin-sidebar { display: flex; flex: 0 0 238px; flex-direction: column; padding: 22px 14px 16px; border-right: 1px solid var(--border-subtle); background: color-mix(in srgb, var(--layer-base) 82%, transparent); }
.sidebar-heading { display: flex; flex-direction: column; gap: 3px; padding: 0 10px 18px; }
.sidebar-heading span { color: var(--accent); font-size: 9px; font-weight: 700; letter-spacing: .16em; }
.sidebar-heading strong { font-size: 16px; }
.nav-section { margin-bottom: 20px; }
.nav-section h2 { margin: 0 10px 7px; color: var(--text-muted); font-size: 10px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.nav-item { display: flex; align-items: center; width: 100%; min-height: 44px; gap: 10px; padding: 9px 10px; border: 0; border-radius: 8px; background: transparent; color: var(--text-secondary); font: inherit; font-size: 13px; text-align: left; cursor: pointer; transition: background .18s, color .18s; }
.nav-item svg { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.nav-item:hover { background: var(--layer-hover); color: var(--text-primary); }
.nav-item:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.nav-item.active { background: var(--accent-dim); color: var(--accent); font-weight: 600; }
.unsaved-dot { width: 6px; height: 6px; margin-left: auto; border-radius: 50%; background: var(--orange, #f59e0b); }
.sidebar-footer { margin-top: auto; padding: 12px 10px 0; border-top: 1px solid var(--border-subtle); color: var(--text-muted); font-size: 10px; }
.admin-content { min-width: 0; flex: 1; overflow-y: auto; padding: 18px clamp(20px, 4vw, 58px) 56px; }
.admin-content:focus { outline: none; }
.page-context { max-width: 1080px; margin: 0 auto 18px; color: var(--text-muted); font-size: 11px; }
.stacked-pages { display: flex; max-width: 1080px; margin: 0 auto; flex-direction: column; gap: 28px; }
@media (max-width: 720px) { .admin-sidebar { flex-basis: 64px; padding-inline: 8px; } .sidebar-heading strong, .nav-section h2, .nav-item span, .sidebar-footer { display: none; } .sidebar-heading { align-items: center; padding-inline: 0; } .nav-item { justify-content: center; } .front-switch { min-width: 44px; min-height: 44px; justify-content:center; font-size: 0; } .admin-topbar { padding-inline: 10px; } .surface-badge { display:none; } .admin-content { padding-inline:14px; } }
@media (prefers-reduced-motion: reduce) { .nav-item, .front-switch { transition: none; } }
</style>
