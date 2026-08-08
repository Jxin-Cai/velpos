<script setup>
import { ref, computed, watch } from 'vue'
import { useSettingsManager } from '../model/useSettingsManager'
import { useUserPreferences } from '@shared/lib/useUserPreferences'
import { useDialogManager, useVisibleProxy, useEscapeToClose } from '@shared/lib/useDialogManager'
import { useTimeout } from '@shared/lib/useTimeout'
import CustomSelect from '@shared/ui/CustomSelect.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
  embedded: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close', 'dirty-change'])

const { useDialog } = useDialogManager()
const visibleProxy = useVisibleProxy(props, emit)
useDialog('settings', {
  get value() { return !props.embedded && visibleProxy.value },
  set value(value) { if (!value && !props.embedded) visibleProxy.value = false },
})

const AUTH_ENV_OPTIONS = [
  { value: 'ANTHROPIC_API_KEY', label: 'ANTHROPIC_API_KEY' },
  { value: 'ANTHROPIC_AUTH_TOKEN', label: 'ANTHROPIC_AUTH_TOKEN' },
]

const MODEL_ROLES = [
  { role: 'Sonnet', modelKey: 'ANTHROPIC_DEFAULT_SONNET_MODEL', nameKey: 'ANTHROPIC_DEFAULT_SONNET_MODEL_NAME' },
  { role: 'Opus', modelKey: 'ANTHROPIC_DEFAULT_OPUS_MODEL', nameKey: 'ANTHROPIC_DEFAULT_OPUS_MODEL_NAME' },
  { role: 'Fable', modelKey: 'ANTHROPIC_DEFAULT_FABLE_MODEL', nameKey: 'ANTHROPIC_DEFAULT_FABLE_MODEL_NAME' },
  { role: 'Haiku', modelKey: 'ANTHROPIC_DEFAULT_HAIKU_MODEL', nameKey: 'ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME' },
  { role: 'Subagent', modelKey: 'CLAUDE_CODE_SUBAGENT_MODEL', nameKey: null },
]
const FALLBACK_MODEL_KEY = 'ANTHROPIC_MODEL'

function onModelIdChange(form, role, newValue) {
  if (!role.nameKey) return
  const currentName = form.model_config[role.nameKey] || ''
  if (!currentName || currentName === form.model_config[role.modelKey]) {
    form.model_config[role.nameKey] = newValue
  }
  form.model_config[role.modelKey] = newValue
}

useEscapeToClose(() => !props.embedded && props.visible, () => emit('close'))

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
  handleSync,
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
const addForm = ref({ name: '', host: '', api_key: '', auth_env_name: 'ANTHROPIC_API_KEY', model_config: {} })
const editForm = ref({ name: '', host: '', api_key: '', auth_env_name: 'ANTHROPIC_API_KEY', model_config: {} })
const settingsData = ref(null)
const settingsDirty = computed(() => Boolean(settings.value && settingsData.value)
  && JSON.stringify(settingsData.value) !== JSON.stringify(settings.value))
const addFormDirty = computed(() => showAddForm.value && JSON.stringify(addForm.value) !== JSON.stringify({
  name: '',
  host: '',
  api_key: '',
  auth_env_name: 'ANTHROPIC_API_KEY',
  model_config: {},
}))
const editFormDirty = computed(() => {
  if (!editingProfileId.value) return false
  const profile = profiles.value.find(item => item.profile_id === editingProfileId.value)
  if (!profile) return true
  return JSON.stringify(editForm.value) !== JSON.stringify({
    name: profile.name,
    host: profile.host || '',
    api_key: profile.api_key || '',
    auth_env_name: profile.auth_env_name || 'ANTHROPIC_API_KEY',
    model_config: { ...(profile.model_config || {}) },
  })
})
const isDirty = computed(() => settingsDirty.value || addFormDirty.value || editFormDirty.value)
watch(isDirty, value => emit('dirty-change', value), { immediate: true })

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
}, { immediate: true })

watch(() => settings.value, (val) => {
  if (val) {
    settingsData.value = JSON.parse(JSON.stringify(val))
  }
})

function cancelAdd() {
  if (addFormDirty.value && !confirm('新增渠道尚未保存，确定取消吗？')) return
  showAddForm.value = false
  addForm.value = { name: '', host: '', api_key: '', auth_env_name: 'ANTHROPIC_API_KEY', model_config: {} }
}

async function submitAdd() {
  const created = await handleCreate(addForm.value)
  if (!created) return
  addForm.value = { name: '', host: '', api_key: '', auth_env_name: 'ANTHROPIC_API_KEY', model_config: {} }
  showAddForm.value = false
}

