<script setup>
import { computed, ref, watch } from 'vue'
import { formatFileSize } from '@shared/lib/textParsers'

const props = defineProps({
  attachment: { type: Object, required: true },
  projectId: { type: String, default: '' },
  sessionId: { type: String, default: '' },
})

const emit = defineEmits(['open-file'])
const previewFailed = ref(false)
const previewCandidateIndex = ref(0)

const path = computed(() => props.attachment?.path || '')
const name = computed(() => (
  props.attachment?.filename
  || props.attachment?.name
  || path.value.split('/').pop()
  || 'attachment'
))
const mimeType = computed(() => (
  props.attachment?.mime_type
  || props.attachment?.media_type
  || 'application/octet-stream'
).toLowerCase())
const extension = computed(() => name.value.split('.').pop()?.toLowerCase() || '')
const size = computed(() => formatFileSize(
  props.attachment?.size_bytes || props.attachment?.size || 0,
))
const canOpen = computed(() => Boolean(path.value))
const previewCandidates = computed(() => {
  const candidates = []
  if (props.attachment?.preview) candidates.push(props.attachment.preview)
  if (props.sessionId && path.value) {
    candidates.push(
      `/api/sessions/${encodeURIComponent(props.sessionId)}/attachments/preview`
      + `?path=${encodeURIComponent(path.value)}`,
    )
  }
  if (props.attachment?.id) {
    candidates.push(`/api/attachments/${encodeURIComponent(props.attachment.id)}/preview`)
  }
  return [...new Set(candidates)]
})
const previewUrl = computed(() => previewCandidates.value[previewCandidateIndex.value] || '')
const visualType = computed(() => {
  if (mimeType.value.startsWith('image/')) return 'image'
  if (mimeType.value.startsWith('video/')) return 'video'
  if (mimeType.value.startsWith('audio/')) return 'audio'
  if (extension.value === 'pdf' || mimeType.value === 'application/pdf') return 'pdf'
  if (['csv', 'xls', 'xlsx'].includes(extension.value)) return 'table'
  if (['md', 'markdown'].includes(extension.value)) return 'markdown'
  if (extension.value === 'json') return 'json'
  if (['html', 'htm'].includes(extension.value)) return 'html'
  if ([
    'js', 'jsx', 'ts', 'tsx', 'vue', 'py', 'java', 'go', 'rs', 'rb', 'php',
    'css', 'scss', 'less', 'sh', 'bash', 'zsh', 'sql', 'xml', 'yaml', 'yml',
  ].includes(extension.value)) return 'code'
  return 'file'
})
const typeLabel = computed(() => {
  const labels = {
    image: 'Image',
    video: 'Video',
    audio: 'Audio',
    pdf: 'PDF',
    table: extension.value.toUpperCase() || 'Table',
    markdown: 'Markdown',
    json: 'JSON',
    html: 'HTML',
    code: extension.value.toUpperCase() || 'Code',
    file: extension.value.toUpperCase() || 'File',
  }
  return labels[visualType.value]
})

function openFile() {
  if (canOpen.value) emit('open-file', path.value)
}

function handlePreviewError() {
  if (previewCandidateIndex.value < previewCandidates.value.length - 1) {
    previewCandidateIndex.value += 1
    return
  }
  previewFailed.value = true
}

watch(previewCandidates, () => {
  previewCandidateIndex.value = 0
  previewFailed.value = false
})
</script>

<template>
  <button
    type="button"
    class="message-attachment-card"
    :class="`is-${visualType}`"
    :disabled="!canOpen"
    :title="`在文件管理中打开 ${name}`"
    :aria-label="`在文件管理中打开附件 ${name}`"
    @click.stop="openFile"
  >
    <span class="attachment-type-icon" :data-label="typeLabel" aria-hidden="true">
      <img
        v-if="visualType === 'image' && previewUrl && !previewFailed"
        class="attachment-thumbnail"
        :src="previewUrl"
        :alt="`图片缩略图：${name}`"
        loading="lazy"
        @error="handlePreviewError"
      />
      <svg v-else-if="visualType === 'image'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m4 17 5-5 4 4 3-3 4 4"/>
      </svg>
      <svg v-else-if="visualType === 'video'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <rect x="3" y="5" width="15" height="14" rx="2"/><path d="m18 10 4-2v8l-4-2z"/>
      </svg>
      <svg v-else-if="visualType === 'audio'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>
      </svg>
      <svg v-else-if="visualType === 'pdf'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>
      </svg>
      <svg v-else-if="visualType === 'table'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 9v11M15 9v11"/>
      </svg>
      <svg v-else-if="visualType === 'code' || visualType === 'json' || visualType === 'html'" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path d="m8 9-4 3 4 3M16 9l4 3-4 3M14 5l-4 14"/>
      </svg>
      <svg v-else width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>
      </svg>
    </span>

    <span class="attachment-card-body">
      <span class="attachment-card-name">{{ name }}</span>
      <span class="attachment-card-meta">
        <span>{{ typeLabel }}</span>
        <span v-if="size">{{ size }}</span>
      </span>
    </span>
    <span class="attachment-open-icon" aria-hidden="true">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M3 10h18"/>
      </svg>
    </span>
  </button>
</template>

<style scoped>
.message-attachment-card {
  position: relative;
  width: min(100%, 330px);
  min-height: 68px;
  display: grid;
  grid-template-columns: 50px minmax(0, 1fr) 28px;
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
  transition: border-color var(--transition-fast), background var(--transition-fast), box-shadow var(--transition-fast);
}

.message-attachment-card:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
  background: var(--bg-hover);
  box-shadow: 0 4px 16px rgb(0 0 0 / 9%);
}

.message-attachment-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.message-attachment-card:disabled {
  cursor: wait;
  opacity: 0.62;
}

.attachment-type-icon {
  position: relative;
  width: 50px;
  height: 50px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--bg-primary);
  color: var(--accent);
  overflow: hidden;
}

.attachment-thumbnail {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.is-image .attachment-type-icon { color: var(--green); }
.is-video .attachment-type-icon { color: var(--purple); }
.is-audio .attachment-type-icon { color: var(--yellow); }
.is-pdf .attachment-type-icon { color: var(--red); }
.is-table .attachment-type-icon { color: var(--green); }
.is-code .attachment-type-icon,
.is-json .attachment-type-icon,
.is-html .attachment-type-icon { color: var(--accent); }

.attachment-type-icon:not(:has(.attachment-thumbnail))::after {
  content: attr(data-label);
  position: absolute;
  right: 3px;
  bottom: 2px;
  max-width: 43px;
  overflow: hidden;
  color: var(--text-muted);
  font: 700 7px/1 var(--font-sans);
  letter-spacing: 0.04em;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}

.attachment-card-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.attachment-card-name {
  overflow: hidden;
  font-size: 12px;
  font-weight: 650;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attachment-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.3;
}

.attachment-card-meta span + span::before {
  content: '·';
  margin-right: 8px;
}

.attachment-open-icon {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: var(--text-muted);
}

.message-attachment-card:hover:not(:disabled) .attachment-open-icon {
  color: var(--accent);
  background: var(--accent-dim);
}

@media (max-width: 520px) {
  .message-attachment-card {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .message-attachment-card {
    transition: none;
  }

}
</style>
