<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { pickProjectDirectory } from '@entities/project'
import { createTeamProject, listTeamTemplates } from '../api/teamApi'
import { useAgentManager } from '@features/agent-manager/model/useAgentManager'
import { useEscapeToClose } from '@shared/lib/useDialogManager'

const props = defineProps({
  visible: { type: Boolean, required: true },
})

const emit = defineEmits(['created', 'cancel'])

useEscapeToClose(() => props.visible, () => handleCancel())

const { categories: agentCategories, fetchAgents } = useAgentManager()
const isMac = /Mac|iPhone|iPad|iPod/.test(window.navigator.platform || window.navigator.userAgent)

const teamName = ref('')
const dirPath = ref('')
const creating = ref(false)
const picking = ref(false)
const error = ref('')
const activeSlotIndex = ref(0)
const workflowTemplates = ref([])

const slots = ref([
  { agent_profile_id: '', display_name: '' },
])

const availableAgents = computed(() => agentCategories.value.flatMap(category =>
  (category.agents || []).map(agent => ({ ...agent, category_name: category.name }))
))
const agentById = computed(() => new Map(availableAgents.value.map(agent => [agent.id, agent])))

function assignedAgent(slot) {
  return agentById.value.get(slot.agent_profile_id) || null
}

const canConfirm = computed(() => {
  if (creating.value || !teamName.value.trim()) return false
  return slots.value.length > 0 && slots.value.every(slot => slot.agent_profile_id)
})

function assignAgent(agent) {
  const slot = slots.value[activeSlotIndex.value]
  if (!slot) return
  slot.agent_profile_id = agent.id
  if (!slot.display_name) slot.display_name = agent.name || agent.id
}

function addSlot() {
  slots.value.push({ agent_profile_id: '', display_name: '' })
  activeSlotIndex.value = slots.value.length - 1
}

function removeSlot(idx) {
  if (slots.value.length <= 1) return
  slots.value.splice(idx, 1)
  activeSlotIndex.value = Math.min(idx, slots.value.length - 1)
}

function applyTemplate(tpl) {
  const items = tpl.pipeline || tpl.members || tpl.slots || []
  slots.value = items.map(item => ({
    agent_profile_id: item.agent_profile_id || item.role || '',
    display_name: item.role_label || item.display_name || item.role || '',
  }))
  if (slots.value.length === 0) {
    slots.value = [{ agent_profile_id: '', display_name: '' }]
  }
  activeSlotIndex.value = 0
}

async function loadTemplates() {
  try {
    const result = await listTeamTemplates('en')
    workflowTemplates.value = result?.templates || []
  } catch (err) {
    error.value = err.message || 'Failed to load team templates'
  }
}

watch(() => props.visible, (val) => {
  if (val && workflowTemplates.value.length === 0) {
    loadTemplates()
    return
  }
  if (!val) {
    teamName.value = ''
    dirPath.value = ''
    creating.value = false
    error.value = ''
    activeSlotIndex.value = 0
    slots.value = [{ agent_profile_id: '', display_name: '' }]
  }
})

async function handlePickDirectory() {
  if (!isMac || picking.value) return
  picking.value = true
  try {
    const result = await pickProjectDirectory()
    if (result?.dir_path) dirPath.value = result.dir_path
  } catch (_) {}
  finally { picking.value = false }
}

async function handleCreate() {
  if (!canConfirm.value) return
  creating.value = true
  error.value = ''

  const config = {
    slots: slots.value
      .filter(s => s.agent_profile_id)
      .map(s => ({
        agent_profile_id: s.agent_profile_id,
        display_name: s.display_name || s.agent_profile_id,
      })),
  }

  try {
    const project = await createTeamProject(teamName.value.trim(), dirPath.value.trim(), config)
    emit('created', project)
  } catch (err) {
    error.value = err.message || 'Failed to create team project'
  } finally {
    creating.value = false
  }
}

function handleCancel() {
  if (creating.value) return
  emit('cancel')
}