function startEdit(profile) {
  if (editFormDirty.value && !confirm('当前渠道修改尚未保存，确定切换吗？')) return
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
  const updated = await handleUpdate(editingProfileId.value, editForm.value)
  if (!updated) return
  editingProfileId.value = null
}

function cancelEdit() {
  if (editFormDirty.value && !confirm('当前渠道修改尚未保存，确定取消吗？')) return
  editingProfileId.value = null
}

async function onDelete(profileId) {
  const profile = profiles.value.find(item => item.profile_id === profileId)
  if (!confirm(`确定删除模型渠道「${profile?.name || profileId}」吗？`)) return
  if (editingProfileId.value === profileId) {
    editingProfileId.value = null
  }
  await handleDelete(profileId)
}

async function onActivate(profileId) {
  await handleActivate(profileId)
}

async function onSync(profileId) {
  await handleSync(profileId)
}

function onFetchModelsForAdd() {
  handleFetchModels('_add', addForm.value.host, addForm.value.api_key)
}

function onFetchModelsForEdit() {
  handleFetchModels(editingProfileId.value, editForm.value.host, editForm.value.api_key)
}

const copyJsonSuccess = ref(false)

const saveSuccess = ref(false)
const { set: setTimer } = useTimeout()

async function handleSave() {
  await saveSettings(settingsData.value)
  if (!error.value) {
    saveSuccess.value = true
    setTimer(() => { saveSuccess.value = false }, 1500)
  }
}

async function copyJsonPreview() {
  try {
    await navigator.clipboard.writeText(jsonPreviewText.value)
    copyJsonSuccess.value = true
    setTimer(() => { copyJsonSuccess.value = false }, 1500)
  } catch {
    error.value = '复制配置失败，请检查浏览器剪贴板权限'
  }
}
</script>

