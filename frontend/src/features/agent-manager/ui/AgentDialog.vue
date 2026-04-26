<script setup>
import { ref, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { useAgentManager } from '../model/useAgentManager'

const props = defineProps({
  visible: { type: Boolean, required: true },
  projectId: { type: String, default: '' },
  currentAgent: { type: Object, default: null },
  sessionId: { type: String, default: '' },
})

const emit = defineEmits(['close', 'update:project'])

const {
  categories,
  loading,
  operating,
  error,
  language,
  fetchAgents,
  handleLoad,
  handleUnload,
  setLanguage,
} = useAgentManager()

const activeAgentId = computed(() => props.currentAgent?.id || null)
const loadingAgentId = ref(null)

watch(() => props.visible, (val) => {
  if (val) {
    loadingAgentId.value = null
    fetchAgents()
  }
})

async function onSelect(agentId) {
  if (!props.projectId || operating.value) return
  // If clicking the active agent, unload it
  if (agentId === activeAgentId.value) {
    loadingAgentId.value = agentId
    const project = await handleUnload(props.projectId, props.sessionId)
    loadingAgentId.value = null
    if (project) emit('update:project', project)
    return
  }
  loadingAgentId.value = agentId
  const project = await handleLoad(props.projectId, agentId, props.sessionId)
  loadingAgentId.value = null
  if (project) {
    emit('update:project', project)
    handleClose()
  }
}

async function onUnload() {
  if (!props.projectId || operating.value) return
  loadingAgentId.value = activeAgentId.value
  const project = await handleUnload(props.projectId, props.sessionId)
  loadingAgentId.value = null
  if (project) {
    emit('update:project', project)
    handleClose()
  }
}

function handleClose() {
  emit('close')
}

function handleOverlayClick(e) {
  if (e.target === e.currentTarget) handleClose()
}

function handleKeydown(e) {
  if (!props.visible) return
  if (e.key === 'Escape') handleClose()
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
    <div
      v-if="visible"
      class="dialog-overlay"
      @click="handleOverlayClick"
      role="dialog"
      aria-modal="true"
      aria-label="Agent Manager"
    >
      <div class="dialog">
        <div class="dialog-header">
          <h2 class="dialog-title">Agent</h2>
          <div class="header-actions">
            <div class="lang-toggle">
              <button
                class="lang-btn"
                :class="{ active: language === 'zh' }"
                @click="setLanguage('zh')"
              >CN</button>
              <button
                class="lang-btn"
                :class="{ active: language === 'en' }"
                @click="setLanguage('en')"
              >EN</button>
            </div>
            <button class="close-btn" @click="handleClose">&times;</button>
          </div>
        </div>

        <!-- Active agent banner -->
        <div v-if="activeAgentId" class="active-banner">
          <span class="active-label">{{ language === 'zh' ? '当前 Agent' : 'Active' }}:</span>
          <span class="active-name">{{ activeAgentId }}</span>
          <button class="unload-btn" @click="onUnload" :disabled="operating">
            {{ operating ? '...' : (language === 'zh' ? '卸载' : 'Unload') }}
          </button>
        </div>

        <div v-if="error" class="error-banner">{{ error }}</div>

        <div v-if="loading" class="agent-skeleton">
          <div v-for="g in 2" :key="g" class="skel-group">
            <div class="skel-category-bar"></div>
            <div v-for="i in 3" :key="i" class="skel-agent-row">
              <div class="skel-emoji"></div>
              <div class="skel-text-group">
                <div class="skel-name"></div>
                <div class="skel-desc"></div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="agent-list">
          <div v-for="cat in categories" :key="cat.id" class="category-section">
            <div class="category-header">{{ cat.name }}</div>
            <div class="agent-grid">
              <button
                v-for="agent in cat.agents"
                :key="agent.id"
                class="agent-card"
                :class="{
                  'agent-card--active': agent.id === activeAgentId,
                  'agent-card--loading': loadingAgentId === agent.id,
                }"
                @click="onSelect(agent.id)"
                :disabled="operating"
              >
                <span class="agent-emoji">{{ agent.emoji }}</span>
                <div class="agent-info">
                  <span class="agent-name">
                    {{ agent.name }}
                    <span v-if="agent.has_plugin" class="plugin-badge" :title="language === 'zh' ? '含插件' : 'Has plugin'">P</span>
                  </span>
                  <span class="agent-desc">{{ agent.description }}</span>
                </div>
                <span v-if="loadingAgentId === agent.id" class="agent-spinner"></span>
                <span v-else-if="agent.id === activeAgentId" class="active-dot"></span>
              </button>
            </div>
          </div>
        </div>

        <div class="dialog-footer">
          <span class="footer-hint">
            {{ language === 'zh'
              ? '选择 Agent 后，其提示词将通过 CLAUDE.md 版本自动应用'
              : 'Agent prompt will be applied through CLAUDE.md versions'
            }}
          </span>
        </div>
      </div>
    </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-overlay);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
}

