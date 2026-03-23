<script setup>
defineProps({
  block: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <div class="msg-text markdown-body" v-html="block.html"></div>
</template>

<style scoped>
.msg-text {
  padding: 4px 0;
  line-height: 1.7;
  word-break: break-word;
  color: var(--text-primary);
}
</style>
