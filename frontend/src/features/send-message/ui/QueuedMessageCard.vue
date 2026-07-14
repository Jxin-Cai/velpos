<script setup>
import { computed } from 'vue'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
  busy: {
    type: Boolean,
    default: false,
  },
  canSteer: {
    type: Boolean,
    default: false,
  },
  steering: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['steer', 'edit', 'remove'])

const text = computed(() => String(props.message?.prompt || '').trim())
const attachmentCount = computed(() => Number(
  props.message?.attachment_count || props.message?.image_count || 0,
))
</script>

<template>
  <section class="queued-card" aria-label="Queued follow-up message">
    <div class="queued-card__state">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M5 12h14" />
        <path d="m13 6 6 6-6 6" />
      </svg>
      <span>Next</span>
    </div>

    <div class="queued-card__body">
      <p>{{ text || 'Review the attached files.' }}</p>
      <span v-if="attachmentCount" class="queued-card__attachments">
        {{ attachmentCount }} {{ attachmentCount === 1 ? 'attachment' : 'attachments' }}
      </span>
    </div>

    <div class="queued-card__actions">
      <button
        type="button"
        class="queued-card__steer"
        :disabled="busy || steering || !canSteer"
        :title="canSteer ? '引导到当前执行' : '当前没有正在执行的会话'"
        aria-label="引导到当前执行"
        @click="emit('steer')"
      >
        <svg v-if="!steering" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M5 19V9a4 4 0 0 1 4-4h10" />
          <path d="m15 1 4 4-4 4" />
        </svg>
        <span v-else class="queued-card__spinner" aria-hidden="true" />
        <span>{{ steering ? '引导中' : '引导' }}</span>
      </button>
      <button
        type="button"
        class="queued-card__button"
        :disabled="busy || steering"
        title="Edit queued message"
        aria-label="Edit queued message"
        @click="emit('edit')"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L8 18l-4 1 1-4Z" />
        </svg>
      </button>
      <button
        type="button"
        class="queued-card__button queued-card__button--remove"
        :disabled="busy || steering"
        title="Remove queued message"
        aria-label="Remove queued message"
        @click="emit('remove')"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M3 6h18" />
          <path d="M8 6V4h8v2" />
          <path d="M19 6l-1 14H6L5 6" />
          <path d="M10 11v5M14 11v5" />
        </svg>
      </button>
    </div>
  </section>
</template>

<style scoped>
.queued-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: calc(100% - clamp(36px, 4.8vw, 64px));
  margin: 8px auto 0;
  padding: 9px 10px;
  border: 1px solid color-mix(in srgb, var(--glass-border) 86%, transparent);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--glass-bg-strong) 84%, var(--layer-base));
  box-shadow: var(--shadow-sm), inset 0 1px 0 var(--glass-highlight);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}

.queued-card__state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  align-self: start;
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.queued-card__body {
  min-width: 0;
}

.queued-card__body p {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.queued-card__attachments {
  display: block;
  margin-top: 3px;
  color: var(--text-muted);
  font-size: 10px;
}

.queued-card__actions {
  display: flex;
  align-items: center;
  gap: 3px;
}

.queued-card__steer {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 58px;
  height: 30px;
  padding: 0 9px;
  border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
  border-radius: var(--radius-sm);
  background: var(--accent-dim);
  color: var(--accent);
  font: inherit;
  font-size: 11px;
  font-weight: 650;
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast), border-color var(--transition-fast);
}

.queued-card__steer:hover:not(:disabled),
.queued-card__steer:focus-visible {
  border-color: color-mix(in srgb, var(--accent) 52%, transparent);
  background: color-mix(in srgb, var(--accent-dim) 72%, var(--layer-active));
}

.queued-card__steer:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.queued-card__steer:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.queued-card__spinner {
  width: 12px;
  height: 12px;
  border: 1.5px solid color-mix(in srgb, currentColor 35%, transparent);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: queued-card-spin 0.7s linear infinite;
}

@keyframes queued-card-spin {
  to { transform: rotate(360deg); }
}

.queued-card__button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast);
}

.queued-card__button:hover:not(:disabled),
.queued-card__button:focus-visible {
  background: var(--layer-active);
  color: var(--text-primary);
}

.queued-card__button--remove:hover:not(:disabled),
.queued-card__button--remove:focus-visible {
  color: var(--red);
}

.queued-card__button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.queued-card__button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (max-width: 640px) {
  .queued-card {
    width: calc(100% - 24px);
  }

  .queued-card__state span {
    display: none;
  }
}

@media (pointer: coarse) {
  .queued-card__steer,
  .queued-card__button {
    min-height: 44px;
  }

  .queued-card__button {
    width: 44px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .queued-card__spinner {
    animation-duration: 1.4s;
  }
}
</style>
