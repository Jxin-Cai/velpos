<script setup>
import { ref, computed, nextTick } from 'vue'

const props = defineProps({
  channels: {
    type: Array,
    default: () => [],
  },
  currentSessionId: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['select', 'create', 'delete', 'rename', 'navigate-session'])

const selectedType = ref(null)
const confirmingDelete = ref(null)
const editingId = ref(null)
const editingName = ref('')
const renameInputRef = ref(null)

const ICON_MAP = {
  openim: {
    viewBox: '0 0 24 24',
    path: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />',
  },
  lark: {
    viewBox: '0 0 24 24',
    path: '<path d="M4 4l6 6"/><path d="M14 10l6-6"/><path d="M12 14l-4 8"/><path d="M12 14l4 8"/><path d="M12 14V6"/><circle cx="12" cy="4" r="2"/>',
  },
  qq: {
    viewBox: '0 0 24 24',
    path: '<ellipse cx="12" cy="10" rx="7" ry="8"/><path d="M5 14c-1 2-1.5 4-.5 4.5s2-.5 3-1.5"/><path d="M19 14c1 2 1.5 4 .5 4.5s-2-.5-3-1.5"/><circle cx="9.5" cy="9" r="1.2"/><circle cx="14.5" cy="9" r="1.2"/>',
  },
  weixin: {
    viewBox: '0 0 24 24',
    path: '<path d="M9 4C5.13 4 2 6.58 2 9.8c0 1.81 1.02 3.43 2.6 4.5l-.65 1.95 2.35-1.18c.86.24 1.78.38 2.7.38.33 0 .65-.02.97-.06"/><path d="M15 8c-3.31 0-6 2.24-6 5s2.69 5 6 5c.7 0 1.37-.1 2-.3l1.8.9-.5-1.5c1.27-.88 2.1-2.25 2.1-3.8 0-2.49-2.24-4.3-5.4-5.3"/><circle cx="8" cy="9" r="0.8"/><circle cx="11" cy="9" r="0.8"/><circle cx="13.5" cy="12" r="0.7"/><circle cx="16.5" cy="12" r="0.7"/>',
  },
}

function getIcon(icon) {
  return ICON_MAP[icon] || ICON_MAP.openim
}

const STATUS_LABELS = {
  ready: 'Ready',
  not_initialized: 'Setup Required',
  initializing: 'Initializing...',
  error: 'Error',
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status
}

const currentChannel = computed(() => {
  if (!selectedType.value) return null
  return props.channels.find(ch => ch.channel_type === selectedType.value) || null
})

const instances = computed(() => {
  return currentChannel.value?.instances || []
})

function instanceCount(ch) {
  return (ch.instances || []).length
}

function isBoundToCurrentSession(inst) {
  return inst.bound_session_id && inst.bound_session_id === props.currentSessionId
}

const DISABLED_CHANNELS = new Set(['openim'])

function isChannelDisabled(ch) {
  return DISABLED_CHANNELS.has(ch.channel_type)
}

function selectType(ch) {
  if (isChannelDisabled(ch)) return
  selectedType.value = ch.channel_type
  if ((ch.instances || []).length === 0) {
    emit('create', ch.channel_type, ch.display_name)
  }
}

function backToTypes() {
  selectedType.value = null
  confirmingDelete.value = null
  editingId.value = null
}

function selectInstance(inst) {
  if (isBoundToCurrentSession(inst)) return
  if (editingId.value === inst.id) return
  const ch = currentChannel.value
  emit('select', { ...inst, channel_type: ch.channel_type, display_name: ch.display_name })
}

function createInstance() {
  if (!currentChannel.value) return
  emit('create', currentChannel.value.channel_type, '')
}

function requestDelete(inst) {
  confirmingDelete.value = inst
}

function confirmDelete() {
  const inst = confirmingDelete.value
  confirmingDelete.value = null
  if (inst) emit('delete', inst.id)
}

function cancelDelete() {
  confirmingDelete.value = null
}

async function startRename(inst) {
  editingId.value = inst.id
  editingName.value = inst.name || inst.id
  await nextTick()
  renameInputRef.value?.focus()
  renameInputRef.value?.select()
}

function submitRename(instId) {
  const name = editingName.value.trim()
  const orig = instances.value.find(i => i.id === instId)
  if (name && name !== (orig?.name || '')) {
    emit('rename', instId, name)
  }
  editingId.value = null
}

function cancelRename() {
  editingId.value = null
}
</script>

<template>
  <div class="channel-picker">
    <!-- Level 1: Type grid -->
    <template v-if="!selectedType">
      <p class="picker-title">Select IM Channel</p>
      <div class="channel-grid">
        <button
          v-for="ch in channels"
          :key="ch.channel_type"
          class="channel-card"
          :class="{ 'channel-card--disabled': isChannelDisabled(ch) }"
          :disabled="isChannelDisabled(ch)"
          @click="selectType(ch)"
        >
          <svg
            width="28"
            height="28"
            :viewBox="getIcon(ch.icon).viewBox"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
            v-html="getIcon(ch.icon).path"
          />
          <span class="channel-name">{{ ch.display_name }}</span>
          <span class="instance-count" v-if="instanceCount(ch) > 0">
            {{ instanceCount(ch) }} instance{{ instanceCount(ch) > 1 ? 's' : '' }}
          </span>
          <span class="channel-mode">{{ ch.binding_mode === 'qr_code' ? 'QR Code' : ch.binding_mode }}</span>
        </button>
      </div>
      <p v-if="channels.length === 0" class="picker-empty">
        No IM channels available. Install a plugin first.
      </p>
    </template>

    <!-- Level 2: Instance table -->
    <template v-else>
      <div class="instance-header">
        <button class="back-link" @click="backToTypes">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          Back
        </button>
        <p class="picker-title">{{ currentChannel?.display_name }} Instances</p>
      </div>

      <!-- Table header -->
      <div class="inst-table" v-if="instances.length > 0">
        <div class="inst-row inst-row--head">
          <span class="inst-col inst-col--channel">Channel</span>
          <span class="inst-col inst-col--name">Name</span>
          <span class="inst-col inst-col--appid">AppID</span>
          <span class="inst-col inst-col--session">Session</span>
          <span class="inst-col inst-col--actions"></span>
        </div>

        <!-- Table rows -->
        <div
          v-for="inst in instances"
          :key="inst.id"
          class="inst-row"
          :class="{
            'inst-row--bound': isBoundToCurrentSession(inst),
            'inst-row--other': inst.bound_session_id && !isBoundToCurrentSession(inst),
          }"
          @click="selectInstance(inst)"
        >
          <span class="inst-col inst-col--channel">
            <svg
              width="16" height="16"
              :viewBox="getIcon(currentChannel?.icon).viewBox"
              fill="none" stroke="currentColor" stroke-width="1.5"
              stroke-linecap="round" stroke-linejoin="round"
              v-html="getIcon(currentChannel?.icon).path"
            />
            {{ currentChannel?.display_name }}
          </span>

          <span class="inst-col inst-col--name">
            <input
              v-if="editingId === inst.id"
              ref="renameInputRef"
              v-model="editingName"
              class="rename-input"
              @keydown.enter="submitRename(inst.id)"
              @keydown.escape="cancelRename"
              @blur="submitRename(inst.id)"
              @click.stop
            />
            <template v-else>
              <span class="name-text" :title="inst.name || inst.id">{{ inst.name || inst.id }}</span>
              <button class="edit-btn" @click.stop="startRename(inst)" title="Rename">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
            </template>
          </span>

          <span class="inst-col inst-col--appid" :title="inst.app_id || '-'">
            <span class="appid-text">{{ inst.app_id || '-' }}</span>
          </span>

          <span class="inst-col inst-col--session">
            <a
              v-if="inst.bound_session_id"
              class="session-link"
              :class="{ 'session-link--current': isBoundToCurrentSession(inst) }"
              href="#"
              @click.stop.prevent="emit('navigate-session', inst.bound_session_id)"
              :title="'Go to session ' + inst.bound_session_id"
            >{{ inst.bound_session_id.slice(0, 8) }}</a>
            <span v-else class="session-empty">-</span>
          </span>

          <span class="inst-col inst-col--actions">
            <button
              class="action-btn action-btn--delete"
              @click.stop="requestDelete(inst)"
              title="Delete"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                <path d="M10 11v6"/><path d="M14 11v6"/>
              </svg>
            </button>
          </span>
        </div>
      </div>

      <!-- Add button -->
      <button class="add-btn" @click="createInstance">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        New Instance
      </button>

      <p v-if="instances.length === 0" class="picker-empty">
        No instances yet. Creating one...
      </p>
    </template>

    <!-- Delete confirmation -->
    <Transition name="confirm-fade">
      <div v-if="confirmingDelete" class="confirm-overlay" @click.self="cancelDelete">
        <div class="confirm-card">
          <div class="confirm-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
          </div>
          <p class="confirm-title">Delete instance?</p>
          <p class="confirm-desc">
            <strong>{{ confirmingDelete.name || confirmingDelete.id }}</strong> will be removed.
            <template v-if="confirmingDelete.bound_session_id">The bound session will be disconnected.</template>
          </p>
          <div class="confirm-actions">
            <button class="confirm-btn confirm-btn--cancel" @click="cancelDelete">Cancel</button>
            <button class="confirm-btn confirm-btn--ok" @click="confirmDelete">Delete</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.channel-picker {
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: relative;
}

