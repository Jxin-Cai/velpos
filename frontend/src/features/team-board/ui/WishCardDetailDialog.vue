<script setup>
import { ref, watch } from 'vue'
import { useEscapeToClose } from '@shared/lib/useDialogManager'
import { getExecutionHistory, getTeamArtifactUrl } from '../api/teamBoardApi'

const props = defineProps({
  visible: { type: Boolean, required: true },
  card: { type: Object, required: true },
  projectId: { type: String, required: true },
})

const emit = defineEmits(['close', 'navigate'])

useEscapeToClose(() => props.visible, () => emit('close'))

const history = ref([])
const loading = ref(false)

watch(() => props.visible, async (isVisible) => {
  if (!isVisible) return
  const executionId = props.card.execution_id
  if (!executionId) {
    history.value = []
    return
  }
  loading.value = true
  try {
    const res = await getExecutionHistory(executionId)
    history.value = Array.isArray(res?.data) ? res.data : []
  } catch {
    history.value = []
  } finally {
    loading.value = false
  }
}, { immediate: true })

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function artifactHref(artifact) {
  return getTeamArtifactUrl(props.projectId, artifact.path)
}

function contentItems(output, key) {
  return Array.isArray(output?.content?.[key]) ? output.content[key] : []
}

function shortChecksum(value) {
  return value ? value.slice(0, 12) : '—'
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="detail-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="wish-card-detail-title"
      @click.self="emit('close')"
    >
      <section class="detail-dialog">
        <header class="detail-header">
          <div class="detail-heading">
            <span class="detail-eyebrow">Wish card execution chain</span>
            <h2 id="wish-card-detail-title">{{ card.title }}</h2>
          </div>
          <button type="button" class="icon-button" aria-label="Close details" @click="emit('close')">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" /></svg>
          </button>
        </header>

        <div class="detail-body">
          <p v-if="card.description" class="detail-description">{{ card.description }}</p>

          <div v-if="history.length" class="execution-chain">
            <article v-for="(execution, index) in history" :key="execution.execution_id" class="execution-step">
              <div class="execution-rail" aria-hidden="true">
                <span class="execution-index">{{ index + 1 }}</span>
                <span v-if="index < history.length - 1" class="execution-line"></span>
              </div>
              <div class="execution-content">
                <div class="execution-title-row">
                  <strong>{{ execution.agent_name }}</strong>
                  <span class="execution-status" :data-status="execution.status">{{ execution.status }}</span>
                </div>

                <button
                  v-if="execution.session_id"
                  type="button"
                  class="session-link"
                  @click="emit('navigate', execution.session_id)"
                >
                  <span>Session {{ execution.session_id }}</span>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                </button>
                <span v-else class="session-empty">Session not created</span>
                <span v-if="execution.sdk_session_id" class="sdk-session-id">
                  Claude {{ execution.sdk_session_id }}
                </span>

                <dl class="execution-meta">
                  <div><dt>Started</dt><dd>{{ formatDate(execution.started_at || execution.created_at) }}</dd></div>
                  <div><dt>Finished</dt><dd>{{ formatDate(execution.ended_at) }}</dd></div>
                  <div><dt>Execution ID</dt><dd>{{ execution.execution_id }}</dd></div>
                </dl>

                <p v-if="execution.failure_reason" class="execution-failure">{{ execution.failure_reason }}</p>

                <details v-if="execution.output" class="stage-output">
                  <summary>
                    <span>
                      <span class="stage-output__label">Passed to the next stage</span>
                      <span class="stage-output__version">
                        v{{ execution.output.revision }} · {{ shortChecksum(execution.output.checksum) }}
                      </span>
                    </span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                      <path d="m6 9 6 6 6-6" />
                    </svg>
                  </summary>
                  <div class="stage-output__body">
                    <section v-if="execution.output.content?.stage_summary">
                      <h3>Stage result</h3>
                      <p>{{ execution.output.content.stage_summary }}</p>
                    </section>
                    <section
                      v-for="[label, key] in [
                        ['Completed', 'completed_work'],
                        ['Decisions', 'decisions'],
                        ['Deliverables', 'deliverables'],
                        ['Validation', 'validation'],
                        ['Open items', 'unresolved_issues'],
                        ['Risks', 'risks'],
                      ]"
                      v-show="contentItems(execution.output, key).length"
                      :key="key"
                    >
                      <h3>{{ label }}</h3>
                      <ul>
                        <li v-for="item in contentItems(execution.output, key)" :key="item">{{ item }}</li>
                      </ul>
                    </section>
                    <section v-if="execution.output.content?.next_stage_brief">
                      <h3>Next stage</h3>
                      <p>{{ execution.output.content.next_stage_brief }}</p>
                    </section>
                    <div v-if="execution.output.artifacts?.length" class="artifact-list">
                      <a
                        v-for="artifact in execution.output.artifacts"
                        :key="artifact.id || artifact.path"
                        :href="artifactHref(artifact)"
                        target="_blank"
                        rel="noopener noreferrer"
                      >{{ artifact.name }}</a>
                    </div>
                  </div>
                </details>

                <div v-if="execution.handoff" class="handoff-block">
                  <span class="handoff-label">Input consumed from {{ execution.handoff.source_agent_name }}</span>
                  <span v-if="execution.handoff.stage_output_id" class="handoff-snapshot">
                    Snapshot {{ execution.handoff.stage_output_id }}
                  </span>
                  <div v-if="execution.handoff.artifacts?.length" class="artifact-list">
                    <a
                      v-for="artifact in execution.handoff.artifacts"
                      :key="artifact.path"
                      :href="artifactHref(artifact)"
                      target="_blank"
                      rel="noopener noreferrer"
                    >{{ artifact.name }}</a>
                  </div>
                </div>
              </div>
            </article>
          </div>
          <div v-else class="empty-chain">This card has not started an execution yet.</div>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: var(--dialog-overlay);
  backdrop-filter: blur(6px);
}

