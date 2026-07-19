<script setup>
import { ref, watch } from 'vue'
import { useEscapeToClose } from '@shared/lib/useDialogManager'

const props = defineProps({
  visible: { type: Boolean, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

useEscapeToClose(() => props.visible, () => emit('cancel'))

const title = ref('')
const description = ref('')
const submitting = ref(false)

watch(() => props.visible, (val) => {
  if (!val) {
    title.value = ''
    description.value = ''
    submitting.value = false
  }
})

async function handleConfirm() {
  if (!title.value.trim() || submitting.value) return
  submitting.value = true
  emit('confirm', {
    title: title.value.trim(),
    description: description.value.trim(),
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
      aria-labelledby="create-card-title"
    >
      <div class="dialog">
        <header class="dialog-header">
          <h2 id="create-card-title" class="dialog-title">New Wish Card</h2>
          <button class="close-btn" type="button" aria-label="Close" @click="handleCancel">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" /></svg>
          </button>
        </header>

        <div class="dialog-body">
          <div class="form-group">
            <label class="form-label" for="card-title-input">Title <span class="required">*</span></label>
            <input
              id="card-title-input"
              v-model="title"
              type="text"
              class="form-input"
              placeholder="What do you wish to accomplish?"
              autofocus
              @keydown.enter="handleConfirm"
            />
          </div>
          <div class="form-group">
            <label class="form-label" for="card-desc-input">Description</label>
            <textarea
              id="card-desc-input"
              v-model="description"
              class="form-input form-textarea"
              placeholder="Optional context or acceptance criteria..."
              rows="3"
            ></textarea>
          </div>
        </div>

        <footer class="dialog-actions">
          <button class="btn-ghost" @click="handleCancel" :disabled="submitting">Cancel</button>
          <button class="btn-primary" @click="handleConfirm" :disabled="!title.trim() || submitting">
            <span v-if="submitting" class="spinner"></span>
            {{ submitting ? 'Creating...' : 'Create' }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--dialog-overlay);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  padding: 16px;
}

.dialog {
  width: 440px;
  max-width: calc(100vw - 32px);
  background: var(--dialog-surface);
  border: 1px solid var(--dialog-border);
  border-radius: var(--dialog-radius);
  box-shadow: var(--dialog-shadow);
  display: flex;
  flex-direction: column;
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px 0;
}

.dialog-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.close-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.close-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.dialog-body {
  padding: 18px 22px;
}

.form-group {
  margin-bottom: 14px;
}

.form-group:last-child {
  margin-bottom: 0;
}

.form-label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.required {
  color: var(--red);
}

.form-input {
  width: 100%;
  padding: 8px 10px;
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

.form-input::placeholder {
  color: var(--text-muted);
}

.form-textarea {
  resize: vertical;
  min-height: 60px;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 22px;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
  border-radius: 0 0 var(--dialog-radius) var(--dialog-radius);
}

.btn-ghost {
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
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
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: filter var(--transition-fast);
  box-shadow: var(--shadow-sm);
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.1);
}

.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
