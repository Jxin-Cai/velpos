<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { useProject } from '@entities/project/model/useProject'
import { pickProjectDirectory } from '@entities/project'
import CustomSelect from '@shared/ui/CustomSelect.vue'
import { createTeamProject, listTeamTemplates } from '../api/teamApi'
import { useEscapeToClose } from '@shared/lib/useDialogManager'

const props = defineProps({
  visible: { type: Boolean, required: true },
})

const emit = defineEmits(['created', 'cancel'])

useEscapeToClose(() => props.visible, () => emit('cancel'))

const { singleAgentProjects } = useProject()
const isMac = /Mac|iPhone|iPad|iPod/.test(window.navigator.platform || window.navigator.userAgent)

const teamName = ref('')
const dirPath = ref('')
const teamMode = ref('delegation')
const creating = ref(false)
const picking = ref(false)
const error = ref('')
const selectedAgentId = ref('all')
const projectKeyword = ref('')
const activeAssignment = ref({ type: 'pipeline', index: 0 })

const pipeline = ref([
  { project_id: '', role: '', role_label: '', handoff_input: '', handoff_output: '' },
])

const members = ref([
  { project_id: '', role: '', role_label: '', trigger: '', provides: '' },
])
const defaultWorkflow = ref('')
const maxDepth = ref(5)

const maxConcurrent = ref(2)
const workerMaxTurns = ref(50)
const workerMaxBudget = ref(1.0)
const fileCheckpointing = ref(true)
const workflowTemplates = ref([])

const agentOptions = computed(() => {
  const counts = new Map()
  for (const project of singleAgentProjects.value) {
    const agentId = projectAgentId(project)
    if (!agentId) continue
    counts.set(agentId, (counts.get(agentId) || 0) + 1)
  }
  const options = [...counts.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([agentId, count]) => ({ value: agentId, label: `${agentId} (${count})` }))
  return [{ value: 'all', label: `All agents (${singleAgentProjects.value.length})` }, ...options]
})

const filteredProjects = computed(() => {
  const keyword = projectKeyword.value.trim().toLowerCase()
  return singleAgentProjects.value.filter(project => {
    const agentId = projectAgentId(project)
    if (!agentId) return false
    if (selectedAgentId.value !== 'all' && agentId !== selectedAgentId.value) return false
    if (!keyword) return true
    return [project.name, project.dir_path, agentId, projectAgentLanguage(project)]
      .filter(Boolean)
      .some(value => String(value).toLowerCase().includes(keyword))
  })
})

const projectById = computed(() => {
  const map = new Map()
  for (const project of singleAgentProjects.value) map.set(project.id, project)
  return map
})

const activeItems = computed(() => teamMode.value === 'delegation' ? pipeline.value : members.value)
const activeProjectId = computed(() => activeItems.value[activeAssignment.value.index]?.project_id || '')

const canConfirm = computed(() => {
  if (creating.value || !teamName.value.trim() || !dirPath.value.trim()) return false
  const items = teamMode.value === 'delegation' ? pipeline.value : members.value
  return items.length > 0 && items.every(item => item.project_id && item.role)
})

function projectAgentId(project) {
  return project?.agents?.current?.id || ''
}

function projectAgentLanguage(project) {
  return project?.agents?.current?.language || ''
}

function projectDisplayName(project) {
  return `${project?.name || ''} (agent)`
}

function selectedProject(projectId) {
  return projectById.value.get(projectId) || null
}

function assignmentLabel(type, idx) {
  return type === 'pipeline' ? `Step ${idx + 1}` : `Member ${idx + 1}`
}

function isActiveAssignment(type, idx) {
  return activeAssignment.value.type === type && activeAssignment.value.index === idx
}

function setActiveAssignment(type, idx) {
  activeAssignment.value = { type, index: idx }
}

function assignProject(project) {
  const items = activeAssignment.value.type === 'pipeline' ? pipeline.value : members.value
  const item = items[activeAssignment.value.index]
  if (!item) return
  item.project_id = project.id
}

function isProjectSelected(projectId) {
  return activeProjectId.value === projectId
}

