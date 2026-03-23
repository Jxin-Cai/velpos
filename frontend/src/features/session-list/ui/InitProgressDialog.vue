<script setup>
import { ref, computed, watch } from 'vue'
import { initAgent, getInitStatus } from '@entities/project'
import { getSession } from '@entities/session'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
  projectId: {
    type: String,
    default: '',
  },
  projectName: {
    type: String,
    default: '',
  },
  agentType: {
    type: String,
    default: '',
  },
  agentInitStatus: {
    type: String,
    default: 'none',
  },
  agentInitSessionId: {
    type: String,
    default: '',
  },
  agents: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['close', 'done'])

const STEPS = [
  { key: 'check', label: '检查运行环境', desc: '验证 Node.js / npm 是否可用' },
  { key: 'claude_md', label: '写入 CLAUDE.md', desc: '生成 Agent 配置文件' },
  { key: 'session', label: '创建 Init 会话', desc: '创建或复用初始化会话' },
  { key: 'prompt', label: '发送初始化指令', desc: '向 Init 会话发送安装步骤' },
]

// Step status: 'pending' | 'running' | 'done' | 'error' | 'skipped'
const stepStates = ref({})
const error = ref(null)
const initSessionId = ref('')
const allDone = ref(false)
const alreadyInitializing = ref(false)

function resetState() {
  const states = {}
  for (const s of STEPS) states[s.key] = 'pending'
  stepStates.value = states
  error.value = null
  initSessionId.value = ''
  allDone.value = false
  alreadyInitializing.value = false
}

watch(() => props.visible, async (val) => {
  if (!val) return
  resetState()

  // Get status for this specific agent type from agents dict (preferred) or legacy props
  const agentInfo = props.agents?.[props.agentType]
  const status = agentInfo?.status || props.agentInitStatus
  const sessionId = agentInfo?.session_id || props.agentInitSessionId

  // Check current status
  if (status === 'ready') {
    // All done already
    for (const s of STEPS) stepStates.value[s.key] = 'done'
    allDone.value = true
    initSessionId.value = sessionId
    return
  }

  if (status === 'initializing') {
    // Already in progress — mark all steps done (backend has passed them)
    for (const s of STEPS) stepStates.value[s.key] = 'done'
    alreadyInitializing.value = true
    initSessionId.value = sessionId
    return
  }

  // Execute init: none or error
  await runInit()
})

async function runInit() {
  try {
    // Step 1: check (will be done by backend)
    stepStates.value.check = 'running'
    // We call initAgent which does check + write + create + prompt
    // Simulate step progression by setting steps as the backend processes

    // Actually call the backend — it does all steps synchronously (except prompt which is async)
    stepStates.value.check = 'running'

    let project
    try {
      project = await initAgent(props.projectId, props.agentType)
    } catch (e) {
      // Determine which step failed
      const msg = e.message || ''
      if (msg.includes('PREREQ') || msg.includes('Prerequisite')) {
        stepStates.value.check = 'error'
        error.value = '环境检查失败：' + msg
      } else if (msg.includes('ALREADY_RUNNING')) {
        // Already initializing — treat as success
        for (const s of STEPS) stepStates.value[s.key] = 'done'
        alreadyInitializing.value = true
        // Try to get session id from status
        try {
          const status = await getInitStatus(props.projectId)
          const agentInfo = status.agents?.[props.agentType]
          initSessionId.value = agentInfo?.session_id || status.agent_init_session_id || ''
        } catch {}
        return
      } else {
        stepStates.value.check = 'error'
        error.value = msg
      }
      return
    }

    // All backend steps succeeded
    stepStates.value.check = 'done'
    stepStates.value.claude_md = 'done'
    stepStates.value.session = 'done'
    stepStates.value.prompt = 'done'

    // Extract init session id from the agents dict (preferred) or legacy field
    const agentInfo = project.agents?.[props.agentType]
    initSessionId.value = agentInfo?.session_id || project.agent_init_session_id || ''

    // Notify parent to update project in list
    emit('done', project)
  } catch (e) {
    error.value = e.message || '初始化失败'
  }
}

