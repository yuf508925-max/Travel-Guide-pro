<!-- =====================================================================
     AdminView.vue —— 管理员专用后台（没有聊天界面）
     ---------------------------------------------------------------------
     三块内容：
       1. 用户反馈消息窗口（前台「设置 → 意见反馈」写进来的）
       2. 统计：网页访问量 / 高德地图调用量 / 接口调用量（折线 + 环形）
       3. 账号表：每个账号一行，点「调用明细」弹出该用户各接口的用量图
===================================================================== -->

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import LineChart from '../components/charts/LineChart.vue'
import BarChart from '../components/charts/BarChart.vue'
import DonutChart from '../components/charts/DonutChart.vue'
import { useAnnouncements } from '../composables/useAnnouncements'

const props = defineProps({
  username: { type: String, default: '' },
})

const emit = defineEmits(['logout'])

interface AdminUserRow {
  id: number
  username: string
  role: 'user' | 'admin'
  created_at: string | null
  providers: number
  routes: number
  calls: number
  feedback: number
  is_me: boolean
}

interface SeriesPoint {
  date: string
  count: number
}

interface Analytics {
  start: string
  end: string
  days: number
  visits: SeriesPoint[]
  amap: SeriesPoint[]
  weather: SeriesPoint[]
  api: SeriesPoint[]
  keys: { key: string; provider: string; model: string; total: number; data: number[]; is_tts?: boolean }[]
  by_kind: { kind: string; label: string; count: number }[]
  totals: {
    visits: number
    amap: number
    api: number
    visits_today: number
    amap_today: number
    weather: number
    weather_today: number
    feedback_new: number
  }
}

interface FeedbackRow {
  id: number
  username: string
  content: string
  status: 'new' | 'read'
  created_at: string
}

interface UsageData {
  user: { id: number; username: string; role: string }
  start: string
  end: string
  days: number
  total: number
  amap: number
  by_kind: { kind: string; label: string; count: number }[]
  by_day: SeriesPoint[]
  series: { kind: string; label: string; data: number[] }[]
  recent: { kind: string; detail: string; at: string }[]
}

const analytics = ref<Analytics | null>(null)

// 时间范围：近七天 / 一个月 / 一年 / 自定义
type RangeMode = '7' | '30' | '365' | 'custom'
const rangeMode = ref<RangeMode>('7')
const todayIso = new Date().toISOString().slice(0, 10)
const weekAgoIso = new Date(Date.now() - 6 * 86400000).toISOString().slice(0, 10)
const customStart = ref(weekAgoIso)
const customEnd = ref(todayIso)

const rangeOptions: { value: RangeMode; label: string }[] = [
  { value: '7', label: '近七天' },
  { value: '30', label: '一个月' },
  { value: '365', label: '一年' },
  { value: 'custom', label: '自定义' },
]
const users = ref<AdminUserRow[]>([])
const feedback = ref<FeedbackRow[]>([])
const keyword = ref('')
const loading = ref(true)
const errorText = ref('')
const toast = ref('')
const feedbackOpen = ref(false)

// 账号表分页：一页 10 个
const PAGE_SIZE = 10
const page = ref(1)
const pageCount = computed(() => Math.max(1, Math.ceil(users.value.length / PAGE_SIZE)))
const pagedUsers = computed(() =>
  users.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE),
)

function goPage(next: number) {
  page.value = Math.min(pageCount.value, Math.max(1, next))
}

// 调用明细弹窗
const usageOpen = ref(false)
const usageUser = ref<AdminUserRow | null>(null)
const usage = ref<UsageData | null>(null)
const usageLoading = ref(false)

let toastTimer: ReturnType<typeof setTimeout> | null = null
let searchTimer: ReturnType<typeof setTimeout> | null = null

const dayLabels = computed(() =>
  (analytics.value?.visits ?? []).map((p) => p.date.slice(5).replace('-', '/')),
)

const visitSeries = computed(() => [
  {
    name: '网页访问',
    color: '#7ee7cd',
    data: (analytics.value?.visits ?? []).map((p) => p.count),
  },
  {
    name: '高德调用',
    color: '#ffc478',
    data: (analytics.value?.amap ?? []).map((p) => p.count),
  },
])

// 三根线：天气 / 访问量 / 高德调用，勾哪个画哪个
const trendOptions = [
  { key: 'weather', name: '天气接口', color: '#c8a6ff' },
  { key: 'visits', name: '网页访问量', color: '#7ee7cd' },
  { key: 'amap', name: '高德调用', color: '#ffc478' },
] as const

const trendOn = ref<Record<string, boolean>>({ weather: true, visits: true, amap: true })

const trendSeries = computed(() =>
  trendOptions
    .filter((opt) => trendOn.value[opt.key])
    .map((opt) => ({
      name: opt.name,
      color: opt.color,
      data: ((analytics.value?.[opt.key] ?? []) as SeriesPoint[]).map((p) => p.count),
    })),
)

// 每个 Key + 模型一条线，同样可勾选
const KEY_COLORS = ['#7ee7cd', '#7fc3e8', '#ffc478', '#c8a6ff', '#ff9fa8', '#9ae6a0', '#f2d97f']
const keyOn = ref<Record<string, boolean>>({})
const keyMenuOpen = ref(false)
const keyQuery = ref('')

/** 按「厂商 + 模型名」过滤勾选面板里的条目，index 保留原始顺序用于配色 */
const filteredKeys = computed(() => {
  const q = keyQuery.value.trim().toLowerCase()
  return (analytics.value?.keys ?? [])
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => {
      if (!q) return true
      const kindWords = item.is_tts ? '语音 语音合成 tts' : '语言 语言模型 chat'
      return `${item.provider} ${item.model} ${kindWords}`.toLowerCase().includes(q)
    })
})

// ---------------------------------------------------------------------
// 页面切换：数据总览 / 模型库
// ---------------------------------------------------------------------
type AdminPage = 'dashboard' | 'models' | 'notice' | 'map'
const adminPage = ref<AdminPage>('dashboard')

interface ModelRow {
  id: number
  name: string
  vendor: string
  kind: 'chat' | 'tts'
  kind_label: string
  created_at: string
}

const models = ref<ModelRow[]>([])
const modelQuery = ref('')
const modelForm = ref<{ name: string; vendor: string; kind: 'chat' | 'tts' }>({
  name: '',
  vendor: '',
  kind: 'chat',
})
const modelSaving = ref(false)

async function loadModels() {
  models.value = await api<ModelRow[]>(
    `/api/admin/models?q=${encodeURIComponent(modelQuery.value.trim())}`,
  )
}

function switchPage(next: AdminPage) {
  adminPage.value = next
  if (next === 'models') void loadModels()
  if (next === 'notice') void loadNotices(true)
  if (next === 'map') void loadMapConfig()
}

async function addModel() {
  const name = modelForm.value.name.trim()
  if (!name) {
    say('模型名称不能为空')
    return
  }
  modelSaving.value = true
  try {
    await api<ModelRow>('/api/admin/models', {
      method: 'POST',
      body: JSON.stringify({
        name,
        vendor: modelForm.value.vendor.trim(),
        kind: modelForm.value.kind,
      }),
    })
    say(`已添加「${name}」`)
    modelForm.value = { name: '', vendor: '', kind: modelForm.value.kind }
    await Promise.all([loadModels(), loadAnalytics()])
  } catch (err) {
    say(err instanceof Error ? err.message : '添加失败')
  } finally {
    modelSaving.value = false
  }
}

async function removeModel(row: ModelRow) {
  if (!window.confirm(`确定从模型库删除「${row.name}」？`)) return
  try {
    await api(`/api/admin/models/${row.id}`, { method: 'DELETE' })
    say('已删除')
    await Promise.all([loadModels(), loadAnalytics()])
  } catch (err) {
    say(err instanceof Error ? err.message : '删除失败')
  }
}

const modelCounts = computed(() => ({
  chat: models.value.filter((m) => m.kind === 'chat').length,
  tts: models.value.filter((m) => m.kind === 'tts').length,
}))

let modelTimer: ReturnType<typeof setTimeout> | null = null
function onModelSearch() {
  if (modelTimer) clearTimeout(modelTimer)
  modelTimer = setTimeout(() => void loadModels(), 250)
}

