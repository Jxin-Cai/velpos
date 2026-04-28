<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useSettingsManager } from '../model/useSettingsManager'
import { useUserPreferences } from '@shared/lib/useUserPreferences'
import { useDialogManager } from '@shared/lib/useDialogManager'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys.js'
import CustomSelect from '@shared/ui/CustomSelect.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits(['close'])

// 创建一个包装对象来管理可见性，避免直接修改 prop
const visibleWrapper = {
  get value() {
    return props.visible
  },
  set value(newValue) {
    if (!newValue) {
      emit('close')
    }
  }
}

const { useDialog } = useDialogManager()
useDialog('settings', visibleWrapper)

const AUTH_ENV_OPTIONS = [
  { value: 'ANTHROPIC_API_KEY', label: 'ANTHROPIC_API_KEY' },
  { value: 'ANTHROPIC_AUTH_TOKEN', label: 'ANTHROPIC_AUTH_TOKEN' },
]

const MODEL_ENV_KEYS = [
  { key: 'ANTHROPIC_MODEL', label: 'Default Model' },
  { key: 'ANTHROPIC_REASONING_MODEL', label: 'Think Model' },
  { key: 'ANTHROPIC_DEFAULT_OPUS_MODEL', label: 'Opus Model' },
  { key: 'ANTHROPIC_DEFAULT_HAIKU_MODEL', label: 'Haiku Model' },
  { key: 'ANTHROPIC_DEFAULT_SONNET_MODEL', label: 'Sonnet Model' },
]

// ESC to close dialog
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

const {
  settings,
  profiles,
  loading,
  saving,
  operating,
  error,
  fetchedModels,
  fetchingModels,
  loadData,
  saveSettings,
  handleCreate,
  handleUpdate,
  handleDelete,
  handleActivate,
  handleFetchModels,
} = useSettingsManager()

const {
  enterBehavior,
  enterBehaviors,
  setEnterBehavior,
} = useUserPreferences()

const editingProfileId = ref(null)
const showAddForm = ref(false)
const showJsonPreview = ref(false)
const jsonPreviewEl = ref(null)
const addForm = ref({ name: '', host: '', api_key: '', auth_env_name: 'ANTHROPIC_API_KEY', model_config: {} })
const editForm = ref({ name: '', host: '', api_key: '', auth_env_name: 'ANTHROPIC_API_KEY', model_config: {} })
const settingsData = ref(null)

const defaultMode = computed({
  get() {
    return settingsData.value?.permissions?.defaultMode || 'default'
  },
  set(val) {
    if (!settingsData.value) return
    if (!settingsData.value.permissions) {
      settingsData.value.permissions = {}
    }
    settingsData.value.permissions.defaultMode = val
  },
})

const hasCompletedOnboarding = computed({
  get() {
    return settingsData.value?.hasCompletedOnboarding !== false
  },
  set(val) {
    if (!settingsData.value) return
    settingsData.value.hasCompletedOnboarding = val
  },
})

const effortLevel = computed({
  get() {
    return settingsData.value?.effortLevel || ''
  },
  set(val) {
    if (!settingsData.value) return
    settingsData.value.effortLevel = val || undefined
  },
})

const skipDangerousPrompt = computed({
  get() {
    return settingsData.value?.skipDangerousModePermissionPrompt === true
  },
  set(val) {
    if (!settingsData.value) return
    settingsData.value.skipDangerousModePermissionPrompt = val
  },
})

const attributionCommit = computed({
  get() {
    return settingsData.value?.attribution?.commit ?? ''
  },
  set(val) {
    if (!settingsData.value) return
    if (!settingsData.value.attribution) settingsData.value.attribution = {}
    settingsData.value.attribution.commit = val
  },
})

const attributionPr = computed({
  get() {
    return settingsData.value?.attribution?.pr ?? ''
  },
  set(val) {
    if (!settingsData.value) return
    if (!settingsData.value.attribution) settingsData.value.attribution = {}
    settingsData.value.attribution.pr = val
  },
})

function getEnvVar(key) {
  return settingsData.value?.env?.[key] || ''
}

function setEnvVar(key, val) {
  if (!settingsData.value) return
  if (!settingsData.value.env) settingsData.value.env = {}
  if (val) {
    settingsData.value.env[key] = val
  } else {
    delete settingsData.value.env[key]
  }
}

const jsonPreviewText = computed(() => {
  if (!settingsData.value) return '{}'
  return JSON.stringify(settingsData.value, null, 2)
})

