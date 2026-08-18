<script setup>
import { ref, computed, watch } from 'vue'
import { usePluginManager } from '../model/usePluginManager'
import { useEscapeToClose } from '@shared/lib/useDialogManager'
import { formatRelativeTime } from '@shared/lib/formatTime'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
  projectDir: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['close'])

useEscapeToClose(() => props.visible, () => emit('close'))

const {
  plugins,
  marketplaces,
  loading,
  marketplacesLoading,
  operating,
  error,
  loadPlugins,
  loadMarketplaces,
  handleInstall,
  handleUninstall,
  handleUpgradePlugin,
  handleUpgradeAllPlugins,
  handleUpdateMarketplace,
  handleRemoveMarketplace,
} = usePluginManager()

const activeTab = ref('plugins')
const searchQuery = ref('')

const filteredPlugins = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  const matched = q
    ? plugins.value.filter(p =>
      p.name.toLowerCase().includes(q) ||
      (p.description && p.description.toLowerCase().includes(q)) ||
      p.marketplace.toLowerCase().includes(q)
    )
    : plugins.value

  return matched
    .map((plugin, index) => ({ plugin, index }))
    .sort((a, b) => {
      const scopeRank = Number(b.plugin.scope === 'project') - Number(a.plugin.scope === 'project')
      return scopeRank || a.index - b.index
    })
    .map(item => item.plugin)
})

watch(() => props.visible, (val) => {
  if (val) {
    activeTab.value = 'plugins'
    if (props.projectDir) {
      loadPlugins(props.projectDir)
    }
  }
})

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'marketplaces' && !marketplaces.value.length && !marketplacesLoading.value) {
    loadMarketplaces()
  }
}

function onInstall(pluginKey) {
  handleInstall(pluginKey, props.projectDir)
}

function onUninstall(pluginKey) {
  handleUninstall(pluginKey, props.projectDir)
}

function onUpgrade(pluginKey) {
  handleUpgradePlugin(pluginKey, props.projectDir)
}

function onUpgradeAll() {
  handleUpgradeAllPlugins(props.projectDir)
}

function onUpdateMarketplace(name) {
  handleUpdateMarketplace(name)
}

function onRemoveMarketplace(name) {
  handleRemoveMarketplace(name)
}

function onRefresh() {
  if (activeTab.value === 'plugins') {
    loadPlugins(props.projectDir)
  } else {
    loadMarketplaces()
  }
}