// ---------------------------------------------------------------------
// 发布公告：写一条 → 所有登录用户在前台顶栏「公告」里看到
// ---------------------------------------------------------------------
const { notices, loadNotices, createNotice, updateNotice, deleteNotice } =
  useAnnouncements()
const noticeForm = ref<{ title: string; content: string; pinned: boolean }>({
  title: '',
  content: '',
  pinned: false,
})
const noticeSaving = ref(false)

async function publishNotice() {
  const title = noticeForm.value.title.trim()
  const content = noticeForm.value.content.trim()
  if (!title) {
    say('公告标题不能为空')
    return
  }
  noticeSaving.value = true
  try {
    await createNotice(title, content, noticeForm.value.pinned)
    say('公告已发布')
    noticeForm.value = { title: '', content: '', pinned: false }
  } catch (err) {
    say(err instanceof Error ? err.message : '发布失败')
  } finally {
    noticeSaving.value = false
  }
}

async function toggleNoticePin(item: { id: number; pinned: boolean }) {
  try {
    await updateNotice(item.id, { pinned: !item.pinned })
    say(item.pinned ? '已取消置顶' : '已置顶')
  } catch (err) {
    say(err instanceof Error ? err.message : '操作失败')
  }
}

async function removeNotice(item: { id: number; title: string }) {
  if (!window.confirm(`确定删除公告「${item.title}」？`)) return
  try {
    await deleteNotice(item.id)
    say('已删除')
  } catch (err) {
    say(err instanceof Error ? err.message : '删除失败')
  }
}

// ---------------------------------------------------------------------
// 地图 Key：高德「Web端 (JS API)」的 Key + 安全密钥，全局一份
// 前端所有用户通过 GET /api/map 读同一份；这里只有管理员能改。
// ---------------------------------------------------------------------
interface MapConfig {
  amap_key: string
  security_code: string
  updated_by: string
  updated_at: string
  configured: boolean
}

const mapConfig = ref<MapConfig>({
  amap_key: '',
  security_code: '',
  updated_by: '',
  updated_at: '',
  configured: false,
})
const mapSaving = ref(false)

async function loadMapConfig() {
  try {
    mapConfig.value = await api<MapConfig>('/api/admin/map')
  } catch (err) {
    say(err instanceof Error ? err.message : '读取地图配置失败')
  }
}

async function saveMapConfig() {
  const amapKey = mapConfig.value.amap_key.trim()
  if (!amapKey) {
    say('高德地图 Key 不能为空')
    return
  }
  mapSaving.value = true
  try {
    await api('/api/admin/map', {
      method: 'PUT',
      body: JSON.stringify({
        amap_key: amapKey,
        security_code: mapConfig.value.security_code.trim(),
      }),
    })
    say('地图 Key 已保存，所有用户刷新页面后生效')
    await loadMapConfig()
  } catch (err) {
    say(err instanceof Error ? err.message : '保存失败')
  } finally {
    mapSaving.value = false
  }
}

async function clearMapConfig() {
  if (!window.confirm('清空之后行程面板会用不了（前端会提示「管理员还没配置」），确定清空？')) return
  mapSaving.value = true
  try {
    await api('/api/admin/map', { method: 'DELETE' })
    say('已清空地图 Key')
    await loadMapConfig()
  } catch (err) {
    say(err instanceof Error ? err.message : '清空失败')
  } finally {
    mapSaving.value = false
  }
}

const selectedKeyCount = computed(
  () => (analytics.value?.keys ?? []).filter((k) => keyOn.value[k.key]).length,
)

function closeKeyMenuOnOutside(event: PointerEvent) {
  if (!keyMenuOpen.value) return
  const target = event.target as HTMLElement | null
  if (target?.closest('.pick')) return
  keyMenuOpen.value = false
}

watch(analytics, (value) => {
  if (!value) return
  const next: Record<string, boolean> = {}
  value.keys.forEach((k) => {
    // 没产生过调用的（模型库登记但还没用）默认不勾，避免一堆 0 线糊在一起
    next[k.key] = keyOn.value[k.key] ?? k.total > 0
  })
  keyOn.value = next
})

const keySeries = computed(() =>
  (analytics.value?.keys ?? [])
    .map((item, index) => ({
      name: `${item.provider} · ${item.model}`,
      color: KEY_COLORS[index % KEY_COLORS.length] ?? '#7ee7cd',
      data: item.data,
      key: item.key,
    }))
    .filter((item) => keyOn.value[item.key]),
)

const kindItems = computed(() =>
  (analytics.value?.by_kind ?? []).filter((k) => k.kind !== 'visit'),
)

const newFeedback = computed(() => feedback.value.filter((f) => f.status === 'new').length)

function say(message: string) {
  toast.value = message
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = ''), 2200)
}

// ---------------------------------------------------------------------
async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

  if (res.status === 401) {
    errorText.value = '登录已过期，请重新登录'
    throw new Error(errorText.value)
  }
  if (res.status === 403) {
    errorText.value = '当前账号不是管理员，进不了后台'
    throw new Error(errorText.value)
  }
  if (!res.ok) {
    const data: unknown = await res.json().catch(() => null)
    const detail =
      data && typeof data === 'object' && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : `HTTP ${res.status}`
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

async function loadAnalytics() {
  const params = new URLSearchParams()
  if (rangeMode.value === 'custom') {
    if (customStart.value && customEnd.value) {
      params.set('start', customStart.value)
      params.set('end', customEnd.value)
    } else {
      params.set('days', '7')
    }
  } else {
    params.set('days', rangeMode.value)
  }

  analytics.value = await api<Analytics>(`/api/admin/analytics?${params.toString()}`)
}

async function pickRange(mode: RangeMode) {
  rangeMode.value = mode
  if (mode !== 'custom') {
    try {
      await loadAnalytics()
    } catch (err) {
      say(err instanceof Error ? err.message : '加载失败')
    }
  }
}

async function applyCustomRange() {
  if (!customStart.value || !customEnd.value) return say('选一下开始和结束日期')
  if (customEnd.value < customStart.value) return say('结束日期不能早于开始日期')
  try {
    await loadAnalytics()
    say('已切换区间')
  } catch (err) {
    say(err instanceof Error ? err.message : '加载失败')
  }
}

async function loadUsers() {
  const data = await api<{ users: AdminUserRow[] }>(
    `/api/admin/users?q=${encodeURIComponent(keyword.value.trim())}`,
  )
  users.value = data.users
  page.value = 1
}

async function loadFeedback() {
  const data = await api<{ feedback: FeedbackRow[] }>('/api/admin/feedback')
  feedback.value = data.feedback
}

async function refresh() {
  loading.value = true
  errorText.value = ''
  try {
    await Promise.all([loadAnalytics(), loadUsers(), loadFeedback(), loadModels()])
  } catch (err) {
    errorText.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    loadUsers().catch((err) => say(err instanceof Error ? err.message : '搜索失败'))
  }, 260)
}

// ---- 反馈 ----
async function toggleFeedback(item: FeedbackRow) {
  try {
    await api(`/api/admin/feedback/${item.id}`, { method: 'PATCH' })
    await loadFeedback()
  } catch (err) {
    say(err instanceof Error ? err.message : '操作失败')
  }
}

async function removeFeedback(item: FeedbackRow) {
  if (!window.confirm('删除这条反馈？')) return
  try {
    await api(`/api/admin/feedback/${item.id}`, { method: 'DELETE' })
    await loadFeedback()
    say('已删除')
  } catch (err) {
    say(err instanceof Error ? err.message : '删除失败')
  }
}

// ---- 用户 ----
// 弹窗里的时间范围，和总览用同一套选项
const usageRange = ref<RangeMode>('7')
const usageCustomStart = ref(weekAgoIso)
const usageCustomEnd = ref(todayIso)
const usageKindOn = ref<Record<string, boolean>>({})
const usagePickOpen = ref(false)
const usageQuery = ref('')

// 每类接口固定一个颜色，勾选变化时柱子颜色不会跟着跳
const KIND_COLORS = [
  '#7ee7cd',
  '#7fc3e8',
  '#ffc478',
  '#c8a6ff',
  '#ff9fa8',
  '#9ae6a0',
  '#f2d06b',
  '#8fd9c1',
]

