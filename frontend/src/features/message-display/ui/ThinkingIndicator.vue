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
  </div>
</template>

<style scoped>
.thinking-indicator {
  padding: 0;
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
</style>