function handleClose() {
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
    <div
      v-if="visible"
      class="dialog-overlay"
      @click.self="handleClose"
      role="dialog"
      aria-modal="true"
      aria-labelledby="plugin-dialog-title"
    >
      <div class="dialog">
        <div class="dialog-header">
          <h2 id="plugin-dialog-title" class="dialog-title">Plugin Manager</h2>
          <div class="header-actions">
            <button
              class="header-btn"
              type="button"
              aria-label="Refresh"
              title="Refresh"
              @click="onRefresh"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="1 4 1 10 7 10"/><polyline points="23 20 23 14 17 14"/>
                <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
              </svg>
            </button>
            <button class="close-btn" type="button" aria-label="Close Plugin Manager" @click="handleClose">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" /></svg>
            </button>
          </div>
        </div>

        <!-- Tab bar -->
        <div class="tab-bar">
          <button
            class="tab-btn"
            :class="{ 'tab-btn--active': activeTab === 'plugins' }"
            @click="switchTab('plugins')"
          >Plugins</button>
          <button
            class="tab-btn"
            :class="{ 'tab-btn--active': activeTab === 'marketplaces' }"
            @click="switchTab('marketplaces')"
          >Marketplaces</button>
        </div>

        <div v-if="error" class="error-banner">
          {{ error }}
        </div>

        <!-- Plugins Tab -->
        <template v-if="activeTab === 'plugins'">
          <div class="search-bar">
            <input
              v-model="searchQuery"
              type="text"
              class="search-input"
              placeholder="Search plugins..."
            />
          </div>

          <div v-if="loading" class="loading-state">
            <div class="spinner"></div>
            <span>Loading plugins...</span>
          </div>

          <div v-else-if="filteredPlugins.length === 0" class="empty-state">
            {{ searchQuery.trim() ? 'No matching plugins' : 'No plugins available' }}
          </div>

          <div v-else class="plugin-list">
            <div
              v-for="plugin in filteredPlugins"
              :key="plugin.key"
              class="plugin-item"
            >
              <div class="plugin-info">
                <div class="plugin-name-row">
                  <span class="plugin-name">{{ plugin.name }}</span>
                  <span class="plugin-marketplace">@{{ plugin.marketplace }}</span>
                  <span v-if="plugin.version" class="plugin-version">v{{ plugin.version }}</span>
                  <span
                    v-if="plugin.scope === 'user'"
                    class="scope-badge scope-user"
                  >global</span>
                  <span
                    v-else-if="plugin.scope === 'project'"
                    class="scope-badge scope-project"
                  >project</span>
                </div>
                <div v-if="plugin.description" class="plugin-desc">
                  {{ plugin.description }}
                </div>
                <div v-if="plugin.updated_at" class="plugin-time">
                  Updated {{ formatRelativeTime(plugin.updated_at) }}
                </div>
              </div>
              <div class="plugin-actions">
                <template v-if="plugin.scope === 'user'">
                  <span class="status-text installed-text">Installed (Global)</span>
                </template>
                <template v-else-if="plugin.installed && plugin.scope === 'project'">
                  <button
                    class="btn-upgrade"
                    :disabled="!!operating"
                    @click="onUpgrade(plugin.key)"
                  >
                    <span v-if="operating === plugin.key" class="spinner-sm"></span>
                    {{ operating === plugin.key ? 'Upgrading...' : 'Upgrade' }}
                  </button>
                  <button
                    class="btn-uninstall"
                    :disabled="!!operating"
                    @click="onUninstall(plugin.key)"
                  >
                    <span v-if="operating === plugin.key" class="spinner-sm"></span>
                    {{ operating === plugin.key ? 'Removing...' : 'Uninstall' }}
                  </button>
                </template>
                <template v-else>
                  <button
                    class="btn-install"
                    :disabled="!!operating"
                    @click="onInstall(plugin.key)"
                  >
                    <span v-if="operating === plugin.key" class="spinner-sm"></span>
                    {{ operating === plugin.key ? 'Installing...' : 'Install' }}
                  </button>
                </template>
              </div>
            </div>
          </div>

          <!-- Upgrade All button -->
          <div v-if="plugins.some(p => p.installed && p.scope === 'project')" class="action-bar">
            <button
              class="btn-upgrade-all"
              :disabled="!!operating"
              @click="onUpgradeAll"
            >
              <span v-if="operating === '__upgrade_all__'" class="spinner-sm"></span>
              {{ operating === '__upgrade_all__' ? 'Upgrading all...' : 'Upgrade All Plugins' }}
            </button>
          </div>
        </template>

        <!-- Marketplaces Tab -->
        <template v-if="activeTab === 'marketplaces'">
          <div v-if="marketplacesLoading" class="loading-state">
            <div class="spinner"></div>
            <span>Loading marketplaces...</span>
          </div>

          <div v-else-if="marketplaces.length === 0" class="empty-state">
            No marketplaces configured
          </div>

          <div v-else class="plugin-list">
            <div
              v-for="mkt in marketplaces"
              :key="mkt.name"
              class="plugin-item"
            >
              <div class="plugin-info">
                <div class="plugin-name-row">
                  <span class="plugin-name">{{ mkt.name }}</span>
                </div>
                <div v-if="mkt.source" class="plugin-desc">
                  {{ mkt.source }}
                </div>
              </div>
              <div class="plugin-actions marketplace-actions">
                <button
                  class="btn-upgrade"
                  :disabled="!!operating"
                  @click="onUpdateMarketplace(mkt.name)"
                >
                  <span v-if="operating === mkt.name" class="spinner-sm"></span>
                  {{ operating === mkt.name ? 'Updating...' : 'Update' }}
                </button>
                <button
                  class="btn-uninstall"
                  :disabled="!!operating"
                  @click="onRemoveMarketplace(mkt.name)"
                >
                  <span v-if="operating === mkt.name" class="spinner-sm"></span>
                  {{ operating === mkt.name ? 'Removing...' : 'Remove' }}
                </button>
              </div>
            </div>
          </div>
        </template>

        <div class="dialog-footer">
          <span class="footer-hint">
            Plugins are installed at project scope for: {{ projectDir || 'N/A' }}
          </span>
        </div>
      </div>
    </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dialog {
  width: 560px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  background: var(--dialog-surface);
  border: 1px solid var(--dialog-border);
  border-radius: var(--dialog-radius);
  box-shadow: var(--dialog-shadow);
  display: flex;
  flex-direction: column;
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px;
  flex-shrink: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.header-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.tab-bar {
  display: flex;
  gap: 0;
  padding: 0 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.tab-btn {
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn--active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.error-banner {
  padding: 8px 20px;
  background: var(--red-dim);
  color: var(--red);
  font-size: 13px;
  flex-shrink: 0;
}

.search-bar {
  padding: 12px 20px 4px;
  flex-shrink: 0;
}

.search-input {
  width: 100%;
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}

.search-input::placeholder {
  color: var(--text-muted);
}

.search-input:focus {
  border-color: var(--accent);
}

.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  color: var(--text-muted);
  font-size: 14px;
}

.plugin-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.plugin-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  gap: 12px;
  transition: background 0.1s;
}

.plugin-item:hover {
  background: var(--bg-hover);
}

.plugin-info {
  flex: 1;
  min-width: 0;
}

.plugin-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.plugin-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.plugin-marketplace {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}

.plugin-version {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  padding: 1px 5px;
  background: var(--bg-tertiary);
  border-radius: 3px;
}

.scope-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 1px 6px;
  border-radius: 3px;
}

.scope-user {
  background: var(--purple-dim);
  color: var(--purple);
}

.scope-project {
  background: var(--accent-dim);
  color: var(--accent);
}

.plugin-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plugin-time {
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-muted);
  opacity: 0.7;
}

