<script setup>
import { watch, computed, ref, onMounted, onUnmounted, nextTick } from 'vue'
import { configuredMarked } from '@features/message-display'
import { listWorkspaceFileHistory, readWorkspaceFileAtRef } from '@entities/project/api/projectApi'
import { useMemoryManager } from '../model/useMemoryManager'
import { useDialogManager } from '@shared/lib/useDialogManager'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys'

const props = defineProps({
  visible: { type: Boolean, default: false },
  projectDir: { type: String, default: '' },
  projectId: { type: String, default: '' },
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
const claudeCompareRevisionId = ref('')
const claudeDiffCursor = ref(-1)
const ruleHistory = ref([])
const ruleHistoryLoading = ref(false)
const ruleHistoryRef = ref('')
const ruleHistoryContents = ref({})
const ruleDiffCursor = ref(-1)

const {
  content, versions, selectedRevision, selectedContent, canEditSelected,
  rules, selectedRule, ruleEditing, ruleDraft,
  loading, editing, editContent, saving, applying, error, conflictMessage,
  loadClaudeMd, loadRules, selectRevision, selectRule,
  startEdit, cancelEdit, save, startRuleEdit, startRuleDraft, cancelRuleEdit,
  saveRule, removeRule, deleteSelectedRevision, applySelected, reset,
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
const canApply = computed(() => ['draft', 'approved'].includes(selectedState.value))
const canDeleteRevision = computed(() => Boolean(selectedRevision.value))
const rulePathLocked = computed(() => Boolean(ruleEditing.value && selectedRule.value))
const claudeCompareOptions = computed(() => versions.value.filter(revision => revision.id !== selectedRevision.value?.id))
const selectedClaudeCompareRevision = computed(() => claudeCompareOptions.value.find(revision => revision.id === claudeCompareRevisionId.value) || null)
const claudeCompareRows = computed(() => {
  if (!selectedRevision.value || !selectedClaudeCompareRevision.value) return []
  return buildSideBySideDiff(
    splitLines(selectedClaudeCompareRevision.value.content),
    splitLines(selectedRevision.value.content),
  )
})
const claudeDiffIndexes = computed(() => claudeCompareRows.value
  .map((row, index) => (row.type === 'same' ? -1 : index))
  .filter(index => index >= 0))
const claudeDiffSummary = computed(() => `${claudeDiffIndexes.value.length} diffs`)
const selectedRuleWorkspacePath = computed(() => selectedRule.value?.path ? `.claude/rules/${selectedRule.value.path}` : '')
const selectedRuleHistoryNode = computed(() => ruleHistory.value.find(item => item.hash === ruleHistoryRef.value) || null)
const selectedRuleHistoryContent = computed(() => {
  if (!selectedRuleWorkspacePath.value || !ruleHistoryRef.value) return ''
  return ruleHistoryContents.value[`${selectedRuleWorkspacePath.value}@${ruleHistoryRef.value}`] || ''
})
const ruleCompareRows = computed(() => {
  if (!selectedRule.value || !ruleHistoryRef.value) return []
  return buildSideBySideDiff(
    splitLines(selectedRuleHistoryContent.value),
    splitLines(selectedRule.value.content || ''),
  )
})
const ruleDiffIndexes = computed(() => ruleCompareRows.value
  .map((row, index) => (row.type === 'same' ? -1 : index))
  .filter(index => index >= 0))
const ruleDiffSummary = computed(() => `${ruleDiffIndexes.value.length} diffs`)

watch(() => props.visible, async (visible) => {
  if (visible && props.projectDir) {
    await Promise.all([
      loadClaudeMd(props.projectDir),
      loadRules(props.projectDir),
    ])
  } else if (!visible) {
    resetCompareState()
    reset()
  }
})

watch(() => props.projectId, async (projectId) => {
  if (props.visible && projectId && selectedRule.value) {
    await loadRuleHistory()
  }
})

watch(selectedRevision, () => {
  claudeCompareRevisionId.value = ''
  claudeDiffCursor.value = -1
})

watch(selectedRule, async (rule) => {
  ruleHistoryRef.value = ''
  ruleDiffCursor.value = -1
  ruleHistory.value = []
  if (!rule || !props.projectId) return
  await loadRuleHistory()
})

function handleRefresh() {
  if (props.visible && props.projectDir) {
    loadClaudeMd(props.projectDir)
    loadRules(props.projectDir)
  }
}

async function handleOpenRuleDraft(event) {
  if (props.projectDir) {
    await loadRules(props.projectDir)
  }
  activeTab.value = 'rules'
  startRuleDraft(event.detail || {})
  ruleHistoryRef.value = ''
  ruleDiffCursor.value = -1
}

function handleOpenTab(event) {
  activeTab.value = event.detail?.tab === 'rules' ? 'rules' : 'claude'
}

onMounted(() => {
  window.addEventListener('vp-memory-refresh', handleRefresh)
  window.addEventListener('vp-memory-open-rule-draft', handleOpenRuleDraft)
  window.addEventListener('vp-memory-open-tab', handleOpenTab)
})

onUnmounted(() => {
  window.removeEventListener('vp-memory-refresh', handleRefresh)
  window.removeEventListener('vp-memory-open-rule-draft', handleOpenRuleDraft)
  window.removeEventListener('vp-memory-open-tab', handleOpenTab)
})

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
  if (props.projectId && selectedRule.value) {
    await loadRuleHistory()
  }
}

async function handleRemoveRule() {
  await removeRule(props.projectDir, selectedRule.value?.path)
  ruleHistory.value = []
  ruleHistoryRef.value = ''
  ruleDiffCursor.value = -1
}

function handleNewRule() {
  ruleHistoryRef.value = ''
  ruleDiffCursor.value = -1
  selectRule(null)
  startRuleEdit()
}

function handleSelectRule(rule) {
  selectRule(rule)
}

async function loadRuleHistory() {
  if (!props.projectId || !selectedRuleWorkspacePath.value) {
    ruleHistory.value = []
    ruleHistoryRef.value = ''
    return
  }
  ruleHistoryLoading.value = true
  error.value = ''
  try {
    const data = await listWorkspaceFileHistory(props.projectId, selectedRuleWorkspacePath.value, 20)
    ruleHistory.value = data.commits || []
    if (ruleHistoryRef.value && !ruleHistory.value.some(item => item.hash === ruleHistoryRef.value)) {
      ruleHistoryRef.value = ''
    }
  } catch (e) {
    ruleHistory.value = []
    ruleHistoryRef.value = ''
    error.value = e.message || 'Failed to load rule history'
  } finally {
    ruleHistoryLoading.value = false
  }
}

async function handleRuleCompareChange() {
  ruleDiffCursor.value = -1
  if (!ruleHistoryRef.value || !props.projectId || !selectedRuleWorkspacePath.value) return
  const cacheKey = `${selectedRuleWorkspacePath.value}@${ruleHistoryRef.value}`
  if (ruleHistoryContents.value[cacheKey] !== undefined) return
  try {
    const data = await readWorkspaceFileAtRef(props.projectId, selectedRuleWorkspacePath.value, ruleHistoryRef.value)
    ruleHistoryContents.value = {
      ...ruleHistoryContents.value,
      [cacheKey]: data.content || '',
    }
  } catch (e) {
    error.value = e.message || 'Failed to load rule version'
    ruleHistoryRef.value = ''
  }
}

function resetCompareState() {
  claudeCompareRevisionId.value = ''
  claudeDiffCursor.value = -1
  ruleHistory.value = []
  ruleHistoryLoading.value = false
  ruleHistoryRef.value = ''
  ruleHistoryContents.value = {}
  ruleDiffCursor.value = -1
}

function splitLines(contentValue) {
  return (contentValue || '').split('\n')
}

function buildSideBySideDiff(before, after) {
  if (before.length * after.length > 1000000) return buildSequentialDiff(before, after)
  const rows = []
  const dp = Array.from({ length: before.length + 1 }, () => new Uint32Array(after.length + 1))

  for (let i = before.length - 1; i >= 0; i -= 1) {
    for (let j = after.length - 1; j >= 0; j -= 1) {
      dp[i][j] = before[i] === after[j]
        ? dp[i + 1][j + 1] + 1
        : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }

  let i = 0
  let j = 0
  while (i < before.length && j < after.length) {
    if (before[i] === after[j]) {
      rows.push(createDiffRow('same', before[i], after[j], i + 1, j + 1))
      i += 1
      j += 1
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      rows.push(createDiffRow('removed', before[i], '', i + 1, null))
      i += 1
    } else {
      rows.push(createDiffRow('added', '', after[j], null, j + 1))
      j += 1
    }
  }

  while (i < before.length) {
    rows.push(createDiffRow('removed', before[i], '', i + 1, null))
    i += 1
  }
  while (j < after.length) {
    rows.push(createDiffRow('added', '', after[j], null, j + 1))
    j += 1
  }

  return rows
}

function buildSequentialDiff(before, after) {
  const rows = []
  const max = Math.max(before.length, after.length)
  for (let index = 0; index < max; index += 1) {
    const beforeLine = before[index]
    const afterLine = after[index]
    if (beforeLine === afterLine) {
      rows.push(createDiffRow('same', beforeLine || '', afterLine || '', index + 1, index + 1))
    } else {
      if (beforeLine !== undefined) rows.push(createDiffRow('removed', beforeLine, '', index + 1, null))
      if (afterLine !== undefined) rows.push(createDiffRow('added', '', afterLine, null, index + 1))
    }
  }
  return rows
}

function createDiffRow(type, beforeLine, afterLine, beforeLineNo, afterLineNo) {
  const source = `${type}:${beforeLineNo || 0}:${afterLineNo || 0}:${beforeLine}:${afterLine}`
  const displayLine = afterLineNo ? afterLine : beforeLine
  const displayLineNo = afterLineNo || beforeLineNo
  return {
    id: `${type}-${beforeLineNo || 0}-${afterLineNo || 0}-${hashString(source)}`,
    type,
    beforeLine,
    afterLine,
    beforeLineNo,
    afterLineNo,
    displayLine,
    displayLineNo,
  }
}

function hashString(value) {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) - hash + value.charCodeAt(index)) | 0
  }
  return Math.abs(hash).toString(36)
}

