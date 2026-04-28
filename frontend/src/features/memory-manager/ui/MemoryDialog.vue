<script setup>
import { watch, computed, ref, onMounted, onUnmounted } from 'vue'
import { configuredMarked } from '@features/message-display'
import { useMemoryManager } from '../model/useMemoryManager'
import { useDialogManager } from '@shared/lib/useDialogManager'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys'

const props = defineProps({
  visible: { type: Boolean, default: false },
  projectDir: { type: String, default: '' },
})
const emit = defineEmits(['close', 'evolve'])

const { useDialog } = useDialogManager()
const visibleWrapper = {
  get value() {
    return props.visible
  },
  set value(newValue) {
    if (!newValue) emit('close')
  }
}
useDialog('memory-manager', visibleWrapper)

useGlobalHotkeys({
  keys: 'Escape',
  handler: () => {
    if (props.visible) {
      emit('close')
      return false
    }
    return true
  },
  priority: 100
})

const activeTab = ref('claude')

const {
  content, versions, selectedRevision, selectedContent, canEditSelected,
  rules, selectedRule, ruleEditing, ruleDraft,
  loading, editing, editContent, saving, applying, error, conflictMessage,
  loadClaudeMd, loadRules, selectRevision, selectRule,
  startEdit, cancelEdit, save, startRuleEdit, cancelRuleEdit,
  saveRule, removeRule,
  proposeSelected, approveSelected, rejectSelected, deleteSelectedRevision, applySelected, reset,
} = useMemoryManager()

const renderedContent = computed(() => {
  if (!selectedContent.value) return ''
  return configuredMarked(selectedContent.value)
})

const renderedPreview = computed(() => {
  if (!editContent.value) return ''
  return configuredMarked(editContent.value)
})

const renderedRuleContent = computed(() => {
  if (!selectedRule.value?.content) return ''
  return configuredMarked(selectedRule.value.content)
})

const renderedRulePreview = computed(() => {
  if (!ruleDraft.value.content) return ''
  return configuredMarked(ruleDraft.value.content)
})

const selectedState = computed(() => selectedRevision.value?.state || '')
const canPropose = computed(() => selectedState.value === 'draft')
const canApprove = computed(() => selectedState.value === 'proposed')
const canApply = computed(() => selectedState.value === 'approved')
const canReject = computed(() => ['draft', 'proposed', 'approved', 'conflicted'].includes(selectedState.value))
const canDeleteRevision = computed(() => Boolean(selectedRevision.value))

watch(() => props.visible, (v) => {
  if (v && props.projectDir) {
    loadClaudeMd(props.projectDir)
    loadRules(props.projectDir)
  } else if (!v) {
    reset()
  }
})

function handleRefresh() {
  if (props.visible && props.projectDir) {
    loadClaudeMd(props.projectDir)
    loadRules(props.projectDir)
  }
}

onMounted(() => window.addEventListener('vp-memory-refresh', handleRefresh))
onUnmounted(() => window.removeEventListener('vp-memory-refresh', handleRefresh))

async function handleSave() {
  await save(props.projectDir)
}

async function handleDeleteRevision() {
  await deleteSelectedRevision(props.projectDir)
}

async function handleApply() {
  await applySelected(props.projectDir)
}

async function handleRuleSave() {
  await saveRule(props.projectDir)
}

async function handleRemoveRule() {
  await removeRule(props.projectDir, selectedRule.value?.path)
}

function handleNewRule() {
  selectRule(null)
  startRuleEdit()
}
</script>

