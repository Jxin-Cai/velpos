<script setup>
defineProps({
  src: { type: String, required: true },
  path: { type: String, default: '' },
  type: { type: String, required: true },
  zoom: { type: Number, default: 1 },
})
</script>

<template>
  <div class="media-preview">
    <div class="media-stage">
      <video
        v-if="type === 'video'"
        :src="src"
        :aria-label="path || 'Video preview'"
        :style="{ width: `${Math.min(100, 72 * zoom)}%` }"
        controls
        preload="metadata"
      ></video>
      <div v-else class="audio-card" :style="{ width: `${Math.min(92, 62 * zoom)}%` }">
        <div class="audio-art" aria-hidden="true">
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>
          </svg>
        </div>
        <div class="audio-info">
          <strong :title="path">{{ path.split('/').pop() || 'Audio file' }}</strong>
          <span>Project audio</span>
        </div>
        <audio :src="src" :aria-label="path || 'Audio preview'" controls preload="metadata"></audio>
      </div>
    </div>
  </div>
</template>

<style scoped>
.media-preview {
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: 24px;
  box-sizing: border-box;
  background:
    radial-gradient(circle at 50% 45%, color-mix(in srgb, var(--accent) 8%, transparent), transparent 48%),
    var(--layer-base);
}

.media-stage {
  min-width: 100%;
  min-height: 100%;
  display: grid;
  place-items: center;
}

video {
  display: block;
  min-width: 280px;
  max-width: 100%;
  max-height: calc(100vh - 180px);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: #000;
  box-shadow: var(--shadow-lg);
  transition: width var(--transition-fast);
}

.audio-card {
  min-width: min(420px, 100%);
  max-width: 720px;
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr);
  gap: 12px;
  padding: 14px;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
  box-shadow: var(--shadow-md);
  transition: width var(--transition-fast);
}

.audio-art {
  grid-row: 1 / 3;
  width: 58px;
  height: 58px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: var(--accent);
  background: var(--accent-dim);
}

.audio-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
}

.audio-info strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.audio-info span {
  color: var(--text-muted);
  font-size: 10px;
}

audio {
  width: 100%;
  height: 32px;
}

@media (max-width: 620px) {
  .media-preview {
    padding: 12px;
  }

  .audio-card {
    width: 100% !important;
    min-width: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  video,
  .audio-card {
    transition: none;
  }
}
</style>
