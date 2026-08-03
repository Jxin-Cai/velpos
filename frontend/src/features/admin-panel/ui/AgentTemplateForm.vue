<script setup>
import { ref, onMounted } from 'vue'
import { createAgentTemplate, updateAgentTemplate } from '../api/adminAgentApi'

const props = defineProps({
  template: { type: Object, default: null },
})

const emit = defineEmits(['saved', 'cancel'])

const form = ref({
  name_en: '',
  name_zh: '',
  description_en: '',
  description_zh: '',
  category: '',
  emoji: '🤖',
  color: '#6366f1',
  prompt_en: '',
  prompt_zh: '',
})

const saving = ref(false)
const isEdit = ref(false)

onMounted(() => {
  if (props.template) {
    isEdit.value = true
    form.value = {
      name_en: props.template.name_en || '',
      name_zh: props.template.name_zh || '',
      description_en: props.template.description_en || '',
      description_zh: props.template.description_zh || '',
      category: props.template.category || '',
      emoji: props.template.emoji || '🤖',
      color: props.template.color || '#6366f1',
      prompt_en: props.template.prompt_en || '',
      prompt_zh: props.template.prompt_zh || '',
    }
  }
})

async function handleSubmit() {
  saving.value = true
  try {
    if (isEdit.value) {
      await updateAgentTemplate(props.template.id, form.value)
    } else {
      await createAgentTemplate(form.value)
    }
    emit('saved')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="agent-form">
    <h3 class="form-title">{{ isEdit ? '编辑 Agent 模板' : '新增 Agent 模板' }}</h3>

    <div class="form-grid">
      <div class="form-group">
        <label>名称（中文）</label>
        <input v-model="form.name_zh" type="text" placeholder="例: 代码审查助手" />
      </div>
      <div class="form-group">
        <label>名称（英文）</label>
        <input v-model="form.name_en" type="text" placeholder="e.g. Code Review Assistant" />
      </div>
      <div class="form-group">
        <label>描述（中文）</label>
        <input v-model="form.description_zh" type="text" placeholder="简短描述" />
      </div>
      <div class="form-group">
        <label>描述（英文）</label>
        <input v-model="form.description_en" type="text" placeholder="Short description" />
      </div>
      <div class="form-group">
        <label>分类</label>
        <input v-model="form.category" type="text" placeholder="例: development" />
      </div>
      <div class="form-group form-group-inline">
        <div class="form-group">
          <label>Emoji</label>
          <input v-model="form.emoji" type="text" class="input-sm" />
        </div>
        <div class="form-group">
          <label>颜色</label>
          <input v-model="form.color" type="color" class="input-color" />
        </div>
      </div>
    </div>

    <div class="form-group full">
      <label>Prompt（中文）</label>
      <textarea v-model="form.prompt_zh" rows="8" placeholder="Agent 系统提示词（中文）"></textarea>
    </div>

    <div class="form-group full">
      <label>Prompt（英文）</label>
      <textarea v-model="form.prompt_en" rows="8" placeholder="Agent system prompt (English)"></textarea>
    </div>

    <div class="form-actions">
      <button class="glass-btn" @click="emit('cancel')">取消</button>
      <button class="glass-btn primary" :disabled="saving" @click="handleSubmit">
        {{ saving ? '保存中...' : '保存' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.agent-form {
  max-width: 800px;
}

.form-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 20px;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 16px;
  margin-bottom: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-group.full {
  margin-bottom: 16px;
}

.form-group label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-group input,
.form-group textarea {
  padding: 8px 12px;
  background: var(--layer-base);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  transition: border-color var(--transition-fast);
  resize: vertical;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--accent);
}

.form-group-inline {
  display: flex;
  flex-direction: row;
  gap: 12px;
}

.input-sm {
  width: 60px;
  text-align: center;
}

.input-color {
  width: 40px;
  height: 32px;
  padding: 2px;
  cursor: pointer;
}

.form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 20px;
}
</style>
