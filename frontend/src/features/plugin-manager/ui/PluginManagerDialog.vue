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
  loading,
  operating,
  error,
  loadPlugins,
  handleInstall,
  handleUninstall,
} = usePluginManager()

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
  if (val && props.projectDir) {
    loadPlugins(props.projectDir)
  }
})

function onInstall(pluginKey) {
  handleInstall(pluginKey, props.projectDir)
}

function onUninstall(pluginKey) {
  handleUninstall(pluginKey, props.projectDir)
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
          <button class="close-btn" type="button" aria-label="Close Plugin Manager" @click="handleClose">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" /></svg>
          </button>
        </div>

        <div v-if="error" class="error-banner">
          {{ error }}
        </div>

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
                  class="btn-uninstall"
                  :disabled="operating === plugin.key"
                  @click="onUninstall(plugin.key)"
                >
                  <span v-if="operating === plugin.key" class="spinner-sm"></span>
                  {{ operating === plugin.key ? 'Removing...' : 'Uninstall' }}
                </button>
              </template>
              <template v-else>
                <button
                  class="btn-install"
                  :disabled="operating === plugin.key"
                  @click="onInstall(plugin.key)"
                >
                  <span v-if="operating === plugin.key" class="spinner-sm"></span>
                  {{ operating === plugin.key ? 'Installing...' : 'Install' }}
                </button>
              </template>
            </div>
          </div>
        </div>

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
.btn-uninstall {
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

.btn-uninstall {
  border: 1px solid var(--red);
  background: transparent;
  color: var(--red);
}

.btn-uninstall:hover:not(:disabled) {
  background: var(--red-dim);
}

.btn-install:disabled,
.btn-uninstall:disabled {
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
