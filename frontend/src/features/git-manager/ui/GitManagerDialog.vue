<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { getGitConfig, setGitConfig, listSshKeys, generateSshKey } from '../api/gitApi'
import { useDialogManager, useVisibleProxy, useEscapeToClose } from '@shared/lib/useDialogManager'
import { useTimeout } from '@shared/lib/useTimeout'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
  embedded: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close', 'dirty-change'])

const { useDialog } = useDialogManager()
const visibleProxy = useVisibleProxy(props, emit)
useDialog('git-manager', {
  get value() { return !props.embedded && visibleProxy.value },
  set value(value) { if (!value && !props.embedded) visibleProxy.value = false },
})
useEscapeToClose(() => !props.embedded && props.visible, () => emit('close'))

const loading = ref(false)
const saving = ref(false)
const error = ref('')

// Git config
const userName = ref('')
const userEmail = ref('')
const configSaved = ref(false)
const initialUserName = ref('')
const initialUserEmail = ref('')

// SSH keys
const sshKeys = ref([])
const generating = ref(false)
const showGenForm = ref(false)
const genKeyType = ref('ed25519')
const genComment = ref('')
const copiedKey = ref('')
const isDirty = computed(() => userName.value !== initialUserName.value
  || userEmail.value !== initialUserEmail.value
  || (showGenForm.value && (genKeyType.value !== 'ed25519' || Boolean(genComment.value))))
watch(isDirty, value => emit('dirty-change', value), { immediate: true })
const { set: setTimer } = useTimeout()
let _loadDataSeq = 0

async function loadData() {
  loading.value = true
  error.value = ''
  configSaved.value = false
  const seq = ++_loadDataSeq
  try {
    const [config, keys] = await Promise.all([
      getGitConfig(),
      listSshKeys(),
    ])
    if (seq !== _loadDataSeq) return
    userName.value = config.user_name || ''
    userEmail.value = config.user_email || ''
    initialUserName.value = userName.value
    initialUserEmail.value = userEmail.value
    sshKeys.value = keys.keys || []
  } catch (e) {
    if (seq !== _loadDataSeq) return
    error.value = e.message || 'Failed to load git config'
  } finally {
    if (seq === _loadDataSeq) loading.value = false
  }
  if (seq !== _loadDataSeq) return
  await nextTick()
  if (seq !== _loadDataSeq) return
  initialUserName.value = userName.value
  initialUserEmail.value = userEmail.value
}

