<!-- ====================================================================
  PhoneCall —— 和芙芙打电话（可拖动浮窗 / 可收起成小窗）
  --------------------------------------------------------------------
  · 只负责"把聊天里芙芙说的话读出来"，自己不再发消息
  · 打开后从 ChatView 收到 speak(text) 就排队合成 Qwen-TTS 并播放
  · 标题栏可拖动；点「—」收起成右下角的小电话球，点小窗再展开
  · 音量由父组件的 voiceVolume 控制（和背景音乐分开）
==================================================================== -->

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  voiceVolume: number
}>()

const emit = defineEmits<{
  close: []
}>()

const minimized = ref(false)
const seconds = ref(0)
const ringing = ref(true)
const speaking = ref(false)
const error = ref('')
const ttsReady = ref(true)
const ttsHint = ref('')
const lastSpoken = ref('')

let timer: ReturnType<typeof setInterval> | null = null
let audio: HTMLAudioElement | null = null
let audioUrl = ''

const secondsText = computed(() => {
  const m = String(Math.floor(seconds.value / 60)).padStart(2, '0')
  const s = String(seconds.value % 60).padStart(2, '0')
  return `${m}:${s}`
})

const statusText = computed(() => {
  if (ringing.value) return '正在呼叫…'
  if (speaking.value) return '芙芙正在说…'
  return `通话中 ${secondsText.value}`
})

// ---------------- 拖动 ----------------
const pos = ref({ x: 24, y: 24 })
const dragging = ref(false)
let startX = 0
let startY = 0
let originX = 0
let originY = 0

function clampPosition(x: number, y: number) {
  const width = 330
  const height = 420
  const maxX = Math.max(8, window.innerWidth - width - 8)
  const maxY = Math.max(8, window.innerHeight - height - 8)
  return {
    x: Math.min(Math.max(8, x), maxX),
    y: Math.min(Math.max(8, y), maxY),
  }
}

function placeBottomRight() {
  pos.value = clampPosition(window.innerWidth - 360, window.innerHeight - 520)
}

