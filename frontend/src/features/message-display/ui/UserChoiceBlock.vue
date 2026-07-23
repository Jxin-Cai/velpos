<script setup>
import { ref, computed, nextTick, useId } from 'vue'

const props = defineProps({
  block: { type: Object, required: true },
  answered: { type: Boolean, default: false },
})

const emit = defineEmits(['answer'])

const selections = ref({})
const otherTexts = ref({})
const activeQuestionIndex = ref(0)
const questionTabs = ref([])
const componentId = useId()
const OTHER_LABEL = '__other__'

const questions = computed(() => props.block.input?.questions || [])
const activeQuestion = computed(() => questions.value[activeQuestionIndex.value])

function hasBuiltinOther(q) {
  return (q.options || []).some(opt => String(opt.label || '').toLowerCase() === 'other')
}

function isOtherOpt(opt) {
  return String(opt.label || '').toLowerCase() === 'other'
}

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

  if (!multiSelect && optLabel !== OTHER_LABEL) {
    nextTick(() => completeQuestion(qIdx))
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

function isOtherSelected(qIdx, multiSelect) {
  return isSelected(qIdx, OTHER_LABEL, multiSelect)
}

function hasAnswered(qIdx) {
  const key = `q${qIdx}`
  const val = selections.value[key]
  if (Array.isArray(val)) {
    if (val.length === 0) return false
    if (val.includes(OTHER_LABEL)) {
      return !!(otherTexts.value[key] || '').trim()
    }
    return true
  }
  if (val === OTHER_LABEL) {
    return !!(otherTexts.value[key] || '').trim()
  }
  return !!val
}

const allAnswered = computed(() => {
  return questions.value.every((_, i) => hasAnswered(i))
})

function tabLabel(question, index) {
  return question.header || `Question ${index + 1}`
}

function selectQuestion(index, moveFocus = false) {
  activeQuestionIndex.value = index
  if (moveFocus) {
    nextTick(() => questionTabs.value[index]?.focus())
  }
}

function nextUnansweredQuestion(afterIndex) {
  for (let index = afterIndex + 1; index < questions.value.length; index += 1) {
    if (!hasAnswered(index)) return index
  }
  for (let index = 0; index < afterIndex; index += 1) {
    if (!hasAnswered(index)) return index
  }
  return -1
}

function completeQuestion(questionIndex) {
  if (!hasAnswered(questionIndex) || props.answered) return

  const nextIndex = nextUnansweredQuestion(questionIndex)
  if (nextIndex >= 0) {
    activeQuestionIndex.value = nextIndex
    return
  }

  if (allAnswered.value) submitAnswers()
}

function submitAnswers() {
  if (!allAnswered.value || props.answered) return

  const answers = {}
  questions.value.forEach((q, i) => {
    const key = `q${i}`
    const val = selections.value[key]
    if (Array.isArray(val)) {
      const resolved = val.map(v => v === OTHER_LABEL ? (otherTexts.value[key] || '').trim() : v)
      answers[q.question] = resolved.join(', ')
    } else if (val === OTHER_LABEL) {
      answers[q.question] = (otherTexts.value[key] || '').trim()
    } else {
      answers[q.question] = val || ''
    }
  })
  emit('answer', { answers })
}
</script>

<template>
  <div class="user-choice-block" :class="{ 'choice-answered': answered }">
    <div class="choice-header">
      <div class="choice-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10"/>
          <path d="M9.1 9a3 3 0 1 1 5.83 1c0 2-2.93 2-2.93 4"/>
          <path d="M12 18h.01"/>
        </svg>
        <span>User Input Required</span>
      </div>
      <span v-if="answered" class="answered-badge">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
          <path d="m5 12 4 4L19 6"/>
        </svg>
        Submitted
      </span>
    </div>

    <div
      v-if="questions.length > 1"
      class="question-tabs"
      role="tablist"
      aria-label="Questions"
    >
      <button
        v-for="(q, qIdx) in questions"
        ref="questionTabs"
        :id="`${componentId}-question-tab-${qIdx}`"
        :key="qIdx"
        type="button"
        class="question-tab"
        :class="{
          'question-tab-active': activeQuestionIndex === qIdx,
          'question-tab-complete': hasAnswered(qIdx),
        }"
        role="tab"
        :aria-selected="activeQuestionIndex === qIdx"
        :aria-controls="`${componentId}-question-panel-${qIdx}`"
        :tabindex="activeQuestionIndex === qIdx ? 0 : -1"
        @click="selectQuestion(qIdx)"
        @keydown.left.prevent="selectQuestion((qIdx - 1 + questions.length) % questions.length, true)"
        @keydown.right.prevent="selectQuestion((qIdx + 1) % questions.length, true)"
        @keydown.home.prevent="selectQuestion(0, true)"
        @keydown.end.prevent="selectQuestion(questions.length - 1, true)"
      >
        <span class="tab-index">
          <svg v-if="hasAnswered(qIdx)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
            <path d="m5 12 4 4L19 6"/>
          </svg>
          <span v-else>{{ qIdx + 1 }}</span>
        </span>
        <span class="tab-label">{{ tabLabel(q, qIdx) }}</span>
      </button>
    </div>

    <div
      v-if="activeQuestion"
      :id="`${componentId}-question-panel-${activeQuestionIndex}`"
      class="question-panel"
      role="tabpanel"
      :aria-labelledby="questions.length > 1 ? `${componentId}-question-tab-${activeQuestionIndex}` : undefined"
    >
      <div v-if="activeQuestion.header && questions.length === 1" class="question-kicker">
        {{ activeQuestion.header }}
      </div>
      <div class="question-text">{{ activeQuestion.question }}</div>

      <div class="options-list">
        <template v-for="(opt, oIdx) in (activeQuestion.options || [])" :key="oIdx">
          <button
            v-if="!isOtherOpt(opt)"
            type="button"
            class="option-btn"
            :class="{
              'option-selected': isSelected(activeQuestionIndex, opt.label, activeQuestion.multiSelect),
              'option-multi': activeQuestion.multiSelect,
            }"
            :disabled="answered"
            @click="toggleOption(activeQuestionIndex, opt.label, activeQuestion.multiSelect)"
          >
            <span class="option-indicator">
              <span v-if="activeQuestion.multiSelect" class="checkbox">
                <svg v-if="isSelected(activeQuestionIndex, opt.label, true)" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                </svg>
              </span>
              <span v-else class="radio">
                <span v-if="isSelected(activeQuestionIndex, opt.label, false)" class="radio-dot"/>
              </span>
            </span>
            <span class="option-content">
              <span class="option-label">{{ opt.label }}</span>
              <span v-if="opt.description" class="option-desc">{{ opt.description }}</span>
            </span>
          </button>

          <button
            v-else
            type="button"
            class="option-btn option-other"
            :class="{ 'option-selected': isOtherSelected(activeQuestionIndex, activeQuestion.multiSelect) }"
            :disabled="answered"
            @click="toggleOption(activeQuestionIndex, OTHER_LABEL, activeQuestion.multiSelect)"
          >
            <span class="option-indicator">
              <span v-if="activeQuestion.multiSelect" class="checkbox">
                <svg v-if="isOtherSelected(activeQuestionIndex, true)" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                </svg>
              </span>
              <span v-else class="radio">
                <span v-if="isOtherSelected(activeQuestionIndex, false)" class="radio-dot"/>
              </span>
            </span>
            <span class="option-content">
              <span class="option-label">Other</span>
              <span class="option-desc">{{ opt.description || 'Provide your own answer' }}</span>
            </span>
          </button>
        </template>

        <button
          v-if="!hasBuiltinOther(activeQuestion)"
          type="button"
          class="option-btn option-other"
          :class="{ 'option-selected': isOtherSelected(activeQuestionIndex, activeQuestion.multiSelect) }"
          :disabled="answered"
          @click="toggleOption(activeQuestionIndex, OTHER_LABEL, activeQuestion.multiSelect)"
        >
          <span class="option-indicator">
            <span v-if="activeQuestion.multiSelect" class="checkbox">
              <svg v-if="isOtherSelected(activeQuestionIndex, true)" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
              </svg>
            </span>
            <span v-else class="radio">
              <span v-if="isOtherSelected(activeQuestionIndex, false)" class="radio-dot"/>
            </span>
          </span>
          <span class="option-content">
            <span class="option-label">Other</span>
            <span class="option-desc">Provide your own answer</span>
          </span>
        </button>
      </div>

      <div v-if="isOtherSelected(activeQuestionIndex, activeQuestion.multiSelect) && !answered" class="other-input-wrap">
        <textarea
          class="other-input"
          :value="otherTexts[`q${activeQuestionIndex}`] || ''"
          @input="otherTexts[`q${activeQuestionIndex}`] = $event.target.value"
          placeholder="Type your answer here..."
          rows="2"
        />
      </div>
    </div>

    <div v-if="!answered && activeQuestion" class="choice-footer">
      <span class="progress-label">
        {{ activeQuestionIndex + 1 }} of {{ questions.length }}
        <span v-if="!activeQuestion.multiSelect && !isOtherSelected(activeQuestionIndex, false)">· Select to continue</span>
        <span v-else>· Confirm when ready</span>
      </span>
      <button
        v-if="activeQuestion.multiSelect || isOtherSelected(activeQuestionIndex, activeQuestion.multiSelect)"
        type="button"
        class="continue-btn"
        :disabled="!hasAnswered(activeQuestionIndex)"
        @click="completeQuestion(activeQuestionIndex)"
      >
        {{ allAnswered ? 'Submit' : 'Next' }}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="m9 18 6-6-6-6"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.user-choice-block {
  overflow: hidden;
  background: color-mix(in srgb, var(--bg-secondary) 94%, var(--bg-primary));
  border: 1px solid var(--border);
  border-radius: 14px;
  margin: 8px 0;
  box-shadow: 0 8px 28px color-mix(in srgb, #000 9%, transparent);
}

.choice-answered {
  box-shadow: none;
}

.choice-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 44px;
  padding: 0 16px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
}

