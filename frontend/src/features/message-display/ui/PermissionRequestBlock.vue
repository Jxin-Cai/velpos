<script setup>
const props = defineProps({
  block: { type: Object, required: true },
  answered: { type: Boolean, default: false },
})

const emit = defineEmits(['respond'])

function handleAllow() {
  emit('respond', { decision: 'allow' })
}

function handleDeny() {
  emit('respond', { decision: 'deny' })
}
</script>

<template>
  <div class="permission-block" :class="{ 'perm-answered': answered }">
    <div class="perm-header">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      </svg>
      <span>Permission Required</span>
    </div>

    <div class="perm-tool">
      <span class="tool-label">Tool:</span>
      <span class="tool-name">{{ block.tool_name }}</span>
    </div>

    <div v-if="block.tool_input" class="perm-input">
      <pre class="input-preview">{{ block.tool_input }}</pre>
    </div>

    <div v-if="!answered" class="perm-actions">
      <button class="perm-btn perm-allow" @click="handleAllow">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        Allow
      </button>
      <button class="perm-btn perm-deny" @click="handleDeny">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
        Deny
      </button>
    </div>
    <div v-else class="perm-resolved">Responded</div>
  </div>
</template>

<style scoped>
.permission-block {
  background: var(--bg-secondary);
  border: 1px solid var(--yellow, #e5a100);
  border-radius: var(--radius-md);
  padding: 16px;
  margin: 8px 0;
}

.perm-answered {
  opacity: 0.7;
  border-color: var(--border);
}

.perm-header {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--yellow, #e5a100);
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 10px;
}

.perm-tool {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 13px;
}

.tool-label {
  color: var(--text-muted);
}

.tool-name {
  color: var(--text-primary);
  font-weight: 600;
  font-family: var(--font-mono);
}

.perm-input {
  margin-bottom: 12px;
}

.input-preview {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow: auto;
  margin: 0;
}

.perm-actions {
  display: flex;
  gap: 8px;
}

.perm-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-sm);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.perm-btn:hover {
  opacity: 0.85;
}

.perm-allow {
  background: var(--green, #22c55e);
  color: white;
}

.perm-deny {
  background: var(--red, #ef4444);
  color: white;
}

.perm-resolved {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
}
</style>