function onHeadDown(event: PointerEvent) {
  if ((event.target as HTMLElement).closest('button')) return
  dragging.value = true
  startX = event.clientX
  startY = event.clientY
  originX = pos.value.x
  originY = pos.value.y
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

function onMove(event: PointerEvent) {
  if (!dragging.value) return
  pos.value = clampPosition(
    originX + event.clientX - startX,
    originY + event.clientY - startY
  )
}

function onUp() {
  dragging.value = false
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
}

// ---------------- 小窗（电话球）也能拖 ----------------
const bubblePos = ref({ x: 0, y: 0 })
let bubbleStartX = 0
let bubbleStartY = 0
let bubbleOriginX = 0
let bubbleOriginY = 0
let bubbleMoved = false

function clampBubble(x: number, y: number) {
  const size = 66
  return {
    x: Math.min(Math.max(8, x), Math.max(8, window.innerWidth - size - 8)),
    y: Math.min(Math.max(8, y), Math.max(8, window.innerHeight - size - 8)),
  }
}

/** 小窗默认贴右边缘（留 16px 边距） */
function placeBubbleRightEdge(y?: number) {
  bubblePos.value = clampBubble(
    window.innerWidth - 66 - 16,
    y ?? window.innerHeight - 230
  )
}

function placeBubbleBottomRight() {
  placeBubbleRightEdge()
}

function onBubbleDown(event: PointerEvent) {
  event.preventDefault()
  bubbleMoved = false
  bubbleStartX = event.clientX
  bubbleStartY = event.clientY
  bubbleOriginX = bubblePos.value.x
  bubbleOriginY = bubblePos.value.y
  window.addEventListener('pointermove', onBubbleMove)
  window.addEventListener('pointerup', onBubbleUp)
}

function onBubbleMove(event: PointerEvent) {
  const dx = event.clientX - bubbleStartX
  const dy = event.clientY - bubbleStartY
  if (!bubbleMoved && Math.abs(dx) + Math.abs(dy) > 6) bubbleMoved = true
  if (!bubbleMoved) return
  bubblePos.value = clampBubble(bubbleOriginX + dx, bubbleOriginY + dy)
}

function onBubbleUp() {
  window.removeEventListener('pointermove', onBubbleMove)
  window.removeEventListener('pointerup', onBubbleUp)
  // 没拖动 = 点了一下 → 展开
  if (!bubbleMoved) minimized.value = false
}

// ---------------- 播放队列（边播边预取下一段） ----------------
interface Job {
  text: string
  blob?: Promise<Blob>
}

let playing = false
let fetching = 0
const queue: Job[] = []
const PREFETCH = 2   // 同时最多预合成 2 段

/**
 * 按句子切成小段（每段 ≤ 60 字）。
 * 合成耗时和字数几乎成正比，段越大第一声越晚；
 * 切小之后加上后面的"预取"，开口延迟能压到 1 秒左右。
 */
function splitText(text: string): string[] {
  const parts = text.replace(/\s+/g, ' ').match(/[^。！？!?…\n]+[。！？!?…\n]?/g) ?? [text]
  const out: string[] = []
  let buffer = ''

  const pushLong = (piece: string) => {
    // 超长句再按逗号/分号切，避免一段太长
    for (const seg of piece.split(/[，,；;]/)) {
      const s = seg.trim()
      if (!s) continue
      if (s.length > 60) {
        for (let i = 0; i < s.length; i += 60) out.push(s.slice(i, i + 60))
      } else {
        out.push(s)
      }
    }
  }

  for (const part of parts) {
    const piece = part.trim()
    if (!piece) continue
    if (piece.length > 60) {
      if (buffer.trim()) out.push(buffer.trim())
      buffer = ''
      pushLong(piece)
      continue
    }
    if ((buffer + piece).length > 60) {
      if (buffer.trim()) out.push(buffer.trim())
      buffer = piece
    } else {
      buffer += piece
    }
  }
  if (buffer.trim()) out.push(buffer.trim())
  return out
}

function ensureAudio(): HTMLAudioElement {
  if (!audio) audio = new Audio()
  audio.volume = Math.min(1, Math.max(0, props.voiceVolume / 100))
  return audio
}

watch(
  () => props.voiceVolume,
  (value) => {
    if (audio) audio.volume = Math.min(1, Math.max(0, value / 100))
  }
)

async function fetchAudio(text: string): Promise<Blob> {
  const res = await fetch('/api/tts/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!res.ok) {
    // 后端出错时可能是 JSON（{detail}），也可能是纯文本（Internal Server Error）
    const raw = await res.text().catch(() => '')
    let detail = raw
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed.detail === 'string') detail = parsed.detail
    } catch {
      // 不是 JSON，就原样当文本
    }
    throw new Error(
      detail
        ? `语音合成失败（HTTP ${res.status}）：${detail}`
        : `语音合成失败（HTTP ${res.status}）`
    )
  }
  return res.blob()
}

/** 把队列里还没请求的段先发出去合成，最多同时 2 个 */
function prefetch() {
  for (let i = 0; i < queue.length && fetching < PREFETCH; i += 1) {
    const job = queue[i]
    if (!job || job.blob) continue
    fetching += 1
    job.blob = fetchAudio(job.text).finally(() => {
      fetching -= 1
    })
  }
}

async function playBlob(blob: Blob): Promise<void> {
  if (audioUrl) URL.revokeObjectURL(audioUrl)
  audioUrl = URL.createObjectURL(blob)
  const el = ensureAudio()
  el.src = audioUrl
  await new Promise<void>((resolve) => {
    const done = () => {
      el.onended = null
      el.onerror = null
      resolve()
    }
    el.onended = done
    el.onerror = done
    el.play().catch(done)
  })
}

async function pump() {
  if (playing) return
  playing = true
  speaking.value = queue.length > 0

  while (queue.length) {
    prefetch()
    const job = queue.shift() as Job
    lastSpoken.value = job.text
    try {
      const blob = await (job.blob ?? fetchAudio(job.text))
      await playBlob(blob)
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      queue.length = 0
      break
    }
    prefetch()   // 当前这段在播时，下一段已经在合成了
  }

  speaking.value = false
  playing = false
}