function getModelOptions(key) {
  const models = fetchedModels.value[key] || []
  return models.map(m => ({
    value: m.value || m.id || '',
    label: m.displayName || m.value || m.id || '',
  }))
}

watch(() => props.visible, (val) => {
  if (val) {
    loadData()
    editingProfileId.value = null
    showAddForm.value = false
  }
})

watch(() => settings.value, (val) => {
  if (val) {
    settingsData.value = JSON.parse(JSON.stringify(val))
  }
})

function handleOverlayClick(e) {
  if (e.target === e.currentTarget) {
    emit('close')
  }
}

function cancelAdd() {
  showAddForm.value = false
  addForm.value = { name: '', host: '', api_key: '', auth_env_name: 'ANTHROPIC_API_KEY', model_config: {} }
}

async function submitAdd() {
  await handleCreate(addForm.value)
  addForm.value = { name: '', host: '', api_key: '', auth_env_name: 'ANTHROPIC_API_KEY', model_config: {} }
  showAddForm.value = false
}

function startEdit(profile) {
  editingProfileId.value = profile.profile_id
  editForm.value = {
    name: profile.name,
    host: profile.host || '',
    api_key: profile.api_key || '',
    auth_env_name: profile.auth_env_name || 'ANTHROPIC_API_KEY',
    model_config: { ...(profile.model_config || {}) },
  }
}

async function submitEdit() {
  await handleUpdate(editingProfileId.value, editForm.value)
  editingProfileId.value = null
}

function cancelEdit() {
  editingProfileId.value = null
}

async function onDelete(profileId) {
  if (editingProfileId.value === profileId) {
    editingProfileId.value = null
  }
  await handleDelete(profileId)
}

async function onActivate(profileId) {
  await handleActivate(profileId)
}

function onFetchModelsForAdd() {
  handleFetchModels('_add', addForm.value.host, addForm.value.api_key)
}

function onFetchModelsForEdit() {
  handleFetchModels(editingProfileId.value, editForm.value.host, editForm.value.api_key)
}

const copyJsonSuccess = ref(false)
let copyJsonTimer = null

const saveSuccess = ref(false)

async function handleSave() {
  await saveSettings(settingsData.value)
  if (!error.value) {
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 1500)
  }
}

function handleKeydown(e) {
  if (e.key === 'Escape' && props.visible) {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  clearTimeout(copyJsonTimer)
})