onMounted(() => {
  loadTemplates()
  fetchAgents()
})
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="dialog-overlay" @click.self="handleCancel" role="dialog" aria-modal="true" aria-labelledby="create-team-dialog-title">
      <div class="dialog" :aria-busy="creating">
        <header class="dialog-header">
          <div>
            <h2 id="create-team-dialog-title" class="dialog-title">Create Agent Team</h2>
            <p class="dialog-subtitle">Add agent slots, then assign agents from catalog.</p>
          </div>
          <button class="close-btn" type="button" aria-label="Close" :disabled="creating" @click="handleCancel">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" /></svg>
          </button>
        </header>

        <div class="dialog-body">
          <section class="basic-grid">
            <div class="form-group">
              <label class="form-label">Team Name <span class="required">*</span></label>
              <input v-model="teamName" type="text" class="form-input" placeholder="e.g. My Dev Team" />
            </div>

            <div class="form-group form-group--wide">
              <label class="form-label">Working Directory</label>
              <div class="path-row">
                <input v-model="dirPath" type="text" class="form-input" placeholder="~/.velpos/teams/my-team" />
                <button v-if="isMac" class="btn-ghost" @click="handlePickDirectory" :disabled="picking">
                  {{ picking ? '...' : 'Choose' }}
                </button>
              </div>
            </div>
          </section>

          <section v-if="workflowTemplates.length" class="templates-section">
            <label class="form-label">Quick Start Templates</label>
            <div class="template-row">
              <button
                v-for="tpl in workflowTemplates"
                :key="tpl.id"
                class="template-btn"
                @click="applyTemplate(tpl)"
                :title="tpl.description"
              >{{ tpl.name }}</button>
            </div>
          </section>

          <section class="workspace-grid">
            <div class="project-picker panel-card">
              <div class="panel-header">
                <div>
                  <h3 class="panel-title">Agent Catalog</h3>
                  <p class="panel-hint">{{ availableAgents.length }} available</p>
                </div>
              </div>

              <div v-if="availableAgents.length === 0" class="empty-card">
                <span class="empty-title">No agents available</span>
                <span class="empty-desc">Check the agent catalog configuration.</span>
              </div>
              <div v-else class="project-list">
                <button
                  v-for="agent in availableAgents"
                  :key="agent.id"
                  class="project-card"
                  :class="{ selected: slots[activeSlotIndex]?.agent_profile_id === agent.id }"
                  @click="assignAgent(agent)"
                >
                  <span class="project-card-main">
                    <span class="project-card-title">{{ agent.name }}</span>
                    <span class="project-card-path">{{ agent.description }}</span>
                  </span>
                  <span class="project-card-meta">
                    <span class="agent-badge">{{ agent.id }}</span>
                    <span class="lang-badge">{{ agent.category_name }}</span>
                  </span>
                </button>
              </div>
            </div>

            <div class="assignment-panel panel-card">
              <div class="panel-header">
                <div>
                  <h3 class="panel-title">Agent Slots</h3>
                  <p class="panel-hint">Select a slot, then click an agent to assign.</p>
                </div>
              </div>

              <div v-for="(slot, idx) in slots" :key="idx" class="assignment-card" :class="{ active: activeSlotIndex === idx }">
                <div class="assignment-header">
                  <button class="assignment-project" @click="activeSlotIndex = idx">
                    <span class="step-badge">Slot {{ idx + 1 }}</span>
                    <span v-if="assignedAgent(slot)" class="selected-project-name">
                      {{ assignedAgent(slot).name }}
                    </span>
                    <span v-else class="selected-project-placeholder">Select an agent</span>
                  </button>
                  <button v-if="slots.length > 1" class="btn-icon" @click="removeSlot(idx)" title="Remove" aria-label="Remove slot">&times;</button>
                </div>
                <div class="step-row">
                  <input v-model="slot.display_name" class="form-input" placeholder="Display name (optional)" />
                </div>
              </div>
              <button class="btn-ghost add-btn" @click="addSlot">+ Add Slot</button>
            </div>
          </section>

          <div v-if="error" class="form-error">{{ error }}</div>
        </div>

        <footer class="dialog-actions">
          <button class="btn-ghost" @click="handleCancel" :disabled="creating">Cancel</button>
          <button class="btn-primary" @click="handleCreate" :disabled="!canConfirm">
            <span v-if="creating" class="spinner"></span>
            {{ creating ? 'Creating...' : 'Create' }}
          </button>
        </footer>

        <Transition name="creation-state">
          <div v-if="creating" class="team-creation-state" role="status" aria-live="polite">
            <div class="team-creation-state__graphic" aria-hidden="true">
              <span class="team-creation-state__core">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="8" r="3" />
                  <path d="M6.5 19a5.5 5.5 0 0 1 11 0" />
                </svg>
              </span>
              <span
                v-for="(_, index) in slots.slice(0, 6)"
                :key="index"
                class="team-creation-state__node"
                :style="{ '--node-index': index, '--node-count': Math.min(slots.length, 6) }"
              />
            </div>
            <div class="team-creation-state__copy">
              <strong>Creating {{ teamName.trim() }}</strong>
              <span>Preparing the workspace and connecting {{ slots.length }} {{ slots.length === 1 ? 'agent' : 'agents' }}…</span>
            </div>
            <span class="team-creation-state__progress" aria-hidden="true">
              <span />
            </span>
          </div>
        </Transition>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
  padding: 16px;
}

