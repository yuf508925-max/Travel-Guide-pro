<template>
  <div class="music-float" ref="rootRef">
    <button
      class="music-btn"
      :class="{ 'music-btn--on': open, 'music-btn--playing': playing }"
      type="button"
      :title="playing ? `正在播放：${currentTrack?.name ?? ''}` : '音乐：上传你喜欢的歌（只存在本机临时目录）'"
      :aria-expanded="open"
      @click="toggle()"
    >
      <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
        <path
          d="M9 18V6.6l9-1.6v10.4"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <circle cx="6.6" cy="18" r="2.4" fill="none" stroke="currentColor" stroke-width="1.6" />
        <circle cx="15.6" cy="15.4" r="2.4" fill="none" stroke="currentColor" stroke-width="1.6" />
      </svg>
      <span>{{ playing && !open ? '播放中' : '音乐' }}</span>
    </button>

    <div v-if="open" class="music-panel" role="dialog" aria-label="我的音乐">
      <header class="music-panel__head">
        <span class="music-panel__title">我的音乐</span>
        <span class="music-panel__count">{{ playlist.length }} 首</span>
        <button class="music-panel__upload" type="button" :disabled="uploading > 0" @click="pickFiles">
          {{ uploading > 0 ? `上传中 ${uploading}` : '＋ 上传' }}
        </button>
        <button class="music-panel__close" type="button" aria-label="关闭" @click="open = false">×</button>
        <input
          ref="fileRef"
          class="music-panel__file"
          type="file"
          accept="audio/*,.mp3,.wav,.ogg,.m4a,.aac,.flac,.opus"
          multiple
          @change="onFiles"
        />
      </header>

      <p v-if="error" class="music-panel__error">{{ error }}</p>

      <ul class="music-list">
        <li
          v-for="(track, i) in playlist"
          :key="track.id"
          class="music-item"
          :class="{ 'music-item--active': i === currentIndex }"
          @click="playIndex(i)"
        >
          <span class="music-item__idx">{{ i === currentIndex && playing ? '♪' : i + 1 }}</span>
          <span class="music-item__name" :title="track.name">{{ track.name }}</span>
          <span class="music-item__size">{{ track.builtin ? '' : fmtSize(track.size) }}</span>
          <button
            v-if="!track.builtin"
            class="music-item__del"
            type="button"
            title="删掉这首"
            @click.stop="remove(track)"
          >×</button>
          <span v-else class="music-item__keep" title="自带的背景音乐，永久保留">内置</span>
        </li>
      </ul>
      <p v-if="!tracks.length" class="music-panel__empty">
        想听自己的歌点击「上传」（小于40MB）
      </p>

      <!-- 播放条 -->
      <div class="music-bar">
        <div class="music-bar__row">
          <button class="music-bar__btn" type="button" title="上一首" :disabled="!playlist.length" @click="prev()">
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <path d="M7 6v12M18 6.6v10.8L9.6 12z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" />
            </svg>
          </button>

          <button class="music-bar__btn music-bar__btn--main" type="button" :title="playing ? '暂停' : '播放'" :disabled="!playlist.length" @click="togglePlay">
            <svg v-if="playing" viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
              <path d="M8.5 6v12M15.5 6v12" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" fill="none" />
            </svg>
            <svg v-else viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
              <path d="M8 5.5l10 6.5-10 6.5z" fill="currentColor" />
            </svg>
          </button>

          <button class="music-bar__btn" type="button" title="下一首" :disabled="!playlist.length" @click="next()">
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <path d="M17 6v12M6 6.6v10.8L14.4 12z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" />
            </svg>
          </button>

          <span class="music-bar__time">{{ fmtTime(currentTime) }} / {{ fmtTime(duration) }}</span>
        </div>

        <input
          class="music-bar__seek"
          type="range"
          min="0"
          :max="duration || 0"
          step="0.1"
          :value="currentTime"
          :disabled="!duration"
          aria-label="播放进度"
          @input="onSeek"
        />
      </div>
    </div>

    <audio
      ref="audioRef"
      preload="metadata"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoaded"
      @ended="onEnded"
      @play="onPlay"
      @pause="onPause"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

