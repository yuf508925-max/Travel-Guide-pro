<!--
  VideoFloat.vue —— 网页内浮窗播放器
  ------------------------------------------------------------------
  先用后端给的 mp4 直链塞进 <video> 自己播：
    · 官方 iframe 播放器会在画面里糊一个「进入哔哩哔哩，观看更高清」
      的引导按钮，那玩意儿在跨域 iframe 里，外面删不掉；
    · 自己拿直链播就没这个问题，画面干净、还能用自己的控制条。
  拿不到直链时（限流 / 视频被限制）才退回官方 iframe，保证还能看。

  交互跟电话浮窗一致：
    · 按住标题栏拖动（拖到边上会被 clamp 回来，不会拖出屏幕）
    · × 关掉，视频随之停止
    · 「在B站看」跳原页面，方便看完整弹幕/评论
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { VlogVideo } from '../types/vlog'

const props = defineProps<{ video: VlogVideo }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const HEAD_H = 46

// 窗口宽度可拖拽调整（保持 16:9，高度跟着算）
const MIN_W = 320
const DEFAULT_W = 480
const WIDTH_KEY = 'fufu-video-float-w'

function maxWidth() {
  return Math.max(MIN_W, Math.min(920, window.innerWidth - 32))
}

function readSavedWidth(): number {
  const saved = Number(localStorage.getItem(WIDTH_KEY))
  if (!Number.isFinite(saved) || saved < MIN_W) return DEFAULT_W
  return Math.min(saved, maxWidth())
}

const panelW = ref(readSavedWidth())
const playerH = computed(() => Math.round((panelW.value - 2) * 9 / 16))   // 16:9

// 直链播放（首选）
const streamUrl = ref('')
const streamError = ref('')
const loadingStream = ref(true)

// 官方 iframe（兜底）
const iframeSrc = computed(
  () =>
    'https://player.bilibili.com/player.html' +
    `?bvid=${encodeURIComponent(props.video.bvid)}` +
    '&page=1&autoplay=1&danmaku=1&high_quality=1'
)

/** 向后端要 mp4 直链；拿不到就把 error 标上，模板会自动退回 iframe */
async function loadStream() {
  loadingStream.value = true
  streamError.value = ''
  try {
    const response = await fetch(`/api/vlog/play?bvid=${encodeURIComponent(props.video.bvid)}`)
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}))
      throw new Error((detail as { detail?: string }).detail || `接口返回 ${response.status}`)
    }
    const data = (await response.json()) as { url?: string }
    if (!data.url) throw new Error('B站没给播放地址')
    streamUrl.value = data.url
  } catch (exc) {
    streamError.value = exc instanceof Error ? exc.message : '拿不到播放地址'
  } finally {
    loadingStream.value = false
  }
}

// ---------------- 拖动 ----------------
const pos = ref({ x: 0, y: 0 })
const dragging = ref(false)
let startX = 0
let startY = 0
let originX = 0
let originY = 0

function clampPosition(x: number, y: number) {
  const height = HEAD_H + playerH.value
  const maxX = Math.max(8, window.innerWidth - panelW.value - 8)
  const maxY = Math.max(8, window.innerHeight - height - 8)
  return {
    x: Math.min(Math.max(8, x), maxX),
    y: Math.min(Math.max(8, y), maxY),
  }
}

function onHeadDown(event: PointerEvent) {
  if ((event.target as HTMLElement).closest('button, a')) return
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

// ---------------- 拉大 / 缩小 ----------------
// 右下角有个把手，横着拖就能改宽度（高度按 16:9 自动跟），松手记到 localStorage，
// 下次打开还是你习惯的大小。
const resizing = ref(false)
let resizeStartX = 0
let resizeStartW = 0

function onResizeDown(event: PointerEvent) {
  event.preventDefault()
  resizing.value = true
  resizeStartX = event.clientX
  resizeStartW = panelW.value
  window.addEventListener('pointermove', onResizeMove)
  window.addEventListener('pointerup', onResizeUp)
}

function onResizeMove(event: PointerEvent) {
  if (!resizing.value) return
  const next = Math.min(
    Math.max(MIN_W, resizeStartW + (event.clientX - resizeStartX)),
    maxWidth()
  )
  panelW.value = next
  // 变宽之后可能顶到屏幕右边，顺手夹一下位置
  pos.value = clampPosition(pos.value.x, pos.value.y)
}

function onResizeUp() {
  resizing.value = false
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeUp)
  try {
    localStorage.setItem(WIDTH_KEY, String(panelW.value))
  } catch {
    // 存不上也无所谓，这次能用就行
  }
}

// 第一次渲染前把窗口放到右下角（避开右侧聊天面板和电话浮窗的位置）
const ready = ref(false)

onMounted(() => {
  pos.value = clampPosition(
    window.innerWidth - panelW.value - 40,
    window.innerHeight - HEAD_H - playerH.value - 40
  )
  ready.value = true
  void loadStream()
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeUp)
})

function onResize() {
  // 屏幕变小了：窗口宽度也别超过屏幕
  panelW.value = Math.min(panelW.value, maxWidth())
  pos.value = clampPosition(pos.value.x, pos.value.y)
}
window.addEventListener('resize', onResize)
onBeforeUnmount(() => window.removeEventListener('resize', onResize))
</script>