.choice-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  font-weight: 600;
  font-size: 13px;
}

.choice-title svg {
  color: var(--text-muted);
}

.question-tabs {
  display: flex;
  gap: 2px;
  padding: 8px 10px 0;
  overflow-x: auto;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
  scrollbar-width: thin;
}

.question-tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 7px;
  min-height: 38px;
  max-width: 180px;
  padding: 0 10px 8px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: color 180ms ease;
}

.question-tab::after {
  position: absolute;
  right: 8px;
  bottom: -1px;
  left: 8px;
  height: 2px;
  border-radius: 2px 2px 0 0;
  background: transparent;
  content: '';
}

.question-tab:hover,
.question-tab-active {
  color: var(--text-primary);
}

.question-tab-active::after {
  background: var(--accent);
}

.question-tab:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
  border-radius: 7px;
}

.tab-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  border: 1px solid var(--border);
  border-radius: 50%;
  font-size: 10px;
  line-height: 1;
}

.question-tab-complete .tab-index {
  border-color: color-mix(in srgb, var(--green) 45%, var(--border));
  background: var(--green-dim);
  color: var(--green);
}

.tab-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.question-panel {
  padding: 16px;
}

.question-kicker {
  margin-bottom: 5px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.question-text {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 12px;
  line-height: 1.55;
}

.options-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.option-btn {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-height: 44px;
  padding: 10px 12px;
  background: color-mix(in srgb, var(--bg-primary) 76%, transparent);
  border: 1px solid var(--border);
  border-radius: 9px;
  cursor: pointer;
  text-align: left;
  transition: background 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 13px;
}

.option-btn:not(:disabled):hover {
  border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
  background: var(--bg-hover);
}

.option-btn.option-selected {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 9%, var(--bg-primary));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 16%, transparent);
}

