<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { getGitConfig, setGitConfig, listSshKeys, generateSshKey } from '../api/gitApi'
import { useDialogManager } from '@shared/lib/useDialogManager'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits(['close'])

// 创建包装对象来管理可见性
const visibleWrapper = {
  get value() {
    return props.visible
  },
  set value(newValue) {
    if (!newValue) {
      emit('close')
    }
  }
}

const { useDialog } = useDialogManager()
useDialog('git-manager', visibleWrapper)

const loading = ref(false)
const saving = ref(false)
const error = ref('')

// Git config
const userName = ref('')
const userEmail = ref('')
const configSaved = ref(false)

// SSH keys
const sshKeys = ref([])
const generating = ref(false)
const showGenForm = ref(false)
const genKeyType = ref('ed25519')
const genComment = ref('')
const copiedKey = ref('')

async function loadData() {
  loading.value = true
  error.value = ''
  configSaved.value = false
  try {
    const [config, keys] = await Promise.all([
      getGitConfig(),
      listSshKeys(),
    ])
    userName.value = config.user_name || ''
    userEmail.value = config.user_email || ''
    sshKeys.value = keys.keys || []
  } catch (e) {
    error.value = e.message || 'Failed to load git config'
  } finally {
    loading.value = false
  }
}

async function handleSaveConfig() {
  saving.value = true
  error.value = ''
  configSaved.value = false
  try {
    const result = await setGitConfig(userName.value, userEmail.value)
    userName.value = result.user_name
    userEmail.value = result.user_email
    configSaved.value = true
    setTimeout(() => { configSaved.value = false }, 2000)
  } catch (e) {
    error.value = e.message || 'Failed to save git config'
  } finally {
    saving.value = false
  }
}

async function handleGenerate() {
  generating.value = true
  error.value = ''
  try {
    await generateSshKey(genKeyType.value, genComment.value)
    showGenForm.value = false
    genComment.value = ''
    // Reload keys
    const keys = await listSshKeys()
    sshKeys.value = keys.keys || []
  } catch (e) {
    error.value = e.message || 'Failed to generate SSH key'
  } finally {
    generating.value = false
  }
}

async function copyPublicKey(publicKey, keyName) {
  try {
    await navigator.clipboard.writeText(publicKey)
    copiedKey.value = keyName
    setTimeout(() => { copiedKey.value = '' }, 2000)
  } catch {
    // Fallback for non-HTTPS
    const ta = document.createElement('textarea')
    ta.value = publicKey
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    copiedKey.value = keyName
    setTimeout(() => { copiedKey.value = '' }, 2000)
  }
}

function handleOverlayClick(e) {
  if (e.target === e.currentTarget) {
    emit('close')
  }
}

