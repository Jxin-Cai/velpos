<script setup>
import { watch } from 'vue'
import { useEvolution } from '../model/useEvolution'
import { useDialogManager } from '@shared/lib/useDialogManager'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys'

const props = defineProps({
  visible: { type: Boolean, default: false },
  projectId: { type: String, default: '' },
  projectDir: { type: String, default: '' },
  sessionId: { type: String, default: '' },
})
const emit = defineEmits(['close', 'draft-created'])

const { useDialog } = useDialogManager()
const visibleWrapper = {
  get value() { return props.visible },
  set value(v) { if (!v) emit('close') },
}
useDialog('evolution', visibleWrapper)

const { loading, saving, error, lessons, revision, extract, updateLesson, removeLesson, createDraft, reset } = useEvolution()

watch(() => props.visible, (v) => {
  if (v) {
    reset()
    extract({ projectId: props.projectId, projectDir: props.projectDir, sessionId: props.sessionId })
  }
})

useGlobalHotkeys({
  keys: 'Escape',
  handler: () => {
    if (props.visible) {
      emit('close')
      return false
    }
    return true
  },
  priority: 100,
})

async function handleCreateDraft() {
  const data = await createDraft(props.projectDir)
  if (data?.revision) {
    emit('draft-created', data.revision)
  }
}
</script>

<template>
  <teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="evolution-overlay" @click.self="emit('close')">
        <div class="evolution-dialog">
          <div class="evolution-header">
            <div>
              <h3>Evolution</h3>
              <p>Extract reusable lessons and create a CLAUDE.md draft</p>
            </div>
            <button class="close-btn" @click="emit('close')">×</button>
          </div>

          <div v-if="error" class="notice">{{ error }}</div>
          <div v-if="revision" class="success">
            Draft created: v{{ revision.version_no }}. Open Memory to review, propose, approve and apply.
          </div>

          <div class="evolution-body">
            <div class="evolution-actions">
              <button class="secondary-btn" :disabled="loading" @click="extract({ projectId, projectDir, sessionId })">
                {{ loading ? 'Extracting...' : 'Re-extract' }}
              </button>
              <button class="primary-btn" :disabled="saving || loading || lessons.length === 0" @click="handleCreateDraft">
                {{ saving ? 'Creating...' : 'Generate CLAUDE.md Draft' }}
              </button>
            </div>

            <div v-if="loading" class="empty">Extracting lessons...</div>
            <div v-else-if="lessons.length === 0" class="empty">No lessons extracted</div>
            <div v-else class="lesson-list">
              <div v-for="(lesson, index) in lessons" :key="lesson.id || index" class="lesson-item">
                <label class="lesson-enabled">
                  <input
                    type="checkbox"
                    :checked="lesson.enabled !== false"
                    @change="updateLesson(index, { enabled: $event.target.checked })"
                  />
                </label>
                <div class="lesson-main">
                  <input
                    class="lesson-title"
                    :value="lesson.title"
                    @input="updateLesson(index, { title: $event.target.value })"
                  />
                  <textarea
                    class="lesson-content"
                    :value="lesson.content"
                    @input="updateLesson(index, { content: $event.target.value })"
                  ></textarea>
                  <div class="lesson-meta">
                    {{ lesson.type }} · {{ lesson.source_session_id || 'current scope' }}
                  </div>
                </div>
                <button class="remove-btn" @click="removeLesson(index)">Remove</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </teleport>
</template>

<style scoped>
.evolution-overlay { position: fixed; inset: 0; z-index: 100; background: var(--bg-overlay); display: flex; align-items: center; justify-content: center; }
.evolution-dialog { width: 860px; max-width: 94vw; max-height: 84vh; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-xl); overflow: hidden; display: flex; flex-direction: column; }
.evolution-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--border); }
.evolution-header h3 { margin: 0; font-size: 15px; color: var(--text-primary); }
.evolution-header p { margin: 3px 0 0; font-size: 12px; color: var(--text-muted); }
.close-btn { border: none; background: transparent; color: var(--text-muted); font-size: 24px; cursor: pointer; }
.notice { padding: 8px 18px; color: var(--danger, #ef4444); background: var(--bg-tertiary); border-bottom: 1px solid var(--border); font-size: 12px; }
.success { padding: 8px 18px; color: var(--success, #22c55e); background: var(--bg-tertiary); border-bottom: 1px solid var(--border); font-size: 12px; }
.evolution-body { padding: 14px; overflow-y: auto; min-height: 460px; }
.evolution-actions { display: flex; justify-content: flex-end; gap: 8px; margin-bottom: 12px; }
.primary-btn, .secondary-btn { border-radius: var(--radius-sm); padding: 7px 12px; cursor: pointer; }
.primary-btn { background: var(--accent); border: 1px solid var(--accent); color: var(--text-on-accent); }
.secondary-btn { background: transparent; border: 1px solid var(--border); color: var(--text-secondary); }
.primary-btn:disabled, .secondary-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.empty { color: var(--text-muted); text-align: center; padding: 40px; font-size: 13px; }
.lesson-list { display: flex; flex-direction: column; gap: 10px; }
.lesson-item { display: flex; gap: 10px; align-items: flex-start; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg-primary); }
.lesson-enabled { padding-top: 7px; }
.lesson-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.lesson-title, .lesson-content { border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-secondary); color: var(--text-primary); padding: 7px 9px; font-family: var(--font-sans); }
.lesson-title { font-weight: 600; }
.lesson-content { min-height: 74px; resize: vertical; }
.lesson-meta { color: var(--text-muted); font-size: 11px; }
.remove-btn { border: 1px solid var(--border); background: transparent; color: var(--danger, #ef4444); border-radius: var(--radius-sm); padding: 6px 9px; cursor: pointer; }
.dialog-fade-enter-active, .dialog-fade-leave-active { transition: opacity 0.15s ease; }
.dialog-fade-enter-from, .dialog-fade-leave-to { opacity: 0; }
</style>