.detail-dialog {
  width: min(680px, calc(100vw - 32px));
  max-height: min(760px, calc(100vh - 40px));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--dialog-border);
  border-radius: var(--dialog-radius);
  background: var(--dialog-surface);
  box-shadow: var(--dialog-shadow);
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.detail-heading { min-width: 0; }
.detail-eyebrow { display: block; margin-bottom: 5px; color: var(--text-muted); font-size: 11px; letter-spacing: .04em; text-transform: uppercase; }
.detail-heading h2 { margin: 0; color: var(--text-primary); font-size: 17px; font-weight: 600; line-height: 1.35; }
.icon-button { width: 32px; height: 32px; display: grid; place-items: center; flex: none; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); cursor: pointer; }
.icon-button:hover { background: var(--bg-hover); color: var(--text-primary); }
.detail-body { overflow-y: auto; padding: 18px 22px 24px; }
.detail-description { margin: 0 0 18px; color: var(--text-secondary); font-size: 13px; line-height: 1.6; white-space: pre-wrap; }
.execution-chain { display: flex; flex-direction: column; }
.execution-step { display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 10px; }
.execution-rail { display: flex; flex-direction: column; align-items: center; }
.execution-index { width: 24px; height: 24px; display: grid; place-items: center; border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--border)); border-radius: 50%; background: var(--accent-dim); color: var(--accent); font: 600 11px/1 var(--font-mono); }
.execution-line { width: 1px; flex: 1; min-height: 24px; background: var(--border); }
.execution-content { min-width: 0; padding: 1px 0 22px; }
.execution-title-row { display: flex; align-items: center; gap: 8px; }
.execution-title-row strong { flex: 1; color: var(--text-primary); font-size: 13px; }
.execution-status { padding: 2px 6px; border-radius: 999px; background: var(--bg-hover); color: var(--text-muted); font-size: 10px; text-transform: capitalize; }
.execution-status[data-status="completed"] { background: var(--status-success-bg); color: var(--status-success); }
.execution-status[data-status="failed"] { background: var(--status-danger-bg); color: var(--status-danger); }
.execution-status[data-status="running"] { background: var(--status-running-bg); color: var(--status-running); }
.session-link { display: inline-flex; align-items: center; gap: 5px; margin-top: 8px; padding: 5px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-secondary); color: var(--accent); font: 500 11px/1.2 var(--font-mono); cursor: pointer; }
.session-link:hover { border-color: var(--accent); background: var(--accent-dim); }
.session-empty { display: block; margin-top: 8px; color: var(--text-muted); font-size: 11px; }
.sdk-session-id { display: block; margin-top: 5px; color: var(--text-muted); font: 10px/1.4 var(--font-mono); overflow-wrap: anywhere; }
.execution-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 14px; margin: 12px 0 0; }
.execution-meta div:last-child { grid-column: 1 / -1; }
.execution-meta dt { color: var(--text-muted); font-size: 10px; text-transform: uppercase; }
.execution-meta dd { margin: 2px 0 0; overflow-wrap: anywhere; color: var(--text-secondary); font: 11px/1.4 var(--font-mono); }
.execution-failure { margin: 10px 0 0; padding: 8px 10px; border-left: 2px solid var(--status-danger); background: var(--status-danger-bg); color: var(--status-danger); font-size: 11px; line-height: 1.5; }
.handoff-block { margin-top: 12px; padding: 10px; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: var(--bg-tertiary); }
.handoff-label { color: var(--text-muted); font-size: 10px; text-transform: uppercase; }
.handoff-snapshot { display: block; margin-top: 5px; color: var(--text-muted); font: 10px/1.4 var(--font-mono); overflow-wrap: anywhere; }
.handoff-block p { margin: 6px 0 0; color: var(--text-secondary); font-size: 11px; line-height: 1.5; white-space: pre-wrap; }
.artifact-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.artifact-list a { color: var(--accent); font-size: 11px; text-decoration: none; }
.artifact-list a:hover { text-decoration: underline; }
.empty-chain { padding: 28px 12px; border: 1px dashed var(--border); border-radius: var(--radius-sm); color: var(--text-muted); font-size: 12px; text-align: center; }

