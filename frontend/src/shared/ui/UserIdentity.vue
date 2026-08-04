<script setup>
import { computed } from 'vue'

const props = defineProps({
  user: { type: Object, default: null },
  compact: { type: Boolean, default: false },
})

const emit = defineEmits(['logout'])

const displayName = computed(() => props.user?.display_name || props.user?.username || '未登录')
const initial = computed(() => displayName.value.slice(0, 1).toUpperCase())
</script>

<template>
  <div class="user-identity" :class="{ compact }">
    <span class="avatar" aria-hidden="true">{{ initial }}</span>
    <span v-if="!compact" class="identity-copy">
      <span class="display-name">{{ displayName }}</span>
      <span class="account-meta">{{ user?.username }} · {{ user?.role === 'admin' ? '管理员' : '用户' }}</span>
    </span>
    <button class="logout-button" type="button" title="退出登录" aria-label="退出登录" @click="emit('logout')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
        <polyline points="16 17 21 12 16 7" />
        <line x1="21" y1="12" x2="9" y2="12" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.user-identity {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  padding-left: 10px;
  border-left: 1px solid var(--border-subtle);
}

.avatar {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  border: 1px solid color-mix(in srgb, var(--accent) 36%, transparent);
  border-radius: 9px;
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}

.identity-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.15;
}

.display-name {
  max-width: 130px;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-meta {
  max-width: 150px;
  margin-top: 3px;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.logout-button {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.logout-button:hover,
.logout-button:focus-visible {
  background: var(--layer-active);
  color: var(--text-primary);
  outline: none;
}

.compact .identity-copy {
  display: none;
}

@media (max-width: 900px) {
  .identity-copy {
    display: none;
  }
}
@media (max-width: 720px) { .logout-button { width: 44px; height: 44px; } .avatar { width: 36px; height: 36px; } .user-identity { gap: 4px; padding-left: 6px; } }
</style>