async function loadUsage() {
  const row = usageUser.value
  if (!row) return
  usageLoading.value = true
  usageKindOn.value = {}
  try {
    const query =
      usageRange.value === 'custom'
        ? `?start=${usageCustomStart.value}&end=${usageCustomEnd.value}`
        : `?days=${usageRange.value}`
    const data = await api<UsageData>(`/api/admin/users/${row.id}/usage${query}`)
    usage.value = data
    // 默认全画；数据里没出现过的类别不用记
    const next: Record<string, boolean> = {}
    data.by_kind.forEach((k) => {
      next[k.kind] = true
    })
    usageKindOn.value = next
  } catch (err) {
    say(err instanceof Error ? err.message : '加载失败')
  } finally {
    usageLoading.value = false
  }
}

async function pickUsageRange(mode: RangeMode) {
  usageRange.value = mode
  if (mode !== 'custom') await loadUsage()
}

async function openUsage(row: AdminUserRow) {
  usageUser.value = row
  usageOpen.value = true
  usageLoading.value = true
  usage.value = null
  usageRange.value = '7'
  await loadUsage()
}

function toggleUsageKind(kind: string) {
  usageKindOn.value = { ...usageKindOn.value, [kind]: !usageKindOn.value[kind] }
}

function closeUsage() {
  usageOpen.value = false
  usage.value = null
  usageUser.value = null
}

const usageKinds = computed(() =>
  (usage.value?.by_kind ?? []).map((k, i) => {
    const voice = k.kind.startsWith('tts')
    const chat = k.kind === 'chat_key'
    return {
      ...k,
      color: KIND_COLORS[i % KIND_COLORS.length],
      tag: voice ? '语音' : chat ? '语言' : '接口',
      tagClass: voice ? 'pick__kind--tts' : chat ? 'pick__kind--chat' : 'pick__kind--api',
    }
  }),
)

const usageBars = computed(() =>
  usageKinds.value.filter((k) => usageKindOn.value[k.kind] !== false),
)

const usageSeries = computed(() => {
  const map = new Map(usageKinds.value.map((k) => [k.kind, k.color]))
  return (usage.value?.series ?? [])
    .filter((s) => usageKindOn.value[s.kind] !== false)
    .map((s) => ({
      name: s.label,
      color: map.get(s.kind) ?? '#7ee7cd',
      data: s.data,
    }))
})

const usageMax = computed(() =>
  Math.max(1, ...usageKinds.value.map((k) => k.count)),
)

const filteredUsageKinds = computed(() => {
  const q = usageQuery.value.trim().toLowerCase()
  if (!q) return usageKinds.value
  return usageKinds.value.filter(
    (k) => k.label.toLowerCase().includes(q) || k.kind.toLowerCase().includes(q),
  )
})

function toggleUsagePick() {
  usagePickOpen.value = !usagePickOpen.value
  if (usagePickOpen.value) usageQuery.value = ''
}

async function toggleRole(row: AdminUserRow) {
  const next = row.role === 'admin' ? 'user' : 'admin'
  const verb = next === 'admin' ? '设为管理员' : '取消管理员'
  if (!window.confirm(`确定把「${row.username}」${verb}？`)) return

  try {
    await api(`/api/admin/users/${row.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ role: next }),
    })
    await refresh()
    say(`${verb}成功`)
  } catch (err) {
    say(err instanceof Error ? err.message : '修改失败')
  }
}

async function resetPassword(row: AdminUserRow) {
  const pwd = window.prompt(`给「${row.username}」设置新密码（至少 6 位）`, '')
  if (pwd === null) return
  if (pwd.length < 6) return say('密码至少要 6 位')

  try {
    await api(`/api/admin/users/${row.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ password: pwd }),
    })
    say('密码已重置')
  } catch (err) {
    say(err instanceof Error ? err.message : '重置失败')
  }
}

async function removeUser(row: AdminUserRow) {
  if (!window.confirm(`删除「${row.username}」？Key、行程、登录会话都会一起删掉。`)) return
  try {
    await api(`/api/admin/users/${row.id}`, { method: 'DELETE' })
    await refresh()
    say('已删除')
  } catch (err) {
    say(err instanceof Error ? err.message : '删除失败')
  }
}

const KIND_LABELS: Record<string, string> = {
  visit: '网页访问',
  amap: '高德地图',
  chat: 'AI 对话',
  tts: '语音合成',
  trains: '动车班次',
  weather: '天气查询',
  routes: '行程记录',
  providers: '模型 Key',
  map: '地图配置',
  auth: '登录注册',
  feedback: '意见反馈',
  poster: '旅行一图流',
  trip: '行程规划',
  other: '其它接口',
}

function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind
}