.picker-title {
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
  margin: 0;
}

/* ── Level 1: Type grid ── */

.channel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.channel-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s, transform 0.2s, box-shadow 0.2s;
}

.channel-card:hover {
  border-color: var(--accent);
  background: var(--accent-dim);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0,0,0,0.08));
}

.channel-card:active { transform: translateY(0); }

.channel-card--disabled {
  opacity: 0.4;
  cursor: not-allowed;
  pointer-events: none;
}

.channel-card svg {
  color: var(--text-secondary);
  transition: color 0.2s;
}
.channel-card:hover svg { color: var(--accent); }

.channel-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.instance-count {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--accent-dim);
  color: var(--accent);
  font-weight: 500;
}

.channel-mode {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ── Level 2: Instance table ── */

.instance-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
  align-self: flex-start;
  transition: color 0.15s;
}
.back-link:hover { color: var(--text-primary); }

.inst-table {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.inst-row {
  display: grid;
  grid-template-columns: 80px 1fr 100px 80px 36px;
  align-items: center;
  gap: 4px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.15s;
  min-height: 40px;
}

.inst-row:last-child { border-bottom: none; }

.inst-row:not(.inst-row--head):hover {
  background: var(--accent-dim);
}

.inst-row--head {
  background: var(--bg-tertiary);
  cursor: default;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  min-height: 32px;
  padding: 6px 10px;
}

.inst-row--bound {
  background: var(--green-dim, rgba(52, 211, 153, 0.04));
  cursor: default;
}
.inst-row--bound:hover {
  background: var(--green-dim, rgba(52, 211, 153, 0.08));
}

.inst-row--other {
  background: var(--yellow-dim, rgba(245, 158, 11, 0.04));
}

.inst-col {
  font-size: 12px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inst-col--channel {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-secondary);
  font-size: 11px;
}

.inst-col--channel svg {
  flex-shrink: 0;
}

.inst-col--name {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.name-text {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.edit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
}
.inst-row:hover .edit-btn { opacity: 1; }
.edit-btn:hover {
  color: var(--accent);
  background: var(--accent-dim);
}

.rename-input {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  background: var(--bg-input, var(--bg-primary));
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  outline: none;
  width: 100%;
  max-width: 160px;
  font-family: inherit;
}

.inst-col--appid {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
}

.appid-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inst-col--status { text-align: center; }

.inst-col--actions {
  display: flex;
  justify-content: center;
}

.inst-col--session {
  text-align: center;
}

.session-link {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--accent);
  text-decoration: none;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  transition: background 0.15s, color 0.15s;
}

.session-link:hover {
  background: var(--accent-dim);
  text-decoration: underline;
}

.session-link--current {
  color: var(--green);
}

.session-link--current:hover {
  background: var(--green-dim, rgba(52, 211, 153, 0.1));
}

.session-empty {
  font-size: 11px;
  color: var(--text-muted);
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.action-btn--delete:hover {
  color: var(--red);
  background: var(--red-dim);
}

/* (init-badge styles removed — status shown via session link) */

/* ── Add button ── */

.add-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}

.add-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-dim);
}

