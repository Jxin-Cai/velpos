<script setup>
import { ref, watch, computed } from 'vue'
import { useEvolution } from '../model/useEvolution'
import { useDialogManager, useVisibleProxy, useEscapeToClose } from '@shared/lib/useDialogManager'

const props = defineProps({
  visible: { type: Boolean, default: false },
  projectId: { type: String, default: '' },
  projectDir: { type: String, default: '' },
  sessionId: { type: String, default: '' },
})
const emit = defineEmits(['close', 'draft-created'])

const { useDialog } = useDialogManager()
useDialog('evolution', useVisibleProxy(props, emit))

const target = ref('claude')
const rulePath = ref('')
const rulePathsText = ref('')
const canCreate = computed(() => {
  if (loading.value || saving.value || lessons.value.length === 0) return false
  if (target.value === 'rule') return Boolean(rulePath.value.trim())
  return true
})

const {
  loading,
  saving,
  error,
  lessons,
  createdDraft,
  extract,
  updateLesson,
  removeLesson,
  createClaudeDraft,
  createRuleDraft,
  reset,
} = useEvolution()

watch(() => props.visible, (v) => {
  if (v) {
    target.value = 'claude'
    rulePath.value = ''
    rulePathsText.value = ''
    reset()
    extract({ projectId: props.projectId, projectDir: props.projectDir, sessionId: props.sessionId })
  }
})

useEscapeToClose(() => props.visible, () => emit('close'))

async function handleCreateDraft() {
  if (target.value === 'rule') {
    const data = await createRuleDraft({ path: rulePath.value, pathsText: rulePathsText.value })
    if (data?.ruleDraft) {
      emit('draft-created', { type: 'rule', ruleDraft: data.ruleDraft })
    }
    return
  }

  const data = await createClaudeDraft(props.projectDir)
  if (data?.revision) {
    emit('draft-created', { type: 'claude', revision: data.revision })
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="evolution-overlay" @click.self="emit('close')" role="dialog" aria-modal="true" aria-labelledby="evolution-dialog-title">
        <div class="evolution-dialog">
          <div class="evolution-header">
            <div>
              <h3 id="evolution-dialog-title">Evolution</h3>
              <p>Extract reusable lessons from this session and turn them into a CLAUDE.md version or rule draft</p>
            </div>
            <button class="close-btn" type="button" aria-label="Close Evolution" @click="emit('close')">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" /></svg>
            </button>
          </div>

          <div v-if="error" class="notice">{{ error }}</div>
          <div v-if="createdDraft?.type === 'claude'" class="success">
            Version created: v{{ createdDraft.revision?.version_no }}. Open Rule to review and apply.
          </div>
          <div v-else-if="createdDraft?.type === 'rule'" class="success">
            Rule draft created. Open Rule to review and save.
          </div>

          <div class="evolution-body">
            <div class="target-panel">
              <button class="target-btn" :class="{ active: target === 'claude' }" @click="target = 'claude'">CLAUDE.md</button>
              <button class="target-btn" :class="{ active: target === 'rule' }" @click="target = 'rule'">Rule</button>
            </div>

            <div v-if="target === 'rule'" class="rule-config">
              <input
                v-model="rulePath"
                class="rule-input"
                placeholder="Rule path, e.g. frontend.md or vue/components.md"
              />
              <textarea
                v-model="rulePathsText"
                class="rule-input rule-paths"
                placeholder="paths globs, one per line. Empty means global."
              ></textarea>
            </div>

            <div class="evolution-actions">
              <button class="secondary-btn" :disabled="loading" @click="extract({ projectId, projectDir, sessionId })">
                {{ loading ? 'Extracting...' : 'Re-extract' }}
              </button>
              <button class="primary-btn" :disabled="!canCreate" @click="handleCreateDraft">
                {{ saving ? 'Creating...' : target === 'rule' ? 'Generate Rule Draft' : 'Generate CLAUDE.md Version' }}
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
  </Teleport>
</template>

<style scoped>
.evolution-overlay { position: fixed; inset: 0; z-index: 100; padding: var(--dialog-gutter); background: var(--dialog-overlay); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; }
.evolution-dialog { width: 860px; max-width: 100%; max-height: calc(100dvh - (var(--dialog-gutter) * 2)); background: var(--dialog-surface); border: 1px solid var(--dialog-border); border-radius: var(--dialog-radius); box-shadow: var(--dialog-shadow); overflow: hidden; display: flex; flex-direction: column; }
.evolution-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--border); }
.evolution-header h3 { margin: 0; font-size: 15px; color: var(--text-primary); }
.evolution-header p { margin: 3px 0 0; font-size: 12px; color: var(--text-muted); max-width: 560px; }
.close-btn { flex: 0 0 36px; border: 1px solid transparent; background: transparent; color: var(--text-muted); cursor: pointer; }
.notice { padding: 8px 18px; color: var(--danger, #ef4444); background: var(--bg-tertiary); border-bottom: 1px solid var(--border); font-size: 12px; }
.success { padding: 8px 18px; color: var(--success, #22c55e); background: var(--bg-tertiary); border-bottom: 1px solid var(--border); font-size: 12px; }
.evolution-body { padding: 14px; overflow-y: auto; min-height: 460px; }
.target-panel { display: flex; gap: 8px; margin-bottom: 12px; }
.target-btn { border: 1px solid var(--border); background: transparent; color: var(--text-secondary); border-radius: var(--radius-sm); padding: 7px 12px; cursor: pointer; }
.target-btn.active { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }
.rule-config { display: grid; gap: 8px; margin-bottom: 12px; }
.rule-input { border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-primary); color: var(--text-primary); padding: 8px 10px; font-family: var(--font-sans); }
.rule-paths { min-height: 72px; resize: vertical; }
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
