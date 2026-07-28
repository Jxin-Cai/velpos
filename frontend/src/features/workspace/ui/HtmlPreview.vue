<script setup>
import { computed } from 'vue'
import DOMPurify from 'dompurify'

const props = defineProps({
  content: { type: String, default: '' },
  zoom: { type: Number, default: 1 },
  truncated: { type: Boolean, default: false },
})

const contentSecurityPolicy = [
  "default-src 'none'",
  "img-src data: blob:",
  "style-src 'unsafe-inline'",
  'font-src data:',
  'media-src data: blob:',
  "connect-src 'none'",
  "frame-src 'none'",
  "object-src 'none'",
  "form-action 'none'",
].join('; ')

const safeDocument = computed(() => {
  const sanitized = DOMPurify.sanitize(props.content, {
    WHOLE_DOCUMENT: true,
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'base', 'meta', 'link'],
    FORBID_ATTR: ['href', 'action', 'formaction', 'srcdoc'],
  })
  const securityHead = [
    `<meta http-equiv="Content-Security-Policy" content="${contentSecurityPolicy}">`,
    '<meta name="referrer" content="no-referrer">',
    '<style>html{color-scheme:light}body{margin:16px;overflow-wrap:anywhere}</style>',
  ].join('')
  if (sanitized.includes('<head>')) return sanitized.replace('<head>', `<head>${securityHead}`)
  return `<!doctype html><html><head>${securityHead}</head><body>${sanitized}</body></html>`
})
</script>

<template>
  <div class="html-preview">
    <div class="html-security-note">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/>
      </svg>
      Scripts, forms, external resources, and navigation are disabled.
    </div>
    <div v-if="truncated" class="html-warning">The file is truncated; the preview may be incomplete.</div>
    <div class="html-frame-wrap">
      <iframe
        class="html-frame"
        title="HTML preview"
        :srcdoc="safeDocument"
        sandbox=""
        referrerpolicy="no-referrer"
        :style="{ zoom }"
      ></iframe>
    </div>
  </div>
</template>

<style scoped>
.html-preview {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
}

.html-security-note {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--green, #66a56f);
  font-size: 11px;
}

.html-frame-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}

.html-frame {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 420px;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: #fff;
  transform-origin: top left;
}

.html-warning {
  padding: 8px 12px;
  color: var(--yellow);
  font-size: 11px;
}
</style>