async function copyJsonPreview() {
  try {
    await navigator.clipboard.writeText(jsonPreviewText.value)
    copyJsonSuccess.value = true
    clearTimeout(copyJsonTimer)
    copyJsonTimer = setTimeout(() => { copyJsonSuccess.value = false }, 1500)
  } catch (err) {
    console.error('Failed to copy JSON:', err)
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="dialog-overlay" @click="handleOverlayClick" role="dialog" aria-modal="true">
      <div class="dialog">
        <div class="dialog-header">
          <h2 class="dialog-title">Settings</h2>
          <button class="close-btn" @click="emit('close')">&times;</button>
        </div>

        <div v-if="error" class="error-banner">{{ error }}</div>

        <div v-if="loading" class="loading-state">
          <div class="spinner"></div>
          Loading settings...
        </div>

        <div v-else class="dialog-body">
          <!-- Section 1: Channel Profiles -->
          <div class="section">
            <div class="section-header">
              <h3 class="section-title">Channel Profiles</h3>
              <button v-if="!showAddForm" class="btn-add" @click="showAddForm = true">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                Add Channel
              </button>
            </div>

            <div v-if="showAddForm" class="channel-form">
              <div class="form-section-label">Basic Info</div>
              <div class="form-grid">
                <div class="form-group">
                  <label class="form-label">Name <span class="required">*</span></label>
                  <input class="form-input" v-model="addForm.name" placeholder="e.g. Production" />
                </div>
                <div class="form-group">
                  <label class="form-label">Host</label>
                  <input class="form-input" v-model="addForm.host" placeholder="https://api.anthropic.com" />
                </div>
                <div class="form-group form-group--full">
                  <label class="form-label">API Key</label>
                  <input class="form-input" v-model="addForm.api_key" type="password" placeholder="sk-ant-..." />
                </div>
                <div class="form-group">
                  <label class="form-label">Auth Env Variable</label>
                  <CustomSelect v-model="addForm.auth_env_name" :options="AUTH_ENV_OPTIONS" />
                </div>
              </div>

              <div class="form-section-label">
                Model Configuration
                <button
                  class="btn-fetch"
                  :disabled="fetchingModels === '_add'"
                  @click="onFetchModelsForAdd"
                >
                  <svg v-if="fetchingModels !== '_add'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                  </svg>
                  {{ fetchingModels === '_add' ? 'Fetching...' : 'Fetch Models' }}
                </button>
                <span v-if="(fetchedModels['_add'] || []).length" class="fetch-count">
                  {{ fetchedModels['_add'].length }} available
                </span>
              </div>
              <div class="model-grid">
                <div v-for="m in MODEL_ENV_KEYS" :key="m.key" class="model-field-row">
                  <label class="model-field-label">{{ m.label }}</label>
                  <select
                    v-if="(fetchedModels['_add'] || []).length"
                    class="form-select"
                    v-model="addForm.model_config[m.key]"
                  >
                    <option value="">-- None --</option>
                    <option
                      v-for="opt in getModelOptions('_add')"
                      :key="opt.value"
                      :value="opt.value"
                    >{{ opt.label }}</option>
                  </select>
                  <input
                    v-else
                    class="form-input"
                    v-model="addForm.model_config[m.key]"
                    :placeholder="m.key"
                  />
                </div>
              </div>

              <div class="form-actions">
                <button class="btn-save" :disabled="!addForm.name.trim()" @click="submitAdd">Create</button>
                <button class="btn-cancel" @click="cancelAdd">Cancel</button>
              </div>
            </div>

            <div class="channel-list">
              <div
                v-for="p in profiles"
                :key="p.profile_id"
                class="channel-card"
                :class="{ 'channel-card--active': p.is_active, 'channel-card--editing': editingProfileId === p.profile_id }"
              >
                <template v-if="editingProfileId !== p.profile_id">
                  <div class="channel-row">
                    <div class="channel-info">
                      <div class="channel-name-row">
                        <span class="channel-name">{{ p.name }}</span>
                        <span v-if="p.is_active" class="active-badge">Active</span>
                      </div>
                      <span class="channel-host">{{ p.host || 'https://api.anthropic.com (default)' }}</span>
                    </div>
                    <div class="channel-actions">
                      <button
                        v-if="!p.is_active"
                        class="btn-activate"
                        :disabled="operating === p.profile_id"
                        @click="onActivate(p.profile_id)"
                      >Activate</button>
                      <button class="btn-edit" @click="startEdit(p)">Edit</button>
                      <button
                        class="btn-delete"
                        :disabled="operating === p.profile_id"
                        @click="onDelete(p.profile_id)"
                      >Delete</button>
                    </div>
                  </div>
                </template>

                <template v-else>
                  <div class="channel-form channel-form--inline">
                    <div class="form-section-label">Basic Info</div>
                    <div class="form-grid">
                      <div class="form-group">
                        <label class="form-label">Name <span class="required">*</span></label>
                        <input class="form-input" v-model="editForm.name" placeholder="Name" />
                      </div>
                      <div class="form-group">
                        <label class="form-label">Host</label>
                        <input class="form-input" v-model="editForm.host" placeholder="https://api.anthropic.com" />
                      </div>
                      <div class="form-group form-group--full">
                        <label class="form-label">API Key</label>
                        <input class="form-input" v-model="editForm.api_key" type="password" placeholder="sk-ant-..." />
                      </div>
                      <div class="form-group">
                        <label class="form-label">Auth Env Variable</label>
                        <CustomSelect v-model="editForm.auth_env_name" :options="AUTH_ENV_OPTIONS" />
                      </div>
                    </div>

                    <div class="form-section-label">
                      Model Configuration
                      <button
                        class="btn-fetch"
                        :disabled="fetchingModels === p.profile_id"
                        @click="onFetchModelsForEdit"
                      >
                        <svg v-if="fetchingModels !== p.profile_id" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                        </svg>
                        {{ fetchingModels === p.profile_id ? 'Fetching...' : 'Fetch Models' }}
                      </button>
                      <span v-if="(fetchedModels[p.profile_id] || []).length" class="fetch-count">
                        {{ fetchedModels[p.profile_id].length }} available
                      </span>
                    </div>
                    <div class="model-grid">
                      <div v-for="m in MODEL_ENV_KEYS" :key="m.key" class="model-field-row">
                        <label class="model-field-label">{{ m.label }}</label>
                        <select
                          v-if="(fetchedModels[p.profile_id] || []).length"
                          class="form-select"
                          v-model="editForm.model_config[m.key]"
                        >
                          <option value="">-- None --</option>
                          <option
                            v-for="opt in getModelOptions(p.profile_id)"
                            :key="opt.value"
                            :value="opt.value"
                          >{{ opt.label }}</option>
                        </select>
                        <input
                          v-else
                          class="form-input"
                          v-model="editForm.model_config[m.key]"
                          :placeholder="m.key"
                        />
                      </div>
                    </div>

                    <div class="form-actions">
                      <button class="btn-save" :disabled="!editForm.name.trim()" @click="submitEdit">Save</button>
                      <button class="btn-cancel" @click="cancelEdit">Cancel</button>
                    </div>
                  </div>
                </template>
              </div>
            </div>

            <div v-if="!profiles.length && !showAddForm" class="empty-channels">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="opacity: 0.3">
                <rect x="2" y="7" width="20" height="14" rx="2" ry="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
              </svg>
              <span>No channel profiles configured</span>
            </div>
          </div>

          <!-- Section 2: Settings Configuration -->
          <div class="section">
            <div class="section-header">
              <h3 class="section-title">Settings Configuration</h3>
              <button class="btn-preview" :class="{ active: showJsonPreview }" @click="showJsonPreview = !showJsonPreview" title="Toggle JSON Preview">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              </button>
            </div>
            <Transition name="preview-slide">
              <div v-if="showJsonPreview" class="json-preview-wrapper">
                <button class="json-copy-btn" :class="{ copied: copyJsonSuccess }" @click="copyJsonPreview" title="Copy JSON">
                  <svg v-if="!copyJsonSuccess" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                  </svg>
                  <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </button>
                <pre class="json-preview">{{ jsonPreviewText }}</pre>
              </div>
            </Transition>
            <div class="settings-card" v-if="settingsData">
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">Permission Mode</label>
                  <span class="field-desc">Controls tool approval policy: default prompts each time, bypass auto-allows all</span>
                </div>
                <CustomSelect v-model="defaultMode" :options="[{ value: 'default', label: 'Default' }, { value: 'acceptEdits', label: 'Accept Edits' }, { value: 'plan', label: 'Plan' }, { value: 'bypassPermissions', label: 'Bypass' }]" />
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">Completed Onboarding</label>
                  <span class="field-desc">Skip the first-run onboarding flow on launch</span>
                </div>
                <label class="toggle-label">
                  <input type="checkbox" class="toggle-checkbox" v-model="hasCompletedOnboarding" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">Effort Level</label>
                  <span class="field-desc">Reasoning effort: low is fast/cheap, high is thorough</span>
                </div>
                <CustomSelect v-model="effortLevel" :options="[{ value: '', label: 'Default' }, { value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium' }, { value: 'high', label: 'High' }]" />
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">Skip Dangerous Mode Prompt</label>
                  <span class="field-desc">Suppress the safety confirmation when entering bypass mode</span>
                </div>
                <label class="toggle-label">
                  <input type="checkbox" class="toggle-checkbox" v-model="skipDangerousPrompt" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">Disable Non-Essential Traffic</label>
                  <span class="field-desc">Disables updater, feedback, error reporting and telemetry</span>
                </div>
                <label class="toggle-label">
                  <input type="checkbox" class="toggle-checkbox" :checked="getEnvVar('CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC') === '1'" @change="setEnvVar('CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC', $event.target.checked ? '1' : '')" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">Agent Teams (Experimental)</label>
                  <span class="field-desc">Enable multi-agent collaboration within a session</span>
                </div>
                <label class="toggle-label">
                  <input type="checkbox" class="toggle-checkbox" :checked="getEnvVar('CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS') === '1'" @change="setEnvVar('CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS', $event.target.checked ? '1' : '')" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">Tool Search</label>
                  <span class="field-desc">Enable MCP tool search and dynamic loading</span>
                </div>
                <label class="toggle-label">
                  <input type="checkbox" class="toggle-checkbox" :checked="getEnvVar('ENABLE_TOOL_SEARCH') === 'true'" @change="setEnvVar('ENABLE_TOOL_SEARCH', $event.target.checked ? 'true' : '')" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="field-row field-row--stacked">
                <div class="field-info">
                  <label class="field-label">Attribution: Commit</label>
                  <span class="field-desc">Text appended to commit messages; empty to disable</span>
                </div>
                <input class="form-input" v-model="attributionCommit" placeholder="e.g. Co-authored-by: ..." />
              </div>
              <div class="field-row field-row--stacked">
                <div class="field-info">
                  <label class="field-label">Attribution: PR</label>
                  <span class="field-desc">Text appended to PR descriptions; empty to disable</span>
                </div>
                <input class="form-input" v-model="attributionPr" placeholder="e.g. Co-authored-by: ..." />
              </div>
            </div>
          </div>

          <!-- Section 3: User Preferences -->
          <div class="section">
            <h3 class="section-title">User Preferences</h3>
            <div class="settings-card">
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">Enter Key Behavior</label>
                  <span class="field-desc">Choose how Enter and Ctrl+Enter keys behave in the chat input</span>
                </div>
                <CustomSelect :model-value="enterBehavior" @update:model-value="setEnterBehavior" :options="[{ value: 'enter-send', label: 'Enter to send, Ctrl+Enter for new line' }, { value: 'ctrl-enter-send', label: 'Ctrl+Enter to send, Enter for new line' }]" :display-map="{ 'enter-send': 'Enter to send', 'ctrl-enter-send': 'Ctrl+Enter to send' }" />
              </div>
            </div>
          </div>
        </div>

        <div class="dialog-footer">
          <button
            class="btn-primary"
            :class="{ 'btn-primary--success': saveSuccess }"
            :disabled="saving || loading"
            @click="handleSave"
          >
            <svg v-if="saveSuccess" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            {{ saving ? 'Saving...' : saveSuccess ? 'Saved' : 'Save' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay-glass);
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
}

.dialog {
  width: 720px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-glass);
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--glass-border);
  background: var(--layer-glass);
  flex-shrink: 0;
}