function shortTime(value: string | null): string {
  if (!value) return '—'
  const iso = value.includes('T') ? value : value.replace(' ', 'T') + 'Z'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function relative(value: string): string {
  const iso = value.includes('T') ? value : value.replace(' ', 'T') + 'Z'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return value
  const diff = Math.max(0, Date.now() - then)
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}

function closeOnEsc(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  if (usageOpen.value) closeUsage()
  else if (feedbackOpen.value) feedbackOpen.value = false
}

function closeFeedbackOnOutside(event: PointerEvent) {
  if (!feedbackOpen.value) return
  const target = event.target as HTMLElement | null
  if (!target) return
  if (target.closest('.admin-pop') || target.closest('.admin-ghost--msg')) return
  feedbackOpen.value = false
}

onMounted(() => {
  refresh()
  window.addEventListener('keydown', closeOnEsc)
  document.addEventListener('pointerdown', closeFeedbackOnOutside)
  document.addEventListener('pointerdown', closeKeyMenuOnOutside)
})

onBeforeUnmount(() => {
  if (toastTimer) clearTimeout(toastTimer)
  if (searchTimer) clearTimeout(searchTimer)
  window.removeEventListener('keydown', closeOnEsc)
  document.removeEventListener('pointerdown', closeFeedbackOnOutside)
  document.removeEventListener('pointerdown', closeKeyMenuOnOutside)
})
</script>

<template>
  <div class="admin">
    <!-- 顶栏 -->
    <header class="admin-top">
      <div class="admin-brand">
        <span class="admin-title">后台管理</span>
        <span class="admin-tag">ADMIN</span>
        <span v-if="newFeedback" class="admin-dot">{{ newFeedback }} 条新反馈</span>

        <nav class="admin-tabs">
          <button
            class="admin-tab"
            :class="{ 'admin-tab--on': adminPage === 'dashboard' }"
            @click="switchPage('dashboard')"
          >
            数据总览
          </button>
          <button
            class="admin-tab"
            :class="{ 'admin-tab--on': adminPage === 'models' }"
            @click="switchPage('models')"
          >
            模型库
          </button>
          <button
            class="admin-tab"
            :class="{ 'admin-tab--on': adminPage === 'notice' }"
            @click="switchPage('notice')"
          >
            发布公告
          </button>
          <button
            class="admin-tab"
            :class="{ 'admin-tab--on': adminPage === 'map' }"
            @click="switchPage('map')"
          >
            地图 Key
          </button>
        </nav>
      </div>

      <div class="admin-top__right">
        <span class="admin-me">{{ props.username }}</span>

        <!-- 用户反馈：点开是浮层，位置在 admin 和「刷新」之间 -->
        <button
          class="admin-ghost admin-ghost--msg"
          :class="{ 'is-open': feedbackOpen }"
          @click="feedbackOpen = !feedbackOpen"
        >
          用户反馈
          <span v-if="newFeedback" class="admin-count">{{ newFeedback }}</span>
        </button>

        <button class="admin-ghost" :disabled="loading" @click="refresh">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
        <button class="admin-back" @click="emit('logout')">退出登录</button>
      </div>
    </header>

        <div v-if="feedbackOpen" class="admin-pop">
          <div class="admin-panel__head">
            <h2>
              用户反馈
              <span v-if="newFeedback" class="admin-badge">{{ newFeedback }} 条未读</span>
            </h2>
          </div>

          <div class="admin-feedback__list">
            <article
              v-for="item in feedback"
              :key="item.id"
              class="msg"
              :class="{ 'msg--new': item.status === 'new' }"
            >
              <div class="msg__head">
                <span class="msg__user">{{ item.username }}</span>
                <span class="msg__time">{{ relative(item.created_at) }}</span>
                <span v-if="item.status === 'new'" class="msg__new">未读</span>
                <span class="msg__ops">
                  <button class="admin-op" @click="toggleFeedback(item)">
                    {{ item.status === 'new' ? '标为已读' : '标为未读' }}
                  </button>
                  <button class="admin-op admin-op--danger" @click="removeFeedback(item)">删除</button>
                </span>
              </div>
              <p class="msg__text">{{ item.content }}</p>
            </article>

            <p v-if="!feedback.length" class="admin-empty">
              还没有收到反馈。
            </p>
          </div>
        </div>


    <main class="admin-body">
      <section v-if="errorText" class="admin-denied">
        <h2>进不去</h2>
        <p>{{ errorText }}</p>
        <button class="admin-back" @click="emit('logout')">退出登录</button>
      </section>

      <template v-else-if="adminPage === 'dashboard'">
        <!-- ② 统计数字 -->
        <section class="admin-cards">
          <article class="admin-card">
            <span class="admin-card__label">网页访问量</span>
            <strong class="admin-card__value">{{ analytics?.totals.visits ?? '—' }}</strong>
            <span class="admin-card__hint">今日 {{ analytics?.totals.visits_today ?? 0 }} 次</span>
          </article>
          <article class="admin-card">
            <span class="admin-card__label">高德地图调用</span>
            <strong class="admin-card__value">{{ analytics?.totals.amap ?? '—' }}</strong>
            <span class="admin-card__hint">今日 {{ analytics?.totals.amap_today ?? 0 }} 次</span>
          </article>
          <article class="admin-card">
            <span class="admin-card__label">天气接口调用量</span>
            <strong class="admin-card__value">{{ analytics?.totals.weather ?? '—' }}</strong>
            <span class="admin-card__hint">今日 {{ analytics?.totals.weather_today ?? 0 }} 次</span>
          </article>
          <article class="admin-card">
            <span class="admin-card__label">账号总数</span>
            <strong class="admin-card__value">{{ users.length }}</strong>
            <span class="admin-card__hint">其中管理员 {{ users.filter((u) => u.role === 'admin').length }}</span>
          </article>
        </section>

        <!-- ③ 图表 -->
        <section class="admin-charts">
          <!-- 左：天气 / 访问量 / 高德（可勾选） -->
          <article class="admin-panel admin-panel--chart">
            <div class="admin-panel__head admin-panel__head--range">
              <h2>天气 / 访问量 / 高德调用</h2>
          <div class="range-inline">
            <button
              v-for="opt in rangeOptions"
              :key="opt.value"
              class="range-btn"
              :class="{ 'range-btn--on': rangeMode === opt.value }"
              @click="pickRange(opt.value)"
            >
              {{ opt.label }}
            </button>
            </div>

          <div v-if="rangeMode === 'custom'" class="range-inline__custom">
            <input v-model="customStart" type="date" class="range-date" />
            <span class="range-dash">—</span>
            <input v-model="customEnd" type="date" class="range-date" />
            <button class="admin-op" @click="applyCustomRange">查询</button>
            <span class="range-inline__hint">
              {{ analytics ? `${analytics.start} ~ ${analytics.end}` : '' }}
            </span>
          </div>
            </div>

            <div class="chips">
              <button
                v-for="opt in trendOptions"
                :key="opt.key"
                class="chip"
                :class="{ 'chip--on': trendOn[opt.key] }"
                @click="trendOn[opt.key] = !trendOn[opt.key]"
              >
                <i :style="{ background: opt.color }" />
                {{ opt.name }}
              </button>
            </div>

            <LineChart :labels="dayLabels" :series="trendSeries" :height="150" :show-legend="false" />
          </article>

          <!-- 右上：每个 Key / 模型的用量（下拉多选） -->
          <article class="admin-panel admin-panel--chart">
            <div class="admin-panel__head">
              <h2>API Key 用量</h2>
            </div>

            <div v-if="analytics?.keys.length" class="pick">
              <button
                type="button"
                class="pick__btn"
                @click="(keyMenuOpen = !keyMenuOpen), (keyQuery = '')"
              >
                模型用量
                <span class="pick__count">{{ selectedKeyCount }}/{{ analytics.keys.length }}</span>
                <span class="pick__caret">▾</span>
              </button>

              <div v-if="keyMenuOpen" class="pick__menu">
                <input
                  v-model="keyQuery"
                  class="pick__search"
                  placeholder="搜模型 / 厂商…"
                  maxlength="40"
                />
                <p class="pick__hint">
                  勾选要画的模型（含语音 TTS）· 共 {{ filteredKeys.length }} 条
                </p>
                <label v-for="{ item, index } in filteredKeys" :key="item.key" class="pick__row">
                  <input v-model="keyOn[item.key]" type="checkbox" />
                  <i :style="{ background: KEY_COLORS[index % KEY_COLORS.length] }" />
                  <span class="pick__kind" :class="item.is_tts ? 'pick__kind--tts' : 'pick__kind--chat'">
                    {{ item.is_tts ? '语音' : '语言' }}
                  </span>
                  <span class="pick__name">{{ item.provider }} · {{ item.model }}</span>
                  <b>{{ item.total }}</b>
                </label>

                <p v-if="!filteredKeys.length" class="pick__empty">没有匹配的模型</p>
              </div>
            </div>
            <p v-else class="admin-empty">还没有用任何 Key 聊过天。</p>

            <LineChart :labels="dayLabels" :series="keySeries" :height="150" :show-legend="false" />
          </article>

          <!-- 右：各接口调用量 -->
          <article class="admin-panel">
            <div class="admin-panel__head">
              <h2>各接口调用量</h2>
            </div>
            <BarChart :items="kindItems" />
          </article>

          <!-- 右下：调用构成 -->
          <article class="admin-panel">
            <div class="admin-panel__head">
              <h2>调用构成</h2>
            </div>
            <DonutChart :items="kindItems" :size="122" center-label="总调用" />
          </article>
        </section>

        <!-- ④ 账号表 -->
        <section class="admin-panel">
          <div class="admin-panel__head">
            <h2>账号列表</h2>
            <div class="admin-tools">
              <input
                v-model="keyword"
                class="admin-search"
                placeholder="搜用户名…"
                maxlength="64"
                @input="onSearch"
                @keyup.enter="loadUsers()"
              />
            </div>
          </div>

          <div class="admin-table-wrap">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>用户名</th>
                  <th>角色</th>
                  <th class="num">Key</th>
                  <th class="num">行程</th>
                  <th class="num">调用量</th>
                  <th>注册时间</th>
                  <th class="ops">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in pagedUsers" :key="row.id" :class="{ 'is-me': row.is_me }">
                  <td>
                    <span class="admin-name">{{ row.username }}</span>
                    <span v-if="row.is_me" class="admin-badge">你</span>
                  </td>
                  <td>
                    <span class="admin-role" :class="`admin-role--${row.role}`">
                      {{ row.role === 'admin' ? '管理员' : '普通用户' }}
                    </span>
                  </td>
                  <td class="num">{{ row.providers }}</td>
                  <td class="num">{{ row.routes }}</td>
                  <td class="num">
                    <button class="admin-calls" @click="openUsage(row)">{{ row.calls }}</button>
                  </td>
                  <td class="time">{{ shortTime(row.created_at) }}</td>
                  <td class="ops">
                    <button class="admin-op" @click="openUsage(row)">调用明细</button>
                    <button
                      class="admin-op"
                      :disabled="row.is_me"
                      :title="row.is_me ? '不能改自己的角色' : ''"
                      @click="toggleRole(row)"
                    >
                      {{ row.role === 'admin' ? '取消管理员' : '设为管理员' }}
                    </button>
                    <button class="admin-op" @click="resetPassword(row)">重置密码</button>
                    <button
                      class="admin-op admin-op--danger"
                      :disabled="row.is_me"
                      :title="row.is_me ? '不能删自己' : ''"
                      @click="removeUser(row)"
                    >
                      删除
                    </button>
                  </td>
                </tr>
                <tr v-if="!users.length">
                  <td class="empty" colspan="7">没有匹配的账号</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="pager">
            <span class="pager__info">
              共 {{ users.length }} 个账号 · 第 {{ page }} / {{ pageCount }} 页
            </span>
            <button class="admin-op" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
            <button class="admin-op" :disabled="page >= pageCount" @click="goPage(page + 1)">下一页</button>
          </div>

        </section>
      </template>

      <!-- 模型库：一页放模型清单，带搜索 / 新增 / 删除 -->
      <template v-else-if="adminPage === 'models'">
        <section class="admin-panel admin-models">
          <div class="admin-panel__head">
            <h2>
              模型库
              <span class="admin-badge">
                语言模型 {{ modelCounts.chat }} · 语音合成 {{ modelCounts.tts }}
              </span>
            </h2>
            <div class="admin-tools">
              <input
                v-model="modelQuery"
                class="admin-search"
                placeholder="搜模型名 / 厂商…"
                maxlength="40"
                @input="onModelSearch"
                @keyup.enter="loadModels()"
              />
            </div>
          </div>

          <form class="model-add" @submit.prevent="addModel">
            <input v-model="modelForm.name" class="admin-search" placeholder="模型名称，如 GPT-4o" maxlength="60" />
            <input v-model="modelForm.vendor" class="admin-search" placeholder="厂商（可空）" maxlength="40" />
            <select v-model="modelForm.kind" class="model-select">
              <option value="chat">语言模型</option>
              <option value="tts">语音合成模型</option>
            </select>
            <button class="admin-op admin-op--primary" type="submit" :disabled="modelSaving">
              {{ modelSaving ? '添加中…' : '添加' }}
            </button>
          </form>

          <div class="admin-table-wrap">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>模型名称</th>
                  <th>厂商</th>
                  <th>类型</th>
                  <th>添加时间</th>
                  <th class="ops">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in models" :key="row.id">
                  <td><span class="admin-name">{{ row.name }}</span></td>
                  <td>{{ row.vendor || '—' }}</td>
                  <td>
                    <span class="model-kind" :class="`model-kind--${row.kind}`">
                      {{ row.kind_label }}
                    </span>
                  </td>
                  <td class="time">{{ shortTime(row.created_at) }}</td>
                  <td class="ops">
                    <button class="admin-op admin-op--danger" @click="removeModel(row)">删除</button>
                  </td>
                </tr>
                <tr v-if="!models.length">
                  <td class="empty" colspan="5">没有匹配的模型</td>
                </tr>
              </tbody>
            </table>
          </div>

          <p class="admin-empty">
            共 {{ models.length }} 条。模型库只做「清单 + 类型」管理，不参与计费；用户自己的 Key 用的模型名也可以加进来。
          </p>
        </section>
      </template>

      <!-- 发布公告：写一条，所有登录用户在前台顶栏「公告」里看到 -->
      <template v-else-if="adminPage === 'notice'">
        <section class="admin-panel admin-notice">
          <div class="admin-panel__head">
            <h2>
              发布公告
              <span class="admin-badge">已发 {{ notices.length }} 条</span>
            </h2>
          </div>

          <form class="notice-form" @submit.prevent="publishNotice">
            <input
              v-model="noticeForm.title"
              class="admin-search notice-form__title"
              placeholder="公告标题，比如 今晚 23:00 维护"
              maxlength="60"
            />
            <textarea
              v-model="noticeForm.content"
              class="notice-form__text"
              placeholder="正文（可空）：说明一下改了什么、要注意什么…"
              maxlength="4000"
              rows="5"
            ></textarea>
            <div class="notice-form__foot">
              <label class="notice-form__pin">
                <input v-model="noticeForm.pinned" type="checkbox" />
                <span>置顶（排在最前面）</span>
              </label>
              <button class="admin-op admin-op--primary" type="submit" :disabled="noticeSaving">
                {{ noticeSaving ? '发布中…' : '发布公告' }}
              </button>
            </div>
          </form>

          <div class="admin-table-wrap">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>标题</th>
                  <th>正文</th>
                  <th>发布人</th>
                  <th>时间</th>
                  <th class="ops">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in notices" :key="row.id">
                  <td>
                    <span v-if="row.pinned" class="notice-tag">置顶</span>
                    <span class="admin-name">{{ row.title }}</span>
                  </td>
                  <td class="notice-cell">
                    {{ row.content ? (row.content.length > 40 ? row.content.slice(0, 40) + '…' : row.content) : '—' }}
                  </td>
                  <td>{{ row.publisher || '—' }}</td>
                  <td class="time">{{ shortTime(row.created_at) }}</td>
                  <td class="ops">
                    <button class="admin-op" @click="toggleNoticePin(row)">
                      {{ row.pinned ? '取消置顶' : '置顶' }}
                    </button>
                    <button class="admin-op admin-op--danger" @click="removeNotice(row)">删除</button>
                  </td>
                </tr>
                <tr v-if="!notices.length">
                  <td class="empty" colspan="5">还没有发过公告</td>
                </tr>
              </tbody>
            </table>
          </div>

          <p class="admin-empty">
            公告对所有登录用户可见；前台顶栏「公告」里按「置顶 → 最新」排。已读状态记在各自浏览器里，不用你管。
          </p>
        </section>
      </template>

      <!-- 地图 Key：高德「Web端 (JS API)」的 Key + 安全密钥，全局一份 -->
      <template v-else>
        <section class="admin-panel admin-map">
          <div class="admin-panel__head">
            <h2>
              高德地图 Key
              <span class="admin-badge" :class="{ 'admin-badge--warn': !mapConfig.configured }">
                {{ mapConfig.configured ? '已配置' : '未配置' }}
              </span>
            </h2>
          </div>

          <form class="map-form" @submit.prevent="saveMapConfig">
            <label class="map-form__row">
              <span class="map-form__label">Key</span>
              <input
                v-model="mapConfig.amap_key"
                class="admin-search map-form__input"
                placeholder="高德控制台 → 应用管理 → 我的应用 → Web端(JS API) 的 Key"
                maxlength="128"
                autocomplete="off"
              />
            </label>

            <label class="map-form__row">
              <span class="map-form__label">安全密钥</span>
              <input
                v-model="mapConfig.security_code"
                class="admin-search map-form__input"
                placeholder="同一应用的安全密钥 securityJsCode（2021-12-02 之后申请的 Key 必须带）"
                maxlength="128"
                autocomplete="off"
              />
            </label>

            <div class="map-form__foot">
              <button class="admin-op admin-op--primary" type="submit" :disabled="mapSaving">
                {{ mapSaving ? '保存中…' : '保存' }}
              </button>
              <button
                class="admin-op admin-op--danger"
                type="button"
                :disabled="mapSaving || !mapConfig.configured"
                @click="clearMapConfig"
              >
                清空
              </button>
              <span v-if="mapConfig.updated_at" class="map-form__meta">
                最近修改：{{ mapConfig.updated_by || '—' }} · {{ shortTime(mapConfig.updated_at) }}
              </span>
            </div>
          </form>

          <p class="admin-empty">
            这份 Key 全站共用：所有登录用户通过 <code>GET /api/map</code> 读到同一份，用来加载高德 JS API（行程规划的地图、路线、地点搜索）。
            改完不用重启后端，前端刷新页面即可生效。<br />
            注意 Key 类型必须是 <strong>Web端(JS API)</strong>，并在高德控制台把本站域名加进「域名白名单」；换成「Web服务」类型的 Key 会报 <code>INVALID_USER_SCODE</code>。
          </p>
        </section>
      </template>
    </main>

    <!-- ⑤ 用户用量弹窗 -->
    <transition name="fade">
      <div v-if="usageOpen" class="modal" @click.self="closeUsage">
        <div class="modal__card">
          <header class="modal__head">
            <h3>
              调用明细
              <span class="modal__user">{{ usageUser?.username }}</span>
            </h3>
            <button class="modal__close" @click="closeUsage">×</button>
          </header>

          <div v-if="usageLoading" class="modal__loading">加载中…</div>

          <template v-else-if="usage">
            <div class="modal__stats">
              <div>
                <span>总调用</span>
                <strong>{{ usage.total }}</strong>
              </div>
              <div>
                <span>高德地图</span>
                <strong>{{ usage.amap }}</strong>
              </div>
              <div>
                <span>用到的接口</span>
                <strong>{{ usage.by_kind.length }}</strong>
              </div>
            </div>

            <div class="modal__range">
              <button
                v-for="opt in rangeOptions"
                :key="opt.value"
                type="button"
                class="modal__range-btn"
                :class="{ 'modal__range-btn--on': usageRange === opt.value }"
                @click="pickUsageRange(opt.value)"
              >
                {{ opt.label }}
              </button>

              <template v-if="usageRange === 'custom'">
                <input v-model="usageCustomStart" class="modal__date" type="date" />
                <span class="modal__dash">—</span>
                <input v-model="usageCustomEnd" class="modal__date" type="date" />
                <button type="button" class="modal__range-btn" @click="loadUsage()">查询</button>
              </template>

              <span class="modal__range-hint">{{ usage.start }} ~ {{ usage.end }}</span>
            </div>

            <div class="modal__charts">
              <div>
                <h4>各接口调用量</h4>

                <ul class="usage-bars">
                  <li
                    v-for="k in usageKinds"
                    :key="k.kind"
                    :class="{ 'usage-bars__row--off': usageKindOn[k.kind] === false }"
                    @click="toggleUsageKind(k.kind)"
                  >
                    <i class="usage-bars__dot" :style="{ background: k.color }" />
                    <span class="pick__kind" :class="k.tagClass">{{ k.tag }}</span>
                    <span class="usage-bars__name">{{ k.label }}</span>
                    <span class="usage-bars__track">
                      <span
                        class="usage-bars__fill"
                        :style="{
                          width: `${Math.max(2, (k.count / usageMax) * 100)}%`,
                          background: `linear-gradient(90deg, ${k.color}55, ${k.color})`,
                        }"
                      />
                    </span>
                    <b class="usage-bars__count">{{ k.count }}</b>
                  </li>
                </ul>
              </div>
              <div>
                <h4>每天调用量</h4>
                <LineChart
                  :labels="usage.by_day.map((p) => p.date.slice(5).replace('-', '/'))"
                  :series="usageSeries"
                  :height="150"
                  :show-legend="false"
                />
                <p v-if="!usageSeries.length" class="usage-empty">左侧至少勾一个接口</p>
              </div>
            </div>

            <div class="modal__recent">
              <h4>最近记录</h4>
              <ul>
                <li v-for="(item, index) in usage.recent" :key="index">
                  <span class="modal__kind">{{ kindLabel(item.kind) }}</span>
                  <span class="modal__detail">{{ item.detail }}</span>
                  <span class="modal__at">{{ shortTime(item.at) }}</span>
                </li>
                <li v-if="!usage.recent.length" class="modal__empty">这个账号还没有调用记录</li>
              </ul>
            </div>
          </template>
        </div>
      </div>
    </transition>

    <transition name="fade">
      <div v-if="toast" class="admin-toast">{{ toast }}</div>
    </transition>
  </div>