/** 父组件（ChatView）在聊天输出结束后调用 */
function speak(text: string) {
  const clean = (text || '').trim()
  if (!clean) return
  error.value = ''
  for (const chunk of splitText(clean)) queue.push({ text: chunk })
  void pump()
}

/**
 * 整段一次性合成并播放（"一口气说完"）。
 * 返回音频时长（毫秒），页面按这个节奏同步跳字。
 */
async function speakAll(text: string): Promise<number> {
  stopAudio()
  const clean = (text || '').trim()
  if (!clean) return 0

  error.value = ''
  speaking.value = true
  try {
    const blob = await fetchAudio(clean)
    const el = ensureAudio()
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    audioUrl = URL.createObjectURL(blob)
    el.src = audioUrl

    const duration = await new Promise<number>((resolve) => {
      let done = false
      const finish = (ms: number) => {
        if (done) return
        done = true
        resolve(ms)
      }
      el.onloadedmetadata = () =>
        finish(Number.isFinite(el.duration) ? el.duration * 1000 : 0)
      el.onerror = () => finish(0)
      window.setTimeout(
        () => finish(Number.isFinite(el.duration) ? el.duration * 1000 : 0),
        4000
      )
    })

    el.onended = () => {
      speaking.value = false
    }
    await el.play().catch(() => {
      speaking.value = false
    })

    lastSpoken.value = clean
    return duration || clean.length * 200
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    speaking.value = false
    return 0
  }
}
function stopAudio() {
  queue.length = 0
  fetching = 0
  speaking.value = false
  playing = false
  if (audio) {
    audio.pause()
    audio.src = ''
  }
  if (audioUrl) {
    URL.revokeObjectURL(audioUrl)
    audioUrl = ''
  }
}

function toggleMinimize() {
  if (!minimized.value) {
    // 收起：默认贴到最右边（高度沿用浮窗当前位置，避免跳来跳去）
    placeBubbleRightEdge(pos.value.y)
  }
  minimized.value = !minimized.value
}

function hangUp() {
  stopAudio()
  emit('close')
}

// getAudio：把正在播的那个 <audio> 交给口型同步用（见 composables/useLipSync.ts）
defineExpose({ speak, speakAll, stopAudio, toggleMinimize, getAudio: () => audio })

onMounted(async () => {
  placeBottomRight()
  placeBubbleBottomRight()
  window.addEventListener('resize', placeBottomRight)
  // 模拟"拨号中"：1.2 秒后接通并开始计时
  window.setTimeout(() => {
    ringing.value = false
    timer = setInterval(() => { seconds.value += 1 }, 1000)
  }, 1200)
  try {
    const res = await fetch('/api/tts/settings')
    if (res.ok) {
      const data = await res.json()
      ttsReady.value = Boolean(data.has_key)
      if (!data.has_key) ttsHint.value = '还没配语音 Key：去「设置 → 语音（电话）」填一下，芙芙才会出声'
    }
  } catch {
    ttsHint.value = '读取语音配置失败，可能没有声音'
  }
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  window.removeEventListener('resize', placeBottomRight)
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
  stopAudio()
})
</script>

