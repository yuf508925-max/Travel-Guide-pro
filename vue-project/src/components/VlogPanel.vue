<!--
  VlogPanel.vue —— 「观看 vlog」面板
  ------------------------------------------------------------------
  打开后自动要 5 条和这个地区相关的 B 站旅行视频：
    · 搜索词不是直接把城市名丢给 B 站，而是让后端请模型想几条
      （「青岛 旅行vlog」这种），否则搜出来全是新闻和航拍；
    · 「换一批」= 带上已经看过的 bvid 再要一次，优先播放量高的、不重复；
    · 点卡片 → 交给 ChatView 弹浮窗播放器（VideoFloat.vue），
      关掉这个面板视频也不会停。
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { VlogVideo } from '../types/vlog'
// 搜索词和行程记录存在同一张表里（kind=vlog），下拉建议也从这里来
import SearchBar from './SearchBar.vue'

const props = defineProps<{ initialRegion?: string }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'open', video: VlogVideo): void
}>()

const region = ref((props.initialRegion || '青岛').trim() || '青岛')
const regionDraft = ref(region.value)
const videos = ref<VlogVideo[]>([])
const loading = ref(false)
const error = ref('')
const repeat = ref(false)
// 按 UP 主搜时，后端会告诉我们到底匹配到了谁（同名号很多，得让用户看见）
interface MatchedUser {
  mid: number
  uname: string
  fans: number
  avatar: string
}
const matchedUsers = ref<MatchedUser[]>([])
const matchedUser = computed(() => matchedUsers.value[0] ?? null)

// 手动搜索：搜了就切到「搜索模式」，换一批也继续搜这个词；
// 清空搜索框并回车就退回按地区推荐。
const searchDraft = ref('')
const activeSearch = ref('')

// 搜索框下拉（最近搜过的词）和输入框本身都交给 SearchBar 组件，
// 这里只关心「搜了什么」和「要不要退回按地区推荐」。

// 搜索类型：按视频标题搜 / 按 UP 主搜（搜 TA 发的视频）
type SearchKind = 'video' | 'up'
const kind = ref<SearchKind>('video')
const kindOpen = ref(false)
const KIND_OPTIONS: { value: SearchKind; label: string; hint: string }[] = [
  { value: 'video', label: '标题', hint: '按视频标题搜' },
  { value: 'up', label: 'UP主', hint: '按 UP 主搜 TA 的视频' },
]
const kindLabel = computed(() => KIND_OPTIONS.find((item) => item.value === kind.value)?.label ?? '标题')

function pickKind(value: SearchKind) {
  kindOpen.value = false
  if (kind.value === value) return
  kind.value = value
  // 已经在搜索里就按新类型重搜一遍，否则只记下来、等按回车
  if (activeSearch.value) {
    seen.clear()
    videos.value = []
    repeat.value = false
    void load()
  }
}

/** 点空白处收起下拉 */
function onDocPointerDown(event: PointerEvent) {
  const target = event.target as HTMLElement | null
  if (kindOpen.value && !target?.closest?.('.vlog-kind')) kindOpen.value = false
}
// 这次打开面板期间已经展示过的视频：刷新时发给后端，让它跳过
const seen = new Set<string>()

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ limit: '5', seen: [...seen].slice(-60).join(',') })
    if (activeSearch.value) {
      params.set('q', activeSearch.value)
      params.set('kind', kind.value)
    } else params.set('region', region.value)
    const response = await fetch(`/api/vlog/recommend?${params.toString()}`)
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}))
      throw new Error((detail as { detail?: string }).detail || `接口返回 ${response.status}`)
    }
    const data = (await response.json()) as {
      videos?: VlogVideo[]
      repeat?: boolean
      users?: MatchedUser[]
    }
    videos.value = data.videos || []
    repeat.value = Boolean(data.repeat)
    matchedUsers.value = data.users || []
    for (const video of videos.value) seen.add(video.bvid)
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '拿不到视频列表'
    matchedUsers.value = []
  } finally {
    loading.value = false
  }
}

