<script setup>
import { computed } from 'vue'

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  success: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['confirm'])

const busy = computed(() => props.disabled || props.loading || props.success)
const spinning = computed(() => props.loading && !props.success)

const label = computed(() => {
  if (props.success) return '已同步'
  if (props.loading) return '同步中…'
  return '同步'
})

function onClick() {
  if (busy.value) return
  emit('confirm')
}
</script>

<template>
  <button
    class="btn-sync"
    type="button"
    :class="{
      'btn-sync--loading': spinning,
      'btn-sync--success': success,
    }"
    :disabled="busy"
    :aria-label="success ? '渠道已同步' : loading ? '正在同步渠道环境' : '同步渠道环境到 Claude Code'"
    :aria-busy="loading"
    title="同步渠道环境到 Claude Code，会断开当前 SDK 会话"
    @click="onClick"
  >
    <span class="btn-sync__content">
      <svg
        v-if="success"
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <polyline points="20 6 9 17 4 12" />
      </svg>
      <svg
        v-else
        class="btn-sync__icon"
        :class="{ 'btn-sync__icon--spin': spinning }"
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <polyline points="1 4 1 10 7 10" />
        <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
      </svg>
      {{ label }}
    </span>
  </button>
</template>

<style scoped>
.btn-sync {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 76px;
  min-height: 26px;
  padding: 4px 12px;
  border: 1px solid var(--blue, #58a6ff);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--blue, #58a6ff);
  font-size: 12px;
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast), color var(--transition-fast);
}

.btn-sync:hover:not(:disabled) {
  background: var(--blue-dim, rgba(88, 166, 255, 0.1));
}

.btn-sync:focus-visible {
  outline: 2px solid var(--blue, #58a6ff);
  outline-offset: 2px;
}

.btn-sync:disabled {
  cursor: not-allowed;
}

.btn-sync:disabled:not(.btn-sync--success):not(.btn-sync--loading) {
  opacity: 0.4;
}

.btn-sync--loading {
  opacity: 0.85;
}

.btn-sync--success {
  border-color: var(--green);
  color: var(--green);
  background: var(--green-dim);
  opacity: 1;
}

.btn-sync__content {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}

.btn-sync__icon--spin {
  animation: sync-spin 0.7s linear infinite;
}

@keyframes sync-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .btn-sync__icon--spin {
    animation: none;
  }
}
</style>
