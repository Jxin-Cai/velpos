<script setup>
defineProps({
  prefix: {
    type: String,
    default: 'logo',
  },
})
</script>

<template>
  <div class="logo">
    <img class="logo-image" src="/logo.png" alt="" aria-hidden="true" />
    <span class="logo-text">Velpos</span>
  </div>
</template>

<style scoped>
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-image {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  object-fit: contain;
  filter: drop-shadow(0 2px 5px rgba(109, 40, 217, 0.2));
}

.logo-text {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}
</style>