</template>

<style scoped>
.admin {
  position: relative;
  z-index: 5;
  min-height: 100vh;
  padding: clamp(14px, 2vw, 24px);
  color: #e8fbf7;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ---- 顶栏 ---- */
.admin-top {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 18px;
  border-radius: 16px;
  background: rgba(12, 41, 48, 0.84);
  border: 1px solid rgba(126, 231, 205, 0.28);
  backdrop-filter: blur(8px);
}

.admin-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.admin-title {
  font-size: 1.08rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.admin-tag {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(126, 231, 205, 0.16);
  border: 1px solid rgba(126, 231, 205, 0.5);
  color: #9ff0dc;
  font-size: 0.64rem;
  letter-spacing: 0.12em;
}

.admin-dot {
  padding: 2px 9px;
  border-radius: 999px;
  background: rgba(255, 160, 122, 0.18);
  border: 1px solid rgba(255, 160, 122, 0.55);
  color: #ffc4a8;
  font-size: 0.7rem;
}

.admin-top__right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.admin-me {
  font-size: 0.85rem;
  color: #cdeee7;
}

.admin-back,
.admin-ghost {
  padding: 6px 13px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.26);
  background: rgba(255, 255, 255, 0.08);
  color: #eaf9f5;
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.18s, border-color 0.18s;
}

.admin-back:hover,
.admin-ghost:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(255, 255, 255, 0.5);
}

