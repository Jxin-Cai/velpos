import { ref } from 'vue'
import { getSettings, updateSettings } from '../api/settingsApi'
import {
  listChannelProfiles,
  createChannelProfile,
  updateChannelProfile,
  deleteChannelProfile,
  activateChannelProfile,
  fetchModelsForChannel,
} from '../api/channelProfileApi'

export function useSettingsManager() {
  const settings = ref(null)
  const profiles = ref([])
  const loading = ref(false)
  const saving = ref(false)
  const operating = ref(null)
  const error = ref(null)
  // Fetched models cache: keyed by profileId or '_add' for the add form
  const fetchedModels = ref({})
  const fetchingModels = ref(null) // profileId currently fetching

  async function loadData() {
    loading.value = true
    error.value = null
    try {
      const [settingsData, profilesData] = await Promise.all([
        getSettings(),
        listChannelProfiles(),
      ])
      settings.value = settingsData
      profiles.value = profilesData.profiles || []
    } catch (err) {
      error.value = err.message || 'Failed to load data'
    } finally {
      loading.value = false
    }
  }

  async function saveSettings(data) {
    saving.value = true
    error.value = null
    try {
      settings.value = await updateSettings(data)
    } catch (err) {
      error.value = err.message || 'Failed to save settings'
    } finally {
      saving.value = false
    }
  }

  async function handleCreate(form) {
    error.value = null
    try {
      await createChannelProfile(form)
      await loadData()
    } catch (err) {
      error.value = err.message || 'Failed to create channel profile'
    }
  }

  async function handleUpdate(profileId, form) {
    error.value = null
    try {
      await updateChannelProfile(profileId, form)
      await loadData()
    } catch (err) {
      error.value = err.message || 'Failed to update channel profile'
    }
  }

  async function handleDelete(profileId) {
    operating.value = profileId
    error.value = null
    try {
      await deleteChannelProfile(profileId)
      await loadData()
    } catch (err) {
      error.value = err.message || 'Failed to delete channel profile'
    } finally {
      operating.value = null
    }
  }

  async function handleActivate(profileId) {
    operating.value = profileId
    error.value = null
    try {
      await activateChannelProfile(profileId)
      await loadData()
    } catch (err) {
      error.value = err.message || 'Failed to activate channel profile'
    } finally {
      operating.value = null
    }
  }

  async function handleFetchModels(key, host, apiKey) {
    fetchingModels.value = key
    error.value = null
    try {
      const models = await fetchModelsForChannel(host, apiKey)
      fetchedModels.value = { ...fetchedModels.value, [key]: models || [] }
    } catch (err) {
      error.value = err.message || 'Failed to fetch models'
    } finally {
      fetchingModels.value = null
    }
  }

  return {
    settings,
    profiles,
    loading,
    saving,
    operating,
    error,
    fetchedModels,
    fetchingModels,
    loadData,
    saveSettings,
    handleCreate,
    handleUpdate,
    handleDelete,
    handleActivate,
    handleFetchModels,
  }
}