.stage-output { margin-top: 12px; overflow: hidden; border: 1px solid color-mix(in srgb, var(--status-success) 28%, var(--border)); border-radius: var(--radius-sm); background: color-mix(in srgb, var(--status-success-bg) 55%, var(--bg-secondary)); }
.stage-output summary { min-height: 44px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 11px; color: var(--text-primary); cursor: pointer; list-style: none; }
.stage-output summary::-webkit-details-marker { display: none; }
.stage-output summary:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.stage-output summary > svg { flex: none; transition: transform var(--transition-fast); }
.stage-output[open] summary > svg { transform: rotate(180deg); }
.stage-output__label { display: block; color: var(--status-success); font-size: 11px; font-weight: 600; }
.stage-output__version { display: block; margin-top: 2px; color: var(--text-muted); font: 9px/1.4 var(--font-mono); }
.stage-output__body { padding: 0 11px 12px; border-top: 1px solid color-mix(in srgb, var(--status-success) 18%, var(--border-subtle)); }
.stage-output__body section { margin-top: 11px; }
.stage-output__body h3 { margin: 0 0 4px; color: var(--text-muted); font-size: 10px; font-weight: 600; letter-spacing: .025em; text-transform: uppercase; }
.stage-output__body p, .stage-output__body ul { margin: 0; color: var(--text-secondary); font-size: 11px; line-height: 1.55; white-space: pre-wrap; }
.stage-output__body ul { padding-left: 17px; }
.stage-output__body li + li { margin-top: 3px; }

@media (prefers-reduced-motion: reduce) {
  .stage-output summary > svg { transition: none; }
}

@media (max-width: 560px) {
  .detail-overlay { padding: 8px; }
  .detail-dialog { width: calc(100vw - 16px); max-height: calc(100vh - 16px); }
  .detail-header, .detail-body { padding-left: 16px; padding-right: 16px; }
  .execution-meta { grid-template-columns: 1fr; }
  .execution-meta div:last-child { grid-column: auto; }
}
</style>