.admin-ghost:disabled {
  opacity: 0.55;
  cursor: default;
}

/* ---- 主体 ---- */
.admin-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
}

.admin-panel {
  padding: 14px 16px 12px;
  border-radius: 16px;
  background: rgba(12, 41, 48, 0.8);
  border: 1px solid rgba(126, 231, 205, 0.22);
}

.admin-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.admin-panel h2 {
  margin: 0;
  font-size: 0.94rem;
  font-weight: 600;
  color: #d8f7ef;
  display: flex;
  align-items: center;
  gap: 8px;
}

.admin-hint {
  font-size: 0.72rem;
  color: #7fa8a3;
}

/* ---- 反馈 ---- */
.admin-feedback__list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 10px;
  max-height: 218px;
  overflow: auto;
  padding-right: 2px;
}

.msg {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(7, 30, 34, 0.65);
  border: 1px solid rgba(126, 231, 205, 0.16);
}

.msg--new {
  border-color: rgba(255, 196, 120, 0.55);
  background: rgba(52, 38, 20, 0.35);
}

.msg__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.74rem;
  color: #9fc9c2;
}

.msg__user {
  color: #d9f7ef;
  font-weight: 600;
}

.msg__new {
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(255, 196, 120, 0.2);
  color: #ffd79b;
  font-size: 0.66rem;
}

.msg__ops {
  margin-left: auto;
  display: flex;
  gap: 6px;
}

.msg__text {
  margin: 6px 0 0;
  font-size: 0.82rem;
  line-height: 1.55;
  color: #cfeae4;
  word-break: break-word;
}

.admin-empty {
  margin: 8px 2px;
  font-size: 0.8rem;
  color: #7fa8a3;
}

/* ---- 用户反馈浮层 ---- */
.admin-ghost--msg {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.admin-ghost--msg.is-open {
  background: rgba(126, 231, 205, 0.22);
  border-color: rgba(126, 231, 205, 0.8);
}

.admin-count {
  min-width: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: #ffb27a;
  color: #2a1508;
  font-size: 0.68rem;
  font-weight: 700;
  line-height: 17px;
  text-align: center;
}

.admin-pop {
  position: absolute;
  top: 64px;
  right: clamp(14px, 2vw, 24px);
  z-index: 30;
  width: min(520px, calc(100vw - 32px));
  max-height: 62vh;
  overflow: auto;
  padding: 12px 14px;
  border-radius: 14px;
  background: #0b2f36;
  border: 1px solid rgba(126, 231, 205, 0.45);
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.55);
}

.admin-pop .admin-feedback__list {
  max-height: none;
  grid-template-columns: 1fr;
}

/* ---- 数字卡 ---- */
.admin-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.admin-card {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(12, 41, 48, 0.78);
  border: 1px solid rgba(126, 231, 205, 0.2);
}

.admin-card__label {
  font-size: 0.74rem;
  color: #93c9c0;
}

.admin-card__value {
  font-size: clamp(1.35rem, 2vw, 1.75rem);
  font-weight: 700;
  color: #c9f7ea;
  font-variant-numeric: tabular-nums;
}

.admin-card__hint {
  font-size: 0.68rem;
  color: #7fb3ab;
}

/* ---- 图表区 ---- */
.admin-charts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

/* ---- 时间范围 ---- */
/* 两个折线面板：标题区高度一致，图表底边才对得上 */
.admin-panel--chart .admin-panel__head {
  min-height: 46px;
  align-items: flex-start;
}

.admin-panel--chart .chips {
  min-height: 26px;
  align-items: center;
}

.pick {
  position: relative;
  margin-bottom: 6px;
}

.pick__btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid rgba(126, 231, 205, 0.26);
  background: rgba(14, 52, 60, 0.7);
  color: #cfe9e4;
  font-size: 0.74rem;
  cursor: pointer;
}

