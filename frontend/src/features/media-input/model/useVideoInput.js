import { ref } from 'vue'

const isCapturing = ref(false)
const stream = ref(null)
const supported = ref(typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia)

export function useVideoInput() {
  async function startCapture() {
    if (!supported.value) return null
    try {
      stream.value = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } } })
      isCapturing.value = true
      return stream.value
    } catch {
      isCapturing.value = false
      return null
    }
  }

  function stopCapture() {
    if (stream.value) {
      stream.value.getTracks().forEach(t => t.stop())
      stream.value = null
    }
    isCapturing.value = false
  }

  function captureFrame(videoEl) {
    if (!videoEl) return null
    const canvas = document.createElement('canvas')
    canvas.width = videoEl.videoWidth
    canvas.height = videoEl.videoHeight
    const ctx = canvas.getContext('2d')
    ctx.drawImage(videoEl, 0, 0)
    const dataUrl = canvas.toDataURL('image/png')
    const base64 = dataUrl.split(',')[1]
    return { data: base64, media_type: 'image/png', preview: dataUrl }
  }

  return { isCapturing, stream, supported, startCapture, stopCapture, captureFrame }
}