<template>
  <teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="memory-overlay" @click.self="emit('close')">
        <div class="memory-dialog" :class="{ 'memory-dialog--editing': editing || ruleEditing }">
          <div class="memory-header">
            <div>
              <h3 class="memory-title">Project Instructions</h3>
              <div class="memory-subtitle">Versioned CLAUDE.md and Claude Code rules</div>
            </div>
            <div class="header-actions">
              <template v-if="activeTab === 'claude'">
                <template v-if="!editing">
                  <button
                    class="action-btn"
                    :disabled="!props.projectDir"
                    title="Extract lessons from the current session and propose a CLAUDE.md upgrade"
                    @click="emit('evolve')"
                  >
                    Evolve
                  </button>
                  <button class="action-btn edit" @click="startEdit" :disabled="!canEditSelected || loading">
                    {{ selectedRevision ? 'Edit' : 'New Draft' }}
                  </button>
                  <button class="action-btn" @click="proposeSelected" :disabled="!canPropose || saving">Propose</button>
                  <button class="action-btn" @click="approveSelected" :disabled="!canApprove || saving">Approve</button>
                  <button class="action-btn save" @click="handleApply" :disabled="!canApply || applying">
                    {{ applying ? 'Applying...' : 'Apply' }}
                  </button>
                  <button class="action-btn danger" @click="handleDeleteRevision" :disabled="!canDeleteRevision || saving">Delete Version</button>
                  <button class="action-btn danger" @click="rejectSelected('Rejected from UI')" :disabled="!canReject || saving">Reject</button>
                </template>
                <template v-else>
                  <button class="action-btn save" @click="handleSave" :disabled="saving">
                    {{ saving ? 'Saving...' : 'Save Draft' }}
                  </button>
                  <button class="action-btn cancel" @click="cancelEdit">Cancel</button>
                </template>
              </template>
              <template v-else>
                <template v-if="!ruleEditing">
                  <button class="action-btn edit" @click="handleNewRule">New Rule</button>
                  <button class="action-btn" @click="startRuleEdit(selectedRule)" :disabled="!selectedRule">Edit</button>
                  <button class="action-btn danger" @click="handleRemoveRule" :disabled="!selectedRule || saving">Delete</button>
                </template>
                <template v-else>
                  <button class="action-btn save" @click="handleRuleSave" :disabled="saving || !ruleDraft.path">
                    {{ saving ? 'Saving...' : 'Save Rule' }}
                  </button>
                  <button class="action-btn cancel" @click="cancelRuleEdit">Cancel</button>
                </template>
              </template>
              <button class="close-btn" @click="emit('close')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          </div>

          <div class="memory-tabs">
            <button :class="{ active: activeTab === 'claude' }" @click="activeTab = 'claude'">CLAUDE.md</button>
            <button :class="{ active: activeTab === 'rules' }" @click="activeTab = 'rules'">Rules</button>
          </div>

          <div v-if="error || conflictMessage" class="notice" :class="{ conflict: conflictMessage }">
            {{ conflictMessage || error }}
          </div>

          <div class="memory-body">
            <div v-if="loading" class="loading-state">
              <div class="spinner"></div>
              <span>Loading...</span>
            </div>

            <template v-else-if="activeTab === 'claude'">
              <aside class="version-sidebar">
                <div class="version-header">Versions</div>
                <button
                  v-for="revision in versions"
                  :key="revision.id"
                  class="version-item"
                  :class="{ active: selectedRevision?.id === revision.id }"
                  @click="selectRevision(revision)"
                >
                  <span class="version-main">v{{ revision.version_no }}</span>
                  <span class="state-badge" :class="revision.state">{{ revision.state }}</span>
                </button>
                <div v-if="versions.length === 0" class="empty-version">No versions</div>
              </aside>

              <section class="content-panel">
                <div v-if="selectedRevision" class="revision-meta">
                  <span>v{{ selectedRevision.version_no }}</span>
                  <span class="state-badge" :class="selectedRevision.state">{{ selectedRevision.state }}</span>
                  <span class="hash">{{ selectedRevision.content_hash?.slice(0, 8) }}</span>
                </div>

                <template v-if="editing">
                  <div class="split-pane">
                    <div class="split-editor">
                      <div class="split-label">Editor</div>
                      <textarea v-model="editContent" class="content-editor" spellcheck="false"></textarea>
                    </div>
                    <div class="split-divider"></div>
                    <div class="split-preview">
                      <div class="split-label">Preview</div>
                      <div class="content-rendered markdown-body" v-html="renderedPreview"></div>
                    </div>
                  </div>
                </template>

                <div v-else-if="selectedContent || content" class="content-rendered markdown-body" v-html="renderedContent"></div>
                <div v-else class="empty-state">(empty)</div>
              </section>
            </template>

            <template v-else>
              <aside class="version-sidebar">
                <div class="version-header">Rules</div>
                <button
                  v-for="rule in rules"
                  :key="rule.path"
                  class="version-item"
                  :class="{ active: selectedRule?.path === rule.path }"
                  @click="selectRule(rule)"
                >
                  <span class="version-main">{{ rule.path }}</span>
                  <span class="state-badge applied">active</span>
                </button>
                <div v-if="rules.length === 0" class="empty-version">No rules</div>
              </aside>

              <section class="content-panel">
                <div v-if="selectedRule" class="revision-meta">
                  <span>{{ selectedRule.path }}</span>
                  <span class="state-badge applied">active</span>
                  <span class="hash">{{ selectedRule.paths?.length ? selectedRule.paths.join(', ') : 'global' }}</span>
                </div>

                <template v-if="ruleEditing">
                  <div class="split-pane">
                    <div class="split-editor">
                      <div class="split-label">Editor</div>
                      <input v-model="ruleDraft.path" class="memory-title-input" placeholder="Rule path, e.g. frontend.md or vue/components.md" />
                      <textarea v-model="ruleDraft.pathsText" class="memory-paths-input" placeholder="paths globs, one per line. Empty means global." spellcheck="false"></textarea>
                      <textarea v-model="ruleDraft.content" class="content-editor memory-editor" spellcheck="false"></textarea>
                    </div>
                    <div class="split-divider"></div>
                    <div class="split-preview">
                      <div class="split-label">Preview</div>
                      <div class="content-rendered markdown-body" v-html="renderedRulePreview"></div>
                    </div>
                  </div>
                </template>

                <div v-else-if="selectedRule" class="content-rendered markdown-body" v-html="renderedRuleContent"></div>
                <div v-else class="empty-state">Select or create a rule</div>
              </section>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </teleport>
</template>

