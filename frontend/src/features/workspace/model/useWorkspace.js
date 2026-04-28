import { ref } from 'vue'
import {
  getWorkspaceDiff,
  listWorkspaceFileHistory,
  listWorkspaceFiles,
  readWorkspaceFile,
  readWorkspaceFileAtRef,
} from '@entities/project/api/projectApi'

export function useWorkspace() {
  const files = ref([])
  const selectedFile = ref(null)
  const selectedDiff = ref(null)
  const fileHistory = ref([])
  const historicalFile = ref(null)
  const loading = ref(false)
  const reading = ref(false)
  const historyLoading = ref(false)
  const error = ref('')

  async function loadFiles(projectId, options = {}) {
    if (!projectId) return
    loading.value = true
    error.value = ''
    try {
      const data = await listWorkspaceFiles(projectId, options)
      files.value = data.files || []
    } catch (e) {
      files.value = []
      error.value = e.message || 'Failed to load files'
    } finally {
      loading.value = false
    }
  }

  async function openFile(projectId, path) {
    if (!projectId || !path) return
    reading.value = true
    error.value = ''
    historicalFile.value = null
    fileHistory.value = []
    try {
      const [file, diff] = await Promise.all([
        readWorkspaceFile(projectId, path),
        getWorkspaceDiff(projectId, path),
      ])
      selectedFile.value = file
      selectedDiff.value = diff
    } catch (e) {
      selectedFile.value = null
      selectedDiff.value = null
      error.value = e.message || 'Failed to read file'
    } finally {
      reading.value = false
    }
  }

  async function loadFileHistory(projectId, path) {
    if (!projectId || !path) return
    historyLoading.value = true
    try {
      const data = await listWorkspaceFileHistory(projectId, path, 20)
      fileHistory.value = data.commits || []
      return fileHistory.value
    } catch (e) {
      fileHistory.value = []
      error.value = e.message || 'Failed to load file history'
      return []
    } finally {
      historyLoading.value = false
    }
  }

  async function openHistoricalFile(projectId, path, ref) {
    if (!projectId || !path || !ref) return null
    historyLoading.value = true
    try {
      const file = await readWorkspaceFileAtRef(projectId, path, ref)
      historicalFile.value = file
      return file
    } catch (e) {
      historicalFile.value = null
      error.value = e.message || 'Failed to read historical file'
      return null
    } finally {
      historyLoading.value = false
    }
  }

  function clearSelection() {
    selectedFile.value = null
    selectedDiff.value = null
    historicalFile.value = null
    fileHistory.value = []
  }

  return {
    files,
    selectedFile,
    selectedDiff,
    fileHistory,
    historicalFile,
    loading,
    reading,
    historyLoading,
    error,
    loadFiles,
    openFile,
    loadFileHistory,
    openHistoricalFile,
    clearSelection,
  }
}
