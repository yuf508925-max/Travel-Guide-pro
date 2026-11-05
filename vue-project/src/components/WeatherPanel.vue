<!-- ====================================================================
  WeatherPanel —— 顶部「天气」按钮弹出的小窗口，显示未来 7 天预报
  数据来自后端 GET /api/weather?province=山东&city=青岛（server/routers/weather.py）。
  这个组件只管展示 + 交互：
    填省/市 → 回车或点查询 → 重新请求 → 渲染
  关闭方式：右上角 ×、点窗口外面、Esc、或者再点一次顶部按钮（父组件处理）
==================================================================== -->

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

// ------------------------------------------------------------------
// 后端返回的数据结构（只挑前端要用的字段声明）
// ------------------------------------------------------------------
interface WeatherDay {
  date: string
  weekday: string
  desc: string
  icon: string
  temp_max: number | null
  temp_min: number | null
  rain_prob: number | null
}

interface WeatherData {
  city: string
  region: string
  updated_at: string
  current: {
    temp: number | null
    desc: string
    icon: string
    wind: number | null
    humidity: number | null
  }
  days: WeatherDay[]
}

const props = withDefaults(
  defineProps<{
    // 上次查过的省 / 市，由父组件从 localStorage 读出来传进来
    initialProvince?: string
    initialCity?: string
  }>(),
  { initialProvince: '山东', initialCity: '青岛' }
)

const emit = defineEmits<{
  close: []
  // 查询成功后把（省, 市）回传给父组件保存，下次打开还是这里
  'update:place': [province: string, city: string]
}>()

// 天气图标：后端只给 key（sunny / rain / snow…），这里翻成 emoji。
// 用 emoji 是为了不额外引入图标库，系统自带彩色字形，一眼能认。
const ICONS: Record<string, string> = {
  sunny: '☀️',
  partly: '⛅',
  cloudy: '☁️',
  fog: '🌫️',
  drizzle: '🌦️',
  rain: '🌧️',
  snow: '🌨️',
  thunder: '⛈️',
}

function iconOf(key: string): string {
  return ICONS[key] ?? '🌡️'
}

// ------------------------------------------------------------------
// 状态：省 + 市两个输入框，市必填、省可空（用来区分同名城市）
// ------------------------------------------------------------------
const province = ref(props.initialProvince)
const city = ref(props.initialCity)
const data = ref<WeatherData | null>(null)
const loading = ref(false)
const error = ref('')

const canSearch = computed(() => !loading.value && city.value.trim().length > 0)

async function load() {
  const cityName = city.value.trim()
  if (!cityName) return

  loading.value = true
  error.value = ''

  const params = new URLSearchParams({ city: cityName, days: '7' })
  const provinceName = province.value.trim()
  if (provinceName) params.set('province', provinceName)

  try {
    const res = await fetch(`/api/weather?${params.toString()}`)
    // 后端出错时会给 { detail: "人话" }，优先用它，别给用户看 HTTP 500
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      throw new Error(
        (body && typeof body.detail === 'string' && body.detail) || `查询失败（HTTP ${res.status}）`
      )
    }
    const payload = (await res.json()) as WeatherData
    data.value = payload
    // 后端会把名字规整好（「北京市」→「北京」，省份以表里的为准），写回输入框
    city.value = payload.city
    province.value = payload.region
    emit('update:place', payload.region, payload.city)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '查询失败，稍后再试'
  } finally {
    loading.value = false
  }
}

function search() {
  if (!canSearch.value) return
  load()
}

// Esc 关闭：弹窗类界面基本都该有
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  load()
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
})

// 日期显示：2026-11-04 → 11/04
function shortDate(iso: string): string {
  return iso.slice(5).replace('-', '/')
}

// 更新时间：2026-11-04T17:20+08:00 → 17:20
function shortTime(iso: string): string {
  return iso.length >= 16 ? iso.slice(11, 16) : iso
}
</script>