function handleKeydown(e) {
  if (e.key === 'Escape' && props.visible) {
    emit('close')
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    loadData()
    showGenForm.value = false
  }
})

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="dialog-overlay" @click="handleOverlayClick">
      <div class="dialog">
        <div class="dialog-header">
          <h2>Git Management</h2>
          <button class="close-btn" @click="emit('close')" title="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div v-if="error" class="error-bar">{{ error }}</div>

        <div v-if="loading" class="loading-state">Loading...</div>

        <div v-else class="dialog-body">
          <!-- Git Config Section -->
          <div class="section">
            <h3 class="section-title">Git Identity</h3>
            <p class="section-desc">Configure the global git user for commits.</p>
            <div class="field-row">
              <label>user.name</label>
              <input
                v-model="userName"
                type="text"
                class="field-input"
                placeholder="Velpos"
              />
            </div>
            <div class="field-row">
              <label>user.email</label>
              <input
                v-model="userEmail"
                type="text"
                class="field-input"
                placeholder="velpos@local"
              />
            </div>
            <div class="section-actions">
              <button
                class="btn-primary"
                :disabled="saving"
                @click="handleSaveConfig"
              >
                {{ saving ? 'Saving...' : configSaved ? 'Saved' : 'Save' }}
              </button>
            </div>
          </div>

          <!-- SSH Keys Section -->
          <div class="section">
            <div class="section-header">
              <div>
                <h3 class="section-title">SSH Keys</h3>
                <p class="section-desc">Manage SSH keys for GitHub authentication.</p>
              </div>
              <button
                v-if="!showGenForm"
                class="btn-secondary"
                @click="showGenForm = true"
              >
                + Generate Key
              </button>
            </div>

            <!-- Generate form -->
            <div v-if="showGenForm" class="gen-form">
              <div class="field-row">
                <label>Type</label>
                <select v-model="genKeyType" class="field-input">
                  <option value="ed25519">Ed25519 (recommended)</option>
                  <option value="rsa">RSA</option>
                  <option value="ecdsa">ECDSA</option>
                </select>
              </div>
              <div class="field-row">
                <label>Comment</label>
                <input
                  v-model="genComment"
                  type="text"
                  class="field-input"
                  placeholder="your-email@example.com"
                />
              </div>
              <div class="gen-actions">
                <button
                  class="btn-primary"
                  :disabled="generating"
                  @click="handleGenerate"
                >
                  {{ generating ? 'Generating...' : 'Generate' }}
                </button>
                <button
                  class="btn-secondary"
                  @click="showGenForm = false"
                >
                  Cancel
                </button>
              </div>
            </div>

            <!-- Key list -->
            <div v-if="sshKeys.length === 0 && !showGenForm" class="empty-state">
              No SSH keys found. Generate one to get started.
            </div>
            <div v-for="key in sshKeys" :key="key.name" class="key-card">
              <div class="key-info">
                <div class="key-name">{{ key.name }}</div>
                <div class="key-meta">{{ key.type }} &middot; {{ key.fingerprint }}</div>
              </div>
              <button
                class="btn-copy"
                :class="{ copied: copiedKey === key.name }"
                @click="copyPublicKey(key.public_key, key.name)"
                :title="copiedKey === key.name ? 'Copied!' : 'Copy public key'"
              >
                <svg v-if="copiedKey !== key.name" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                {{ copiedKey === key.name ? 'Copied' : 'Copy' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay-glass);
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg, 12px);
  width: 560px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-glass);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--glass-border);
  background: var(--layer-glass);
  flex-shrink: 0;
}

.dialog-header h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.close-btn:hover {
  background: var(--layer-active);
  color: var(--accent);
}

.error-bar {
  padding: 8px 20px;
  background: var(--status-error-bg, rgba(255, 59, 48, 0.1));
  color: var(--status-error, #ff3b30);
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}

.loading-state {
  padding: 40px 20px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.dialog-body {
  padding: 16px 20px;
  overflow-y: auto;
  flex: 1;
}

.section {
  margin-bottom: 24px;
}

.section:last-child {
  margin-bottom: 0;
}

.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.section-title {
  margin: 0 0 4px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.section-desc {
  margin: 0 0 12px 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.field-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.field-row label {
  min-width: 80px;
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.field-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 12px;
  font-family: var(--font-mono, monospace);
  outline: none;
  transition: border-color var(--transition-fast);
}

.field-input:focus {
  border-color: var(--accent);
}

select.field-input {
  cursor: pointer;
}

.section-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

.btn-primary {
  padding: 6px 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: color var(--transition-fast), border-color var(--transition-fast);
  white-space: nowrap;
}

.btn-secondary:hover {
  color: var(--text-primary);
  border-color: var(--accent);
}

.gen-form {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px;
  margin-bottom: 12px;
}

.gen-actions {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}

.empty-state {
  padding: 20px 0;
  text-align: center;
  color: var(--text-secondary);
  font-size: 12px;
}

.key-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
  background: var(--bg-secondary);
}

.key-info {
  min-width: 0;
  flex: 1;
}

.key-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-mono, monospace);
}

.key-meta {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.btn-copy {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition: color var(--transition-fast), border-color var(--transition-fast);
  white-space: nowrap;
  flex-shrink: 0;
  margin-left: 12px;
}

.btn-copy:hover {
  color: var(--text-primary);
  border-color: var(--accent);
}

.btn-copy.copied {
  color: var(--status-success, #34c759);
  border-color: var(--status-success, #34c759);
}
</style>