.plugin-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.marketplace-actions {
  gap: 6px;
}

.status-text {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}

.installed-text {
  color: var(--green);
}

.btn-install,
.btn-uninstall,
.btn-upgrade {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.btn-install {
  border: none;
  background: var(--accent);
  color: var(--bg-primary);
}

.btn-install:hover:not(:disabled) {
  filter: brightness(1.1);
}

.btn-upgrade {
  border: 1px solid var(--accent);
  background: transparent;
  color: var(--accent);
}

.btn-upgrade:hover:not(:disabled) {
  background: var(--accent-dim);
}

.btn-uninstall {
  border: 1px solid var(--red);
  background: transparent;
  color: var(--red);
}

.btn-uninstall:hover:not(:disabled) {
  background: var(--red-dim);
}

.btn-install:disabled,
.btn-uninstall:disabled,
.btn-upgrade:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-bar {
  padding: 8px 20px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.btn-upgrade-all {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--accent);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  justify-content: center;
  transition: all 0.15s;
}

.btn-upgrade-all:hover:not(:disabled) {
  background: var(--accent-dim);
}

.btn-upgrade-all:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.dialog-footer {
  padding: 10px 20px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.footer-hint {
  font-size: 11px;
  color: var(--text-muted);
}

.spinner {
  width: 20px;
  height: 20px;
  animation: spin 0.6s linear infinite;
}

.spinner-sm {
  width: 12px;
  height: 12px;
  border-color: currentColor;
  border-top-color: transparent;
  animation: spin 0.6s linear infinite;
}
</style>