/** 换了地区就从头来：清掉「已看过」的记录，否则可能一条都刷不出来 */
function applyRegion() {
  const next = regionDraft.value.trim()
  if (!next || (next === region.value && !activeSearch.value)) {
    regionDraft.value = region.value
    return
  }
  region.value = next
  // 换地区 = 退出搜索模式
  activeSearch.value = ''
  searchDraft.value = ''
  seen.clear()
  videos.value = []
  repeat.value = false
  void load()
}

/** 搜索（回车 / 点放大镜）：按关键词搜 5 条，同样支持「换一批」不重复 */
function doSearch() {
  const next = searchDraft.value.trim()
  if (!next) {
    // 搜索框清空后回车 = 回到按地区推荐
    if (activeSearch.value) {
      activeSearch.value = ''
      seen.clear()
      videos.value = []
      repeat.value = false
      void load()
    }
    return
  }
  if (next === activeSearch.value) return
  activeSearch.value = next
  seen.clear()
  videos.value = []
  repeat.value = false
  void load()
}

/** 搜索框被清空（点 × 或全删掉）→ 退出搜索模式，回到按地区推荐 */
watch(searchDraft, (value) => {
  if (!value.trim() && activeSearch.value) {
    activeSearch.value = ''
    seen.clear()
    videos.value = []
    repeat.value = false
    void load()
  }
})

/** 搜索框右侧的小 × ：清空并回到地区模式（watch 里会重载，这里只清词） */

