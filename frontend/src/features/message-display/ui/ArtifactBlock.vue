<script setup>
import { computed } from 'vue'

const props = defineProps({
  block: {
    type: Object,
    required: true,
  },
})
const emit = defineEmits(['open-file'])

const artifactPath = computed(() => {
  const path = props.block.path
    || props.block.file_path
    || props.block.output_file
    || props.block.url
    || ''
  return typeof path === 'string' ? path : String(path)
})

const artifactLabel = computed(() => {
  const label = props.block.label || props.block.name || props.block.filename
  if (label) return String(label)
  const normalizedPath = artifactPath.value.replace(/\\/g, '/')
  return normalizedPath.split('/').pop() || 'Artifact'
})

const artifactExtension = computed(() => {
  const name = artifactLabel.value
  const extension = name.includes('.') ? name.split('.').pop() : ''
  return extension ? extension.slice(0, 8).toUpperCase() : 'FILE'
})

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
      :title="`Open ${artifactLabel} in a new tab`"
    >
      <span class="artifact-link-name">{{ artifactLabel }}</span>
      <span class="artifact-link-hint">Open in new tab</span>
    </a>
    <button
      v-else-if="artifactPath"
      type="button"
      class="artifact-file-button"
      :title="`Open ${artifactLabel} in workspace`"
      :aria-label="`Open file ${artifactLabel} in workspace`"
      @click.stop="openArtifact"
    >
      <span class="artifact-file-icon" :data-label="artifactExtension" aria-hidden="true">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <path d="M14 2v6h6"/>
        </svg>
      </span>
      <span class="artifact-file-body">
        <span class="artifact-file-name">{{ artifactLabel }}</span>
        <span class="artifact-file-hint">Open file</span>
      </span>
      <span class="artifact-open-icon" aria-hidden="true">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12h14M13 6l6 6-6 6"/>
        </svg>
      </span>
    </button>
    <span v-else class="artifact-label">{{ artifactLabel }}</span>
  </div>
</template>

<style scoped>
.artifact-block {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 6px 0;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--bg-secondary) 88%, transparent);
}

.artifact-badge {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.artifact-label {
  min-width: 0;
  overflow: hidden;
  color: var(--accent);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-file-button {
  width: min(100%, 340px);
  min-width: 0;
  min-height: 68px;
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) 28px;
  align-items: center;
  gap: 10px;
  padding: 8px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--bg-secondary) 88%, transparent);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  font: inherit;
  transition: border-color var(--transition-fast), background var(--transition-fast), box-shadow var(--transition-fast);
}

.artifact-file-button:hover {
  border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
  background: var(--bg-hover);
  box-shadow: 0 4px 16px rgb(0 0 0 / 9%);
}

.artifact-file-button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.artifact-file-icon {
  position: relative;
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--bg-primary);
  color: var(--accent);
}

.artifact-file-icon::after {
  content: attr(data-label);
  position: absolute;
  right: 3px;
  bottom: 3px;
  max-width: 38px;
  overflow: hidden;
  color: var(--text-muted);
  font: 700 7px/1 var(--font-sans);
  letter-spacing: 0.04em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-file-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.artifact-file-name,
.artifact-link-name {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-file-hint,
.artifact-link-hint {
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.3;
}

.artifact-open-icon {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: var(--text-muted);
}

.artifact-file-button:hover .artifact-open-icon,
.artifact-file-button:focus-visible .artifact-open-icon {
  color: var(--accent);
  background: var(--accent-dim);
}

.artifact-link {
  min-width: 0;
  max-width: 100%;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--accent);
  text-decoration: none;
}

.artifact-link:hover,
.artifact-link:focus-visible {
  text-decoration: underline;
}

@media (max-width: 520px) {
  .artifact-file-button {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .artifact-file-button {
    transition: none;
  }
}
</style>