function assignmentLabelsForProject(projectId) {
  const items = teamMode.value === 'delegation' ? pipeline.value : members.value
  const type = teamMode.value === 'delegation' ? 'pipeline' : 'members'
  return items
    .map((item, idx) => item.project_id === projectId ? assignmentLabel(type, idx) : '')
    .filter(Boolean)
}

function resetFilters() {
  selectedAgentId.value = 'all'
  projectKeyword.value = ''
}

function applyTemplate(tpl) {
  teamMode.value = tpl.mode
  if (tpl.mode === 'delegation') {
    pipeline.value = tpl.pipeline.map(s => ({ ...s, project_id: '' }))
    activeAssignment.value = { type: 'pipeline', index: 0 }
  } else {
    members.value = (tpl.members || []).map(m => ({ ...m, project_id: '' }))
    activeAssignment.value = { type: 'members', index: 0 }
  }

  const defaultConfig = tpl.default_config || {}
  maxConcurrent.value = defaultConfig.max_concurrent ?? maxConcurrent.value
  workerMaxTurns.value = defaultConfig.worker_max_turns ?? workerMaxTurns.value
  workerMaxBudget.value = defaultConfig.worker_max_budget_usd ?? workerMaxBudget.value
  fileCheckpointing.value = defaultConfig.file_checkpointing ?? fileCheckpointing.value

  if (tpl.default_workflow?.length) {
    defaultWorkflow.value = tpl.default_workflow.join(' → ')
  }
}

async function loadTemplates() {
  try {
    const result = await listTeamTemplates('en')
    workflowTemplates.value = result?.templates || []
  } catch (err) {
    error.value = err.message || 'Failed to load team templates'
  }
}

function addPipelineStep() {
  pipeline.value.push({ project_id: '', role: '', role_label: '', handoff_input: '', handoff_output: '' })
  activeAssignment.value = { type: 'pipeline', index: pipeline.value.length - 1 }
}

function removePipelineStep(idx) {
  if (pipeline.value.length <= 1) return
  pipeline.value.splice(idx, 1)
  activeAssignment.value = { type: 'pipeline', index: Math.min(idx, pipeline.value.length - 1) }
}

function addMember() {
  members.value.push({ project_id: '', role: '', role_label: '', trigger: '', provides: '' })
  activeAssignment.value = { type: 'members', index: members.value.length - 1 }
}

function removeMember(idx) {
  if (members.value.length <= 1) return
  members.value.splice(idx, 1)
  activeAssignment.value = { type: 'members', index: Math.min(idx, members.value.length - 1) }
}

watch(teamMode, (mode) => {
  activeAssignment.value = { type: mode === 'delegation' ? 'pipeline' : 'members', index: 0 }
})