<template>
  <div class="weather-layer">
    <!-- 透明遮罩：点窗口外面就关掉。不加深色背景，保持"小窗口"的轻量感 -->
    <div class="weather-backdrop" @click="emit('close')"></div>

    <div class="weather-pop" role="dialog" aria-label="未来天气">
      <!-- ---- 顶部：标题 + 省/市输入 + 关闭 ---- -->
      <header class="weather-head">
        <span class="weather-title">天气</span>

        <form class="weather-search" @submit.prevent="search">
          <input
            v-model="province"
            class="weather-input weather-input--province"
            type="text"
            maxlength="10"
            placeholder="省"
            aria-label="省份"
          />
          <input
            v-model="city"
            class="weather-input weather-input--city"
            type="text"
            maxlength="20"
            placeholder="市"
            aria-label="城市"
          />
          <button class="weather-go" type="submit" :disabled="!canSearch">查询</button>
        </form>

        <button class="weather-close" type="button" aria-label="关闭" @click="emit('close')">
          ×
        </button>
      </header>

      <!-- ---- 加载中 ---- -->
      <p v-if="loading" class="weather-status">正在查天气…</p>

      <!-- ---- 出错：把后端的 detail 原样显示 + 重试 ---- -->
      <div v-else-if="error" class="weather-status weather-status--error">
        <span>{{ error }}</span>
        <button class="weather-retry" type="button" @click="load">重试</button>
      </div>

      <!-- ---- 正常内容 ---- -->
      <template v-else-if="data">
        <!-- 当前天气 -->
        <div class="weather-now">
          <span class="weather-now__icon">{{ iconOf(data.current.icon) }}</span>
          <div class="weather-now__main">
            <p class="weather-now__temp">
              {{ data.current.temp ?? '--' }}<span>°C</span>
            </p>
            <!-- 先省后市：和顶部两个输入框的顺序保持一致 -->
            <p class="weather-now__place">
              <template v-if="data.region">{{ data.region }} · </template>{{ data.city }}
              · {{ data.current.desc }}
            </p>
          </div>
          <dl class="weather-meta">
            <div>
              <dt>风</dt>
              <dd>{{ data.current.wind ?? '--' }} km/h</dd>
            </div>
            <div>
              <dt>湿度</dt>
              <dd>{{ data.current.humidity ?? '--' }}%</dd>
            </div>
          </dl>
        </div>

        <!-- 未来 7 天 -->
        <ul class="weather-days">
          <li v-for="day in data.days" :key="day.date" class="weather-day">
            <span class="weather-day__name">{{ day.weekday }}</span>
            <span class="weather-day__date">{{ shortDate(day.date) }}</span>
            <span class="weather-day__icon" :title="day.desc">{{ iconOf(day.icon) }}</span>
            <span class="weather-day__temps">
              <b>{{ day.temp_max ?? '--' }}°</b>
              <i>{{ day.temp_min ?? '--' }}°</i>
            </span>
            <span class="weather-day__rain">💧{{ day.rain_prob ?? '--' }}%</span>
          </li>
        </ul>

        <p class="weather-foot">
          数据来源 Open-Meteo · 更新于 {{ shortTime(data.updated_at) }} · 10 分钟内不重复请求
        </p>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* 定位在顶部导航条下方（父组件 .chat-nav-wrap 是 relative） */
.weather-layer {
  position: absolute;
  top: calc(100% + 12px);
  left: 0;
  z-index: 60;
}

/* 透明遮罩：铺满视口，点任意空白处关闭 */
.weather-backdrop {
  position: fixed;
  inset: 0;
  z-index: 0;
}