<style scoped>
.memory-overlay {
  position: fixed; inset: 0; z-index: 100;
  background: var(--bg-overlay);
  display: flex; align-items: center; justify-content: center;
}
.memory-dialog {
  width: 980px; max-width: 94vw; max-height: 84vh;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  display: flex; flex-direction: column;
  overflow: hidden;
  transition: width 0.2s ease;
}
.memory-dialog--editing { width: 1180px; }
.memory-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.memory-title {
  font-size: 14px; font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-mono);
  margin: 0;
}
.memory-subtitle { margin-top: 2px; color: var(--text-muted); font-size: 11px; }
.header-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.memory-tabs {
  display: flex;
  gap: 6px;
  padding: 8px 18px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-primary);
}
.memory-tabs button {
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
}
.memory-tabs button.active {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-dim);
}

.close-btn {
  background: transparent; border: none;
  color: var(--text-muted); cursor: pointer;
  padding: 4px; border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background var(--transition-fast);
  display: flex; align-items: center;
}
.close-btn:hover { color: var(--text-primary); background: var(--bg-hover); }
.action-btn {
  padding: 5px 12px; border-radius: var(--radius-sm);
  font-size: 12px; font-weight: 500; cursor: pointer;
  border: 1px solid var(--border); transition: all var(--transition-fast);
  font-family: var(--font-sans); background: transparent; color: var(--text-secondary);
}
.action-btn:hover:not(:disabled) { background: var(--bg-hover); }
.action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.action-btn.edit { color: var(--accent); border-color: var(--accent); }
.action-btn.edit:hover:not(:disabled) { background: var(--accent-dim); }
.action-btn.save { background: var(--accent); color: var(--text-on-accent); border-color: var(--accent); }
.action-btn.save:hover:not(:disabled) { filter: brightness(1.1); }
.action-btn.cancel { color: var(--text-secondary); }
.action-btn.danger { color: var(--danger, #ef4444); }
.notice {
  padding: 8px 18px;
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  font-size: 12px;
}
.notice.conflict { color: var(--danger, #ef4444); }
.memory-body {
  flex: 1; overflow: hidden; display: flex;
  min-height: 460px;
}
.loading-state, .empty-state {
  flex: 1; display: flex; align-items: center; justify-content: center;
  gap: 8px; color: var(--text-muted); font-size: 13px;
}
.spinner {
  width: 18px; height: 18px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.version-sidebar {
  width: 190px;
  border-right: 1px solid var(--border);
  background: var(--bg-primary);
  padding: 10px;
  overflow-y: auto;
}
.version-header { color: var(--text-muted); font-size: 11px; text-transform: uppercase; margin: 4px 6px 8px; }
.version-item {
  width: 100%; display: flex; align-items: center; justify-content: space-between;
  gap: 8px; padding: 8px; margin-bottom: 4px;
  border: 1px solid transparent; border-radius: var(--radius-sm);
  background: transparent; color: var(--text-secondary); cursor: pointer;
}
.version-item:hover { background: var(--bg-hover); }
.version-item.active { border-color: var(--accent); background: var(--accent-dim); color: var(--text-primary); }
.version-main { font-family: var(--font-mono); font-size: 12px; }
.empty-version { color: var(--text-muted); font-size: 12px; padding: 8px; }
.content-panel { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.revision-meta {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  color: var(--text-muted); font-size: 12px;
}
.state-badge {
  padding: 1px 6px; border-radius: 999px;
  background: var(--bg-tertiary); color: var(--text-muted);
  font-size: 10px; text-transform: uppercase;
}
.state-badge.applied { color: #16a34a; }
.state-badge.approved { color: var(--accent); }
.state-badge.disabled { color: var(--text-muted); }
.state-badge.proposed { color: #d97706; }
.state-badge.rejected, .state-badge.conflicted { color: var(--danger, #ef4444); }
.hash { font-family: var(--font-mono); }
.content-rendered {
  flex: 1; padding: 20px 24px;
  overflow-y: auto; font-size: 14px; line-height: 1.7;
}
.split-pane { flex: 1; display: flex; min-height: 0; }
.split-editor, .split-preview { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.split-divider { width: 1px; background: var(--border); }
.split-label {
  padding: 8px 12px; font-size: 11px; font-weight: 600;
  color: var(--text-muted); text-transform: uppercase;
  border-bottom: 1px solid var(--border);
  background: var(--bg-primary);
}
.content-editor {
  flex: 1; padding: 16px; border: none; outline: none; resize: none;
  background: var(--bg-primary); color: var(--text-primary);
  font-family: var(--font-mono); font-size: 13px; line-height: 1.6;
}
.memory-title-input,
.memory-paths-input {
  margin: 10px 12px 0;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-sans);
}
.memory-paths-input {
  min-height: 70px;
  resize: vertical;
}
.memory-editor { margin-top: 10px; }
.dialog-fade-enter-active, .dialog-fade-leave-active { transition: opacity 0.15s ease; }
.dialog-fade-enter-from, .dialog-fade-leave-to { opacity: 0; }
</style>
