<script setup>
import { watch, computed } from 'vue'
import { configuredMarked } from '@features/message-display'
import { useMemoryManager } from '../model/useMemoryManager'

const props = defineProps({
  visible: { type: Boolean, default: false },
  projectDir: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const {
  content, loading, editing, editContent, saving,
  loadClaudeMd, startEdit, cancelEdit, save, reset,
} = useMemoryManager()

const renderedContent = computed(() => {
  if (!content.value) return ''
  return configuredMarked(content.value)
})

const renderedPreview = computed(() => {
  if (!editContent.value) return ''
  return configuredMarked(editContent.value)
})

watch(() => props.visible, (v) => {
  if (v && props.projectDir) {
    loadClaudeMd(props.projectDir)
  } else if (!v) {
    reset()
  }
})

async function handleSave() {
  await save(props.projectDir)
}
</script>

<template>
  <teleport to="body">
    <Transition name="dialog-fade">
    <div v-if="visible" class="memory-overlay" @click.self="emit('close')">
      <div class="memory-dialog" :class="{ 'memory-dialog--editing': editing }">
        <div class="memory-header">
          <h3 class="memory-title">CLAUDE.md</h3>
          <div class="header-actions">
            <template v-if="!editing">
              <button class="action-btn edit" @click="startEdit" :disabled="!content && !editing">Edit</button>
            </template>
            <template v-else>
              <button class="action-btn save" @click="handleSave" :disabled="saving">
                {{ saving ? 'Saving...' : 'Save' }}
              </button>
              <button class="action-btn cancel" @click="cancelEdit">Cancel</button>
            </template>
            <button class="close-btn" @click="emit('close')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>

        <div class="memory-body">
          <div v-if="loading" class="loading-state">
            <div class="spinner"></div>
            <span>Loading...</span>
          </div>

          <!-- Edit mode: split pane -->
          <template v-else-if="editing">
            <div class="split-pane">
              <div class="split-editor">
                <div class="split-label">Editor</div>
                <textarea
                  v-model="editContent"
                  class="content-editor"
                  spellcheck="false"
                ></textarea>
              </div>
              <div class="split-divider"></div>
              <div class="split-preview">
                <div class="split-label">Preview</div>
                <div class="content-rendered markdown-body" v-html="renderedPreview"></div>
              </div>
            </div>
          </template>

          <!-- View mode: rendered markdown -->
          <div v-else-if="content" class="content-rendered markdown-body" v-html="renderedContent"></div>

          <div v-else class="empty-state">(empty)</div>
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
  width: 720px; max-width: 90vw; max-height: 80vh;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  display: flex; flex-direction: column;
  overflow: hidden;
  transition: width 0.2s ease;
}
.memory-dialog--editing {
  width: 960px;
}
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
}
.header-actions {
  display: flex; align-items: center; gap: 6px;
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
  padding: 5px 14px; border-radius: var(--radius-sm);
  font-size: 12px; font-weight: 500; cursor: pointer;
  border: 1px solid var(--border); transition: all var(--transition-fast);
  font-family: var(--font-sans);
}
.action-btn.edit {
  background: transparent; color: var(--accent); border-color: var(--accent);
}
.action-btn.edit:hover { background: var(--accent-dim); }
.action-btn.edit:disabled { opacity: 0.4; cursor: not-allowed; }
.action-btn.save {
  background: var(--accent); color: var(--text-on-accent); border-color: var(--accent);
}
.action-btn.save:hover:not(:disabled) { filter: brightness(1.1); }
.action-btn.save:disabled { opacity: 0.5; cursor: not-allowed; }
.action-btn.cancel {
  background: transparent; color: var(--text-secondary);
}
.action-btn.cancel:hover { background: var(--bg-hover); }

.memory-body {
  flex: 1; overflow: hidden; display: flex; flex-direction: column;
  min-height: 400px;
}
.loading-state {
  flex: 1; display: flex; align-items: center; justify-content: center;
  gap: 8px; color: var(--text-muted); font-size: 13px;
}
.empty-state {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: var(--text-muted); font-size: 13px;
}
.spinner {
  width: 18px; height: 18px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* View mode */
.content-rendered {
  flex: 1; padding: 20px 24px;
  overflow-y: auto; font-size: 14px; line-height: 1.7;
}

/* Edit mode: split pane */
.split-pane {
  flex: 1; display: flex; overflow: hidden;
}
.split-editor, .split-preview {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; min-width: 0;
}
.split-label {
  padding: 6px 14px;
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.5px;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.split-divider {
  width: 1px; background: var(--border); flex-shrink: 0;
}
.content-editor {
  flex: 1; background: var(--bg-primary); color: var(--text-primary);
  border: none; padding: 16px;
  font-size: 13px; font-family: var(--font-mono); line-height: 1.7;
  resize: none; outline: none; overflow-y: auto;
  tab-size: 2;
}
.split-preview .content-rendered {
  padding: 16px;
  font-size: 13px;
}
</style>
