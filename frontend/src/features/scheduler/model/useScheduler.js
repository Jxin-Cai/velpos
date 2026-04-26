import { ref } from 'vue'
import { listSchedules, createSchedule, updateSchedule, deleteSchedule, runScheduleNow } from '../api/schedulerApi'

const tasks = ref([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const activeProjectId = ref('')

export function useScheduler() {
  async function loadSchedules(projectId = '') {
    activeProjectId.value = projectId
    loading.value = true
    error.value = ''
    try {
      const data = await listSchedules(projectId)
      tasks.value = data.tasks || []
    } catch (e) {
      error.value = e.message || 'Failed to load schedules'
    } finally {
      loading.value = false
    }
  }

  async function saveNewSchedule(payload) {
    saving.value = true
    error.value = ''
    try {
      await createSchedule(payload)
      await loadSchedules(activeProjectId.value)
      window.dispatchEvent(new CustomEvent('vp-schedules-changed'))
    } catch (e) {
      error.value = e.message || 'Failed to create schedule'
    } finally {
      saving.value = false
    }
  }

  async function toggleSchedule(task) {
    if (!task) return
    saving.value = true
    error.value = ''
    try {
      await updateSchedule(task.id, { enabled: !task.enabled })
      await loadSchedules(activeProjectId.value)
      window.dispatchEvent(new CustomEvent('vp-schedules-changed'))
    } catch (e) {
      error.value = e.message || 'Failed to update schedule'
    } finally {
      saving.value = false
    }
  }

  async function removeSchedule(taskId) {
    saving.value = true
    error.value = ''
    try {
      await deleteSchedule(taskId)
      await loadSchedules(activeProjectId.value)
      window.dispatchEvent(new CustomEvent('vp-schedules-changed'))
    } catch (e) {
      error.value = e.message || 'Failed to delete schedule'
    } finally {
      saving.value = false
    }
  }

  async function runNow(taskId) {
    saving.value = true
    error.value = ''
    try {
      await runScheduleNow(taskId)
      await loadSchedules(activeProjectId.value)
      window.dispatchEvent(new CustomEvent('vp-schedules-changed'))
    } catch (e) {
      error.value = e.message || 'Failed to run schedule'
    } finally {
      saving.value = false
    }
  }

  return {
    tasks,
    loading,
    saving,
    error,
    loadSchedules,
    saveNewSchedule,
    toggleSchedule,
    removeSchedule,
    runNow,
  }
}