/**
 * 右上角「音乐」：名字和「记忆」中间那个入口。
 *
 * 后端接口：
 *   GET    /api/music                 列出这次登录上传的歌
 *   POST   /api/music/upload?name=..  请求体直接是文件字节
 *   DELETE /api/music/{id}            删一首
 *   GET    /api/music/{id}/file       音频流（带 Range，拖进度条靠它）
 *
 * 歌只存在后端 server/tmp_music/<登录 token>/，退出登录或会话过期后
 * 由后端随会话一起删掉——所以这里不需要任何“云端保存”。
 */

interface Track {
  id: number
  name: string
  ext: string
  size: number
  position: number
  created_at: string
  url: string
  /** 自带的背景音乐：列表里常驻，不许删 */
  builtin?: boolean
}

/** public 下那首自带 BGM（和 ChatView 里的 BGM_SRC 是同一个文件） */
const BUILTIN_TRACK: Track = {
  id: -1,
  name: "Travelers' encore - Andrew Prahlow",
  ext: '.mp3',
  size: 0,
  position: 0,
  created_at: '',
  url: "/Travelers' encore - Andrew Prahlow.mp3",
  builtin: true,
}

const props = defineProps<{
  /** 背景音乐音量（0~100），跟右上角音量菜单里的「音乐」共用 */
  volume?: number
  muted?: boolean
}>()

const emit = defineEmits<{
  (e: 'play'): void      // 开始播放：让 ChatView 把自带的 BGM 停掉
  (e: 'close'): void
}>()

const rootRef = ref<HTMLElement | null>(null)
const fileRef = ref<HTMLInputElement | null>(null)
const audioRef = ref<HTMLAudioElement | null>(null)

const open = ref(false)
const tracks = ref<Track[]>([])
const currentIndex = ref(-1)
const playing = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const uploading = ref(0)
const error = ref('')

// 列表 = 自带那首永久保留 + 本次登录上传的
const playlist = computed<Track[]>(() => [BUILTIN_TRACK, ...tracks.value])
const currentTrack = computed(() => playlist.value[currentIndex.value] ?? null)

// ---------------------------------------------------------------- 工具
function fmtTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '0:00'
  const total = Math.floor(seconds)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function fmtSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}M`
  return `${Math.max(1, Math.round(bytes / 1024))}K`
}

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    const detail = (data as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
  } catch {
    /* 不是 JSON 就用通用文案 */
  }
  return `请求失败（${res.status}）`
}

// ---------------------------------------------------------------- 列表
async function load(): Promise<void> {
  try {
    const res = await fetch('/api/music', { credentials: 'same-origin' })
    if (!res.ok) {
      error.value = await readError(res)
      return
    }
    const data = (await res.json()) as { tracks?: Track[] }
    tracks.value = data.tracks ?? []
    error.value = ''
    // 正在播的那首可能被别处删了，重新对一下下标（下标是在 playlist 里的，含自带那首）
    if (currentIndex.value >= playlist.value.length) {
      currentIndex.value = playlist.value.length - 1
    }
  } catch {
    error.value = '列不出音乐，后端是不是没开？'
  }
}

// ---------------------------------------------------------------- 播放
async function playIndex(index: number): Promise<void> {
  const track = playlist.value[index]
  const audio = audioRef.value
  if (!track || !audio) return

  currentIndex.value = index
  currentTime.value = 0
  duration.value = 0
  audio.src = track.url
  audio.load()
  try {
    await audio.play()
  } catch {
    // 浏览器可能因为没交互拦住自动播；按钮点过之后就正常了
    playing.value = false
  }
}

async function togglePlay(): Promise<void> {
  const audio = audioRef.value
  if (!audio) return

  if (!currentTrack.value && playlist.value.length) {
    await playIndex(0)
    return
  }
  if (audio.paused) {
    try {
      await audio.play()
    } catch {
      playing.value = false
    }
  } else {
    audio.pause()
  }
}

function next(): void {
  if (!playlist.value.length) return
  const index = currentIndex.value < 0 ? 0 : (currentIndex.value + 1) % playlist.value.length
  void playIndex(index)
}

function prev(): void {
  if (!playlist.value.length) return
  const audio = audioRef.value
  // 播了 3 秒以上，先回到本首开头（跟常见播放器一致）
  if (audio && audio.currentTime > 3) {
    audio.currentTime = 0
    return
  }
  const index = currentIndex.value <= 0 ? playlist.value.length - 1 : currentIndex.value - 1
  void playIndex(index)
}

function onPlay(): void {
  playing.value = true
  emit('play')
}

function onPause(): void {
  playing.value = false
}

function onLoaded(): void {
  const audio = audioRef.value
  if (audio && Number.isFinite(audio.duration)) duration.value = audio.duration
}

function onTimeUpdate(): void {
  const audio = audioRef.value
  if (audio) currentTime.value = audio.currentTime
}

function onEnded(): void {
  next()
}

function onSeek(event: Event): void {
  const audio = audioRef.value
  const value = Number((event.target as HTMLInputElement).value)
  if (audio && Number.isFinite(value)) {
    audio.currentTime = value
    currentTime.value = value
  }
}

// ---------------------------------------------------------------- 上传 / 删除
function pickFiles(): void {
  fileRef.value?.click()
}

async function onFiles(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''            // 允许再选同一个文件
  if (!files.length) return

  error.value = ''
  uploading.value = files.length
  let firstAdded = -1

  for (const file of files) {
    try {
      const res = await fetch(`/api/music/upload?name=${encodeURIComponent(file.name)}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: file,
      })
      if (!res.ok) {
        error.value = `${file.name}：${await readError(res)}`
        continue
      }
      const track = (await res.json()) as Track
      if (firstAdded < 0) firstAdded = track.id
    } catch {
      error.value = `${file.name}：上传失败，检查一下后端`
    } finally {
      uploading.value -= 1
    }
  }

  await load()

  // 本来一首都没播，上传完直接放第一首新的
  if (firstAdded >= 0 && currentIndex.value < 0) {
    const index = playlist.value.findIndex((t) => t.id === firstAdded)
    if (index >= 0) await playIndex(index)
  }
}