function formatRuleHistoryLabel(commit) {
  const shortHash = commit.short_hash || String(commit.hash || '').slice(0, 7)
  const message = String(commit.message || '').trim().split('\n')[0]
  return message ? `${shortHash} · ${message}` : shortHash
}

function nextDiff(prefix, indexes, cursorRef) {
  if (!indexes.length) return
  const next = indexes.find(index => index > cursorRef.value) ?? indexes[0]
  cursorRef.value = next
  nextTick(() => {
    document.querySelector(`[data-diff-row="${prefix}-${next}"]`)?.scrollIntoView({ block: 'center' })
  })
}

function nextClaudeDiff() {
  nextDiff('claude', claudeDiffIndexes.value, claudeDiffCursor)
}

function nextRuleDiff() {
  nextDiff('rule', ruleDiffIndexes.value, ruleDiffCursor)
}
</script>

<template>
  <teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="memory-overlay" @click.self="emit('close')">
        <div class="memory-dialog" :class="{ 'memory-dialog--editing': editing || ruleEditing }">
          <div class="memory-header">
            <div>
              <h3 class="memory-title">Project Rules</h3>
              <div class="memory-subtitle">CLAUDE.md and project rules</div>
            </div>
            <div class="header-actions">
              <button
                v-if="!editing && !ruleEditing"
                class="action-btn"
                :disabled="!props.projectDir"
                title="Extract reusable lessons from the current session"
                @click="emit('evolve')"
              >
                Evolve
              </button>
              <template v-if="activeTab === 'claude'">
                <template v-if="!editing">
                  <button class="action-btn edit" @click="startEdit" :disabled="!canEditSelected || loading">
                    {{ selectedRevision ? 'Edit' : 'New Version' }}
                  </button>
                  <button class="action-btn save" @click="handleApply" :disabled="!canApply || applying">
                    {{ applying ? 'Applying...' : 'Apply' }}
                  </button>
                  <button class="action-btn danger" @click="handleDeleteRevision" :disabled="!canDeleteRevision || saving">Delete Version</button>
                </template>
                <template v-else>
                  <button class="action-btn save" @click="handleSave" :disabled="saving">
                    {{ saving ? 'Saving...' : 'Save Version' }}
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

                <div v-if="selectedRevision && !editing" class="compare-toolbar">
                  <label class="compare-select-wrap">
                    <span>Compare</span>
                    <select v-model="claudeCompareRevisionId" class="compare-select">
                      <option value="">Current only</option>
                      <option v-for="revision in claudeCompareOptions" :key="revision.id" :value="revision.id">
                        v{{ revision.version_no }} · {{ revision.state }}
                      </option>
                    </select>
                  </label>
                  <template v-if="selectedClaudeCompareRevision">
                    <span class="compare-summary">vs v{{ selectedClaudeCompareRevision.version_no }} · {{ claudeDiffSummary }}</span>
                    <button class="action-btn" @click="nextClaudeDiff" :disabled="claudeDiffIndexes.length === 0">Next diff</button>
                  </template>
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

                <div v-else-if="selectedClaudeCompareRevision" class="diff-view">
                  <div
                    v-for="(row, index) in claudeCompareRows"
                    :key="row.id"
                    class="diff-row"
                    :class="[row.type, { current: claudeDiffCursor === index }]"
                    :data-diff-row="`claude-${index}`"
                  >
                    <span class="diff-kind">{{ row.type === 'added' ? '+' : row.type === 'removed' ? '-' : '·' }}</span>
                    <span class="diff-line-no">{{ row.displayLineNo || '' }}</span>
                    <pre class="diff-line">{{ row.displayLine || ' ' }}</pre>
                  </div>
                </div>
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
                  @click="handleSelectRule(rule)"
                >
                  <span class="version-main">{{ rule.path }}</span>
                </button>
                <div v-if="rules.length === 0" class="empty-version">No rules</div>
              </aside>

              <section class="content-panel">
                <div v-if="selectedRule" class="revision-meta">
                  <span>{{ selectedRule.path }}</span>
                  <span class="state-badge applied">rule</span>
                  <span class="hash">{{ selectedRule.paths?.length ? selectedRule.paths.join(', ') : 'global' }}</span>
                </div>

                <div v-if="selectedRule && !ruleEditing" class="compare-toolbar">
                  <label class="compare-select-wrap">
                    <span>Compare</span>
                    <select v-model="ruleHistoryRef" class="compare-select" @change="handleRuleCompareChange">
                      <option value="">Current only</option>
                      <option v-for="commit in ruleHistory" :key="commit.hash" :value="commit.hash">
                        {{ formatRuleHistoryLabel(commit) }}
                      </option>
                    </select>
                  </label>
                  <span v-if="ruleHistoryLoading" class="compare-summary">Loading history...</span>
                  <span v-else-if="!ruleHistory.length" class="compare-summary">No git history yet</span>
                  <template v-else-if="selectedRuleHistoryNode">
                    <span class="compare-summary">vs {{ formatRuleHistoryLabel(selectedRuleHistoryNode) }} · {{ ruleDiffSummary }}</span>
                    <button class="action-btn" @click="nextRuleDiff" :disabled="ruleDiffIndexes.length === 0">Next diff</button>
                  </template>
                </div>

                <template v-if="ruleEditing">
                  <div class="split-pane">
                    <div class="split-editor">
                      <div class="split-label">Editor</div>
                      <input
                        v-model="ruleDraft.path"
                        class="memory-title-input"
                        :disabled="rulePathLocked"
                        placeholder="Rule path, e.g. frontend.md or vue/components.md"
                      />
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

                <div v-else-if="selectedRuleHistoryNode" class="diff-view">
                  <div
                    v-for="(row, index) in ruleCompareRows"
                    :key="row.id"
                    class="diff-row"
                    :class="[row.type, { current: ruleDiffCursor === index }]"
                    :data-diff-row="`rule-${index}`"
                  >
                    <span class="diff-kind">{{ row.type === 'added' ? '+' : row.type === 'removed' ? '-' : '·' }}</span>
                    <span class="diff-line-no">{{ row.displayLineNo || '' }}</span>
                    <pre class="diff-line">{{ row.displayLine || ' ' }}</pre>
                  </div>
                </div>
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
  width: 1040px; max-width: 94vw; max-height: 84vh;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  display: flex; flex-direction: column;
  overflow: hidden;
  transition: width 0.2s ease;
}
.memory-dialog--editing { width: 1200px; }
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
  width: 220px;
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
  text-align: left;
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
.compare-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-primary);
  flex-wrap: wrap;
}
.compare-select-wrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
  font-size: 12px;
}
.compare-select {
  min-width: 220px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-primary);
}
.compare-summary { color: var(--text-muted); font-size: 12px; }
.state-badge {
  padding: 1px 6px; border-radius: 999px;
  background: var(--bg-tertiary); color: var(--text-muted);
  font-size: 10px; text-transform: uppercase;
}
.state-badge.applied { color: #16a34a; }
.state-badge.approved { color: var(--accent); }
.state-badge.proposed { color: #d97706; }
.state-badge.rejected, .state-badge.conflicted { color: var(--danger, #ef4444); }
.hash { font-family: var(--font-mono); }
.content-rendered {
  flex: 1; padding: 20px 24px;
  overflow-y: auto; font-size: 14px; line-height: 1.7;
}
.diff-view {
  flex: 1;
  overflow: auto;
  background: var(--bg-primary);
}
.diff-row {
  display: grid;
  grid-template-columns: 24px 56px 1fr;
  gap: 8px;
  padding: 0 14px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 65%, transparent);
  align-items: start;
}
.diff-row.current {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
}
.diff-row.added {
  background: color-mix(in srgb, #22c55e 10%, transparent);
}
.diff-row.removed {
  background: color-mix(in srgb, #ef4444 10%, transparent);
}
.diff-kind,
.diff-line-no {
  padding: 8px 0;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
}
.diff-line {
  margin: 0;
  padding: 8px 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
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
.memory-title-input:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
.memory-paths-input {
  min-height: 70px;
  resize: vertical;
}
.memory-editor { margin-top: 10px; }
.dialog-fade-enter-active, .dialog-fade-leave-active { transition: opacity 0.15s ease; }
.dialog-fade-enter-from, .dialog-fade-leave-to { opacity: 0; }
</style>
