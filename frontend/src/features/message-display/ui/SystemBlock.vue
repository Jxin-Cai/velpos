<script setup>
defineProps({
  content: {
    type: String,
    required: true,
  },
  html: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <div class="msg-system" :class="{ 'msg-system--rich': html }">
    <div class="system-header">
      <span class="system-label">System</span>
      <span>{{ content }}</span>
    </div>
    <div v-if="html" class="system-content markdown-body" v-html="html"></div>
  </div>
</template>

<style scoped>
.msg-system {
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0;
}

.msg-system--rich {
  padding: 8px 0 12px;
  text-align: left;
}

.system-header {
  text-align: center;
}

.system-content {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.65;
  overflow-wrap: anywhere;
  overflow-x: auto;
}

.system-label {
  font-weight: 600;
  margin-right: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-size: 10px;
}
</style>
