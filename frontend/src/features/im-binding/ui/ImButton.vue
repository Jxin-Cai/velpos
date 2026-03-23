<script setup>
defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  bound: {
    type: Boolean,
    default: false,
  },
  channelType: {
    type: String,
    default: '',
  },
  instanceName: {
    type: String,
    default: '',
  },
})

const CHANNEL_LABELS = {
  openim: 'OpenIM',
  lark: 'Lark',
  qq: 'QQ',
  weixin: 'WeChat',
}

const emit = defineEmits(['click'])

function getLabel(bound, channelType, instanceName) {
  if (!bound) return 'IM'
  if (instanceName) return instanceName
  return CHANNEL_LABELS[channelType] || channelType || 'IM'
}
</script>

<template>
  <button
    class="im-btn"
    :class="{ 'im-btn--bound': bound }"
    :disabled="disabled"
    @click="emit('click')"
    title="IM Integration"
  >
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
    <span class="im-btn-label">{{ getLabel(bound, channelType, instanceName) }}</span>
    <span v-if="bound" class="im-status-dot"></span>
  </button>
</template>

<style scoped>
.im-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition:
    color var(--transition-fast),
    background var(--transition-fast),
    border-color var(--transition-fast),
    transform 0.12s var(--ease-spring),
    box-shadow var(--transition-fast);
  font-family: var(--font-sans);
  white-space: nowrap;
  position: relative;
}

.im-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--accent);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.im-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.97);
  box-shadow: var(--shadow-xs);
  transition-duration: 60ms;
}

.im-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.im-btn--bound {
  color: var(--green);
  border-color: var(--green);
  background: var(--green-dim);
  box-shadow: 0 0 0 1px var(--green-dim);
}

.im-btn--bound:hover:not(:disabled) {
  border-color: var(--green);
  color: var(--green);
  background: var(--green-dim);
  box-shadow: var(--shadow-md), 0 0 12px var(--green-dim);
  transform: translateY(-1px);
}

.im-btn--bound:active:not(:disabled) {
  transform: translateY(0) scale(0.97);
  box-shadow: 0 0 0 1px var(--green-dim);
  transition-duration: 60ms;
}

.im-btn-label {
  font-weight: 500;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.im-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 4px var(--green);
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px var(--green); }
  50% { opacity: 0.4; box-shadow: 0 0 8px var(--green); }
}

@media (max-width: 768px) {
  .im-btn-label {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .im-btn {
    transition: color 0.15s, background 0.15s, border-color 0.15s;
  }
  .im-btn:hover:not(:disabled) {
    transform: none;
  }
  .im-btn:active:not(:disabled) {
    transform: none;
  }
  .im-status-dot {
    animation-duration: 0.01ms;
  }
}
</style>
