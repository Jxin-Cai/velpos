<script setup>
defineProps({
  content: {
    type: String,
    required: true,
  },
})
</script>

<template>
  <div class="msg-system">
    <span class="system-label">System</span>
    {{ content }}
  </div>
</template>

<style scoped>
.msg-system {
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0;
}

.system-label {
  font-weight: 600;
  margin-right: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-size: 10px;
}
</style>
