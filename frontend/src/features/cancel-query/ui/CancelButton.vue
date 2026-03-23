<script setup>
defineProps({
  visible: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits(['cancel'])
</script>

<template>
  <button
    v-show="visible"
    class="cancel-btn"
    @click="emit('cancel')"
  >
    Cancel
  </button>
</template>

<style scoped>
.cancel-btn {
  margin-left: auto;
  background: var(--red-dim);
  color: var(--red);
  border: 1px solid var(--red-dim);
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.cancel-btn:hover {
  background: var(--red-dim);
  filter: brightness(1.3);
  box-shadow: var(--shadow-sm);
}
</style>
