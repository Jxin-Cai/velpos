<script setup>
defineEmits(['click'])
</script>

<template>
  <button
    class="glass-btn"
    @click="$emit('click')"
    title="Admin"
  >
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 15v2"/>
      <path d="M5 7.5C5 4.5 8.03 2 12 2s7 2.5 7 5.5c0 2.68-2.03 4.5-4.5 5.5H9.5C7.03 12 5 10.18 5 7.5z"/>
      <rect x="8" y="14" width="8" height="5" rx="1"/>
      <path d="M9 19v1a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2v-1"/>
    </svg>
    <span class="admin-btn-label">Admin</span>
  </button>
</template>

<style scoped>
.admin-btn-label {
  font-weight: 500;
}

@media (max-width: 768px) {
  .admin-btn-label {
    display: none;
  }
}
</style>