async function remove(track: Track): Promise<void> {
  const index = playlist.value.findIndex((t) => t.id === track.id)
  const wasCurrent = index === currentIndex.value
  try {
    const res = await fetch(`/api/music/${track.id}`, {
      method: 'DELETE',
      credentials: 'same-origin',
    })
    if (!res.ok) {
      error.value = await readError(res)
      return
    }
  } catch {
    error.value = '删除失败，检查一下后端'
    return
  }

  if (wasCurrent) {
    audioRef.value?.pause()
    currentIndex.value = -1
    currentTime.value = 0
    duration.value = 0
  }
  await load()
  if (wasCurrent && playlist.value.length) {
    await playIndex(Math.min(index, playlist.value.length - 1))
  }
}

// ---------------------------------------------------------------- 面板开关 / 外部点击 / 音量
function toggle(): void {
  open.value = !open.value
  if (open.value) void load()
}

function onDocPointerDown(event: PointerEvent): void {
  if (!open.value) return
  const root = rootRef.value
  if (root && !root.contains(event.target as Node)) open.value = false
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && open.value) open.value = false
}

function applyVolume(): void {
  const audio = audioRef.value
  if (!audio) return
  const level = props.muted ? 0 : Math.min(1, Math.max(0, (props.volume ?? 20) / 100))
  audio.volume = level
}

watch(() => [props.volume, props.muted], applyVolume)

onMounted(async () => {
  document.addEventListener('pointerdown', onDocPointerDown)
  document.addEventListener('keydown', onKeydown)
  await nextTick()
  applyVolume()
  void load()
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointerDown)
  document.removeEventListener('keydown', onKeydown)
  audioRef.value?.pause()
})
</script>

<style scoped>
.music-float { position: relative; display: inline-flex; }

/* 和「记忆」按钮同款胶囊（父组件的样式是 scoped，够不到子组件内部，所以自己写一份） */
.music-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 10px;
  border: 1px solid rgba(200, 240, 255, 0.35);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  color: #eaf8ff;
  font-size: 0.76rem;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease;
}
.music-btn:hover {
  background: rgba(255, 255, 255, 0.22);
  border-color: rgba(220, 250, 255, 0.6);
}

