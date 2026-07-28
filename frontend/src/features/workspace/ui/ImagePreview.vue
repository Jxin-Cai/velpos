<script setup>
defineProps({
  src: { type: String, required: true },
  path: { type: String, default: '' },
  zoom: { type: Number, default: 1 },
})
</script>

<template>
  <div class="image-preview">
    <div class="image-viewport">
      <div
        class="image-canvas"
        :style="{ width: `${Math.max(1, zoom) * 100}%`, height: `${Math.max(1, zoom) * 100}%` }"
      >
        <img
          :src="src"
          :alt="path || 'Image preview'"
          :style="{ maxWidth: `${Math.min(1, zoom) * 100}%`, maxHeight: `${Math.min(1, zoom) * 100}%` }"
          draggable="false"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.image-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.image-viewport {
  flex: 1;
  overflow: auto;
  padding: 20px;
  background: var(--layer-base);
}

.image-canvas {
  min-width: 100%;
  min-height: 100%;
  display: grid;
  place-items: center;
  transition: width var(--transition-fast), height var(--transition-fast);
}

.image-canvas img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  box-shadow: var(--shadow-md);
}
</style>