/* ---- 小窗口本体 ---- */
.weather-pop {
  position: relative;              /* 盖在遮罩上面 */
  z-index: 1;
  width: min(560px, calc(100vw - 40px));
  padding: 14px 16px 12px;
  box-sizing: border-box;
  border: 1.5px solid rgba(255, 253, 248, 0.4);
  border-radius: 16px;
  background: rgba(12, 46, 46, 0.92);
  backdrop-filter: blur(14px);
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.38);
  color: #fffdf8;
  /* 弹出来一点点，和聊天气泡的风格呼应 */
  animation: weather-in 0.22s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes weather-in {
  from { opacity: 0; transform: translateY(-8px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

/* ---- 顶部 ---- */
.weather-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.weather-title {
  font-size: 1rem;
  font-weight: 500;
  letter-spacing: 0.04em;
}

.weather-search {
  margin-left: auto;
  display: flex;
  gap: 6px;
}
.weather-input {
  height: 30px;
  padding: 0 10px;
  box-sizing: border-box;
  border: 1px solid rgba(255, 253, 248, 0.35);
  border-radius: 15px;
  background: rgba(255, 253, 248, 0.1);
  color: #fffdf8;
  font-size: 0.86rem;
  font-family: inherit;
  outline: none;
  transition: border-color 0.2s, width 0.2s;
}
.weather-input--province { width: 74px; }
.weather-input--city { width: 86px; }
.weather-input::placeholder { color: rgba(255, 253, 248, 0.45); }
.weather-input:focus { border-color: rgba(255, 253, 248, 0.8); }

.weather-go {
  height: 30px;
  padding: 0 14px;
  border: none;
  border-radius: 15px;
  background: #fffdf8;
  color: #2f7d6e;
  font-size: 0.86rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: opacity 0.2s;
}
.weather-go:disabled { opacity: 0.5; cursor: not-allowed; }

.weather-close {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 253, 248, 0.85);
  font-size: 1.2rem;
  line-height: 1;
  cursor: pointer;
  transition: background 0.2s;
}
.weather-close:hover { background: rgba(255, 253, 248, 0.16); }

/* ---- 加载 / 出错 ---- */
.weather-status {
  margin: 16px 2px;
  font-size: 0.9rem;
  color: rgba(255, 253, 248, 0.75);
}
.weather-status--error {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #ffd9d0;
}
.weather-retry {
  padding: 4px 12px;
  border: 1px solid rgba(255, 253, 248, 0.45);
  border-radius: 12px;
  background: transparent;
  color: #fffdf8;
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
}

/* ---- 当前天气 ---- */
.weather-now {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 2px 14px;
}
.weather-now__icon { font-size: 2.2rem; line-height: 1; }
.weather-now__main { min-width: 0; }
.weather-now__temp {
  margin: 0;
  font-size: 1.9rem;
  font-weight: 500;
  line-height: 1.1;
}
.weather-now__temp span {
  margin-left: 2px;
  font-size: 0.85rem;
  font-weight: 400;
  opacity: 0.7;
}
.weather-now__place {
  margin: 4px 0 0;
  font-size: 0.82rem;
  color: rgba(255, 253, 248, 0.72);
}
.weather-meta {
  margin: 0 0 0 auto;
  display: flex;
  gap: 18px;
  text-align: right;
}
.weather-meta dt {
  font-size: 0.72rem;
  color: rgba(255, 253, 248, 0.5);
}
.weather-meta dd {
  margin: 2px 0 0;
  font-size: 0.84rem;
}

/* ---- 7 天 ---- */
.weather-days {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
}
.weather-day {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 8px 2px 7px;
  border-radius: 12px;
  background: rgba(255, 253, 248, 0.07);
  border: 1px solid rgba(255, 253, 248, 0.08);
}
/* 第一天（今天）稍微亮一点 */
.weather-day:first-child {
  background: rgba(255, 253, 248, 0.14);
  border-color: rgba(255, 253, 248, 0.22);
}
.weather-day__name { font-size: 0.78rem; }
.weather-day__date {
  font-size: 0.66rem;
  color: rgba(255, 253, 248, 0.55);
}
.weather-day__icon {
  font-size: 1.25rem;
  line-height: 1.4;
}
.weather-day__temps {
  display: flex;
  align-items: baseline;
  gap: 3px;
  font-size: 0.8rem;
}
.weather-day__temps b { font-weight: 500; }
.weather-day__temps i {
  font-style: normal;
  font-size: 0.72rem;
  color: rgba(255, 253, 248, 0.6);
}
.weather-day__rain {
  font-size: 0.66rem;
  color: rgba(255, 253, 248, 0.6);
}

.weather-foot {
  margin: 10px 2px 0;
  font-size: 0.68rem;
  color: rgba(255, 253, 248, 0.42);
}

/* ---- 窄屏：7 天横向滚动，别把窗口挤变形 ---- */
@media (max-width: 640px) {
  .weather-pop { padding: 12px; }
  .weather-input--province { width: 58px; }
  .weather-input--city { width: 66px; }
  .weather-days {
    display: flex;
    overflow-x: auto;
    padding-bottom: 4px;
  }
  .weather-day { flex: 0 0 64px; }
}

@media (prefers-reduced-motion: reduce) {
  .weather-pop { animation: none; }
}
</style>
