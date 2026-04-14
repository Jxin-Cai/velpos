<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  block: { type: Object, required: true },
  answered: { type: Boolean, default: false },
})

const emit = defineEmits(['answer'])

// Track selected answers per question
const selections = ref({})

const questions = computed(() => props.block.input?.questions || [])

function toggleOption(qIdx, optLabel, multiSelect) {
  const key = `q${qIdx}`
  if (multiSelect) {
    const current = selections.value[key] || []
    if (current.includes(optLabel)) {
      selections.value[key] = current.filter(l => l !== optLabel)
    } else {
      selections.value[key] = [...current, optLabel]
    }
  } else {
    selections.value[key] = optLabel
  }
}

function isSelected(qIdx, optLabel, multiSelect) {
  const key = `q${qIdx}`
  const val = selections.value[key]
  if (multiSelect) {
    return (val || []).includes(optLabel)
  }
  return val === optLabel
}

function hasAnswered(qIdx) {
  const key = `q${qIdx}`
  const val = selections.value[key]
  if (Array.isArray(val)) return val.length > 0
  return !!val
}

const allAnswered = computed(() => {
  return questions.value.every((_, i) => hasAnswered(i))
})

function submitAnswers() {
  const answers = {}
  questions.value.forEach((q, i) => {
    const key = `q${i}`
    answers[q.question] = selections.value[key] || ''
  })
  emit('answer', { answers })
}
</script>

<template>
  <div class="user-choice-block" :class="{ 'choice-answered': answered }">
    <div class="choice-header">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      <span>User Input Required</span>
    </div>

    <div v-for="(q, qIdx) in questions" :key="qIdx" class="question-group">
      <div class="question-header" v-if="q.header">
        <span class="question-chip">{{ q.header }}</span>
      </div>
      <div class="question-text">{{ q.question }}</div>

      <div class="options-list">
        <button
          v-for="(opt, oIdx) in (q.options || [])"
          :key="oIdx"
          class="option-btn"
          :class="{
            'option-selected': isSelected(qIdx, opt.label, q.multiSelect),
            'option-multi': q.multiSelect,
          }"
          :disabled="answered"
          @click="toggleOption(qIdx, opt.label, q.multiSelect)"
        >
          <span class="option-indicator">
            <span v-if="q.multiSelect" class="checkbox">
              <svg v-if="isSelected(qIdx, opt.label, true)" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
              </svg>
            </span>
            <span v-else class="radio">
              <span v-if="isSelected(qIdx, opt.label, false)" class="radio-dot"/>
            </span>
          </span>
          <span class="option-content">
            <span class="option-label">{{ opt.label }}</span>
            <span v-if="opt.description" class="option-desc">{{ opt.description }}</span>
          </span>
        </button>
      </div>
    </div>

    <button
      v-if="!answered && questions.length > 0"
      class="submit-btn"
      :disabled="!allAnswered"
      @click="submitAnswers"
    >
      Submit
    </button>
    <div v-if="answered" class="answered-badge">Answered</div>
  </div>
</template>

<style scoped>
.user-choice-block {
  background: var(--bg-secondary);
  border: 1px solid var(--accent);
  border-radius: var(--radius-md);
  padding: 16px;
  margin: 8px 0;
}

.choice-answered {
  opacity: 0.7;
  border-color: var(--border);
}

.choice-header {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--accent);
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 12px;
}

.question-group {
  margin-bottom: 12px;
}

.question-header {
  margin-bottom: 4px;
}

.question-chip {
  display: inline-block;
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.question-text {
  color: var(--text-primary);
  font-size: 14px;
  margin-bottom: 8px;
  line-height: 1.5;
}

.options-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.option-btn {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  text-align: left;
  transition: all var(--transition-fast);
  color: var(--text-primary);
  font-family: inherit;
  font-size: 13px;
}

.option-btn:not(:disabled):hover {
  border-color: var(--accent);
  background: var(--bg-hover);
  transform: translateX(2px);
}

.option-btn.option-selected {
  border-color: var(--accent);
  background: var(--accent-dim);
}

.option-btn:disabled {
  cursor: default;
  opacity: 0.6;
}

.option-indicator {
  flex-shrink: 0;
  margin-top: 2px;
}

.radio {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 2px solid var(--text-muted);
  border-radius: 50%;
}

.option-selected .radio {
  border-color: var(--accent);
}

.radio-dot {
  width: 8px;
  height: 8px;
  background: var(--accent);
  border-radius: 50%;
}

.checkbox {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 2px solid var(--text-muted);
  border-radius: 3px;
}

.option-selected .checkbox {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--text-on-accent);
}

.option-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.option-label {
  font-weight: 500;
}

.option-desc {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.4;
}

.submit-btn {
  margin-top: 12px;
  padding: 8px 20px;
  background: var(--accent);
  color: var(--text-on-accent);
  border: none;
  border-radius: var(--radius-sm);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.submit-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.submit-btn:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.submit-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.97);
  transition-duration: 80ms;
}

.answered-badge {
  margin-top: 8px;
  color: var(--green);
  font-size: 12px;
  font-weight: 600;
}
</style>
