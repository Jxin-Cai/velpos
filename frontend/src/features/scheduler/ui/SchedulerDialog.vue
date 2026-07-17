<script setup>
import { ref, watch, computed } from 'vue'
import { useSession } from '@entities/session'
import { useProject } from '@entities/project'
import { useImBinding } from '@features/im-binding'
import { fetchCommands } from '@features/command-palette/api/commandApi'
import { useScheduler } from '../model/useScheduler'
import { useDialogManager, useVisibleProxy, useEscapeToClose } from '@shared/lib/useDialogManager'

const props = defineProps({
  visible: { type: Boolean, default: false },
  projectId: { type: String, default: '' },
  sessionId: { type: String, default: '' },
})
const emit = defineEmits(['close'])

useDialogManager().useDialog('scheduler', useVisibleProxy(props, emit))

useEscapeToClose(() => props.visible, () => emit('close'))

const { sessions } = useSession()
const { projects } = useProject()
const { availableChannels, fetchChannels } = useImBinding()
const { tasks, loading, saving, error, loadSchedules, saveNewSchedule, toggleSchedule, removeSchedule, runNow } = useScheduler()

const skillCommands = ref([])
const skillLoading = ref(false)
const skillDropdownOpen = ref(false)
const skillSearch = ref('')

const projectDir = computed(() => {
  const project = projects.value.find(p => p.id === props.projectId)
  return project?.dir_path || ''
})

const filteredSkillCommands = computed(() => {
  const q = skillSearch.value.toLowerCase()
  const skills = skillCommands.value.filter(command => command.type === 'skill')
  if (!q) return skills
  return skills.filter(
    c => c.name.toLowerCase().includes(q) || (c.description || '').toLowerCase().includes(q)
  )
})

async function loadSkillCommands() {
  const dir = projectDir.value
  if (!dir) { skillCommands.value = []; return }
  skillLoading.value = true
  try {
    const data = await fetchCommands(dir)
    skillCommands.value = (data.commands || []).filter(c => c.isUserInvocable !== false)
  } catch { skillCommands.value = [] }
  finally { skillLoading.value = false }
}

function selectSkill(cmd) {
  form.value.skill_name = cmd.name
  form.value.skill_type = cmd.type || 'command'
  skillDropdownOpen.value = false
  skillSearch.value = ''
}

function clearSkill() {
  form.value.skill_name = ''
  form.value.skill_type = ''
}

const form = ref({
  name: '',
  prompt: '',
  skill_name: '',
  skill_type: '',
  prompt_mode: 'prompt',
  execution_mode: 'new_session',
  schedule_type: 'hourly',
  interval_minutes: 30,
  interval_hours: 1,
  time: '09:00',
  weekday: 0,
  session_id: '',
  channel_id: '',
  auto_unbind_after_run: true,
  delete_session_on_success: false,
})

