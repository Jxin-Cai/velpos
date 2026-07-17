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
    class="toolbar-btn im-btn"
    :class="{ 'im-btn--bound': bound }"
    :disabled="disabled"
    @click="emit('click')"
    :data-tooltip="bound ? `IM · ${getLabel(bound, channelType, instanceName)}` : 'IM integration'"
    title="IM Integration"
    aria-label="Open IM integration"
  >
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
    <span v-if="bound" class="im-status-dot" aria-hidden="true"></span>
  </button>
</template>

<style scoped>
.im-btn {
  position: relative;
  overflow: visible;
}

.im-btn > * {
  position: relative;
}

.im-btn--bound {
  color: var(--green);
}

.im-btn--bound:hover:not(:disabled) {
  color: var(--green);
  border-color: var(--border);
  background: var(--bg-tertiary);
  box-shadow: none;
}

.im-status-dot {
  position: absolute;
  top: 3px;
  right: 3px;
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