.dialog {
  position: relative;
  width: 860px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  background: var(--dialog-surface);
  border: 1px solid var(--dialog-border);
  border-radius: var(--dialog-radius);
  box-shadow: var(--dialog-shadow);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.dialog-header {
  align-items: flex-start;
  gap: 16px;
  padding: 18px 22px;
}

.dialog-subtitle {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.close-btn {
  width: 36px;
  height: 36px;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.close-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px;
}

.basic-grid {
  display: grid;
  grid-template-columns: minmax(180px, 0.8fr) minmax(320px, 1.4fr);
  gap: 12px;
  margin-bottom: 14px;
}

.templates-section {
  margin-bottom: 14px;
}

.template-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.template-btn {
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast), color var(--transition-fast);
}

.template-btn:hover {
  background: var(--accent-dim);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  color: var(--accent);
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(300px, 0.9fr) minmax(340px, 1.1fr);
  gap: 14px;
  align-items: start;
}

.panel-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  padding: 12px;
  min-width: 0;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 10px;
}

.panel-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.panel-hint {
  margin: 3px 0 0;
  color: var(--text-muted);
  font-size: 11px;
}

.project-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 2px;
}

.project-card {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.project-card:hover {
  background: var(--bg-hover);
  border-color: var(--border);
}

.project-card.selected {
  background: var(--accent-dim);
  border-color: var(--accent);
  box-shadow: var(--ring);
}

.project-card-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.project-card-title,
.selected-project-name {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-card-path {
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
  flex-wrap: wrap;
  max-width: 180px;
}

.agent-badge,
.lang-badge {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.2;
}

.agent-badge {
  background: var(--accent-dim);
  color: var(--accent);
}

.lang-badge {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.assignment-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px;
  margin-bottom: 8px;
  background: var(--bg-secondary);
  transition: border-color var(--transition-fast), background var(--transition-fast);
}

.assignment-card.active {
  border-color: color-mix(in srgb, var(--accent) 50%, var(--border));
  background: color-mix(in srgb, var(--accent) 6%, var(--bg-secondary));
}

.assignment-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.assignment-project {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  border: none;
  background: transparent;
  padding: 0;
  text-align: left;
  cursor: pointer;
}

.step-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  text-transform: uppercase;
}

.selected-project-placeholder {
  color: var(--text-muted);
  font-size: 12px;
}

.step-row {
  display: flex;
  gap: 8px;
}

.btn-icon {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 18px;
  line-height: 1;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.btn-icon:hover { color: var(--red); background: var(--bg-hover); }

.add-btn {
  font-size: 12px;
  padding: 6px 10px;
  margin-top: 2px;
}

.empty-card {
  min-height: 160px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  text-align: center;
  padding: 18px;
}

.empty-title {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.empty-desc {
  font-size: 12px;
}

.path-row {
  display: flex;
  gap: 8px;
}

.form-group { margin-bottom: 12px; }
.form-group--wide { min-width: 0; }
.form-label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; }
.required { color: var(--red); }
.form-error { font-size: 11px; color: var(--red); margin-top: 10px; }
.path-row .form-input { flex: 1; }

.form-input {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.5;
  outline: none;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.form-input:focus {
  border-color: var(--accent);
  box-shadow: var(--ring);
}

.form-input::placeholder { color: var(--text-muted); }

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 22px;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.btn-ghost {
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.btn-ghost:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); }
.btn-ghost:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-primary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: var(--text-on-accent);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: filter var(--transition-fast);
  box-shadow: var(--shadow-sm);
}

.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--bg-primary);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.team-creation-state {
  position: absolute;
  inset: 0;
  z-index: 4;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 32px;
  background:
    radial-gradient(circle at 50% 42%, color-mix(in srgb, var(--accent) 14%, transparent), transparent 32%),
    color-mix(in srgb, var(--dialog-surface) 94%, transparent);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.team-creation-state__graphic {
  position: relative;
  width: 112px;
  height: 112px;
}

.team-creation-state__core {
  position: absolute;
  inset: 31px;
  display: grid;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--accent) 48%, var(--border));
  border-radius: 16px;
  background: var(--bg-secondary);
  color: var(--accent);
  box-shadow:
    0 0 0 8px color-mix(in srgb, var(--accent) 7%, transparent),
    var(--shadow-md);
  animation: team-core-pulse 1.8s ease-in-out infinite;
}