function fmtCount(value: number): string {
  const n = Number(value) || 0
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1).replace(/\.0$/, '')}亿`
  if (n >= 10_000) return `${(n / 10_000).toFixed(1).replace(/\.0$/, '')}万`
  return String(n)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('pointerdown', onDocPointerDown)
  void load()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('pointerdown', onDocPointerDown)
})
</script>

<template>
  <div class="vlog-layer">
    <div class="vlog-backdrop" @click="emit('close')"></div>

    <section class="vlog-panel" role="dialog" aria-label="观看 vlog">
      <header class="vlog-head">
        <span class="vlog-title">观看 vlog</span>
        <span class="vlog-badge">B站 · 旅行视频</span>

        <!-- 搜什么：标题 / UP 主（参考图里「驾车 / 步行 / 公交」那个下拉） -->
        <div class="vlog-kind" :class="{ 'vlog-kind--open': kindOpen }">
          <button
            class="vlog-kind__btn"
            type="button"
            :aria-label="`搜索类型：${kindLabel}`"
            :aria-expanded="kindOpen"
            @click="kindOpen = !kindOpen"
          >
            {{ kindLabel }}
            <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true" class="vlog-kind__caret">
              <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <ul v-if="kindOpen" class="vlog-kind__menu" role="listbox">
            <li
              v-for="option in KIND_OPTIONS"
              :key="option.value"
              role="option"
              :aria-selected="option.value === kind"
              class="vlog-kind__item"
              :class="{ 'vlog-kind__item--active': option.value === kind }"
              :title="option.hint"
              @click="pickKind(option.value)"
            >{{ option.label }}</li>
          </ul>
        </div>

        <!-- 搜索：按关键词搜 5 条（和按地区推荐是同一套逻辑，也支持换一批）
             输入框 / 历史下拉都来自公共的 SearchBar 组件，和行程那边完全一样 -->
        <SearchBar
          v-model="searchDraft"
          class="vlog-field"
          kind="vlog"
          icon
          button-label="搜索"
          :maxlength="30"
          :limit="8"
          :disabled="loading"
          :placeholder="kind === 'up' ? '搜 UP 主，比如 花二Strange' : '搜视频标题，比如 重庆火锅'"
          title="点一下可以选最近搜过的词"
          @search="doSearch"
          @pick="doSearch"
        />

        <!-- 地区：按地方推荐，右边这个「搜索」是它自己的一份，和上面那个是分开的 -->
        <SearchBar
          v-model="regionDraft"
          class="vlog-field vlog-field--place"
          kind="vlog-region"
          button-label="搜索"
          :maxlength="20"
          :limit="6"
          :disabled="loading"
          placeholder="换个地方，比如 成都"
          title="按这个地方搜，回车或点右边的按钮"
          @search="applyRegion"
          @pick="applyRegion"
        />

        <button
          class="vlog-refresh"
          type="button"
          :disabled="loading"
          :title="activeSearch ? '换 5 条没看过的（按相关度排）' : '优先播放量高的，且不重复前面看过的'"
          @click="load"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
            <path
              d="M20 12a8 8 0 1 1-2.5-5.8M20 4v4.5h-4.5"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          {{ loading ? '换批中…' : '换一批' }}
        </button>

        <button class="vlog-close" type="button" aria-label="关闭" @click="emit('close')">×</button>
      </header>

      <p class="vlog-sub">
        <template v-if="activeSearch && kind === 'up'">
          搜索 UP 主「{{ activeSearch }}」
          <template v-if="matchedUser">
            → 匹配到
            <span class="vlog-sub__user">
              <img v-if="matchedUser.avatar" class="vlog-sub__avatar" :src="matchedUser.avatar" alt="" referrerpolicy="no-referrer" />
              {{ matchedUser.uname }}
            </span>
            <span v-if="matchedUser.fans">· {{ fmtCount(matchedUser.fans) }} 粉</span>
          </template>
          · 点卡片在浮窗里播放，可以拖动
        </template>
        <template v-else-if="activeSearch">
          搜索标题「{{ activeSearch }}」· 点卡片在浮窗里播放，可以拖动
        </template>
        <template v-else>
          正在看「{{ region }}」相关的视频 · 点卡片在浮窗里播放，可以拖动
        </template>
        <span v-if="repeat" class="vlog-sub__warn">（这批已经刷完一轮，开始重复了）</span>
      </p>

      <!-- 加载中：占位的骨架，别让面板空着像坏了 -->
      <div v-if="loading && videos.length === 0" class="vlog-list">
        <div v-for="n in 5" :key="n" class="vlog-card vlog-card--skeleton">
          <div class="vlog-skeleton vlog-skeleton--cover"></div>
          <div class="vlog-card__info">
            <div class="vlog-skeleton vlog-skeleton--line"></div>
            <div class="vlog-skeleton vlog-skeleton--line vlog-skeleton--short"></div>
          </div>
        </div>
      </div>

      <div v-else-if="error" class="vlog-error">
        <p>{{ error }}</p>
        <button type="button" class="vlog-error__btn" @click="load">再试一次</button>
      </div>

      <div v-else-if="videos.length === 0" class="vlog-error">
        <p v-if="activeSearch">没搜到「{{ activeSearch }}」的视频，换个词试试？</p>
        <p v-else>没搜到「{{ region }}」的旅行视频，换个地名试试？</p>
      </div>

      <div v-else class="vlog-list">
        <article
          v-for="video in videos"
          :key="video.bvid"
          class="vlog-card"
          :class="{ 'vlog-card--loading': loading }"
          @click="emit('open', video)"
        >
          <div class="vlog-card__cover">
            <img
              class="vlog-card__img"
              :src="video.cover"
              :alt="video.title"
              loading="lazy"
              referrerpolicy="no-referrer"
            />
            <span class="vlog-card__dur">{{ video.duration }}</span>
            <span class="vlog-card__playbar">▶ {{ fmtCount(video.play) }}</span>
          </div>

          <div class="vlog-card__info">
            <h3 class="vlog-card__title">{{ video.title }}</h3>

            <div class="vlog-card__meta">
              <img
                v-if="video.author_avatar"
                class="vlog-card__avatar"
                :src="video.author_avatar"
                alt=""
                loading="lazy"
                referrerpolicy="no-referrer"
              />
              <span class="vlog-card__author">{{ video.author }}</span>
              <span class="vlog-card__stat">播放 {{ fmtCount(video.play) }}</span>
              <span v-if="video.danmaku" class="vlog-card__stat">弹幕 {{ fmtCount(video.danmaku) }}</span>
            </div>
          </div>

          <a
            class="vlog-card__link"
            :href="video.url"
            target="_blank"
            rel="noopener noreferrer"
            title="在B站打开这条视频"
            @click.stop
          >B站打开</a>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.vlog-layer {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
}

.vlog-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(4, 24, 24, 0.5);
  backdrop-filter: blur(3px);
}

.vlog-panel {
  position: relative;
  z-index: 1;
  width: min(920px, 96vw);
  max-height: min(88vh, 820px);
  overflow-y: auto;
  padding: 14px 16px 16px;
  box-sizing: border-box;
  border: 1.5px solid rgba(255, 253, 248, 0.4);
  border-radius: 16px;
  background: rgba(12, 46, 46, 0.96);
  backdrop-filter: blur(14px);
  box-shadow: 0 22px 60px rgba(0, 0, 0, 0.45);
  color: #fffdf8;
  animation: panel-in 0.2s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes panel-in {
  from { opacity: 0; transform: translateY(8px) scale(0.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.vlog-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  margin-bottom: 8px;
  min-width: 0;
}
/* 除了搜索框，其余控件都不许被挤扁，保证整行放得下 */
.vlog-head > .vlog-title,
.vlog-head > .vlog-badge,
.vlog-head > .vlog-kind,
.vlog-head > .vlog-refresh,
.vlog-head > .vlog-close { flex: none; }
/* 关键词搜索框（连同它的历史下拉）占住剩下的空间 */
.vlog-head > .search-bar { flex: 1 1 auto; min-width: 110px; }
/* 地区那一栏固定一点，别把关键词框挤没 */
.vlog-head > .vlog-field--place { flex: 0 0 auto; width: 190px; min-width: 0; }
@media (max-width: 780px) {
  .vlog-head { flex-wrap: wrap; }
  .vlog-head > .vlog-field--place { width: 100%; }
}
.vlog-title {
  font-size: 1rem;
  font-weight: 500;
  letter-spacing: 0.04em;
}
.vlog-badge {
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(251, 114, 153, 0.22);
  color: #ffc2d4;
  font-size: 0.62rem;
}

/* ---- 搜索类型下拉：标题 / UP主 ---- */
.vlog-kind {
  position: relative;
  flex: none;
}
.vlog-kind__btn {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 4px 8px;
  border: 1px solid rgba(255, 253, 248, 0.28);
  border-radius: 9px;
  background: rgba(255, 253, 248, 0.08);
  color: #fffdf8;
  font-size: 0.7rem;
  cursor: pointer;
  white-space: nowrap;
}
.vlog-kind__btn:hover { background: rgba(255, 253, 248, 0.16); }
.vlog-kind--open .vlog-kind__btn {
  border-color: rgba(159, 232, 196, 0.7);
  background: rgba(159, 232, 196, 0.18);
}
.vlog-kind__caret { flex: none; opacity: 0.7; }
.vlog-kind__menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 6;
  min-width: 92px;
  margin: 0;
  padding: 4px;
  list-style: none;
  border: 1px solid rgba(255, 253, 248, 0.22);
  border-radius: 9px;
  background: rgba(8, 34, 34, 0.98);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.45);
}
.vlog-kind__item {
  padding: 5px 9px;
  border-radius: 6px;
  color: rgba(255, 253, 248, 0.85);
  font-size: 0.72rem;
  cursor: pointer;
  white-space: nowrap;
}
.vlog-kind__item:hover { background: rgba(255, 253, 248, 0.14); }
.vlog-kind__item--active {
  background: rgba(159, 232, 196, 0.22);
  color: #fffdf8;
  font-weight: 500;
}

/* ---- 搜索框 / 历史下拉：由公共的 SearchBar 组件提供，这里只管它在头部占多宽 ---- */
.vlog-field { min-width: 0; }

.vlog-refresh,
.vlog-close {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid rgba(255, 253, 248, 0.24);
  border-radius: 9px;
  background: rgba(255, 253, 248, 0.08);
  color: #fffdf8;
  font-size: 0.72rem;
  padding: 8px 11px;
  cursor: pointer;
}
.vlog-refresh:hover:not(:disabled) { background: rgba(159, 232, 196, 0.2); }
.vlog-refresh:disabled { opacity: 0.55; cursor: default; }
.vlog-refresh svg { display: block; }

.vlog-close {
  width: 30px;
  height: 30px;
  padding: 0;
  justify-content: center;
  border-radius: 50%;
  font-size: 0.9rem;
}
.vlog-close:hover { background: rgba(255, 120, 120, 0.45); }

.vlog-sub {
  margin: 0 0 10px;
  font-size: 0.66rem;
  color: rgba(255, 253, 248, 0.55);
}
.vlog-sub__user {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #fffdf8;
  font-weight: 500;
}
.vlog-sub__avatar {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  object-fit: cover;
  display: block;
}.vlog-sub__warn { color: #ffd08a; }

.vlog-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ---- 一条视频 ---- */
.vlog-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  border: 1px solid rgba(255, 253, 248, 0.14);
  border-radius: 12px;
  background: rgba(255, 253, 248, 0.05);
  cursor: pointer;
  transition: background 0.16s, border-color 0.16s, transform 0.16s;
}
.vlog-card:hover {
  background: rgba(159, 232, 196, 0.12);
  border-color: rgba(159, 232, 196, 0.5);
  transform: translateY(-1px);
}
.vlog-card--loading { opacity: 0.5; pointer-events: none; }

.vlog-card__cover {
  position: relative;
  flex: none;
  width: 168px;
  height: 95px;
  border-radius: 9px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.35);
}
.vlog-card__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.vlog-card__dur,
.vlog-card__playbar {
  position: absolute;
  bottom: 4px;
  padding: 1px 5px;
  border-radius: 5px;
  background: rgba(0, 0, 0, 0.62);
  color: #fff;
  font-size: 0.56rem;
  font-variant-numeric: tabular-nums;
}
.vlog-card__dur { right: 4px; }
.vlog-card__playbar { left: 4px; }

.vlog-card__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.vlog-card__title {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 500;
  line-height: 1.4;
  /* 标题最多两行，超了省略，卡片高度才不会乱 */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.vlog-card__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 0.64rem;
  color: rgba(255, 253, 248, 0.62);
}
.vlog-card__avatar {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  object-fit: cover;
  background: rgba(255, 253, 248, 0.15);
}
.vlog-card__author {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vlog-card__stat { font-variant-numeric: tabular-nums; }

.vlog-card__link {
  flex: none;
  align-self: center;
  padding: 4px 8px;
  border-radius: 8px;
  border: 1px solid rgba(255, 253, 248, 0.2);
  color: rgba(255, 253, 248, 0.75);
  font-size: 0.62rem;
  text-decoration: none;
}
.vlog-card__link:hover {
  color: #fffdf8;
  background: rgba(251, 114, 153, 0.35);
  border-color: rgba(251, 114, 153, 0.6);
}

/* ---- 加载骨架 ---- */
.vlog-card--skeleton { cursor: default; }
.vlog-skeleton {
  background: linear-gradient(
    100deg,
    rgba(255, 253, 248, 0.08) 30%,
    rgba(255, 253, 248, 0.18) 50%,
    rgba(255, 253, 248, 0.08) 70%
  );
  background-size: 200% 100%;
  animation: skeleton-move 1.1s linear infinite;
  border-radius: 6px;
}
.vlog-skeleton--cover { flex: none; width: 168px; height: 95px; border-radius: 9px; }
.vlog-skeleton--line { height: 11px; width: 100%; }
.vlog-skeleton--short { width: 45%; }
@keyframes skeleton-move {
  from { background-position: 120% 0; }
  to   { background-position: -20% 0; }
}

.vlog-error {
  padding: 26px 0;
  text-align: center;
  font-size: 0.78rem;
  color: rgba(255, 253, 248, 0.8);
}
.vlog-error__btn {
  margin-top: 10px;
  padding: 6px 14px;
  border: 1px solid rgba(159, 232, 196, 0.6);
  border-radius: 9px;
  background: rgba(159, 232, 196, 0.16);
  color: #fffdf8;
  font-size: 0.74rem;
  cursor: pointer;
}
</style>