watch(() => props.visible, (val) => {
  if (val && workflowTemplates.value.length === 0) {
    loadTemplates()
    return
  }
  if (!val) {
    teamName.value = ''
    dirPath.value = ''
    teamMode.value = 'delegation'
    creating.value = false
    error.value = ''
    selectedAgentId.value = 'all'
    projectKeyword.value = ''
    activeAssignment.value = { type: 'pipeline', index: 0 }
    pipeline.value = [{ project_id: '', role: '', role_label: '', handoff_input: '', handoff_output: '' }]
    members.value = [{ project_id: '', role: '', role_label: '', trigger: '', provides: '' }]
    defaultWorkflow.value = ''
    maxDepth.value = 5
    maxConcurrent.value = 2
    workerMaxTurns.value = 50
    workerMaxBudget.value = 1.0
    fileCheckpointing.value = true
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

  const config = { max_concurrent: maxConcurrent.value, worker_max_turns: workerMaxTurns.value, worker_max_budget_usd: workerMaxBudget.value, file_checkpointing: fileCheckpointing.value }
  if (teamMode.value === 'delegation') {
    config.mode = 'delegation'
    config.pipeline = pipeline.value.filter(s => s.project_id)
  } else {
    config.mode = 'collaboration'
    config.members = members.value.filter(m => m.project_id)
    config.default_workflow = defaultWorkflow.value.split(/[→,\s]+/).map(s => s.trim()).filter(Boolean)
    config.max_depth = maxDepth.value
  }

  try {
    const project = await createTeamProject(teamName.value.trim(), dirPath.value.trim(), config)
    creating.value = false
    emit('created', project)
  } catch (err) {
    error.value = err.message || 'Failed to create team project'
    creating.value = false
  }
}

function handleCancel() { emit('cancel') }

onMounted(() => {
  loadTemplates()
})
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="dialog-overlay" @click.self="handleCancel" role="dialog" aria-modal="true" aria-labelledby="create-team-dialog-title">
      <div class="dialog">
        <header class="dialog-header">
          <div>
            <h2 id="create-team-dialog-title" class="dialog-title">Create Agent Teams Project</h2>
            <p class="dialog-subtitle">Pick agent-enabled projects, then assign them to each team role.</p>
          </div>
          <button class="close-btn" type="button" aria-label="Close team project dialog" @click="handleCancel">
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
              <label class="form-label">Working Directory <span class="required">*</span></label>
              <div class="path-row">
                <input v-model="dirPath" type="text" class="form-input" placeholder="/path/to/project" />
                <button v-if="isMac" class="btn-ghost" @click="handlePickDirectory" :disabled="picking">
                  {{ picking ? '...' : 'Choose' }}
                </button>
              </div>
            </div>
          </section>

          <section class="setup-row">
            <div class="form-group">
              <label class="form-label">Collaboration Mode</label>
              <div class="mode-switch">
                <button class="mode-btn" :class="{ active: teamMode === 'delegation' }" @click="teamMode = 'delegation'">
                  Delegation
                </button>
                <button class="mode-btn" :class="{ active: teamMode === 'collaboration' }" @click="teamMode = 'collaboration'">
                  Collaboration
                </button>
              </div>
            </div>

            <div class="form-group templates-group">
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
            </div>
          </section>

          <section class="workspace-grid">
            <div class="project-picker panel-card">
              <div class="panel-header">
                <div>
                  <h3 class="panel-title">Agent projects</h3>
                  <p class="panel-hint">{{ filteredProjects.length }} of {{ singleAgentProjects.length }} available</p>
                </div>
              </div>

              <div class="filter-row">
                <CustomSelect v-model="selectedAgentId" :options="agentOptions" />
                <input v-model="projectKeyword" class="form-input search-input" type="search" placeholder="Search project, path, agent..." />
              </div>

              <div v-if="singleAgentProjects.length === 0" class="empty-card">
                <span class="empty-title">No agent projects available</span>
                <span class="empty-desc">Load an agent in an Agents project before creating a team.</span>
              </div>
              <div v-else-if="filteredProjects.length === 0" class="empty-card">
                <span class="empty-title">No projects match this filter</span>
                <button class="link-btn" @click="resetFilters">Clear filter</button>
              </div>
              <div v-else class="project-list">
                <button
                  v-for="project in filteredProjects"
                  :key="project.id"
                  class="project-card"
                  :class="{ selected: isProjectSelected(project.id), assigned: assignmentLabelsForProject(project.id).length > 0 }"
                  @click="assignProject(project)"
                >
                  <span class="project-card-main">
                    <span class="project-card-title">{{ projectDisplayName(project) }}</span>
                    <span class="project-card-path">{{ project.dir_path }}</span>
                  </span>
                  <span class="project-card-meta">
                    <span class="agent-badge">{{ projectAgentId(project) }}</span>
                    <span v-if="projectAgentLanguage(project)" class="lang-badge">{{ projectAgentLanguage(project) }}</span>
                    <span v-if="assignmentLabelsForProject(project.id).length" class="assigned-badge">
                      {{ assignmentLabelsForProject(project.id).join(', ') }}
                    </span>
                    <span v-if="isProjectSelected(project.id)" class="selected-dot" aria-hidden="true"></span>
                  </span>
                </button>
              </div>
            </div>

            <div class="assignment-panel panel-card">
              <div class="panel-header">
                <div>
                  <h3 class="panel-title">{{ teamMode === 'delegation' ? 'Pipeline' : 'Team Members' }}</h3>
                  <p class="panel-hint">Select a row, then click a project card to bind it.</p>
                </div>
              </div>

              <template v-if="teamMode === 'delegation'">
                <div v-for="(step, idx) in pipeline" :key="idx" class="assignment-card" :class="{ active: isActiveAssignment('pipeline', idx) }">
                  <div class="assignment-header">
                    <button class="assignment-project" @click="setActiveAssignment('pipeline', idx)">
                      <span class="step-badge">Step {{ idx + 1 }}</span>
                      <span v-if="selectedProject(step.project_id)" class="selected-project-name">
                        {{ projectDisplayName(selectedProject(step.project_id)) }}
                      </span>
                      <span v-else class="selected-project-placeholder">Select a project</span>
                    </button>
                    <button v-if="pipeline.length > 1" class="btn-icon" @click="removePipelineStep(idx)" title="Remove" aria-label="Remove step">×</button>
                  </div>
                  <div class="step-row">
                    <input v-model="step.role" class="form-input role-input" placeholder="Role (e.g. architect)" />
                    <input v-model="step.role_label" class="form-input role-input" placeholder="Label (e.g. Architect)" />
                  </div>
                  <div class="step-row">
                    <input v-model="step.handoff_input" class="form-input" placeholder="Input from previous step" />
                  </div>
                  <div class="step-row">
                    <input v-model="step.handoff_output" class="form-input" placeholder="Output for next step" />
                  </div>
                </div>
                <button class="btn-ghost add-btn" @click="addPipelineStep">+ Add Step</button>
              </template>

              <template v-else>
                <div v-for="(member, idx) in members" :key="idx" class="assignment-card" :class="{ active: isActiveAssignment('members', idx) }">
                  <div class="assignment-header">
                    <button class="assignment-project" @click="setActiveAssignment('members', idx)">
                      <span class="step-badge">Member {{ idx + 1 }}</span>
                      <span v-if="selectedProject(member.project_id)" class="selected-project-name">
                        {{ projectDisplayName(selectedProject(member.project_id)) }}
                      </span>
                      <span v-else class="selected-project-placeholder">Select a project</span>
                    </button>
                    <button v-if="members.length > 1" class="btn-icon" @click="removeMember(idx)" title="Remove" aria-label="Remove member">×</button>
                  </div>
                  <div class="step-row">
                    <input v-model="member.role" class="form-input role-input" placeholder="Role" />
                    <input v-model="member.role_label" class="form-input role-input" placeholder="Label" />
                  </div>
                  <div class="step-row">
                    <input v-model="member.trigger" class="form-input" placeholder="When to invoke" />
                  </div>
                  <div class="step-row">
                    <input v-model="member.provides" class="form-input" placeholder="What it provides" />
                  </div>
                </div>
                <button class="btn-ghost add-btn" @click="addMember">+ Add Member</button>

                <div class="form-group inline-config">
                  <label class="form-label">Default Workflow</label>
                  <input v-model="defaultWorkflow" class="form-input" placeholder="architect → coder → tester" />
                </div>
                <div class="form-group inline-config inline-config--small">
                  <label class="form-label">Max Nesting Depth</label>
                  <input v-model.number="maxDepth" type="number" class="form-input" min="1" max="10" />
                </div>
              </template>
            </div>
          </section>

          <details class="advanced-section">
            <summary class="form-label">Advanced</summary>
            <div class="advanced-grid">
              <div class="form-group">
                <label class="form-label">Max Concurrent</label>
                <input v-model.number="maxConcurrent" type="number" class="form-input" min="1" max="10" />
              </div>
              <div class="form-group">
                <label class="form-label">Worker Max Turns</label>
                <input v-model.number="workerMaxTurns" type="number" class="form-input" min="1" max="200" />
              </div>
              <div class="form-group">
                <label class="form-label">Worker Budget ($)</label>
                <input v-model.number="workerMaxBudget" type="number" class="form-input" min="0.1" max="50" step="0.1" />
              </div>
              <div class="form-group">
                <label class="form-label checkbox-label">
                  <input type="checkbox" v-model="fileCheckpointing" />
                  File Checkpointing
                </label>
              </div>
            </div>
          </details>

          <div v-if="error" class="form-error">{{ error }}</div>
        </div>

        <footer class="dialog-actions">
          <button class="btn-ghost" @click="handleCancel" :disabled="creating">Cancel</button>
          <button class="btn-primary" @click="handleCreate" :disabled="!canConfirm">
            <span v-if="creating" class="spinner"></span>
            {{ creating ? 'Creating...' : 'Create' }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
  padding: 16px;
}

.dialog {
  width: 920px;
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

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px;
}

.basic-grid {
  display: grid;
  grid-template-columns: minmax(180px, 0.8fr) minmax(320px, 1.4fr);
  gap: 12px;
}

.setup-row {
  display: grid;
  grid-template-columns: minmax(220px, auto) 1fr;
  gap: 16px;
  align-items: end;
  margin-bottom: 14px;
}

.mode-switch,
.template-row,
.filter-row,
.path-row,
.step-row,
.assignment-header,
.project-card-meta,
.advanced-grid,
.dialog-actions {
  display: flex;
}

.mode-switch,
.template-row,
.filter-row,
.path-row,
.step-row,
.project-card-meta,
.advanced-grid {
  gap: 8px;
}

.mode-btn,
.template-btn,
.btn-ghost,
.btn-primary,
.btn-icon,
.link-btn {
  cursor: pointer;
}

.mode-btn {
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  transition: background var(--transition-fast), border-color var(--transition-fast), color var(--transition-fast);
}

.mode-btn.active {
  background: var(--accent-dim);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  color: var(--accent);
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(320px, 0.9fr) minmax(380px, 1.1fr);
  gap: 14px;
  align-items: start;
}

.panel-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  min-width: 0;
}

.project-picker,
.assignment-panel {
  padding: 12px;
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

.filter-row {
  align-items: center;
  margin-bottom: 10px;
}

.search-input {
  flex: 1;
  min-width: 0;
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

.project-card.assigned:not(.selected) {
  border-color: color-mix(in srgb, var(--accent) 28%, transparent);
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
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  max-width: 180px;
}

.agent-badge,
.lang-badge,
.assigned-badge {
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

.assigned-badge {
  background: color-mix(in srgb, var(--green) 14%, transparent);
  color: var(--green);
}

.selected-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
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

.role-input {
  width: 50%;
  min-width: 0;
}

.btn-icon {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 18px;
  line-height: 1;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.btn-icon:hover { color: var(--red); background: var(--bg-hover); }

.add-btn {
  font-size: 12px;
  padding: 6px 10px;
  margin-top: 2px;
}

.inline-config {
  margin-top: 12px;
}

.inline-config--small .form-input {
  width: 110px;
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

.link-btn {
  border: none;
  background: transparent;
  color: var(--accent);
  font-size: 12px;
  font-weight: 600;
}

.advanced-section {
  margin-top: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
}

.advanced-section summary {
  cursor: pointer;
  margin-bottom: 0;
}

.advanced-section[open] summary {
  margin-bottom: 8px;
}

.advanced-grid {
  flex-wrap: wrap;
}

.advanced-grid .form-group {
  min-width: 120px;
  margin-bottom: 0;
}

.advanced-grid .form-input {
  width: 120px;
}

.template-row {
  flex-wrap: wrap;
}

.template-btn {
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  transition: background var(--transition-fast), border-color var(--transition-fast), color var(--transition-fast);
}

.template-btn:hover {
  background: var(--accent-dim);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  color: var(--accent);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  min-height: 34px;
}

.checkbox-label input[type="checkbox"] {
  margin: 0;
  accent-color: var(--accent);
}

.form-group { margin-bottom: 12px; }
.form-group--wide { min-width: 0; }
.templates-group { min-width: 0; }
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
  animation: spin 0.6s linear infinite;
}

@media (max-width: 760px) {
  .dialog {
    max-width: calc(100vw - 20px);
    max-height: calc(100vh - 20px);
  }

  .basic-grid,
  .setup-row,
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .filter-row,
  .step-row {
    flex-direction: column;
  }

  .role-input {
    width: 100%;
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