.pick__btn:hover {
  border-color: rgba(126, 231, 205, 0.5);
}

.pick__count {
  color: #7ee7cd;
  font-variant-numeric: tabular-nums;
}

.pick__caret {
  color: #7fb3ab;
  font-size: 0.7rem;
}

.pick__menu {
  position: absolute;
  z-index: 8;
  top: calc(100% + 6px);
  left: 0;
  min-width: 260px;
  max-width: min(420px, 92vw);
  max-height: 240px;
  overflow: auto;
  padding: 8px;
  border-radius: 12px;
  background: #0a262b;
  border: 1px solid rgba(126, 231, 205, 0.3);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.45);
}

.pick__search {
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 6px;
  padding: 6px 9px;
  border-radius: 8px;
  border: 1px solid rgba(126, 231, 205, 0.24);
  background: rgba(6, 26, 31, 0.9);
  color: #d8f3ee;
  font-size: 0.72rem;
  outline: none;
}

.pick__search:focus {
  border-color: rgba(126, 231, 205, 0.55);
}

.pick__search::placeholder {
  color: #5f8b86;
}

.pick__empty {
  margin: 8px 6px;
  font-size: 0.7rem;
  color: #6f9b95;
}

.pick__hint {
  margin: 0 0 6px;
  padding: 0 6px;
  font-size: 0.68rem;
  color: #6f9b95;
}

.pick__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px;
  border-radius: 8px;
  font-size: 0.74rem;
  color: #cfe9e4;
  cursor: pointer;
}

.pick__row:hover {
  background: rgba(126, 231, 205, 0.08);
}

.pick__row input {
  accent-color: #7ee7cd;
}

.pick__row i {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: 0 0 auto;
}

.pick__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pick__row b {
  margin-left: auto;
  color: #7fb3ab;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}


.admin-tabs {
  display: flex;
  gap: 6px;
  margin-left: 16px;
}

.admin-tab {
  padding: 5px 14px;
  border-radius: 999px;
  border: 1px solid rgba(126, 231, 205, 0.22);
  background: rgba(10, 40, 48, 0.55);
  color: #9fc9c2;
  font-size: 0.78rem;
  cursor: pointer;
}

.admin-tab:hover {
  border-color: rgba(126, 231, 205, 0.45);
  color: #d8f3ee;
}

.admin-tab--on {
  background: rgba(126, 231, 205, 0.16);
  border-color: rgba(126, 231, 205, 0.6);
  color: #eafffb;
}

.model-add {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 4px 0 14px;
}

.model-add .admin-search {
  flex: 0 1 240px;
}

.model-select {
  padding: 7px 10px;
  border-radius: 10px;
  border: 1px solid rgba(126, 231, 205, 0.24);
  background: #0a262b;
  color: #cfe9e4;
  font-size: 0.78rem;
}

/* ---- 发布公告 ---- */
.notice-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 4px 0 16px;
}

.notice-form__title {
  width: 100%;
  flex: none !important;
}

.notice-form__text {
  width: 100%;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1px solid rgba(126, 231, 205, 0.24);
  background: #0a262b;
  color: #cfe9e4;
  font-size: 0.78rem;
  line-height: 1.65;
  font-family: inherit;
  resize: vertical;
  min-height: 90px;
}

.notice-form__text:focus {
  outline: none;
  border-color: rgba(126, 231, 205, 0.6);
}

.notice-form__foot {
  display: flex;
  align-items: center;
  gap: 12px;
}

.notice-form__pin {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.74rem;
  color: #9fc7c2;
  cursor: pointer;
  user-select: none;
}

.notice-form__pin input {
  accent-color: #7ee7cd;
  cursor: pointer;
}

.notice-tag {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid rgba(255, 200, 120, 0.5);
  color: #ffd79a;
  font-size: 0.64rem;
  vertical-align: middle;
}

.notice-cell {
  max-width: 320px;
  color: #9fc7c2;
  font-size: 0.74rem;
}

/* ---- 地图 Key ---- */
.map-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 6px 0 16px;
  max-width: 720px;
}

.map-form__row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.map-form__label {
  flex: none;
  width: 68px;
  font-size: 0.76rem;
  color: #9fc7c2;
}

.map-form__input {
  flex: 1 1 auto;
  min-width: 0;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 0.01em;
}

.map-form__foot {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding-left: 80px;
}

.map-form__meta {
  font-size: 0.72rem;
  color: #7ea8a3;
}

.admin-badge--warn {
  border-color: rgba(255, 160, 120, 0.55);
  color: #ffb59a;
}

.admin-op--primary {
  border-color: rgba(126, 231, 205, 0.6);
  color: #eafffb;
  background: rgba(126, 231, 205, 0.16);
}

.model-kind {
  display: inline-block;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 0.7rem;
  border: 1px solid transparent;
}

.model-kind--chat {
  color: #9fd8ff;
  border-color: rgba(127, 195, 232, 0.45);
  background: rgba(127, 195, 232, 0.12);
}

.model-kind--tts {
  color: #ffd49a;
  border-color: rgba(255, 196, 120, 0.45);
  background: rgba(255, 196, 120, 0.12);
}

.pick__kind {
  flex: 0 0 auto;
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 0.62rem;
  line-height: 1.5;
}

.pick__kind--chat {
  color: #9fd8ff;
  background: rgba(127, 195, 232, 0.16);
}

.pick__kind--tts {
  color: #ffd49a;
  background: rgba(255, 196, 120, 0.16);
}

.admin-models .admin-empty {
  margin-top: 8px;
}

.admin-panel__head--range {
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
}

.admin-panel__head--range h2 {
  white-space: nowrap;
  flex: 0 0 auto;
}

