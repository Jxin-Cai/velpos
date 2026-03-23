import { ref } from 'vue'
import { executeCommand } from '../api/terminalApi'

export function useTerminal() {
  const entries = ref([])
  const executing = ref(false)
  const error = ref(null)

  async function runCommand(command, cwd = null) {
    if (!command.trim()) return
    executing.value = true
    error.value = null
    try {
      const result = await executeCommand(command, 30, cwd)
      entries.value.push({
        command,
        stdout: result.stdout || '',
        stderr: result.stderr || '',
        return_code: result.return_code,
        duration_ms: result.duration_ms,
      })
    } catch (err) {
      entries.value.push({
        command,
        stdout: '',
        stderr: err.message || 'Command execution failed',
        return_code: -1,
        duration_ms: 0,
      })
    } finally {
      executing.value = false
    }
  }

  function clearEntries() {
    entries.value = []
  }

  return { entries, executing, error, runCommand, clearEntries }
}
