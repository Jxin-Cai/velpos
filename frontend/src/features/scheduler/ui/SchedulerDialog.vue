<script setup>
import { ref, watch, computed } from 'vue'
import { useSession } from '@entities/session'
import { useImBinding } from '@features/im-binding'
import { useScheduler } from '../model/useScheduler'
import { useDialogManager } from '@shared/lib/useDialogManager'
import { useGlobalHotkeys } from '@shared/lib/useGlobalHotkeys'

const props = defineProps({
  visible: { type: Boolean, default: false },
  projectId: { type: String, default: '' },
  sessionId: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const visibleWrapper = {
  get value() { return props.visible },
  set value(v) { if (!v) emit('close') },
}
useDialogManager().useDialog('scheduler', visibleWrapper)

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

const { sessions } = useSession()
const { availableChannels, fetchChannels } = useImBinding()
const { tasks, loading, saving, error, loadSchedules, saveNewSchedule, toggleSchedule, removeSchedule, runNow } = useScheduler()
const form = ref({
  name: '',
  prompt: '',
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
  }
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
    session_id: form.value.session_id || '',
    channel_id: form.value.channel_id || '',
    auto_unbind_after_run: form.value.auto_unbind_after_run,
    delete_session_on_success: form.value.delete_session_on_success,
    name: form.value.name || 'Scheduled task',
    prompt: form.value.prompt,
    cron_expr: toCronExpr(form.value),
    enabled: true,
  })
  if (!error.value) {
    form.value = {
      name: '',
      prompt: '',
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
  if (task?.channel_id) {
    const channel = channelInstances.value.find(item => item.id === task.channel_id)
    return channel ? `IM · ${channelOptionLabel(channel)}` : `IM · ${task.channel_id}`
  }
  if (!task?.session_id) return 'Local only'
  const session = projectSessions.value.find(item => item.session_id === task.session_id)
  if (!session) return `Legacy IM notify · ${task.session_id}`
  return `Legacy IM notify · ${session.name || session.session_id}`
}
</script>

<template>
  <teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="scheduler-overlay" @click.self="emit('close')">
        <div class="scheduler-dialog">
          <div class="scheduler-header">
            <div>
              <h3>Project Clock</h3>
              <p>Create sessions in this project and run scheduled work automatically</p>
            </div>
            <button class="close-btn" @click="emit('close')">×</button>
          </div>

          <div v-if="error" class="notice">{{ error }}</div>

          <div class="scheduler-body">
            <section class="schedule-form">
              <input v-model="form.name" placeholder="Name" />
              <div class="schedule-type-grid">
                <button :class="{ active: form.schedule_type === 'minutes' }" @click="form.schedule_type = 'minutes'">Every N minutes</button>
                <button :class="{ active: form.schedule_type === 'hourly' }" @click="form.schedule_type = 'hourly'">Every N hours</button>
                <button :class="{ active: form.schedule_type === 'daily' }" @click="form.schedule_type = 'daily'">Daily</button>
                <button :class="{ active: form.schedule_type === 'weekly' }" @click="form.schedule_type = 'weekly'">Weekly</button>
              </div>
              <input
                v-if="form.schedule_type === 'minutes'"
                v-model.number="form.interval_minutes"
                type="number"
                min="1"
                max="59"
                placeholder="Minutes"
              />
              <input
                v-if="form.schedule_type === 'hourly'"
                v-model.number="form.interval_hours"
                type="number"
                min="1"
                max="23"
                placeholder="Hours"
              />
              <select v-if="form.schedule_type === 'weekly'" v-model.number="form.weekday">
                <option v-for="day in weekdays" :key="day.value" :value="day.value">{{ day.label }}</option>
              </select>
              <input
                v-if="form.schedule_type !== 'minutes'"
                v-model="form.time"
                type="time"
              />
              <div class="schedule-summary">{{ scheduleDescription }}</div>
              <textarea v-model="form.prompt" placeholder="Describe the work this project session should run"></textarea>
              <div class="anchor-field">
                <label class="anchor-label">IM channel for each run</label>
                <select v-model="form.channel_id">
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
                <input v-model="form.delete_session_on_success" type="checkbox" />
                <span>Delete successful execution session</span>
              </label>
              <button class="primary-btn" :disabled="saving || !form.prompt || !props.projectId" @click="submit">
                {{ saving ? 'Saving...' : 'Create Project Clock' }}
              </button>
            </section>

            <section class="schedule-list">
              <div v-if="loading" class="empty">Loading...</div>
              <div v-else-if="tasks.length === 0" class="empty">No schedules</div>
              <div v-for="task in tasks" :key="task.id" class="schedule-item">
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
                  <div class="schedule-prompt">{{ task.prompt }}</div>
                  <div v-if="task.runs?.length" class="schedule-meta">
                    last run: {{ task.runs[0].status }} {{ task.runs[0].result_session_id ? `→ ${task.runs[0].result_session_id}` : '' }}
                  </div>
                </div>
                <div class="schedule-actions">
                  <button @click="runNow(task.id)" :disabled="saving">Run now</button>
                  <button @click="toggleSchedule(task)" :disabled="saving">{{ task.enabled ? 'Disable' : 'Enable' }}</button>
                  <button class="danger" @click="removeSchedule(task.id)" :disabled="saving">Delete</button>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </Transition>
  </teleport>
</template>

<style scoped>
.scheduler-overlay { position: fixed; inset: 0; z-index: 100; background: var(--bg-overlay); display: flex; align-items: center; justify-content: center; }
.scheduler-dialog { width: 920px; max-width: 94vw; max-height: 84vh; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-xl); overflow: hidden; display: flex; flex-direction: column; }
.scheduler-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--border); }
.scheduler-header h3 { margin: 0; font-size: 15px; color: var(--text-primary); }
.scheduler-header p { margin: 3px 0 0; font-size: 12px; color: var(--text-muted); }
.close-btn { border: none; background: transparent; color: var(--text-muted); font-size: 24px; cursor: pointer; }
.notice { padding: 8px 18px; color: var(--danger, #ef4444); background: var(--bg-tertiary); border-bottom: 1px solid var(--border); font-size: 12px; }
.scheduler-body { display: grid; grid-template-columns: 320px 1fr; min-height: 460px; overflow: hidden; }
.schedule-form { display: flex; flex-direction: column; gap: 10px; padding: 14px; border-right: 1px solid var(--border); background: var(--bg-primary); }
.schedule-form input, .schedule-form textarea, .schedule-form select { border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-secondary); color: var(--text-primary); padding: 8px 10px; font-family: var(--font-sans); }
.schedule-type-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.schedule-type-grid button { border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--text-secondary); padding: 7px 8px; cursor: pointer; font-size: 11px; }
.schedule-type-grid button.active { border-color: var(--accent); background: var(--accent-dim); color: var(--accent); }
.schedule-summary { color: var(--text-muted); font-size: 12px; padding: 6px 8px; border: 1px dashed var(--border); border-radius: var(--radius-sm); }
.schedule-form textarea { min-height: 140px; resize: vertical; }
.anchor-field { display: flex; flex-direction: column; gap: 6px; }
.anchor-label { font-size: 12px; color: var(--text-secondary); font-weight: 600; }
.anchor-hint { font-size: 11px; line-height: 1.45; color: var(--text-muted); }
.schedule-option { display: flex; align-items: center; gap: 8px; color: var(--text-secondary); font-size: 12px; }
.schedule-option input { width: auto; }
.primary-btn { background: var(--accent); border: 1px solid var(--accent); color: var(--text-on-accent); border-radius: var(--radius-sm); padding: 8px 12px; cursor: pointer; }
.primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.schedule-list { overflow-y: auto; padding: 10px; }
.empty { color: var(--text-muted); text-align: center; padding: 30px; font-size: 13px; }
.schedule-item { display: flex; justify-content: space-between; gap: 12px; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-md); margin-bottom: 8px; }
.schedule-main { min-width: 0; }
.schedule-title-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.schedule-title { font-weight: 600; color: var(--text-primary); font-size: 13px; }
.schedule-anchor { flex-shrink: 0; font-size: 10px; font-family: var(--font-mono); color: var(--text-muted); border: 1px solid var(--border); border-radius: 999px; padding: 2px 7px; }
.schedule-anchor--active { color: var(--green); border-color: color-mix(in srgb, var(--green) 45%, var(--border)); background: var(--green-dim); }
.schedule-meta { color: var(--text-muted); font-size: 11px; margin-top: 4px; }
.schedule-prompt { color: var(--text-secondary); font-size: 12px; margin-top: 6px; white-space: pre-wrap; max-height: 80px; overflow: hidden; }
.schedule-actions { display: flex; flex-direction: column; gap: 6px; flex-shrink: 0; }
.schedule-actions button { border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--text-secondary); padding: 5px 9px; cursor: pointer; }
.schedule-actions button:hover:not(:disabled) { background: var(--bg-hover); }
.schedule-actions .danger { color: var(--danger, #ef4444); }
.dialog-fade-enter-active, .dialog-fade-leave-active { transition: opacity 0.15s ease; }
.dialog-fade-enter-from, .dialog-fade-leave-to { opacity: 0; }
</style>