function handleGoToSession() {
  if (initSessionId.value) {
    // Auto-complete init when navigating to init session
    emit('done', {
      id: props.projectId,
      agent_type: props.agentType,
      agent_init_status: 'ready',
      agent_init_session_id: initSessionId.value,
    })
    emit('close', { navigateTo: initSessionId.value })
  }
}

function handleClose() {
  emit('close', {})
}

function handleOverlayClick(e) {
  if (e.target === e.currentTarget) {
    handleClose()
  }
}

const isAnyRunning = computed(() =>
  Object.values(stepStates.value).some(s => s === 'running')
)

function stepIcon(state) {
  switch (state) {
    case 'done': return '✓'
    case 'running': return ''
    case 'error': return '✗'
    case 'skipped': return '–'
    default: return ''
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="dialog-overlay"
      @click="handleOverlayClick"
      role="dialog"
      aria-modal="true"
      aria-label="Agent Init Progress"
    >
      <div class="dialog">
        <div class="dialog-header">
          <h2 class="dialog-title">Agent 初始化 — {{ projectName }}</h2>
          <button class="close-btn" @click="handleClose" :disabled="isAnyRunning">&times;</button>
        </div>

        <div class="dialog-body">
          <!-- Already ready -->
          <div v-if="allDone" class="status-banner done-banner">
            所有初始化步骤已完成。
          </div>

          <!-- Already initializing -->
          <div v-if="alreadyInitializing && !allDone" class="status-banner info-banner">
            初始化正在进行中，请前往 Init 会话跟进执行步骤。
          </div>

          <!-- Error -->
          <div v-if="error" class="status-banner error-banner">
            {{ error }}
          </div>

          <!-- Steps list -->
          <div class="steps-list">
            <div
              v-for="step in STEPS"
              :key="step.key"
              class="step-item"
              :class="'step-' + stepStates[step.key]"
            >
              <div class="step-icon">
                <span v-if="stepStates[step.key] === 'running'" class="spinner"></span>
                <span v-else class="step-icon-text">{{ stepIcon(stepStates[step.key]) }}</span>
              </div>
              <div class="step-content">
                <div class="step-label">{{ step.label }}</div>
                <div class="step-desc">{{ step.desc }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="dialog-footer">
          <button v-if="!isAnyRunning" class="btn-ghost" @click="handleClose">
            关闭
          </button>
          <button
            v-if="initSessionId && !isAnyRunning"
            class="btn-primary"
            @click="handleGoToSession"
          >
            前往 Init 会话
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
  max-height: calc(100vh - 64px);
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  display: flex;
  flex-direction: column;
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.dialog-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
}

.close-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 20px;
  cursor: pointer;
  transition: all 0.15s;
}

.close-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.close-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.dialog-body {
  padding: 16px 20px;
  overflow-y: auto;
}

.status-banner {
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  margin-bottom: 16px;
}

.done-banner {
  background: var(--green-dim, rgba(52, 211, 153, 0.1));
  color: var(--green);
}

.info-banner {
  background: var(--accent-dim);
  color: var(--accent);
}

.error-banner {
  background: var(--red-dim);
  color: var(--red);
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  transition: background 0.15s;
}

.step-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 700;
}

.step-pending .step-icon {
  border: 2px solid var(--border);
  color: var(--text-muted);
}

.step-running .step-icon {
  border: 2px solid var(--accent);
}

.step-done .step-icon {
  background: var(--green-dim, rgba(52, 211, 153, 0.15));
  color: var(--green);
  border: 2px solid var(--green);
}

.step-error .step-icon {
  background: var(--red-dim);
  color: var(--red);
  border: 2px solid var(--red);
}

.step-content {
  flex: 1;
  min-width: 0;
}

.step-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.step-pending .step-label {
  color: var(--text-muted);
}

.step-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 1px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.btn-ghost {
  padding: 7px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-ghost:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.btn-primary {
  padding: 7px 14px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: var(--text-on-accent);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: filter 0.15s, transform 0.15s;
  box-shadow: var(--shadow-sm);
}

.btn-primary:hover {
  filter: brightness(1.1);
  transform: translateY(-1px);
}

.spinner {
  display: block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