<template>
  <!-- 收起状态：右下角的小电话球 -->
  <button
    v-if="minimized"
    class="call-bubble"
    :class="{ 'call-bubble--talking': speaking }"
    type="button"
    title="拖动移动；点一下展开通话窗口"
    :style="{ left: `${bubblePos.x}px`, top: `${bubblePos.y}px` }"
    @pointerdown="onBubbleDown"
  >
    <svg class="phone-icon call-head__icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6.62 10.79a15.05 15.05 0 0 0 6.59 6.59l2.2-2.2a1 1 0 0 1 1.02-.24c1.12.37 2.33.57 3.57.57a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1C10.61 21 3 13.39 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.24.2 2.45.57 3.57a1 1 0 0 1-.25 1.02l-2.2 2.2z"/></svg>
    <span class="call-bubble__time">{{ secondsText }}</span>
  </button>

  <!-- 展开状态：可拖动浮窗 -->
  <div
    v-else
    class="call-panel"
    :class="{ 'call-panel--dragging': dragging }"
    :style="{ left: `${pos.x}px`, top: `${pos.y}px` }"
  >
    <header class="call-head" @pointerdown="onHeadDown">
      <svg class="phone-icon call-bubble__icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6.62 10.79a15.05 15.05 0 0 0 6.59 6.59l2.2-2.2a1 1 0 0 1 1.02-.24c1.12.37 2.33.57 3.57.57a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1C10.61 21 3 13.39 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.24.2 2.45.57 3.57a1 1 0 0 1-.25 1.02l-2.2 2.2z"/></svg>
      <span class="call-head__title">和芙芙打电话</span>
      <button class="call-head__btn" type="button" title="收起成小窗" @click="toggleMinimize">
        –
      </button>
      <button class="call-head__btn" type="button" title="挂断" @click="hangUp">×</button>
    </header>

    <div class="call-body">
      <div class="call-avatar" :class="{ 'call-avatar--talking': speaking }">
        <span>芙</span>
      </div>
      <p class="call-name">芙宁娜</p>
      <p class="call-status">{{ statusText }}</p>

      <div class="call-wave" :class="{ 'call-wave--on': speaking }" aria-hidden="true">
        <i v-for="n in 7" :key="n"></i>
      </div>

      <p class="call-subtitle">
        {{ speaking ? lastSpoken : '聊天里芙芙说的话会在这里读出来' }}
      </p>

      <p v-if="error" class="call-error">{{ error }}</p>
      <p v-if="ttsHint" class="call-hint">{{ ttsHint }}</p>

      <div class="call-actions">
        <button
          v-if="speaking"
          class="call-btn"
          type="button"
          @click="stopAudio"
        >
          停止朗读
        </button>
        <button class="call-btn call-btn--hangup" type="button" @click="hangUp">
          <svg class="phone-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6.62 10.79a15.05 15.05 0 0 0 6.59 6.59l2.2-2.2a1 1 0 0 1 1.02-.24c1.12.37 2.33.57 3.57.57a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1C10.61 21 3 13.39 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.24.2 2.45.57 3.57a1 1 0 0 1-.25 1.02l-2.2 2.2z"/></svg> 挂断
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ---- 小窗（收起后） ---- */
.call-bubble {
  position: fixed;
  z-index: 95;
  touch-action: none;
  cursor: grab;
  width: 66px;
  height: 66px;
  border: none;
  border-radius: 50%;
  background: radial-gradient(circle at 32% 28%, #7fc3e8, #2f6b8a 62%, #1d3f57);
  color: #fff;
  cursor: pointer;
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.4);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  animation: bubble-in 0.2s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes bubble-in {
  from { opacity: 0; transform: scale(0.6); }
  to   { opacity: 1; transform: scale(1); }
}
.call-bubble__icon {
  color: #46c98c;
  font-size: 1.9rem;
  line-height: 1;
  display: grid;
  place-items: center;
}
.call-bubble__time {
  font-size: 0.54rem;
  color: rgba(255, 253, 248, 0.85);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.call-bubble--talking {
  animation: bubble-pulse 1.3s ease-in-out infinite;
}
@keyframes bubble-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(159, 232, 196, 0.45), 0 12px 28px rgba(0, 0, 0, 0.4); }
  50%      { box-shadow: 0 0 0 12px rgba(159, 232, 196, 0), 0 12px 28px rgba(0, 0, 0, 0.4); }
}