async function handleSaveConfig() {
  saving.value = true
  error.value = ''
  configSaved.value = false
  try {
    const result = await setGitConfig(userName.value, userEmail.value)
    userName.value = result.user_name || ''
    userEmail.value = result.user_email || ''
    initialUserName.value = userName.value
    initialUserEmail.value = userEmail.value
    configSaved.value = true
    setTimer(() => { configSaved.value = false }, 2000)
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

function cancelGenerate() {
  if (genComment.value && !confirm('SSH 密钥信息尚未生成，确定取消吗？')) return
  showGenForm.value = false
  genComment.value = ''
}

async function copyPublicKey(publicKey, keyName) {
  try {
    await navigator.clipboard.writeText(publicKey)
    copiedKey.value = keyName
    setTimer(() => { copiedKey.value = '' }, 2000)
  } catch {
    // Fallback for non-HTTPS
    const ta = document.createElement('textarea')
    ta.value = publicKey
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    copiedKey.value = keyName
    setTimer(() => { copiedKey.value = '' }, 2000)
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    loadData()
    showGenForm.value = false
  }
}, { immediate: true })
</script>

<template>
  <Teleport to="body" :disabled="embedded">
    <div
      v-if="visible"
      :class="embedded ? 'embedded-page' : 'dialog-overlay'"
      :role="embedded ? undefined : 'dialog'"
      :aria-modal="embedded ? undefined : 'true'"
      aria-labelledby="git-dialog-title"
      @click.self="!embedded && emit('close')"
    >
      <div :class="embedded ? 'embedded-surface' : 'dialog'">
        <div v-if="!embedded" class="dialog-header">
          <h2 id="git-dialog-title">Git Management</h2>
          <button class="close-btn" type="button" aria-label="Close Git Management" @click="emit('close')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div v-else class="embedded-header">
          <span class="eyebrow">GIT</span>
          <h1 id="git-dialog-title">Git 配置</h1>
          <p>管理全局提交身份与本机 SSH 密钥。</p>
        </div>

        <div v-if="error" class="error-bar" role="alert">{{ error }}</div>

        <div v-if="loading" class="loading-state">正在加载 Git 配置…</div>

        <div v-else class="dialog-body">
          <!-- Git Config Section -->
          <div class="section">
            <h3 class="section-title">提交身份</h3>
            <p class="section-desc">配置全局 Git 提交用户名和邮箱。</p>
            <div class="field-row">
              <label>user.name</label>
              <input
                v-model="userName"
                type="text"
                class="field-input"
                name="git-user-name"
                autocomplete="off"
                placeholder="Velpos"
              />
            </div>
            <div class="field-row">
              <label>user.email</label>
              <input
                v-model="userEmail"
                type="text"
                class="field-input"
                name="git-user-email"
                autocomplete="off"
                placeholder="velpos@local"
              />
            </div>
            <div class="section-actions">
              <button
                class="btn-primary"
                :disabled="saving"
                type="button"
                @click="handleSaveConfig"
              >
                {{ saving ? '保存中…' : configSaved ? '已保存' : '保存身份' }}
              </button>
            </div>
          </div>

          <!-- SSH Keys Section -->
          <div class="section">
            <div class="section-header">
              <div>
                <h3 class="section-title">SSH 密钥</h3>
                <p class="section-desc">管理用于 Git 托管平台认证的本机 SSH 密钥。</p>
              </div>
              <button
                v-if="!showGenForm"
                class="btn-secondary"
                type="button"
                @click="showGenForm = true"
              >
                生成密钥
              </button>
            </div>

            <!-- Generate form -->
            <div v-if="showGenForm" class="gen-form">
              <div class="field-row">
                <label>密钥类型</label>
                <select v-model="genKeyType" class="field-input">
                  <option value="ed25519">Ed25519（推荐）</option>
                  <option value="rsa">RSA</option>
                  <option value="ecdsa">ECDSA</option>
                </select>
              </div>
              <div class="field-row">
                <label>备注</label>
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
                  type="button"
                  :disabled="generating"
                  @click="handleGenerate"
                >
                  {{ generating ? '生成中…' : '生成密钥' }}
                </button>
                <button
                  class="btn-secondary"
                  type="button"
                  @click="cancelGenerate"
                >
                  取消
                </button>
              </div>
            </div>

            <!-- Key list -->
            <div v-if="sshKeys.length === 0 && !showGenForm" class="empty-state">
              尚未发现 SSH 密钥，可以先生成一个。
            </div>
            <div v-for="key in sshKeys" :key="key.name" class="key-card">
              <div class="key-info">
                <div class="key-name">{{ key.name }}</div>
                <div class="key-meta">{{ key.type }} &middot; {{ key.fingerprint }}</div>
              </div>
              <button
                class="btn-copy"
                type="button"
                :class="{ copied: copiedKey === key.name }"
                @click="copyPublicKey(key.public_key, key.name)"
                :title="copiedKey === key.name ? '已复制' : '复制公钥'"
              >
                <svg v-if="copiedKey !== key.name" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                {{ copiedKey === key.name ? '已复制' : '复制' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.embedded-page { width: 100%; max-width: 1080px; margin: 0 auto; }
.embedded-surface { width: 100%; padding: 24px; border: 1px solid var(--border-subtle); border-radius: 14px; background: var(--glass-bg); }
.embedded-header { margin-bottom: 24px; }
.embedded-header h1 { margin: 4px 0 7px; color: var(--text-primary); font-size: 22px; letter-spacing: -.02em; }
.embedded-header p { margin: 0; color: var(--text-muted); font-size: 13px; }
.eyebrow { color: var(--accent); font-size: 9px; font-weight: 700; letter-spacing: .14em; }
.embedded-surface .dialog-body { padding: 0; overflow: visible; }

.dialog-overlay {
  background: var(--dialog-overlay);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  z-index: 1000;
}

.dialog {
  background: var(--dialog-surface);
  border: 1px solid var(--dialog-border);
  border-radius: var(--dialog-radius);
  width: 560px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  display: flex;
  flex-direction: column;
  box-shadow: var(--dialog-shadow);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.dialog-header {
  border-bottom: 1px solid var(--dialog-divider);
  background: transparent;
}

.dialog-header h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.close-btn {
  color: var(--text-secondary);
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

@media (max-width: 720px) {
  .embedded-surface { padding: 16px; }
  .field-row { align-items: stretch; flex-direction: column; gap: 5px; }
  .field-row label { min-width: 0; }
  .field-input { min-height: 42px; font-size: 16px; }
  .section-header, .key-card { align-items: stretch; flex-direction: column; }
  .section-header .btn-secondary { min-height: 44px; }
  .btn-copy { min-height: 40px; justify-content: center; margin: 10px 0 0; }
  .gen-actions button, .section-actions button { min-height: 44px; flex: 1; }
}
</style>