.dialog {
  width: 640px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  display: flex;
  flex-direction: column;
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.dialog-title {
  font-weight: 600;
  font-size: 16px;
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.lang-toggle {
  display: flex;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.lang-btn {
  padding: 3px 10px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.lang-btn.active {
  background: var(--accent);
  color: var(--bg-primary);
}

.lang-btn:hover:not(.active) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.close-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 20px;
  cursor: pointer;
  transition: all 0.15s;
}

.close-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.active-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  background: var(--accent-dim);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.active-label {
  font-size: 12px;
  color: var(--text-muted);
}

.active-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
}

.unload-btn {
  margin-left: auto;
  padding: 3px 10px;
  border: 1px solid var(--red);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--red);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}

.unload-btn:hover:not(:disabled) {
  background: var(--red-dim);
}

.unload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-banner {
  padding: 8px 20px;
  background: var(--red-dim);
  color: var(--red);
  font-size: 13px;
  flex-shrink: 0;
}

.agent-skeleton {
  flex: 1;
  overflow: hidden;
  padding: 8px 16px;
}

.skel-group {
  margin-bottom: 16px;
}

.skel-category-bar {
  width: 80px;
  height: 10px;
  background: var(--bg-hover);
  border-radius: 4px;
  margin: 8px 4px 8px;
  animation: skel-pulse 1.5s ease-in-out infinite;
}

.skel-agent-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
}

.skel-emoji {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  flex-shrink: 0;
  animation: skel-pulse 1.5s ease-in-out infinite;
}

.skel-text-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skel-name {
  width: 120px;
  height: 12px;
  background: var(--bg-hover);
  border-radius: 4px;
  animation: skel-pulse 1.5s ease-in-out infinite;
}

.skel-desc {
  width: 200px;
  height: 10px;
  background: var(--bg-hover);
  border-radius: 4px;
  animation: skel-pulse 1.5s ease-in-out infinite;
  animation-delay: 0.1s;
}

@keyframes skel-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.8; }
}

.agent-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 16px;
}

.category-section {
  margin-bottom: 12px;
}

.category-header {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  padding: 8px 4px 4px;
}

.agent-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
  position: relative;
}

.agent-card:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border);
}

.agent-card--active {
  background: var(--accent-dim);
  border-color: var(--accent);
}

.agent-card--active:hover:not(:disabled) {
  background: var(--accent-dim);
  border-color: var(--accent);
}

.agent-card--loading {
  border-color: var(--accent);
  background: var(--accent-dim);
}

.agent-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  flex-shrink: 0;
  animation: agent-spin 0.6s linear infinite;
}

@keyframes agent-spin {
  to { transform: rotate(360deg); }
}

.agent-card:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.agent-emoji {
  font-size: 20px;
  flex-shrink: 0;
  width: 28px;
  text-align: center;
}

.agent-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.plugin-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  font-size: 9px;
  font-weight: 700;
  border-radius: 3px;
  background: var(--accent-dim);
  color: var(--accent);
  flex-shrink: 0;
}

.agent-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.active-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
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

</style>