.option-btn:focus-visible,
.continue-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.option-btn:disabled {
  cursor: default;
  opacity: 0.72;
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
  min-width: 0;
}

.option-label {
  font-weight: 500;
}

.option-desc {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.4;
}

.choice-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 45px;
  padding: 7px 12px 7px 16px;
  border-top: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
}

.progress-label {
  color: var(--text-muted);
  font-size: 11px;
}

.continue-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 32px;
  padding: 0 12px;
  background: var(--accent);
  color: var(--text-on-accent);
  border: none;
  border-radius: 8px;
  font-weight: 600;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: opacity 180ms ease, transform 180ms ease, box-shadow 180ms ease;
}

.continue-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.continue-btn:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.continue-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.97);
  transition-duration: 100ms;
}

.answered-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--green);
  font-size: 11px;
  font-weight: 600;
}

.other-input-wrap {
  margin-top: 8px;
}

.other-input {
  box-sizing: border-box;
  width: 100%;
  padding: 9px 11px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 9px;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  min-height: 40px;
}

.other-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-dim);
}

.other-input::placeholder {
  color: var(--text-muted);
}

@media (max-width: 520px) {
  .question-panel {
    padding: 14px 12px;
  }

  .choice-header {
    padding: 0 12px;
  }

  .progress-label span {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .question-tab,
  .option-btn,
  .continue-btn {
    transition: none;
  }
}
</style>
