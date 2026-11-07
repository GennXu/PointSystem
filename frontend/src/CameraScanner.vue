<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import type { IScannerControls } from '@zxing/browser'
import { parseToken } from './logic'
const emit = defineEmits<{ decoded: [token: string] }>()
const video = ref<HTMLVideoElement | null>(null), active = ref(false), message = ref(''), starting = ref(false)
let controls: IScannerControls | undefined
let generation = 0
function stop() {
  generation++
  controls?.stop(); controls = undefined
  const stream = video.value?.srcObject as MediaStream | null
  stream?.getTracks().forEach(track => track.stop())
  if (video.value) video.value.srcObject = null
  active.value = false; starting.value = false
}
function accept(text: string) {
  try { const token = parseToken(text); stop(); message.value = '已辨識會員憑證'; emit('decoded', token) }
  catch { message.value = '此圖碼不是本系統的會員憑證，請掃描正確圖碼' }
}
async function start() {
  if (starting.value || active.value) return
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    message.value = '即時相機需要 HTTPS 或主機本機網址 localhost。區域網路 HTTP 請改用圖片辨識或 USB 掃描器。'; return
  }
  const attempt = ++generation
  starting.value = true; active.value = true; message.value = '請允許相機權限，將會員圖碼置於鏡頭前'
  try {
    const { BrowserQRCodeReader } = await import('@zxing/browser')
    if (attempt !== generation) return
    const reader = new BrowserQRCodeReader()
    const started = await reader.decodeFromConstraints({ video: { facingMode: { ideal: 'environment' } }, audio: false }, video.value!, (result, _error, scanner) => {
      if (attempt !== generation) { scanner.stop(); return }
      if (result) accept(result.getText())
    })
    if (attempt !== generation) started.stop()
    else controls = started
  } catch (error) {
    if (attempt === generation) { stop(); message.value = error instanceof DOMException && error.name === 'NotAllowedError' ? '相機權限被拒絕，請允許此網站使用相機' : '無法啟動相機，請確認設備可用且未被其他程式占用' }
  } finally { if (attempt === generation) starting.value = false }
}
async function image(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  stop()
  if (file.size > 10 * 1024 * 1024) { message.value = '圖片大小須小於 10 MB'; input.value = ''; return }
  const url = URL.createObjectURL(file)
  try { const { BrowserQRCodeReader } = await import('@zxing/browser'); accept((await new BrowserQRCodeReader().decodeFromImageUrl(url)).getText()) }
  catch { message.value = '無法辨識圖片中的會員圖碼，請使用清晰完整的 QR 圖片' }
  finally { URL.revokeObjectURL(url); input.value = '' }
}
onUnmounted(stop)
</script>
<template><div class="camera-tools"><button type="button" @click="start" :disabled="starting || active">開啟相機掃碼</button><button v-if="active" type="button" @click="stop">關閉相機</button><label class="image-picker">辨識圖片<input type="file" accept="image/*" @change="image" aria-label="辨識 QR 圖片"></label><video ref="video" v-show="active" autoplay muted playsinline aria-label="相機掃碼預覽"></video><p v-if="message" role="note">{{ message }}</p></div></template>