.dialog-title {
  font-weight: 600;
  font-size: 16px;
  color: var(--text-primary);
  margin: 0;
}

.close-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  font-size: 20px;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast), color var(--transition-fast);
}

.close-btn:hover {
  background: var(--layer-active);
  color: var(--accent);
}

.error-banner {
  padding: 8px 20px;
  background: var(--red-dim);
  color: var(--red);
  font-size: 13px;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  color: var(--text-muted);
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
}

.section {
  margin-bottom: 20px;
}

.section + .section {
  padding-top: 20px;
  border-top: 1px solid var(--border);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px;
}

.section-header .section-title {
  margin: 0;
}

.btn-preview {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-preview:hover {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-dim);
}

.btn-preview.active {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-dim);
}

.preview-slide-enter-active {
  transition: max-height 250ms cubic-bezier(0.4, 0, 0.2, 1), opacity 200ms cubic-bezier(0.4, 0, 0.2, 1), margin 250ms cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}
.preview-slide-leave-active {
  transition: max-height 200ms cubic-bezier(0.4, 0, 0.2, 1), opacity 150ms cubic-bezier(0.4, 0, 0.2, 1), margin 200ms cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}
.preview-slide-enter-from,
.preview-slide-leave-to {
  max-height: 0;
  opacity: 0;
  margin-bottom: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.channel-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.channel-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.channel-card:hover {
  border-color: color-mix(in srgb, var(--border) 70%, var(--accent));
}

.channel-card--active {
  border-color: var(--green);
  background: color-mix(in srgb, var(--green) 4%, transparent);
}

.channel-card--editing {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 20%, transparent);
}

