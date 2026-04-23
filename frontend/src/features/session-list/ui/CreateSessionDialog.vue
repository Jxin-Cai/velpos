<script setup>
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { pickProjectDirectory } from '@entities/project'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits(['confirm', 'cancel'])

const mode = ref('github')
const projectName = ref('')
const githubUrl = ref('')
const projectPath = ref('')
const creating = ref(false)
const picking = ref(false)
const pickerError = ref('')
const primaryInput = ref(null)

const isMac = /Mac|iPhone|iPad|iPod/.test(window.navigator.platform || window.navigator.userAgent)
const PROJECT_NAME_RE = /^[a-zA-Z0-9][a-zA-Z0-9._-]*$/

function getPathBaseName(path) {
  const trimmed = path.trim().replace(/[\\/]+$/, '')
  if (!trimmed) return ''
  const parts = trimmed.split(/[\\/]/)
  return parts[parts.length - 1] || ''
}

const resolvedProjectName = computed(() => {
  if (mode.value === 'local') return getPathBaseName(projectPath.value)
  return projectName.value.trim()
})

const nameError = computed(() => {
  if (mode.value !== 'github') return ''
  const name = projectName.value.trim()
  if (!name) return ''
  if (!PROJECT_NAME_RE.test(name)) {
    return 'Only letters, digits, hyphens, underscores, dots allowed. Must start with a letter or digit.'
  }
  return ''
})

const pathError = computed(() => {
  if (mode.value !== 'local') return ''
  return projectPath.value.trim() ? '' : 'Project path is required.'
})

const canConfirm = computed(() => {
  if (creating.value || picking.value) return false
  if (mode.value === 'local') return !!projectPath.value.trim()
  return !!projectName.value.trim() && !nameError.value
})

watch(() => props.visible, (val) => {
  if (val) {
    nextTick(() => {
      primaryInput.value?.focus()
    })
  } else {
    mode.value = 'github'
    projectName.value = ''
    githubUrl.value = ''
    projectPath.value = ''
    creating.value = false
    picking.value = false
    pickerError.value = ''
  }
})

function extractRepoName(url) {
  if (!url) return ''
  const match = url.match(/\/([^/]+?)(?:\.git)?$/)
  return match ? match[1] : ''
}

function handleGithubUrlInput() {
  const extracted = extractRepoName(githubUrl.value)
  if (extracted && (!projectName.value || projectName.value === extractRepoName(githubUrl.value.slice(0, -1)))) {
    projectName.value = extracted
  }
}

async function handlePickDirectory() {
  if (!isMac || picking.value) return
  pickerError.value = ''
  picking.value = true
  try {
    const result = await pickProjectDirectory()
    if (result?.dir_path) {
      mode.value = 'local'
      projectPath.value = result.dir_path
    }
  } catch (err) {
    pickerError.value = err.message || 'Failed to pick directory'
  } finally {
    picking.value = false
  }
}

function handleConfirm() {
  if (!canConfirm.value) return
  creating.value = true

  if (mode.value === 'local') {
    emit('confirm', {
      mode: 'local',
      name: resolvedProjectName.value,
      dirPath: projectPath.value.trim(),
    })
    return
  }

  emit('confirm', {
    mode: 'github',
    name: projectName.value.trim(),
    githubUrl: githubUrl.value.trim(),
  })
}

function handleCancel() {
  emit('cancel')
}

function handleOverlayClick(e) {
  if (e.target === e.currentTarget) {
    handleCancel()
  }
}