.music-btn--on,
.music-btn--playing {
  background: rgba(255, 255, 255, 0.22);
  border-color: rgba(220, 250, 255, 0.6);
}
.music-btn--playing span { color: #b6f5d6; }

.music-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 322px;
  padding: 12px 12px 10px;
  border: 1.5px solid rgba(255, 253, 248, 0.35);
  border-radius: 14px;
  background: rgba(12, 46, 46, 0.97);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.45);
  z-index: 130;
  color: #fffdf8;
}

.music-panel__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.music-panel__title { font-size: 0.86rem; font-weight: 500; letter-spacing: 0.04em; }
.music-panel__count { font-size: 0.68rem; opacity: 0.6; }
.music-panel__upload {
  margin-left: auto;
  border: 1px solid rgba(159, 232, 196, 0.45);
  border-radius: 999px;
  background: rgba(159, 232, 196, 0.16);
  color: #d9f6e6;
  font-size: 0.7rem;
  padding: 4px 10px;
  cursor: pointer;
}
.music-panel__upload:hover:not(:disabled) { background: rgba(159, 232, 196, 0.28); }
.music-panel__upload:disabled { opacity: 0.6; cursor: default; }
.music-panel__close {
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
  padding: 0;
}
.music-panel__close:hover { background: rgba(255, 120, 120, 0.5); }
.music-panel__file { display: none; }

.music-panel__error {
  margin: 8px 0 0;
  font-size: 0.7rem;
  color: #ffb2b2;
  line-height: 1.5;
}

.music-list {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  max-height: 210px;
  overflow-y: auto;
}
.music-item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 7px;
  border-radius: 8px;
  font-size: 0.74rem;
  cursor: pointer;
}
.music-item:hover { background: rgba(255, 253, 248, 0.1); }
.music-item--active { background: rgba(159, 232, 196, 0.16); }
.music-item__idx {
  flex: none;
  width: 16px;
  text-align: center;
  opacity: 0.65;
  font-variant-numeric: tabular-nums;
}
.music-item--active .music-item__idx { color: #9fe8c4; opacity: 1; }
.music-item__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.music-item__size { flex: none; font-size: 0.66rem; opacity: 0.55; }
.music-item__keep {
  flex: none;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(159, 232, 196, 0.16);
  color: #9fe8c4;
  font-size: 0.6rem;
  letter-spacing: 0.04em;
}
.music-item__del {
  flex: none;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 253, 248, 0.5);
  font-size: 0.8rem;
  line-height: 1;
  padding: 0;
  cursor: pointer;
}
.music-item__del:hover { background: rgba(255, 120, 120, 0.45); color: #fff; }

.music-panel__empty {
  margin: 12px 2px 4px;
  font-size: 0.7rem;
  line-height: 1.7;
  opacity: 0.62;
}

.music-bar {
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px solid rgba(255, 253, 248, 0.14);
}
.music-bar__row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.music-bar__btn {
  flex: none;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 253, 248, 0.24);
  border-radius: 50%;
  background: rgba(255, 253, 248, 0.08);
  color: #fffdf8;
  cursor: pointer;
  padding: 0;
}
.music-bar__btn:hover:not(:disabled) { background: rgba(159, 232, 196, 0.22); }
.music-bar__btn:disabled { opacity: 0.4; cursor: default; }
.music-bar__btn--main {
  width: 34px;
  height: 34px;
  background: rgba(159, 232, 196, 0.22);
  border-color: rgba(159, 232, 196, 0.5);
}
.music-bar__time {
  margin-left: auto;
  font-size: 0.66rem;
  opacity: 0.68;
  font-variant-numeric: tabular-nums;
}

.music-bar__seek {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 16px;
  margin: 6px 0 0;
  background: transparent;
  cursor: pointer;
}
.music-bar__seek::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 999px;
  background: rgba(255, 253, 248, 0.22);
}
.music-bar__seek::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 11px;
  height: 11px;
  margin-top: -3.5px;
  border-radius: 50%;
  background: #9fe8c4;
}
.music-bar__seek::-moz-range-track {
  height: 4px;
  border-radius: 999px;
  background: rgba(255, 253, 248, 0.22);
}
.music-bar__seek::-moz-range-thumb {
  width: 11px;
  height: 11px;
  border: none;
  border-radius: 50%;
  background: #9fe8c4;
}
.music-bar__seek:disabled { opacity: 0.5; cursor: default; }
</style>