.picker-empty {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  padding: 20px;
}

/* ── Confirmation modal ── */

.confirm-overlay {
  position: absolute;
  inset: 0;
  background: var(--bg-overlay, rgba(0, 0, 0, 0.4));
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.confirm-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 20px 24px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  max-width: 280px;
  text-align: center;
}

.confirm-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--red-dim);
  color: var(--red);
}

.confirm-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.confirm-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
}

.confirm-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  width: 100%;
}

.confirm-btn {
  flex: 1;
  padding: 7px 14px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.confirm-btn--cancel {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
}
.confirm-btn--cancel:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.confirm-btn--ok {
  border: none;
  background: var(--red);
  color: #fff;
}
.confirm-btn--ok:hover { filter: brightness(1.1); }

/* ── Transitions ── */

.confirm-fade-enter-active,
.confirm-fade-leave-active {
  transition: opacity 0.2s ease;
}
.confirm-fade-enter-active .confirm-card,
.confirm-fade-leave-active .confirm-card {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.confirm-fade-enter-from,
.confirm-fade-leave-to { opacity: 0; }
.confirm-fade-enter-from .confirm-card,
.confirm-fade-leave-to .confirm-card {
  transform: scale(0.95);
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .channel-card,
  .inst-row {
    transition: border-color 0.15s, background 0.15s;
  }
  .channel-card:hover { transform: none; }
  .confirm-fade-enter-active,
  .confirm-fade-leave-active,
  .confirm-fade-enter-active .confirm-card,
  .confirm-fade-leave-active .confirm-card {
    transition-duration: 0.01ms;
  }
}
</style>