function handleKeydown(e) {
  if (!props.visible) return
  if (e.key === 'Escape') {
    handleCancel()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="dialog-overlay"
      @click="handleOverlayClick"
      role="dialog"
      aria-modal="true"
      aria-label="Create new project"
    >
      <div class="dialog">
        <h2 class="dialog-title">New Project</h2>

        <div class="mode-switch">
          <button
            class="mode-btn"
            :class="{ active: mode === 'github' }"
            @click="mode = 'github'"
          >
            GitHub
          </button>
          <button
            class="mode-btn"
            :class="{ active: mode === 'local' }"
            @click="mode = 'local'"
          >
            Local Folder
          </button>
        </div>

        <template v-if="mode === 'github'">
          <div class="form-group">
            <label class="form-label" for="github-url">
              GitHub URL
            </label>
            <input
              id="github-url"
              ref="primaryInput"
              v-model="githubUrl"
              type="text"
              class="form-input"
              placeholder="https://github.com/user/repo.git"
              @input="handleGithubUrlInput"
            />
            <div class="form-hint">Optional. Clone from a GitHub repository.</div>
          </div>

          <div class="form-group">
            <label class="form-label" for="project-name">
              Project Name <span class="required">*</span>
            </label>
            <input
              id="project-name"
              v-model="projectName"
              type="text"
              class="form-input"
              :class="{ 'form-input-error': nameError }"
              placeholder="e.g. my-awesome-project"
              @keydown.enter="handleConfirm"
            />
            <div v-if="nameError" class="form-error">{{ nameError }}</div>
          </div>
        </template>

        <template v-else>
          <div class="form-group">
            <label class="form-label" for="project-path">
              Project Path <span class="required">*</span>
            </label>
            <div class="path-row">
              <input
                id="project-path"
                ref="primaryInput"
                v-model="projectPath"
                type="text"
                class="form-input"
                :class="{ 'form-input-error': pathError || pickerError }"
                placeholder="/Users/you/workspace/my-project"
                @keydown.enter="handleConfirm"
              />
              <button
                v-if="isMac"
                class="btn-ghost path-picker-btn"
                @click="handlePickDirectory"
                :disabled="picking || creating"
                type="button"
              >
                {{ picking ? 'Opening...' : 'Choose Folder' }}
              </button>
            </div>
            <div class="form-hint">Use a full local path, or choose a folder with the macOS picker.</div>
            <div v-if="pathError" class="form-error">{{ pathError }}</div>
            <div v-else-if="pickerError" class="form-error">{{ pickerError }}</div>
          </div>

          <div class="form-group">
            <label class="form-label">Project Name</label>
            <div class="readonly-value" :class="{ empty: !resolvedProjectName }">
              {{ resolvedProjectName || 'Will be derived from the selected folder name' }}
            </div>
          </div>
        </template>

        <div class="dialog-actions">
          <button
            class="btn-ghost"
            @click="handleCancel"
            :disabled="creating || picking"
          >
            Cancel
          </button>
          <button
            class="btn-primary"
            @click="handleConfirm"
            :disabled="!canConfirm"
          >
            <span v-if="creating" class="spinner"></span>
            {{ creating ? (mode === 'github' ? (githubUrl ? 'Cloning...' : 'Creating...') : 'Opening...') : 'Create' }}
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
  background: var(--bg-overlay);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
}

.dialog {
  width: 520px;
  max-width: calc(100vw - 32px);
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 24px;
  box-shadow: var(--shadow-xl);
}

.dialog-title {
  font-weight: 600;
  font-size: 16px;
  color: var(--text-primary);
  margin-bottom: 20px;
}

.mode-switch {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.mode-btn {
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: background var(--transition-fast), border-color var(--transition-fast), color var(--transition-fast);
}

.mode-btn.active {
  background: var(--accent-dim);
  border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  color: var(--accent);
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.required {
  color: var(--red);
}

.path-row {
  display: flex;
  gap: 8px;
}

.path-row .form-input {
  flex: 1;
}

.path-picker-btn {
  flex-shrink: 0;
  white-space: nowrap;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  outline: none;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.form-input:focus {
  border-color: var(--accent);
  box-shadow: var(--ring);
}

.form-input::placeholder {
  color: var(--text-muted);
}

.form-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

.form-input-error {
  border-color: var(--red);
}

.form-input-error:focus {
  border-color: var(--red);
  box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.15);
}

.form-error {
  font-size: 11px;
  color: var(--red);
  margin-top: 4px;
}

.readonly-value {
  min-height: 38px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  word-break: break-all;
}

.readonly-value.empty {
  color: var(--text-muted);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 24px;
}

.btn-ghost {
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast);
}

.btn-ghost:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.btn-ghost:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

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
  transition: filter var(--transition-fast), transform var(--transition-spring), box-shadow var(--transition-fast);
  box-shadow: var(--shadow-sm);
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.1);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.btn-primary:active:not(:disabled) {
  transform: translateY(0);
}

.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--bg-primary);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
