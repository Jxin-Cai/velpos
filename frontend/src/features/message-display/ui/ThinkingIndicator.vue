<script setup>
defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
})
</script>

<template>
  <div v-show="visible" class="thinking-indicator">
    <div class="thinking-bar">
      <div class="bar-fill"></div>
    </div>
    <span class="thinking-text">Claude is working...</span>
  </div>
</template>

<style scoped>
.thinking-indicator {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 0;
  color: var(--text-muted);
  font-size: 12px;
}

.thinking-bar {
  height: 2px;
  background: var(--border);
  border-radius: 1px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  width: 40%;
  background: linear-gradient(90deg, var(--accent), var(--purple));
  border-radius: 1px;
  animation: slide 1.5s ease-in-out infinite;
}

@keyframes slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}

.thinking-text {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.3px;
}
</style>