.team-creation-state__node {
  --node-angle: calc(360deg / var(--node-count) * var(--node-index));
  position: absolute;
  top: 50%;
  left: 50%;
  width: 11px;
  height: 11px;
  margin: -5.5px;
  border: 2px solid var(--dialog-surface);
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 42%, var(--border));
  transform: rotate(var(--node-angle)) translateY(-50px);
  animation: team-node-pulse 1.4s ease-in-out infinite;
  animation-delay: calc(var(--node-index) * 120ms);
}

.team-creation-state__copy {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  max-width: 380px;
  text-align: center;
}

.team-creation-state__copy strong {
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 650;
}

.team-creation-state__copy span {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.team-creation-state__progress {
  width: min(260px, 70%);
  height: 3px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 12%, var(--border));
}

.team-creation-state__progress span {
  display: block;
  width: 42%;
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
  animation: team-progress 1.3s ease-in-out infinite;
}

.creation-state-enter-active,
.creation-state-leave-active {
  transition: opacity 160ms ease;
}

.creation-state-enter-from,
.creation-state-leave-to {
  opacity: 0;
}

@keyframes team-core-pulse {
  0%, 100% { transform: scale(0.96); }
  50% { transform: scale(1.04); }
}

@keyframes team-node-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

@keyframes team-progress {
  0% { transform: translateX(-110%); }
  50% { transform: translateX(70%); }
  100% { transform: translateX(240%); }
}

@media (prefers-reduced-motion: reduce) {
  .spinner,
  .team-creation-state__core,
  .team-creation-state__node,
  .team-creation-state__progress span {
    animation: none;
  }

  .team-creation-state__node {
    opacity: 0.8;
  }

  .team-creation-state__progress span {
    width: 72%;
  }
}

@media (max-width: 760px) {
  .dialog {
    max-width: calc(100vw - 20px);
    max-height: calc(100vh - 20px);
  }

  .basic-grid,
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .project-card {
    align-items: flex-start;
    flex-direction: column;
  }

  .project-card-meta {
    justify-content: flex-start;
    max-width: none;
  }
}
</style>
