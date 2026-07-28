<script setup>
import { computed } from 'vue'

const props = defineProps({
  block: {
    type: Object,
    required: true,
  },
})
const emit = defineEmits(['open-file'])

const artifactPath = computed(() => (
  props.block.path
  || props.block.file_path
  || props.block.output_file
  || props.block.url
  || ''
))

const artifactLabel = computed(() => (
  props.block.label
  || props.block.name
  || props.block.filename
  || artifactPath.value.split('/').pop()
  || 'Artifact'
))

const isWebUrl = computed(() => /^https?:\/\//i.test(artifactPath.value))
function openArtifact() {
  if (!artifactPath.value || isWebUrl.value) return
  emit('open-file', artifactPath.value)
}
</script>

<template>
  <div class="artifact-block">
    <span class="artifact-badge">Artifact</span>
    <a
      v-if="isWebUrl"
      class="artifact-link"
      :href="artifactPath"
      target="_blank"
      rel="noreferrer"
    >
      {{ artifactLabel }}
    </a>
    <button
      v-else-if="artifactPath"
      type="button"
      class="artifact-link artifact-button"
      :title="artifactPath"
      @click="openArtifact"
    >
      {{ artifactLabel }}
    </button>
    <span v-else class="artifact-label">{{ artifactLabel }}</span>
  </div>
</template>

<style scoped>
.artifact-block {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.artifact-badge {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.artifact-link,
.artifact-label {
  min-width: 0;
  overflow: hidden;
  color: var(--accent);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-button {
  border: 0;
  padding: 0;
  background: transparent;
  font: inherit;
  cursor: pointer;
}

.artifact-link:hover,
.artifact-link:focus-visible {
  text-decoration: underline;
}

</style>
