import { ref } from 'vue'

const isRecording = ref(false)
const transcript = ref('')
const supported = ref(typeof window !== 'undefined' && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window))

let recognition = null

export function useVoiceInput() {
  function startRecording(onResult) {
    if (!supported.value) return

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    recognition = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'zh-CN'

    transcript.value = ''
    isRecording.value = true

    recognition.onresult = (event) => {
      let interim = ''
      let final = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript
        if (event.results[i].isFinal) {
          final += t
        } else {
          interim += t
        }
      }
      if (final) {
        transcript.value += final
        if (onResult) onResult(final)
      }
    }

    recognition.onerror = () => {
      isRecording.value = false
    }

    recognition.onend = () => {
      isRecording.value = false
    }

    recognition.start()
  }

  function stopRecording() {
    if (recognition) {
      recognition.stop()
      recognition = null
    }
    isRecording.value = false
  }

  function toggle(onResult) {
    if (isRecording.value) {
      stopRecording()
    } else {
      startRecording(onResult)
    }
  }

  return { isRecording, transcript, supported, startRecording, stopRecording, toggle }
}