<template>
  <div
    v-if="ready"
    class="video-float"
    :class="{ 'video-float--dragging': dragging, 'video-float--resizing': resizing }"
    :style="{ left: pos.x + 'px', top: pos.y + 'px', width: panelW + 'px' }"
  >
    <header class="video-float__head" title="按住拖动" @pointerdown="onHeadDown">
      <span class="video-float__dot" aria-hidden="true"></span>
      <span class="video-float__title">{{ props.video.title }}</span>
      <a
        class="video-float__link"
        :href="props.video.url"
        target="_blank"
        rel="noopener noreferrer"
      >在B站看</a>
      <button class="video-float__close" type="button" aria-label="关闭播放器" @click="emit('close')">
        ×
      </button>
    </header>

    <div class="video-float__screen" :style="{ height: playerH + 'px' }">
      <!-- 首选：自己的 <video>，画面里没有 B 站那个「进入哔哩哔哩」按钮 -->
      <video
        v-if="streamUrl"
        class="video-float__video"
        :src="streamUrl"
        controls
        autoplay
        playsinline
        preload="metadata"
      ></video>

      <!-- 直链没拿到：退回官方 iframe，至少还能看 -->
      <iframe
        v-else-if="streamError"
        :src="iframeSrc"
        class="video-float__frame"
        frameborder="0"
        scrolling="no"
        allow="autoplay; fullscreen; picture-in-picture"
        allowfullscreen
        referrerpolicy="no-referrer"
        :title="props.video.title"
      ></iframe>

      <!-- 还在要地址 -->
      <div v-else class="video-float__loading">
        <span class="video-float__spinner" aria-hidden="true"></span>
        <span>正在取播放地址…</span>
      </div>
    </div>

    <!-- 右侧竖条把手：横着拖 = 拉大/缩小（高度跟着 16:9 走） -->
    <span
      class="video-float__resize"
      title="左右拖动调整窗口大小"
      @pointerdown="onResizeDown"
    ></span>
  </div>
</template>

<style scoped>
.video-float {
  position: fixed;
  z-index: 96;                 /* 比电话浮窗(95)高一层，两个都开着时视频在上面 */
  border: 1.5px solid rgba(255, 253, 248, 0.3);
  border-radius: 14px;
  background: rgba(8, 32, 32, 0.97);
  backdrop-filter: blur(14px);
  box-shadow: 0 22px 52px rgba(0, 0, 0, 0.55);
  overflow: hidden;
  color: #fffdf8;
  animation: video-in 0.22s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes video-in {
  from { opacity: 0; transform: translateY(10px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
.video-float--dragging {
  transition: none;
  user-select: none;
}
.video-float--resizing {
  transition: none;
  user-select: none;
}

/* 右侧把手：不挡播放器底部那排控制键 */
.video-float__resize {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 9px;
  height: 44px;
  border-radius: 5px 0 0 5px;
  background: rgba(255, 253, 248, 0.16);
  cursor: ew-resize;
  touch-action: none;
  display: grid;
  place-items: center;
}
.video-float__resize::after {
  content: '';
  width: 2px;
  height: 18px;
  border-left: 2px dotted rgba(255, 253, 248, 0.75);
}
.video-float__resize:hover { background: rgba(251, 114, 153, 0.4); }

.video-float__head {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 46px;
  padding: 0 10px 0 12px;
  box-sizing: border-box;
  cursor: grab;
  touch-action: none;
  background: rgba(255, 253, 248, 0.05);
}
.video-float--dragging .video-float__head { cursor: grabbing; }

.video-float__dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #fb7299;          /* B 站粉，一眼知道这是 B 站视频 */
  box-shadow: 0 0 8px rgba(251, 114, 153, 0.8);
}

.video-float__title {
  flex: 1;
  min-width: 0;
  font-size: 0.76rem;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.video-float__link {
  flex: none;
  font-size: 0.68rem;
  color: rgba(159, 232, 196, 0.9);
  text-decoration: none;
  padding: 3px 6px;
  border-radius: 6px;
}
.video-float__link:hover { background: rgba(159, 232, 196, 0.14); }

.video-float__close {
  flex: none;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 253, 248, 0.12);
  color: #fffdf8;
  font-size: 0.9rem;
  line-height: 1;
  cursor: pointer;
  display: grid;
  place-items: center;
}
.video-float__close:hover { background: rgba(255, 120, 120, 0.5); }

.video-float__screen {
  background: #000;
}
.video-float__frame {
  display: block;
  width: 100%;
  height: 100%;
  border: none;
}

.video-float__video {
  display: block;
  width: 100%;
  height: 100%;
  background: #000;
  object-fit: contain;
}

.video-float__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 100%;
  font-size: 0.72rem;
  color: rgba(255, 253, 248, 0.6);
}

.video-float__spinner {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(255, 253, 248, 0.2);
  border-top-color: #fb7299;
  animation: video-spin 0.8s linear infinite;
}
@keyframes video-spin {
  to { transform: rotate(360deg); }
}
</style>