/* ---- 展开的浮窗 ---- */
.call-panel {
  position: fixed;
  z-index: 95;
  width: 330px;
  padding: 12px 14px 14px;
  box-sizing: border-box;
  border: 1.5px solid rgba(255, 253, 248, 0.35);
  border-radius: 18px;
  background: rgba(10, 40, 40, 0.96);
  backdrop-filter: blur(16px);
  box-shadow: 0 22px 52px rgba(0, 0, 0, 0.5);
  color: #fffdf8;
  animation: call-in 0.22s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
.call-panel--dragging { transition: none; user-select: none; }
@keyframes call-in {
  from { opacity: 0; transform: translateY(8px) scale(0.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.call-head {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 10px;
  cursor: grab;
  touch-action: none;
  font-size: 0.76rem;
  color: rgba(255, 253, 248, 0.75);
}
.call-panel--dragging .call-head { cursor: grabbing; }
.call-head__icon {
  width: 14px;
  height: 14px;
  color: #46c98c;
  flex: 0 0 auto;
}
.phone-icon {
  width: 1em;
  height: 1em;
  fill: currentColor;
  display: inline-block;
  vertical-align: -0.12em;
}
.call-head__title { font-weight: 500; }
.call-head__btn {
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 253, 248, 0.8);
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}
.call-head__btn:first-of-type { margin-left: auto; }
.call-head__btn:hover { background: rgba(255, 253, 248, 0.14); }

.call-body { text-align: center; }

.call-avatar {
  width: 64px;
  height: 64px;
  margin: 4px auto 8px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 1.4rem;
  color: #fffdf8;
  background: radial-gradient(circle at 32% 28%, #7fc3e8, #2f6b8a 62%, #1d3f57);
  box-shadow: 0 0 0 3px rgba(255, 253, 248, 0.18);
}
.call-avatar--talking { animation: avatar-pulse 1.4s ease-in-out infinite; }
@keyframes avatar-pulse {
  0%, 100% { box-shadow: 0 0 0 3px rgba(159, 232, 196, 0.28); }
  50%      { box-shadow: 0 0 0 8px rgba(159, 232, 196, 0.08); }
}

.call-name { margin: 0; font-size: 0.95rem; }
.call-status {
  margin: 3px 0 8px;
  font-size: 0.72rem;
  color: rgba(255, 253, 248, 0.55);
  font-variant-numeric: tabular-nums;
}

.call-wave {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 3px;
  height: 20px;
  margin-bottom: 8px;
}
.call-wave i {
  width: 3px;
  height: 5px;
  border-radius: 2px;
  background: rgba(159, 232, 196, 0.35);
}
.call-wave--on i { animation: wave 0.9s ease-in-out infinite; }
.call-wave--on i:nth-child(2) { animation-delay: 0.1s; }
.call-wave--on i:nth-child(3) { animation-delay: 0.2s; }
.call-wave--on i:nth-child(4) { animation-delay: 0.3s; }
.call-wave--on i:nth-child(5) { animation-delay: 0.2s; }
.call-wave--on i:nth-child(6) { animation-delay: 0.1s; }
.call-wave--on i:nth-child(7) { animation-delay: 0s; }
@keyframes wave {
  0%, 100% { height: 5px; background: rgba(159, 232, 196, 0.35); }
  50%      { height: 18px; background: rgba(159, 232, 196, 0.9); }
}

.call-subtitle {
  margin: 0 0 10px;
  min-height: 34px;
  max-height: 68px;
  overflow-y: auto;
  padding: 7px 9px;
  border-radius: 9px;
  background: rgba(0, 0, 0, 0.2);
  font-size: 0.7rem;
  line-height: 1.55;
  color: rgba(255, 253, 248, 0.7);
  text-align: left;
}

.call-error {
  margin: 0 0 8px;
  font-size: 0.7rem;
  color: #ffb4a8;
}
.call-hint {
  margin: 0 0 8px;
  font-size: 0.68rem;
  line-height: 1.5;
  color: #ffdca8;
}

.call-actions { display: flex; gap: 8px; }
.call-btn {
  flex: 1;
  height: 34px;
  border-radius: 11px;
  border: 1px solid rgba(255, 253, 248, 0.3);
  background: rgba(255, 253, 248, 0.06);
  color: #fffdf8;
  font-size: 0.76rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s ease;
}
.call-btn:hover { background: rgba(255, 253, 248, 0.14); }
.call-btn--hangup {
  border-color: transparent;
  background: #e05b4a;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
}
.call-btn--hangup .phone-icon {
  width: 0.95em;
  height: 0.95em;
  color: #fff;
}
.call-btn--hangup:hover { background: #c94b3b; }

@media (prefers-reduced-motion: reduce) {
  .call-panel, .call-bubble, .call-bubble--talking, .call-avatar--talking, .call-wave--on i {
    animation: none;
  }
}
</style>