<template>
  <Teleport to="body" :disabled="embedded">
    <div
      v-if="visible"
      :class="embedded ? 'embedded-page' : 'dialog-overlay'"
      :role="embedded ? undefined : 'dialog'"
      :aria-modal="embedded ? undefined : 'true'"
      aria-labelledby="settings-dialog-title"
      @click.self="!embedded && emit('close')"
    >
      <div :class="embedded ? 'embedded-surface' : 'dialog'">
        <div v-if="!embedded" class="dialog-header">
          <h2 id="settings-dialog-title" class="dialog-title">Claude Code 配置</h2>
          <button class="close-btn" type="button" aria-label="关闭 Claude Code 配置" @click="emit('close')">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" /></svg>
          </button>
        </div>
        <div v-else class="embedded-header">
          <div>
            <span class="eyebrow">CLAUDE CODE</span>
            <h1 id="settings-dialog-title">Claude Code 配置</h1>
            <p>管理 Claude Code 运行参数、API Host、Token 与模型渠道。</p>
          </div>
        </div>

        <div v-if="error" class="error-banner" role="alert">{{ error }}</div>

        <div v-if="loading" class="loading-state">
          <div class="spinner"></div>
          正在加载配置…
        </div>

        <div v-else class="dialog-body">
          <!-- Section 1: Channel Profiles -->
          <div class="section">
            <div class="section-header">
              <h3 class="section-title">模型渠道</h3>
              <button v-if="!showAddForm" class="btn-add" type="button" @click="showAddForm = true">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                添加渠道
              </button>
            </div>

            <div v-if="showAddForm" class="channel-form">
              <div class="form-section-label">基本信息</div>
              <div class="form-grid">
                <div class="form-group">
                  <label class="form-label">名称 <span class="required">*</span></label>
                  <input class="form-input" v-model="addForm.name" placeholder="例如：生产环境" />
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
                  <label class="form-label">认证环境变量</label>
                  <CustomSelect v-model="addForm.auth_env_name" :options="AUTH_ENV_OPTIONS" />
                </div>
              </div>

              <div class="form-section-label">
                模型配置
                <button
                  class="btn-fetch"
                  :disabled="fetchingModels === '_add'"
                  @click="onFetchModelsForAdd"
                >
                  <svg v-if="fetchingModels !== '_add'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                  </svg>
                  {{ fetchingModels === '_add' ? '获取中…' : '获取模型' }}
                </button>
                <span v-if="(fetchedModels['_add'] || []).length" class="fetch-count">
                  可用 {{ fetchedModels['_add'].length }} 个
                </span>
              </div>
              <div class="model-grid model-grid--3col">
                <div class="model-grid-header">角色</div>
                <div class="model-grid-header">显示名称</div>
                <div class="model-grid-header">Model ID</div>

                <div class="model-field-label">兜底模型</div>
                <div class="model-field-cell model-field-cell--disabled">
                  <span class="model-field-hint">覆盖全部角色</span>
                </div>
                <div class="model-field-cell">
                  <select
                    v-if="(fetchedModels['_add'] || []).length"
                    class="form-select"
                    v-model="addForm.model_config[FALLBACK_MODEL_KEY]"
                  >
                    <option value="">-- 无 --</option>
                    <option v-for="opt in getModelOptions('_add')" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                  </select>
                  <input v-else class="form-input" v-model="addForm.model_config[FALLBACK_MODEL_KEY]" placeholder="ANTHROPIC_MODEL" />
                </div>

                <template v-for="r in MODEL_ROLES" :key="r.modelKey">
                  <div class="model-field-label">{{ r.role }}</div>
                  <div class="model-field-cell" :class="{ 'model-field-cell--disabled': !r.nameKey }">
                    <input v-if="r.nameKey" class="form-input" v-model="addForm.model_config[r.nameKey]" placeholder="显示名称" />
                    <span v-else class="model-field-hint">不显示在 /model 菜单</span>
                  </div>
                  <div class="model-field-cell">
                    <select
                      v-if="(fetchedModels['_add'] || []).length"
                      class="form-select"
                      :value="addForm.model_config[r.modelKey] || ''"
                      @change="onModelIdChange(addForm, r, $event.target.value)"
                    >
                      <option value="">-- 无 --</option>
                      <option v-for="opt in getModelOptions('_add')" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                    </select>
                    <input
                      v-else
                      class="form-input"
                      :value="addForm.model_config[r.modelKey] || ''"
                      @input="onModelIdChange(addForm, r, $event.target.value)"
                      :placeholder="r.modelKey"
                    />
                  </div>
                </template>
              </div>

              <div class="form-actions">
                <button class="btn-save" type="button" :disabled="!addForm.name.trim()" @click="submitAdd">创建</button>
                <button class="btn-cancel" type="button" @click="cancelAdd">取消</button>
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
                        <span v-if="p.is_active" class="active-badge">当前启用</span>
                      </div>
                      <span class="channel-host">{{ p.host || 'https://api.anthropic.com (default)' }}</span>
                    </div>
                    <div class="channel-actions">
                      <button
                        v-if="!p.is_active"
                        class="btn-activate"
                        :disabled="operating === p.profile_id"
                        @click="onActivate(p.profile_id)"
                      >启用</button>
                      <button
                        class="btn-sync"
                        :disabled="operating === p.profile_id"
                        @click="onSync(p.profile_id)"
                      >{{ operating === p.profile_id ? '同步中…' : '同步' }}</button>
                      <button class="btn-edit" type="button" @click="startEdit(p)">编辑</button>
                      <button
                        class="btn-delete"
                        :disabled="operating === p.profile_id"
                        @click="onDelete(p.profile_id)"
                      >删除</button>
                    </div>
                  </div>
                </template>

                <template v-else>
                  <div class="channel-form channel-form--inline">
                    <div class="form-section-label">基本信息</div>
                    <div class="form-grid">
                      <div class="form-group">
                        <label class="form-label">名称 <span class="required">*</span></label>
                        <input class="form-input" v-model="editForm.name" placeholder="渠道名称" />
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
                        <label class="form-label">认证环境变量</label>
                        <CustomSelect v-model="editForm.auth_env_name" :options="AUTH_ENV_OPTIONS" />
                      </div>
                    </div>

                    <div class="form-section-label">
                      模型配置
                      <button
                        class="btn-fetch"
                        :disabled="fetchingModels === p.profile_id"
                        @click="onFetchModelsForEdit"
                      >
                        <svg v-if="fetchingModels !== p.profile_id" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                        </svg>
                        {{ fetchingModels === p.profile_id ? '获取中…' : '获取模型' }}
                      </button>
                      <span v-if="(fetchedModels[p.profile_id] || []).length" class="fetch-count">
                        可用 {{ fetchedModels[p.profile_id].length }} 个
                      </span>
                    </div>
                    <div class="model-grid model-grid--3col">
                      <div class="model-grid-header">角色</div>
                      <div class="model-grid-header">显示名称</div>
                      <div class="model-grid-header">Model ID</div>

                      <div class="model-field-label">兜底模型</div>
                      <div class="model-field-cell model-field-cell--disabled">
                        <span class="model-field-hint">覆盖全部角色</span>
                      </div>
                      <div class="model-field-cell">
                        <select
                          v-if="(fetchedModels[p.profile_id] || []).length"
                          class="form-select"
                          v-model="editForm.model_config[FALLBACK_MODEL_KEY]"
                        >
                          <option value="">-- 无 --</option>
                          <option v-for="opt in getModelOptions(p.profile_id)" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                        </select>
                        <input v-else class="form-input" v-model="editForm.model_config[FALLBACK_MODEL_KEY]" placeholder="ANTHROPIC_MODEL" />
                      </div>

                      <template v-for="r in MODEL_ROLES" :key="r.modelKey">
                        <div class="model-field-label">{{ r.role }}</div>
                        <div class="model-field-cell" :class="{ 'model-field-cell--disabled': !r.nameKey }">
                          <input v-if="r.nameKey" class="form-input" v-model="editForm.model_config[r.nameKey]" placeholder="显示名称" />
                          <span v-else class="model-field-hint">不显示在 /model 菜单</span>
                        </div>
                        <div class="model-field-cell">
                          <select
                            v-if="(fetchedModels[p.profile_id] || []).length"
                            class="form-select"
                            :value="editForm.model_config[r.modelKey] || ''"
                            @change="onModelIdChange(editForm, r, $event.target.value)"
                          >
                            <option value="">-- 无 --</option>
                            <option v-for="opt in getModelOptions(p.profile_id)" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                          </select>
                          <input
                            v-else
                            class="form-input"
                            :value="editForm.model_config[r.modelKey] || ''"
                            @input="onModelIdChange(editForm, r, $event.target.value)"
                            :placeholder="r.modelKey"
                          />
                        </div>
                      </template>
                    </div>

                    <div class="form-actions">
                      <button class="btn-save" type="button" :disabled="!editForm.name.trim()" @click="submitEdit">保存</button>
                      <button class="btn-cancel" type="button" @click="cancelEdit">取消</button>
                    </div>
                  </div>
                </template>
              </div>
            </div>

            <div v-if="!profiles.length && !showAddForm" class="empty-channels">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="opacity: 0.3">
                <rect x="2" y="7" width="20" height="14" rx="2" ry="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
              </svg>
              <span>尚未配置模型渠道</span>
            </div>
          </div>

          <!-- Section 2: Settings Configuration -->
          <div class="section">
            <div class="section-header">
              <h3 class="section-title">运行配置</h3>
              <button class="btn-preview" type="button" :class="{ active: showJsonPreview }" :aria-expanded="showJsonPreview" @click="showJsonPreview = !showJsonPreview" title="切换 JSON 预览">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              </button>
            </div>
            <Transition name="preview-slide">
              <div v-if="showJsonPreview" class="json-preview-wrapper">
                <button class="json-copy-btn" type="button" :class="{ copied: copyJsonSuccess }" @click="copyJsonPreview" title="复制 JSON" aria-label="复制 JSON 配置">
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
                  <label class="field-label">权限模式</label>
                  <span class="field-desc">控制工具审批策略；默认模式逐次询问，绕过模式自动允许</span>
                </div>
                <CustomSelect v-model="defaultMode" :options="[{ value: 'default', label: 'Default' }, { value: 'acceptEdits', label: 'Accept Edits' }, { value: 'plan', label: 'Plan' }, { value: 'bypassPermissions', label: 'Bypass' }]" />
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">已完成引导</label>
                  <span class="field-desc">启动时跳过首次运行引导</span>
                </div>
                <label class="toggle-label">
                  <input type="checkbox" class="toggle-checkbox" v-model="hasCompletedOnboarding" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">推理强度</label>
                  <span class="field-desc">低强度更快且成本更低，高强度分析更充分</span>
                </div>
                <CustomSelect v-model="effortLevel" :options="[{ value: '', label: 'Default' }, { value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium' }, { value: 'high', label: 'High' }]" />
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">跳过危险模式提示</label>
                  <span class="field-desc">进入绕过权限模式时不再显示安全确认</span>
                </div>
                <label class="toggle-label">
                  <input type="checkbox" class="toggle-checkbox" v-model="skipDangerousPrompt" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">禁用非必要网络流量</label>
                  <span class="field-desc">关闭更新、反馈、错误上报和遥测</span>
                </div>
                <label class="toggle-label">
                  <input type="checkbox" class="toggle-checkbox" :checked="getEnvVar('CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC') === '1'" @change="setEnvVar('CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC', $event.target.checked ? '1' : '')" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">Agent 团队（实验性）</label>
                  <span class="field-desc">允许会话内多 Agent 协作</span>
                </div>
                <label class="toggle-label">
                  <input type="checkbox" class="toggle-checkbox" :checked="getEnvVar('CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS') === '1'" @change="setEnvVar('CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS', $event.target.checked ? '1' : '')" />
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                </label>
              </div>
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">工具搜索</label>
                  <span class="field-desc">启用 MCP 工具搜索与动态加载</span>
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
            <h3 class="section-title">用户偏好</h3>
            <div class="settings-card">
              <div class="field-row">
                <div class="field-info">
                  <label class="field-label">回车键行为</label>
                  <span class="field-desc">设置聊天输入框中 Enter 与 Ctrl+Enter 的行为</span>
                </div>
                <CustomSelect :model-value="enterBehavior" @update:model-value="setEnterBehavior" :options="[{ value: 'enter-send', label: 'Enter to send, Ctrl+Enter for new line' }, { value: 'ctrl-enter-send', label: 'Ctrl+Enter to send, Enter for new line' }]" :display-map="{ 'enter-send': 'Enter to send', 'ctrl-enter-send': 'Ctrl+Enter to send' }" />
              </div>
            </div>
          </div>
        </div>

        <div class="dialog-footer">
          <button
            class="btn-primary"
            type="button"
            :class="{ 'btn-primary--success': saveSuccess }"
            :disabled="saving || loading"
            @click="handleSave"
          >
            <svg v-if="saveSuccess" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            {{ saving ? '保存中…' : saveSuccess ? '已保存' : '保存配置' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.embedded-page,
.embedded-surface {
  width: 100%;
}

.embedded-surface {
  padding: 24px;
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
  background: var(--glass-bg);
}

.embedded-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
}

.embedded-header h1 {
  margin: 4px 0 7px;
  color: var(--text-primary);
  font-size: 22px;
  letter-spacing: -.02em;
}

.embedded-header p {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}

.eyebrow {
  color: var(--accent);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .14em;
}

.embedded-surface .dialog-body {
  padding: 0;
  overflow: visible;
}

.embedded-surface .dialog-footer {
  margin: 20px -24px -24px;
  padding: 14px 24px;
}

.dialog-overlay {
  background: var(--dialog-overlay);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.dialog {
  width: 720px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  background: var(--dialog-surface);
  border: 1px solid var(--dialog-border);
  border-radius: var(--dialog-radius);
  box-shadow: var(--dialog-shadow);
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.dialog-header {
  border-bottom: 1px solid var(--dialog-divider);
  background: transparent;
}

.close-btn {
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
  animation: spin 0.6s linear infinite;
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

.model-grid--3col {
  grid-template-columns: 80px 1fr 1fr;
  gap: 8px 12px;
  align-items: center;
}

.model-grid-header {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.model-field-cell {
  min-width: 0;
}

.model-field-cell .form-input,
.model-field-cell .form-select {
  width: 100%;
}

.model-field-cell--disabled {
  opacity: 0.5;
}

.model-field-hint {
  font-size: 11px;
  font-style: italic;
  color: var(--text-muted);
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

.btn-sync {
  font-size: 12px;
  padding: 4px 12px;
  border: 1px solid var(--blue, #58a6ff);
  color: var(--blue, #58a6ff);
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.btn-sync:hover {
  background: var(--blue-dim, rgba(88, 166, 255, 0.1));
}

.btn-sync:disabled {
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

.settings-card .form-input {
  width: 100%;
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

@media (max-width: 720px) {
  .embedded-surface { padding: 16px; }
  .form-grid { grid-template-columns: 1fr; }
  .form-group--full { grid-column: auto; }
  .model-grid--3col { grid-template-columns: 84px minmax(150px, 1fr) minmax(210px, 1fr); min-width: 500px; }
  .channel-form { padding: 14px; overflow-x: auto; }
  .channel-row { align-items: stretch; flex-direction: column; gap: 12px; }
  .channel-actions { flex-wrap: wrap; }
  .channel-actions button { min-height: 40px; flex: 1; }
  .settings-card .field-row { align-items: stretch; flex-direction: column; }
  .form-input, .form-select { font-size: 16px; }
  .dialog-footer { position: sticky; bottom: 0; margin: 20px -16px -16px !important; padding: 12px 16px !important; background: var(--layer-base); z-index: 2; }
  .json-copy-btn { opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .btn-primary, .json-copy-btn { transition: none; }
  .btn-primary:hover:not(:disabled) { transform: none; }
}
</style>