.channel-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
}

.channel-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.channel-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.channel-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.channel-host {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.active-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--green-dim);
  color: var(--green);
  flex-shrink: 0;
}

.channel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.channel-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  margin-bottom: 8px;
  border: 1px solid var(--border);
}

.channel-form--inline {
  margin-bottom: 0;
  border: none;
  border-radius: 0;
  background: transparent;
}

.form-section-label {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding-bottom: 4px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 50%, transparent);
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-group--full {
  grid-column: 1 / -1;
}

.form-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.required {
  color: var(--red);
}

.model-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-input, var(--bg-primary));
  color: var(--text-primary);
  font-size: 13px;
  font-family: var(--font-sans);
  box-sizing: border-box;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.form-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--ring, 0 0 0 2px rgba(99, 102, 241, 0.2));
}

.form-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-input, var(--bg-primary));
  color: var(--text-primary);
  font-size: 13px;
  font-family: var(--font-sans);
  box-sizing: border-box;
  transition: border-color var(--transition-fast);
}

.form-select:focus {
  outline: none;
  border-color: var(--accent);
}

.form-actions {
  display: flex;
  gap: 8px;
  padding-top: 4px;
}

.btn-add {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--accent);
  background: transparent;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  padding: 5px 14px;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.btn-add:hover {
  background: var(--accent-dim, color-mix(in srgb, var(--accent) 10%, transparent));
}

