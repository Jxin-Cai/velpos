<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  content: { type: String, default: '' },
  truncated: { type: Boolean, default: false },
})

const previewVersion = ref(0)

const contentSecurityPolicy = [
  "default-src 'none'",
  "img-src data: blob:",
  "script-src 'unsafe-inline' 'unsafe-eval' blob:",
  "style-src 'unsafe-inline' blob:",
  'font-src data:',
  'media-src data: blob:',
  "connect-src 'none'",
  "frame-src 'none'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join('; ')

const safeDocument = computed(() => {
  const securityHead = [
    `<meta http-equiv="Content-Security-Policy" content="${contentSecurityPolicy}">`,
    '<meta name="referrer" content="no-referrer">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<style>html{color-scheme:light}body{overflow-wrap:anywhere}</style>',
  ].join('')
  const source = props.content || ''
  if (/<head(?:\s[^>]*)?>/i.test(source)) {
    return source.replace(/<head(\s[^>]*)?>/i, (head) => `${head}${securityHead}`)
  }
  if (/<html(?:\s[^>]*)?>/i.test(source)) {
    return source.replace(/<html(\s[^>]*)?>/i, (html) => `${html}<head>${securityHead}</head>`)
  }
  return `<!doctype html><html><head>${securityHead}</head><body>${source}</body></html>`
})

function reloadPreview() {
  previewVersion.value += 1
}
</script>

<template>
  <div class="html-preview">
    <div class="html-preview-toolbar">
      <div class="html-security-note">
        <span class="interactive-indicator" aria-hidden="true"></span>
        <div>
          <strong>Interactive preview</strong>
          <span>Clicks, typing, forms, and local scripts run in an isolated sandbox.</span>
        </div>
      </div>
      <button type="button" aria-label="Reload HTML preview" title="Reload preview" @click="reloadPreview">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M20 11a8.1 8.1 0 1 0 2 5.3"/><path d="M20 4v7h-7"/>
        </svg>
        <span>Reload</span>
      </button>
    </div>
    <div v-if="truncated" class="html-warning">The file is truncated; the preview may be incomplete.</div>
    <div class="html-frame-wrap">
      <iframe
        :key="previewVersion"
        class="html-frame"
        title="HTML preview"
        :srcdoc="safeDocument"
        sandbox="allow-scripts allow-forms allow-modals allow-pointer-lock"
        referrerpolicy="no-referrer"
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

.html-preview-toolbar {
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 10px 6px 14px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
}

.html-security-note {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--text-secondary);
  font-size: 11px;
}

.html-security-note > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.html-security-note strong {
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 650;
}

.html-security-note span:last-child {
  overflow: hidden;
  color: var(--text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.interactive-indicator {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--green, #66a56f);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--green, #66a56f) 12%, transparent);
}

.html-preview-toolbar button {
  min-width: 76px;
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 0 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  background: var(--bg-primary);
  cursor: pointer;
  font: 600 11px/1 var(--font-sans);
  transition: color var(--transition-fast), border-color var(--transition-fast), background var(--transition-fast);
}

.html-preview-toolbar button:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--layer-active);
}

.html-preview-toolbar button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.html-frame-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: clamp(10px, 1.4vw, 18px);
  background:
    radial-gradient(circle at 50% 0%, color-mix(in srgb, var(--accent) 5%, transparent), transparent 42%),
    var(--layer-base);
}

.html-frame {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 420px;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 10px 32px rgb(0 0 0 / 14%);
  transform-origin: top left;
}

.html-warning {
  padding: 8px 12px;
  color: var(--yellow);
  font-size: 11px;
}

@media (max-width: 620px) {
  .html-security-note span:last-child,
  .html-preview-toolbar button span {
    display: none;
  }

  .html-preview-toolbar button {
    min-width: 40px;
    min-height: 40px;
    padding: 0;
  }
}
</style>
