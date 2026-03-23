<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits(['confirm', 'cancel'])

const projectName = ref('')
const githubUrl = ref('')
const creating = ref(false)
const nameInput = ref(null)

watch(() => props.visible, (val) => {
  if (val) {
    nextTick(() => {
      nameInput.value?.focus()
    })
  } else {
    projectName.value = ''
    githubUrl.value = ''
    creating.value = false
  }
})

function extractRepoName(url) {
  if (!url) return ''
  // Handle URLs like https://github.com/user/repo.git or git@github.com:user/repo.git
  const match = url.match(/\/([^/]+?)(?:\.git)?$/)
  return match ? match[1] : ''
}

function handleGithubUrlInput() {
  // Auto-fill project name from URL if name is empty or was auto-filled
  const extracted = extractRepoName(githubUrl.value)
  if (extracted && (!projectName.value || projectName.value === extractRepoName(githubUrl.value.slice(0, -1)))) {
    projectName.value = extracted
  }
}

function handleConfirm() {
  if (!projectName.value.trim() || creating.value) return
  creating.value = true
  emit('confirm', {
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

        <div class="form-group">
          <label class="form-label" for="github-url">
            GitHub URL
          </label>
          <input
            id="github-url"
            v-model="githubUrl"
            type="text"
            class="form-input"
            placeholder="https://github.com/user/repo.git"
            @input="handleGithubUrlInput"
          />
          <div class="form-hint">Optional. Clone from a GitHub repository (supports private repos via local Git config).</div>
        </div>

        <div class="form-group">
          <label class="form-label" for="project-name">
            Project Name <span class="required">*</span>
          </label>
          <input
            id="project-name"
            ref="nameInput"
            v-model="projectName"
            type="text"
            class="form-input"
            placeholder="e.g. my-awesome-project"
            @keydown.enter="handleConfirm"
          />
        </div>

        <div class="dialog-actions">
          <button
            class="btn-ghost"
            @click="handleCancel"
            :disabled="creating"
          >
            Cancel
          </button>
          <button
            class="btn-primary"
            @click="handleConfirm"
            :disabled="!projectName.trim() || creating"
          >
            <span v-if="creating" class="spinner"></span>
            {{ creating ? (githubUrl ? 'Cloning...' : 'Creating...') : 'Create' }}
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
  width: 440px;
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
  transition:
    background var(--transition-fast),
    color var(--transition-fast),
    border-color var(--transition-fast);
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
  transition:
    filter var(--transition-fast),
    transform var(--transition-spring),
    box-shadow var(--transition-fast);
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