.btn-save {
  background: var(--accent);
  color: var(--bg-primary);
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  border: none;
  cursor: pointer;
}

.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-cancel {
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border);
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
}

.btn-edit {
  font-size: 12px;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 4px 10px;
  cursor: pointer;
  transition: color var(--transition-fast), border-color var(--transition-fast);
}

.btn-edit:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.btn-delete {
  font-size: 12px;
  color: var(--red);
  background: transparent;
  border: 1px solid color-mix(in srgb, var(--red) 30%, var(--border));
  border-radius: var(--radius-sm);
  padding: 4px 10px;
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast);
}

.btn-delete:hover {
  background: var(--red-dim);
  border-color: var(--red);
}

.btn-delete:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-activate {
  font-size: 12px;
  padding: 4px 12px;
  border: 1px solid var(--green);
  color: var(--green);
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.btn-activate:hover {
  background: var(--green-dim);
}

.btn-activate:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.empty-channels {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.btn-fetch {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  padding: 3px 10px;
  border: 1px solid var(--accent);
  color: var(--accent);
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.btn-fetch:hover:not(:disabled) {
  background: var(--accent-dim, color-mix(in srgb, var(--accent) 10%, transparent));
}

.btn-fetch:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.fetch-count {
  font-size: 11px;
  color: var(--green);
  font-weight: 500;
}

.model-field-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.model-field-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.field-desc {
  display: block;
  font-size: 10px;
  font-weight: 400;
  color: var(--text-muted);
  opacity: 0.7;
  margin-top: 1px;
}

.settings-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.settings-card .field-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
}

.settings-card .field-row + .field-row {
  border-top: 1px solid color-mix(in srgb, var(--border) 50%, transparent);
}

.settings-card .field-row--stacked {
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}

.settings-card .field-row:hover {
  background: color-mix(in srgb, var(--bg-hover) 50%, transparent);
}

.field-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.field-label {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.field-info .field-desc {
  display: block;
  font-size: 11px;
  font-weight: 400;
  color: var(--text-muted);
  opacity: 0.7;
  white-space: normal;
}

.form-select--compact {
  width: auto;
  min-width: 140px;
  flex-shrink: 0;
}

.settings-card .form-input {
  width: 100%;
}

.field-divider {
  height: 1px;
  background: var(--border);
  margin: 4px 0;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.toggle-checkbox {
  display: none;
}

.toggle-track {
  position: relative;
  width: 36px;
  height: 20px;
  background: var(--border);
  border-radius: 10px;
  transition: background var(--transition-fast);
  flex-shrink: 0;
}

.toggle-checkbox:checked + .toggle-track {
  background: var(--accent);
}

.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: #fff;
  border-radius: 50%;
  transition: transform var(--transition-fast);
  box-shadow: var(--shadow-sm);
}

.toggle-checkbox:checked + .toggle-track .toggle-thumb {
  transform: translateX(16px);
}

.toggle-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.json-preview-wrapper {
  position: relative;
  margin: 0 0 16px;
}

.json-preview {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  margin: 0;
  font-family: var(--font-mono);
  user-select: text;
  -webkit-user-select: text;
  cursor: text;
  font-size: 12px;
  line-height: 1.5;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  color: var(--text-secondary);
}

.json-copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0;
  transition: opacity var(--transition-fast), color var(--transition-fast), background var(--transition-fast);
  z-index: 1;
}

.json-preview-wrapper:hover .json-copy-btn {
  opacity: 1;
}

.json-copy-btn:hover {
  color: var(--accent);
  background: var(--bg-hover);
  border-color: var(--accent);
}

.json-copy-btn.copied {
  color: var(--green);
  border-color: var(--green);
}

.dialog-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  text-align: right;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--accent);
  color: var(--bg-primary);
  padding: 6px 20px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: filter var(--transition-fast), background var(--transition-fast), transform 0.15s;
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.1);
  transform: translateY(-1px);
}

.btn-primary:active:not(:disabled) {
  transform: translateY(0);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary--success {
  background: var(--green);
  color: #fff;
}
</style>