.range-inline {
  margin-left: auto;
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.range-inline__custom input {
  width: 122px;
  font-size: 0.72rem;
}

.range-inline__custom {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.range-inline__hint {
  font-size: 0.7rem;
  color: #7fa8a3;
  font-variant-numeric: tabular-nums;
}

.range-btn {
  padding: 3px 11px;
  border-radius: 999px;
  border: 1px solid rgba(126, 231, 205, 0.25);
  background: rgba(8, 34, 39, 0.7);
  color: #9fc9c2;
  font-size: 0.74rem;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.range-btn:hover {
  border-color: rgba(126, 231, 205, 0.6);
}

.range-btn--on {
  background: rgba(126, 231, 205, 0.2);
  border-color: rgba(126, 231, 205, 0.8);
  color: #e9fdf7;
}

.range-date {
  padding: 4px 8px;
  border-radius: 8px;
  border: 1px solid rgba(126, 231, 205, 0.3);
  background: rgba(6, 26, 30, 0.8);
  color: #e8fbf7;
  font-size: 0.78rem;
  color-scheme: dark;
}

/* ---- 可勾选图例 ---- */
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(126, 231, 205, 0.22);
  background: rgba(8, 34, 39, 0.7);
  color: #7fa8a3;
  font-size: 0.72rem;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}

.chip i {
  width: 9px;
  height: 3px;
  border-radius: 2px;
  opacity: 0.35;
}

.chip--on {
  color: #dcf8f1;
  border-color: rgba(126, 231, 205, 0.65);
  background: rgba(126, 231, 205, 0.12);
}

.chip--on i {
  opacity: 1;
}

.chip__count {
  color: #8fc0b8;
  font-variant-numeric: tabular-nums;
}

/* ---- 分页 ---- */
.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

.pager__info {
  margin-right: auto;
  font-size: 0.74rem;
  color: #7fa8a3;
}

/* ---- 表格 ---- */
.admin-tools {
  display: flex;
  gap: 8px;
}

.admin-search {
  width: clamp(140px, 20vw, 210px);
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid rgba(126, 231, 205, 0.3);
  background: rgba(6, 26, 30, 0.7);
  color: #eaf9f5;
  font-size: 0.8rem;
  outline: none;
}

.admin-search:focus {
  border-color: rgba(126, 231, 205, 0.75);
}

.admin-table-wrap {
  max-height: min(58vh, 560px);
  overflow: auto;
  border-radius: 12px;
  border: 1px solid rgba(126, 231, 205, 0.16);
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}

.admin-table th,
.admin-table td {
  padding: 8px 11px;
  text-align: left;
  white-space: nowrap;
}

.admin-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: rgba(9, 33, 38, 0.96);
  color: #8fc8bf;
  font-weight: 500;
  font-size: 0.74rem;
}

.admin-table tbody tr {
  border-top: 1px solid rgba(126, 231, 205, 0.09);
}

.admin-table tbody tr:hover {
  background: rgba(126, 231, 205, 0.06);
}

.admin-table tbody tr.is-me {
  background: rgba(126, 231, 205, 0.09);
}

.admin-table .num {
  text-align: center;
  font-variant-numeric: tabular-nums;
  color: #bfe9e0;
}

.admin-table .time {
  color: #93bdba;
  font-size: 0.76rem;
}

.admin-table .ops {
  text-align: right;
}

.admin-table .empty {
  text-align: center;
  color: #7fa8a3;
  padding: 22px 0;
}

.admin-name {
  color: #eafaf6;
}

.admin-badge {
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(126, 231, 205, 0.2);
  color: #9ff0dc;
  font-size: 0.66rem;
}

.admin-role {
  display: inline-block;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 0.72rem;
  border: 1px solid transparent;
}

.admin-role--admin {
  background: rgba(255, 196, 120, 0.16);
  border-color: rgba(255, 196, 120, 0.5);
  color: #ffd79b;
}

.admin-role--user {
  background: rgba(126, 231, 205, 0.12);
  border-color: rgba(126, 231, 205, 0.35);
  color: #a7e8d8;
}

.admin-calls {
  min-width: 40px;
  padding: 2px 9px;
  border-radius: 999px;
  border: 1px solid rgba(126, 231, 205, 0.35);
  background: rgba(126, 231, 205, 0.1);
  color: #b8f2e4;
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}

.admin-calls:hover {
  background: rgba(126, 231, 205, 0.22);
}

.admin-op {
  margin-left: 5px;
  padding: 3px 9px;
  border-radius: 8px;
  border: 1px solid rgba(126, 231, 205, 0.28);
  background: transparent;
  color: #b6ece0;
  font-size: 0.74rem;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.admin-op:hover:not(:disabled) {
  background: rgba(126, 231, 205, 0.15);
  border-color: rgba(126, 231, 205, 0.7);
}

.admin-op--danger {
  border-color: rgba(255, 138, 138, 0.4);
  color: #ffb3b3;
}

.admin-op--danger:hover:not(:disabled) {
  background: rgba(255, 108, 108, 0.16);
}

.admin-op:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.admin-foot {
  margin: 9px 2px 2px;
  font-size: 0.72rem;
  color: #7fa8a3;
}

/* ---- 弹窗 ---- */
.modal {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(3, 16, 18, 0.66);
  backdrop-filter: blur(4px);
}

.modal__card {
  width: min(760px, 96vw);
  max-height: 88vh;
  overflow: auto;
  padding: 16px 18px 18px;
  border-radius: 18px;
  background: #0a262b;
  border: 1px solid rgba(126, 231, 205, 0.35);
  box-shadow: 0 22px 60px rgba(0, 0, 0, 0.5);
}

.modal__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.modal__head h3 {
  margin: 0;
  font-size: 1rem;
  color: #d9f9f0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.modal__user {
  padding: 2px 9px;
  border-radius: 999px;
  background: rgba(126, 231, 205, 0.16);
  color: #9ff0dc;
  font-size: 0.76rem;
}

.modal__close {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: transparent;
  color: #d6f4ec;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}

.modal__close:hover {
  background: rgba(255, 255, 255, 0.12);
}

.modal__loading {
  padding: 26px 0;
  text-align: center;
  color: #8fc0b8;
  font-size: 0.84rem;
}

.modal__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.modal__stats div {
  padding: 9px 12px;
  border-radius: 12px;
  background: rgba(7, 30, 34, 0.7);
  border: 1px solid rgba(126, 231, 205, 0.16);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.modal__stats span {
  font-size: 0.7rem;
  color: #8fc0b8;
}

.modal__stats strong {
  font-size: 1.2rem;
  color: #c9f7ea;
  font-variant-numeric: tabular-nums;
}

.modal__range {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.modal__range-btn {
  padding: 5px 12px;
  font-size: 0.76rem;
  color: #cdeee6;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(126, 231, 205, 0.28);
  border-radius: 999px;
  cursor: pointer;
  transition: 0.18s;
}

.modal__range-btn:hover {
  border-color: rgba(126, 231, 205, 0.6);
}

.modal__range-btn--on {
  color: #06211f;
  background: #7ee7cd;
  border-color: #7ee7cd;
  font-weight: 600;
}

.modal__date {
  padding: 4px 8px;
  font-size: 0.74rem;
  color: #e8fbf7;
  background: rgba(4, 26, 30, 0.9);
  border: 1px solid rgba(126, 231, 205, 0.28);
  border-radius: 8px;
  color-scheme: dark;
}

.modal__dash {
  color: rgba(232, 251, 247, 0.5);
  font-size: 0.8rem;
}

.modal__range-hint {
  margin-left: auto;
  font-size: 0.72rem;
  color: rgba(232, 251, 247, 0.45);
}

.usage-bars {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.usage-bars li {
  display: grid;
  grid-template-columns: 8px auto 78px minmax(0, 1fr) 34px;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  transition: opacity 0.18s;
}

.usage-bars__row--off {
  opacity: 0.35;
}

.usage-bars__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.usage-bars__name {
  font-size: 0.74rem;
  color: #a6d6cd;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.usage-bars__track {
  height: 9px;
  border-radius: 999px;
  background: rgba(126, 231, 205, 0.1);
  overflow: hidden;
}

.usage-bars__fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}

.usage-empty {
  margin: 8px 0 0;
  font-size: 0.72rem;
  color: rgba(232, 251, 247, 0.45);
}

.usage-bars__count {
  text-align: right;
  font-size: 0.74rem;
  color: #d6f4ec;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.pick__menu--inline {
  position: static;
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 14px;
}

.pick__kind--api {
  color: #ffd9a8;
  background: rgba(255, 196, 120, 0.14);
  border-color: rgba(255, 196, 120, 0.4);
}

.modal__charts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.modal__charts h4,
.modal__recent h4 {
  margin: 0 0 8px;
  font-size: 0.8rem;
  font-weight: 600;
  color: #9fd8cd;
}

.modal__recent {
  margin-top: 14px;
}

.modal__recent ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 170px;
  overflow: auto;
}

.modal__recent li {
  display: grid;
  grid-template-columns: 74px minmax(0, 1fr) 120px;
  gap: 8px;
  font-size: 0.74rem;
  padding: 5px 8px;
  border-radius: 8px;
  background: rgba(7, 30, 34, 0.55);
  color: #b6e3d9;
}

.modal__kind {
  color: #9ff0dc;
}

.modal__detail {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #93c0b7;
}

.modal__at {
  text-align: right;
  color: #7fa8a3;
}

.modal__empty {
  grid-template-columns: 1fr !important;
  text-align: center;
  color: #7fa8a3;
}

/* ---- 无权限 / 提示 ---- */
.admin-denied {
  margin: 6vh auto 0;
  max-width: 420px;
  padding: 24px 20px;
  text-align: center;
  border-radius: 16px;
  background: rgba(12, 41, 48, 0.86);
  border: 1px solid rgba(255, 138, 138, 0.35);
}

.admin-denied h2 {
  margin: 0 0 8px;
  font-size: 1rem;
  color: #ffc9c9;
}

.admin-denied p {
  margin: 0 0 14px;
  font-size: 0.84rem;
  color: #cfe9e4;
}

.admin-toast {
  position: fixed;
  left: 50%;
  bottom: 30px;
  transform: translateX(-50%);
  z-index: 50;
  padding: 8px 18px;
  border-radius: 999px;
  background: rgba(11, 46, 50, 0.96);
  border: 1px solid rgba(126, 231, 205, 0.55);
  color: #d8fff4;
  font-size: 0.8rem;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (max-width: 980px) {
  .admin-charts,
  .modal__charts {
    grid-template-columns: 1fr;
  }
  .admin-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