const weekdays = [
  { value: 0, label: 'Monday' },
  { value: 1, label: 'Tuesday' },
  { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' },
  { value: 4, label: 'Friday' },
  { value: 5, label: 'Saturday' },
  { value: 6, label: 'Sunday' },
]

const projectSessions = computed(() => {
  return [...sessions.value]
    .filter(item => item.project_id === props.projectId)
    .sort((a, b) => new Date(b.updated_time || 0).getTime() - new Date(a.updated_time || 0).getTime())
})

const channelInstances = computed(() => {
  return availableChannels.value.flatMap(channel => (channel.instances || []).map(instance => ({
    ...instance,
    channel_type: channel.channel_type,
    display_name: channel.display_name,
  })))
})

const selectedChannel = computed(() => {
  return channelInstances.value.find(item => item.id === form.value.channel_id) || null
})

const scheduleDescription = computed(() => describeCron(toCronExpr(form.value)))
const selectedSkill = computed(() => {
  return skillCommands.value.find(command => command.name === form.value.skill_name) || null
})
const canSubmit = computed(() => {
  if (!props.projectId || saving.value) return false
  if (form.value.execution_mode === 'existing_session' && !form.value.session_id) return false
  if (form.value.prompt_mode === 'skill') return !!form.value.skill_name
  return !!form.value.prompt.trim()
})
const channelHint = computed(() => {
  if (!form.value.channel_id) return 'No IM channel selected. The schedule only creates and runs a local session.'
  if (selectedChannel.value?.bound_session_id) {
    return `This channel is currently bound to session ${selectedChannel.value.bound_session_id}. The run will fail until it is released.`
  }
  if (selectedChannel.value?.init_status !== 'ready') {
    return 'This channel is not ready yet. Initialize it before the schedule runs.'
  }
  return 'Each run will bind the new execution session to this IM channel and disconnect it after completion.'
})

watch(() => props.visible, (v) => {
  if (v) {
    loadSchedules(props.projectId)
    fetchChannels()
    loadSkillCommands()
  }
})

watch(() => form.value.execution_mode, (mode) => {
  if (mode === 'existing_session') form.value.delete_session_on_success = false
})

function parseTime(value) {
  const [hour, minute] = (value || '09:00').split(':').map(n => Number.parseInt(n, 10))
  return {
    hour: Number.isInteger(hour) ? hour : 9,
    minute: Number.isInteger(minute) ? minute : 0,
  }
}

function toCronExpr(value) {
  const time = parseTime(value.time)
  if (value.schedule_type === 'minutes') return `*/${Math.max(Number(value.interval_minutes) || 30, 1)} * * * *`
  if (value.schedule_type === 'hourly') return `${time.minute} */${Math.max(Number(value.interval_hours) || 1, 1)} * * *`
  if (value.schedule_type === 'daily') return `${time.minute} ${time.hour} * * *`
  return `${time.minute} ${time.hour} * * ${Number(value.weekday) || 0}`
}

function describeCron(expr) {
  const [minute, hour, , , weekday] = expr.split(' ')
  if (minute?.startsWith('*/')) return `Every ${minute.slice(2)} minutes`
  if (hour?.startsWith('*/')) return `Every ${hour.slice(2)} hours at minute ${minute}`
  const time = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
  if (weekday !== '*') return `Every ${weekdays.find(day => day.value === Number(weekday))?.label || 'week'} at ${time}`
  return `Every day at ${time}`
}

async function submit() {
  await saveNewSchedule({
    project_id: props.projectId,
    session_id: form.value.execution_mode === 'existing_session' ? form.value.session_id : '',
    execution_mode: form.value.execution_mode,
    prompt_mode: form.value.prompt_mode,
    skill_name: form.value.prompt_mode === 'skill' ? form.value.skill_name : '',
    channel_id: form.value.channel_id || '',
    auto_unbind_after_run: form.value.auto_unbind_after_run,
    delete_session_on_success: form.value.delete_session_on_success,
    name: form.value.name || (form.value.skill_name ? `/${form.value.skill_name}` : 'Scheduled task'),
    prompt: form.value.prompt,
    cron_expr: toCronExpr(form.value),
    enabled: true,
  })
  if (!error.value) {
    form.value = {
      name: '',
      prompt: '',
      skill_name: '',
      skill_type: '',
      prompt_mode: 'prompt',
      execution_mode: 'new_session',
      schedule_type: 'hourly',
      interval_minutes: 30,
      interval_hours: 1,
      time: '09:00',
      weekday: 0,
      session_id: '',
      channel_id: '',
      auto_unbind_after_run: true,
      delete_session_on_success: false,
    }
  }
}

function formatTime(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function channelOptionLabel(item) {
  const name = item?.name || item?.id || 'Channel'
  const appId = item?.app_id ? ` · ${item.app_id}` : ''
  const bound = item?.bound_session_id ? ` · bound ${item.bound_session_id}` : ''
  return `${item.display_name || item.channel_type} · ${name}${appId}${bound}`
}

function taskAnchorLabel(task) {
  if (task?.execution_mode !== 'existing_session') return 'New session each run'
  const session = projectSessions.value.find(item => item.session_id === task.session_id)
  if (!session) return `Existing session · ${task.session_id}`
  return `Existing session · ${session.name || session.session_id}`
}

function taskPromptLabel(task) {
  if (task?.prompt_mode === 'skill' && task.skill_name) {
    return `/${task.skill_name}${task.prompt ? `  ${task.prompt}` : ''}`
  }
  return task?.prompt || ''
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="scheduler-overlay" @click.self="emit('close')">
        <div class="scheduler-dialog" role="dialog" aria-modal="true" aria-labelledby="scheduler-title">
          <div class="scheduler-header">
            <div>
              <span class="scheduler-eyebrow">Project automation</span>
              <h3 id="scheduler-title">Scheduled tasks</h3>
              <p>Run a durable prompt in a fresh session or continue an existing conversation.</p>
            </div>
            <button class="close-btn" type="button" aria-label="Close scheduler" @click="emit('close')">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" /></svg>
            </button>
          </div>

          <div v-if="error" class="notice">{{ error }}</div>

          <div class="scheduler-body">
            <section class="schedule-form" aria-label="Create schedule">
              <div class="form-section">
                <span class="section-kicker">1 · Destination</span>
                <div class="choice-grid" role="radiogroup" aria-label="Execution destination">
                  <button
                    type="button"
                    role="radio"
                    :aria-checked="form.execution_mode === 'new_session'"
                    :class="{ active: form.execution_mode === 'new_session' }"
                    @click="form.execution_mode = 'new_session'"
                  >
                    <strong>New session</strong>
                    <small>Independent context for every run</small>
                  </button>
                  <button
                    type="button"
                    role="radio"
                    :aria-checked="form.execution_mode === 'existing_session'"
                    :class="{ active: form.execution_mode === 'existing_session' }"
                    @click="form.execution_mode = 'existing_session'"
                  >
                    <strong>Existing session</strong>
                    <small>Continue with its current context</small>
                  </button>
                </div>
                <label v-if="form.execution_mode === 'existing_session'" class="anchor-field">
                  <span class="anchor-label">Session</span>
                  <select v-model="form.session_id" required>
                    <option value="" disabled>Select a project session</option>
                    <option v-for="session in projectSessions" :key="session.session_id" :value="session.session_id">
                      {{ session.name || 'Untitled session' }} · {{ session.session_id }}
                    </option>
                  </select>
                  <span class="anchor-hint">Runs are appended to this conversation and execute serially if it is busy.</span>
                </label>
              </div>

              <div class="form-section">
                <span class="section-kicker">2 · Schedule</span>
                <input v-model="form.name" placeholder="Task name" aria-label="Schedule name" />
              <div class="schedule-type-grid">
                <button type="button" :class="{ active: form.schedule_type === 'minutes' }" @click="form.schedule_type = 'minutes'">Every N minutes</button>
                <button type="button" :class="{ active: form.schedule_type === 'hourly' }" @click="form.schedule_type = 'hourly'">Every N hours</button>
                <button type="button" :class="{ active: form.schedule_type === 'daily' }" @click="form.schedule_type = 'daily'">Daily</button>
                <button type="button" :class="{ active: form.schedule_type === 'weekly' }" @click="form.schedule_type = 'weekly'">Weekly</button>
              </div>
              <input
                v-if="form.schedule_type === 'minutes'"
                v-model.number="form.interval_minutes"
                type="number"
                min="1"
                max="59"
                placeholder="Minutes"
                aria-label="Repeat interval in minutes"
              />
              <input
                v-if="form.schedule_type === 'hourly'"
                v-model.number="form.interval_hours"
                type="number"
                min="1"
                max="23"
                placeholder="Hours"
                aria-label="Repeat interval in hours"
              />
              <select v-if="form.schedule_type === 'weekly'" v-model.number="form.weekday" aria-label="Weekday">
                <option v-for="day in weekdays" :key="day.value" :value="day.value">{{ day.label }}</option>
              </select>
              <input
                v-if="form.schedule_type !== 'minutes'"
                v-model="form.time"
                type="time"
                aria-label="Run time"
              />
              <div class="schedule-summary">{{ scheduleDescription }}</div>
              </div>

              <div class="form-section">
                <span class="section-kicker">3 · Instructions</span>
                <div class="choice-grid choice-grid--compact" role="radiogroup" aria-label="Instruction type">
                  <button
                    type="button"
                    role="radio"
                    :aria-checked="form.prompt_mode === 'prompt'"
                    :class="{ active: form.prompt_mode === 'prompt' }"
                    @click="form.prompt_mode = 'prompt'"
                  >
                    <strong>Prompt only</strong>
                    <small>Send exactly what you write</small>
                  </button>
                  <button
                    type="button"
                    role="radio"
                    :aria-checked="form.prompt_mode === 'skill'"
                    :class="{ active: form.prompt_mode === 'skill' }"
                    @click="form.prompt_mode = 'skill'"
                  >
                    <strong>Use a Skill</strong>
                    <small>Invoke it, then append your prompt</small>
                  </button>
                </div>
              <div v-if="form.prompt_mode === 'skill'" class="skill-selector">
                <label class="anchor-label">Skill</label>
                <div v-if="form.skill_name" class="skill-selected">
                  <span class="skill-tag" :class="form.skill_type === 'skill' ? 'skill-tag--skill' : 'skill-tag--builtin'">
                    /{{ form.skill_name }}
                  </span>
                  <button type="button" class="skill-clear" @click="clearSkill" aria-label="Clear skill">×</button>
                  <button type="button" class="skill-change" @click="skillDropdownOpen = !skillDropdownOpen">Change</button>
                </div>
                <button v-else type="button" class="skill-trigger" @click="skillDropdownOpen = !skillDropdownOpen">
                  {{ skillLoading ? 'Loading...' : 'Select Skill / Command (optional)' }}
                </button>
                <div v-if="skillDropdownOpen" class="skill-dropdown">
                  <input
                    v-model="skillSearch"
                    class="skill-search"
                    placeholder="Search skills..."
                    type="text"
                    @keydown.escape.stop="skillDropdownOpen = false"
                  />
                  <div class="skill-list">
                    <div v-if="filteredSkillCommands.length === 0" class="skill-empty">
                      {{ skillLoading ? 'Loading...' : 'No skills found' }}
                    </div>
                    <div
                      v-for="cmd in filteredSkillCommands"
                      :key="cmd.name"
                      class="skill-item"
                      @click="selectSkill(cmd)"
                    >
                      <span class="skill-item-name">/{{ cmd.name }}</span>
                      <span class="skill-item-tag" :class="cmd.type === 'skill' ? 'skill-tag--skill' : 'skill-tag--builtin'">
                        {{ cmd.type === 'skill' ? 'skill' : 'built-in' }}
                      </span>
                      <span class="skill-item-desc">{{ cmd.description }}</span>
                    </div>
                  </div>
                </div>
                <div v-if="selectedSkill" class="skill-preview">
                  <strong>/{{ selectedSkill.name }}</strong>
                  <span>{{ selectedSkill.description || 'No description provided.' }}</span>
                  <code v-if="selectedSkill.argumentHint">{{ selectedSkill.argumentHint }}</code>
                </div>
              </div>
              <textarea
                v-model="form.prompt"
                :required="form.prompt_mode === 'prompt'"
                :aria-label="form.prompt_mode === 'skill' ? 'Additional prompt after the Skill' : 'Task prompt'"
                :placeholder="form.prompt_mode === 'skill' ? 'Additional prompt after the Skill (optional)' : 'Describe the work to run'"
              ></textarea>
              </div>

              <details class="advanced-options">
                <summary>Delivery and cleanup</summary>
              <div class="anchor-field">
                <label class="anchor-label">IM channel for each run</label>
                <select v-model="form.channel_id" aria-label="IM channel for each run">
                  <option value="">No IM channel</option>
                  <option v-for="item in channelInstances" :key="item.id" :value="item.id">
                    {{ channelOptionLabel(item) }}
                  </option>
                </select>
                <div class="anchor-hint">{{ channelHint }}</div>
              </div>
              <label class="checkbox-field schedule-option">
                <input v-model="form.auto_unbind_after_run" type="checkbox" />
                <span>Disconnect IM after each run</span>
              </label>
              <label class="checkbox-field schedule-option">
                <input v-model="form.delete_session_on_success" type="checkbox" :disabled="form.execution_mode === 'existing_session'" />
                <span>Delete successful execution session</span>
              </label>
              </details>
              <button class="primary-btn" type="button" :disabled="!canSubmit" @click="submit">
                {{ saving ? 'Saving...' : 'Create scheduled task' }}
              </button>
            </section>

            <section class="schedule-list">
              <div class="schedule-list-header">
                <div>
                  <span class="scheduler-eyebrow">Tasks and recent runs</span>
                  <strong>{{ tasks.length }} task{{ tasks.length === 1 ? '' : 's' }}</strong>
                </div>
              </div>
              <div v-if="loading" class="empty">Loading...</div>
              <div v-else-if="tasks.length === 0" class="empty">No schedules</div>
              <div v-for="task in tasks" :key="task.id" class="schedule-item" :class="{ 'schedule-item--disabled': !task.enabled }">
                <div class="schedule-main">
                  <div class="schedule-title-row">
                    <div class="schedule-title">{{ task.name }}</div>
                    <span class="schedule-anchor" :class="{ 'schedule-anchor--active': !!task.session_id }">{{ taskAnchorLabel(task) }}</span>
                  </div>
                  <div class="schedule-meta">
                    {{ describeCron(task.cron_expr) }} · next {{ formatTime(task.next_run_time) }}
                    <span v-if="task.auto_unbind_after_run"> · auto-disconnect</span>
                    <span v-if="task.delete_session_on_success"> · delete on success</span>
                  </div>
                  <div class="schedule-prompt">{{ taskPromptLabel(task) }}</div>
                  <div v-if="task.runs?.length" class="schedule-meta">
                    last run: {{ task.runs[0].status }} {{ task.runs[0].result_session_id ? `→ ${task.runs[0].result_session_id}` : '' }}
                  </div>
                </div>
                <div class="schedule-actions">
                  <button type="button" @click="runNow(task.id)" :disabled="saving">Run now</button>
                  <button type="button" @click="toggleSchedule(task)" :disabled="saving">{{ task.enabled ? 'Disable' : 'Enable' }}</button>
                  <button type="button" class="danger" @click="removeSchedule(task.id)" :disabled="saving">Delete</button>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.scheduler-overlay { position: fixed; inset: 0; z-index: 100; background: var(--dialog-overlay); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: var(--dialog-gutter); }
.scheduler-dialog { width: min(1060px, 100%); max-height: min(860px, calc(100dvh - (var(--dialog-gutter) * 2))); background: var(--dialog-surface); border: 1px solid var(--dialog-border); border-radius: var(--dialog-radius); box-shadow: var(--dialog-shadow); overflow: hidden; display: flex; flex-direction: column; }
.scheduler-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; padding: 20px 22px 18px; border-bottom: 1px solid color-mix(in srgb, var(--border) 76%, transparent); }
.scheduler-eyebrow { display: inline-flex; margin-bottom: 6px; color: var(--accent); font-size: 10px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; }
.scheduler-header h3 { margin: 0; font-size: 20px; color: var(--text-primary); letter-spacing: -0.02em; }
.scheduler-header p { margin: 6px 0 0; font-size: 13px; color: var(--text-muted); }
.close-btn { width: 36px; height: 36px; border: 1px solid transparent; border-radius: var(--radius-md); background: transparent; color: var(--text-muted); line-height: 1; cursor: pointer; transition: color var(--transition-fast), border-color var(--transition-fast), background var(--transition-fast); }
.close-btn:hover { color: var(--text-primary); border-color: var(--dialog-divider); background: var(--bg-hover); }
.notice { padding: 10px 22px; color: var(--danger, #ef4444); background: color-mix(in srgb, var(--danger, #ef4444) 10%, var(--bg-tertiary)); border-bottom: 1px solid var(--border); font-size: 12px; }
.scheduler-body { display: grid; grid-template-columns: minmax(320px, 360px) 1fr; min-height: 520px; overflow: hidden; }
.schedule-form { display: flex; flex-direction: column; gap: 12px; padding: 16px; border-right: 1px solid var(--border); background: color-mix(in srgb, var(--bg-primary) 86%, transparent); overflow-y: auto; }
.schedule-form input, .schedule-form textarea, .schedule-form select { border: 1px solid var(--border); border-radius: 12px; background: var(--bg-secondary); color: var(--text-primary); padding: 9px 10px; font-family: var(--font-sans); transition: border-color 180ms ease, box-shadow 180ms ease, background 180ms ease; }
.schedule-form input:focus, .schedule-form textarea:focus, .schedule-form select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 16%, transparent); }
.form-section { display: flex; flex-direction: column; gap: 10px; padding-bottom: 14px; border-bottom: 1px solid color-mix(in srgb, var(--border) 76%, transparent); }
.section-kicker { color: var(--text-muted); font-size: 10px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; }
.choice-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.choice-grid button { min-height: 72px; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 4px; padding: 10px; border: 1px solid var(--border); border-radius: 12px; background: var(--bg-secondary); color: var(--text-secondary); cursor: pointer; text-align: left; transition: color 180ms ease, background 180ms ease, border-color 180ms ease, box-shadow 180ms ease; }
.choice-grid button:hover:not(.active) { color: var(--text-primary); border-color: color-mix(in srgb, var(--accent) 42%, var(--border)); }
.choice-grid button.active { color: var(--accent); border-color: var(--accent); background: color-mix(in srgb, var(--accent) 9%, var(--bg-secondary)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 16%, transparent); }
.choice-grid strong { font-size: 12px; }
.choice-grid small { color: var(--text-muted); font-size: 10px; line-height: 1.35; }
.choice-grid--compact button { min-height: 64px; }
.schedule-type-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.schedule-type-grid button { min-height: 44px; border: 1px solid var(--border); border-radius: 12px; background: var(--bg-secondary); color: var(--text-secondary); padding: 9px 10px; cursor: pointer; font-size: 11px; font-weight: 700; transition: transform 180ms ease, color 180ms ease, background 180ms ease, border-color 180ms ease; }
.schedule-type-grid button:hover:not(.active) { color: var(--text-primary); border-color: color-mix(in srgb, var(--accent) 42%, var(--border)); transform: translateY(-1px); }
.schedule-type-grid button.active { border-color: var(--accent); background: linear-gradient(135deg, var(--accent-dim), color-mix(in srgb, var(--accent) 14%, transparent)); color: var(--accent); }
.schedule-summary { color: var(--accent); font-size: 12px; padding: 8px 10px; border: 1px dashed color-mix(in srgb, var(--accent) 45%, var(--border)); border-radius: 12px; background: color-mix(in srgb, var(--accent) 8%, transparent); }
.schedule-form textarea { min-height: 140px; resize: vertical; line-height: 1.5; }
.anchor-field { display: flex; flex-direction: column; gap: 6px; }
.anchor-label { font-size: 12px; color: var(--text-secondary); font-weight: 700; }
.anchor-hint { font-size: 11px; line-height: 1.5; color: var(--text-muted); }
.skill-selector { display: flex; flex-direction: column; gap: 6px; position: relative; }
.skill-trigger { border: 1px dashed color-mix(in srgb, var(--accent) 45%, var(--border)); border-radius: 12px; background: color-mix(in srgb, var(--accent) 6%, transparent); color: var(--text-secondary); padding: 9px 10px; cursor: pointer; font-size: 12px; text-align: left; transition: border-color 180ms ease, color 180ms ease, background 180ms ease; }
.skill-trigger:hover { border-color: var(--accent); color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); }
.skill-selected { display: flex; align-items: center; gap: 8px; }
.skill-tag { display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 999px; font-family: var(--font-mono); font-size: 12px; font-weight: 700; }
.skill-tag--skill { color: var(--purple, #a855f7); background: color-mix(in srgb, var(--purple, #a855f7) 14%, transparent); border: 1px solid color-mix(in srgb, var(--purple, #a855f7) 32%, var(--border)); }
.skill-tag--builtin { color: var(--text-muted); background: color-mix(in srgb, var(--bg-tertiary) 60%, transparent); border: 1px solid var(--border); }
.skill-clear { width: 22px; height: 22px; border: 1px solid var(--border); border-radius: 999px; background: transparent; color: var(--text-muted); font-size: 14px; line-height: 1; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: color 180ms ease, border-color 180ms ease; }
.skill-clear:hover { color: var(--danger, #ef4444); border-color: var(--danger, #ef4444); }
.skill-change { border: 1px solid var(--border); border-radius: 10px; background: var(--bg-secondary); color: var(--text-muted); padding: 3px 8px; cursor: pointer; font-size: 11px; transition: color 180ms ease, border-color 180ms ease; }
.skill-change:hover { color: var(--accent); border-color: var(--accent); }
.skill-dropdown { position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; z-index: 10; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow-lg, 0 8px 24px rgba(0,0,0,0.15)); max-height: 240px; display: flex; flex-direction: column; overflow: hidden; }
.skill-search { border: none; border-bottom: 1px solid var(--border); background: transparent; color: var(--text-primary); padding: 8px 10px; font-size: 12px; font-family: var(--font-sans); outline: none; }
.skill-search::placeholder { color: var(--text-muted); }
.skill-list { overflow-y: auto; padding: 4px; }
.skill-item { display: flex; align-items: baseline; gap: 8px; padding: 7px 8px; border-radius: 8px; cursor: pointer; transition: background 120ms ease; }
.skill-item:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); }
.skill-item-name { font-family: var(--font-mono); font-size: 12px; color: var(--accent); white-space: nowrap; flex-shrink: 0; }
.skill-item-tag { font-size: 9px; padding: 1px 5px; border-radius: 3px; white-space: nowrap; flex-shrink: 0; }
.skill-item-desc { font-size: 11px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.skill-empty { padding: 12px; text-align: center; color: var(--text-muted); font-size: 12px; }
.skill-preview { display: flex; flex-direction: column; gap: 4px; padding: 9px 10px; border: 1px solid color-mix(in srgb, var(--purple, #a855f7) 28%, var(--border)); border-radius: 10px; background: color-mix(in srgb, var(--purple, #a855f7) 7%, transparent); }
.skill-preview strong { color: var(--purple, #a855f7); font-family: var(--font-mono); font-size: 11px; }
.skill-preview span { color: var(--text-secondary); font-size: 11px; line-height: 1.45; }
.skill-preview code { color: var(--text-muted); font-size: 10px; }
.advanced-options { border: 1px solid var(--border); border-radius: 12px; background: color-mix(in srgb, var(--bg-secondary) 78%, transparent); }
.advanced-options summary { padding: 10px; color: var(--text-secondary); cursor: pointer; font-size: 12px; font-weight: 700; }
.advanced-options[open] summary { border-bottom: 1px solid var(--border); }
.advanced-options > :not(summary) { margin: 10px; }
.schedule-option { display: flex; align-items: center; gap: 8px; color: var(--text-secondary); font-size: 12px; }
.schedule-option input { width: auto; }
.primary-btn { min-height: 44px; background: linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 78%, #ffffff)); border: 1px solid var(--accent); color: var(--text-on-accent); border-radius: 12px; padding: 9px 12px; cursor: pointer; font-weight: 800; transition: transform 180ms ease, box-shadow 180ms ease, opacity 180ms ease; }
.primary-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 10px 26px color-mix(in srgb, var(--accent) 28%, transparent); }
.primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.schedule-list { overflow-y: auto; padding: 16px; }
.schedule-list-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.schedule-list-header strong { display: block; color: var(--text-primary); font-size: 15px; }
.empty { color: var(--text-muted); text-align: center; padding: 48px 20px; font-size: 13px; border: 1px dashed var(--border); border-radius: var(--radius-md); background: color-mix(in srgb, var(--bg-primary) 72%, transparent); }
.schedule-item { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 14px; padding: 14px; border: 1px solid color-mix(in srgb, var(--border) 84%, transparent); border-radius: var(--radius-md); margin-bottom: 10px; background: linear-gradient(135deg, color-mix(in srgb, var(--bg-primary) 92%, transparent), color-mix(in srgb, var(--bg-tertiary) 42%, transparent)); transition: transform 200ms ease, border-color 200ms ease, box-shadow 200ms ease; }
.schedule-item:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--accent) 38%, var(--border)); box-shadow: 0 14px 36px color-mix(in srgb, #000 16%, transparent); }
.schedule-item--disabled { opacity: 0.72; }
.schedule-main { min-width: 0; }
.schedule-title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.schedule-title { font-weight: 800; color: var(--text-primary); font-size: 14px; }
.schedule-anchor { display: inline-flex; align-items: center; border-radius: 999px; font-family: var(--font-mono); }
.schedule-anchor { max-width: 100%; margin-top: 9px; font-size: 10px; color: var(--text-muted); border: 1px solid var(--border); padding: 3px 8px; }
.schedule-anchor--active { color: var(--green); border-color: color-mix(in srgb, var(--green) 45%, var(--border)); background: var(--green-dim); }
.schedule-meta { color: var(--text-muted); font-size: 11px; margin-top: 4px; }
.schedule-prompt { color: var(--text-secondary); font-size: 12px; line-height: 1.5; margin-top: 9px; white-space: pre-wrap; max-height: 92px; overflow: hidden; }
.schedule-actions { display: flex; flex-direction: column; gap: 7px; flex-shrink: 0; }
.schedule-actions button { min-height: 44px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg-secondary); color: var(--text-secondary); padding: 7px 10px; cursor: pointer; transition: transform 180ms ease, color 180ms ease, background 180ms ease, border-color 180ms ease; }
.schedule-actions button:hover:not(:disabled) { color: var(--text-primary); background: var(--bg-hover); border-color: var(--accent); transform: translateY(-1px); }
.schedule-actions .danger { color: var(--danger, #ef4444); }
.dialog-fade-enter-active, .dialog-fade-leave-active { transition: opacity 180ms ease; }
.dialog-fade-enter-active .scheduler-dialog, .dialog-fade-leave-active .scheduler-dialog { transition: transform 220ms ease, opacity 220ms ease; }
.dialog-fade-enter-from, .dialog-fade-leave-to { opacity: 0; }
.dialog-fade-enter-from .scheduler-dialog, .dialog-fade-leave-to .scheduler-dialog { opacity: 0; transform: translateY(16px) scale(0.98); }
@media (max-width: 860px) { .scheduler-overlay { align-items: stretch; padding: 12px; } .scheduler-body { grid-template-columns: 1fr; overflow-y: auto; } .schedule-form { border-right: none; border-bottom: 1px solid var(--border); } .schedule-list { overflow: visible; } }
@media (max-width: 480px) { .choice-grid, .schedule-type-grid { grid-template-columns: 1fr; } .schedule-item { grid-template-columns: 1fr; } .schedule-actions { flex-direction: row; flex-wrap: wrap; } }
@media (prefers-reduced-motion: reduce) { .scheduler-dialog, .schedule-item, .schedule-type-grid button, .primary-btn, .schedule-actions button, .close-btn { transition: none; } .schedule-item:hover, .primary-btn:hover:not(:disabled), .schedule-actions button:hover:not(:disabled), .schedule-type-grid button:hover:not(.active), .close-btn:hover { transform: none; } }
</style>
