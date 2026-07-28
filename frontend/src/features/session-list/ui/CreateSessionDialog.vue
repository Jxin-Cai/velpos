<script setup>
import { ref, watch, nextTick } from 'vue'
import { useEscapeToClose } from '@shared/lib/useDialogManager'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits(['confirm', 'cancel'])

useEscapeToClose(() => props.visible, () => emit('cancel'))

const agentName = ref('')
const githubUrl = ref('')
const creating = ref(false)
const primaryInput = ref(null)

watch(() => props.visible, (val) => {
  if (val) {
    nextTick(() => {
      primaryInput.value?.focus()
    })
  } else {
    agentName.value = ''
    githubUrl.value = ''
    creating.value = false
  }
})

function handleConfirm() {
  if (creating.value) return
  creating.value = true
  emit('confirm', {
    name: agentName.value.trim(),
    githubUrl: githubUrl.value.trim(),
  })
}

function handleCancel() {
  emit('cancel')
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="dialog-overlay"
      @click.self="handleCancel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-project-dialog-title"
    >
      <div class="dialog">
        <h2 id="create-project-dialog-title" class="dialog-title">New Agent</h2>

        <div class="form-group">
          <label class="form-label" for="agent-name">Agent Name</label>
          <input
            id="agent-name"
            ref="primaryInput"
            v-model="agentName"
            type="text"
            class="form-input"
            placeholder="Optional display name"
          />
          <div class="form-hint">
            If omitted, the GitHub repository name or generated workspace folder name will be shown.
          </div>
        </div>

        <div class="form-group">
          <label class="form-label" for="github-url">GitHub URL</label>
          <input
            id="github-url"
            v-model="githubUrl"
            type="text"
            class="form-input"
            placeholder="https://github.com/user/repository.git"
            @keydown.enter="handleConfirm"
          />
          <div class="form-hint">
            Optional. The repository will be cloned under ~/.velpos/agents.
          </div>
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
            :disabled="creating"
          >
            <span v-if="creating" class="spinner"></span>
            {{ creating ? 'Creating...' : 'Create' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.dialog {
  width: 520px;
  max-width: calc(100vw - 32px);
  background: var(--dialog-surface);
  border: 1px solid var(--dialog-border);
  border-radius: var(--dialog-radius);
  padding: 24px;
  box-shadow: var(--dialog-shadow);
}

.dialog-title {
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
  animation: spin 0.6s linear infinite;
}
</style>
