<!-- ====================================================================
  RoutePlanner —— 「行程」面板：填出发地 / 目的地，用高德地图画路线
    · 地图走 高德 JS API 2.0，脚本按需加载（见 composables/useAmap.ts）
    · Key 由后端内置（server/config.py），前端不再需要输入
    · 支持 驾车 / 步行 / 公交 三种方式，查询后自动缩放到整条路线
    · 地址先用 Geocoder 转成经纬度，再交给 Driving/Walking/Transfer 规划
==================================================================== -->

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { hasAmapKey, loadAmap, loadAmapConfig } from '../composables/useAmap'
import {
  deleteRouteSearch,
  fetchLastSearch,
  fetchRecentSearches,
  saveRouteSearch,
  TRAVEL_MODES,
} from '../composables/useRouteHistory'
import type { RouteSearch } from '../composables/useRouteHistory'

const emit = defineEmits<{ close: [] }>()

type TravelMode = 'driving' | 'walking' | 'transit'

// 城市：限定搜索范围，后面两个框就可以写详细地址（街道、门牌、小区）
const city = ref('')
const origin = ref('')
const destination = ref('')
const mode = ref<TravelMode>('driving')
const loading = ref(false)
const error = ref('')
const summary = ref('')
// 实际匹配到的起点 / 终点名字（防止"看起来对了其实差几公里"）
const resolved = ref('')

interface TransitLine {
  // 这一段的交通方式：公交车 / 地铁 / 动车 / 飞机 / 轮渡
  kind: string
  name: string
  from: string
  to: string
  stops: string[]
}

interface TransitOption {
  direct: boolean
  // 高德推荐的那条（地图上画的就是它，对应原始 plans[0]）
  recommended: boolean
  lines: TransitLine[]
  distance: number
  time: number
  cost: string
}

// 公交方案明细（直达的排前面），显示在地图下面
const transitOptions = ref<TransitOption[]>([])

// 城际提示：跨市有没有动车、跨省要不要看飞机
const trainHint = ref('')
const flightTip = ref<{ fromCity: string; toCity: string; km: number; hours: string } | null>(null)

// ---- 动车班次（12306） ----
interface TrainRow {
  code: string
  kind: string
  from_station: string
  to_station: string
  depart: string
  arrive: string
  duration: string
  wuzuo: string
  second: string
  first: string
}

const trains = ref<TrainRow[]>([])
const trainFromStation = ref('')
const trainToStation = ref('')
// 自定义车站下拉（原生 select 的下拉框是系统浅色，太难看，改成自己画）
const stationOpen = ref<'from' | 'to' | null>(null)
const trainFromOptions = ref<string[]>([])
const trainToOptions = ref<string[]>([])
const trainDate = ref('')
const trainLoading = ref(false)
const trainError = ref('')
const trainMeta = ref('')
const trainQuery = ref<{ from: string; to: string } | null>(null)

function isoDay(offset: number): string {
  const d = new Date()
  d.setDate(d.getDate() + offset)
  return d.toISOString().slice(0, 10)
}

const trainMinDate = isoDay(0)
const trainMaxDate = isoDay(14)

/** 输入的是 "XX站" 就用它；否则用城市名，并去掉「市/县/地区」这类后缀（12306 认「三明」不认「三明市」） */
function stationNameOf(place: Place, raw: string): string {
  const text = raw.trim()
  if (/站$/.test(text)) return text
  const name = place.city || text
  return name.replace(/(自治州|地区|特别行政区|市|县|区|盟)$/u, '').trim() || text
}

async function loadTrains(fromName: string, toName: string) {
  trainQuery.value = { from: fromName, to: toName }
  if (!trainDate.value) trainDate.value = isoDay(1)

  trainLoading.value = true
  trainError.value = ''
  trains.value = []
  trainMeta.value = ''

  try {
    const params = new URLSearchParams({ from: fromName, to: toName })
    if (trainDate.value) params.set('date', trainDate.value)
    const res = await fetch(`/api/trains?${params.toString()}`)
    const data = await res.json().catch(() => null)
    if (!res.ok) {
      trainError.value =
        (data && typeof data.detail === 'string' && data.detail) || '动车查询失败'
      return
    }
    trains.value = (data.trains ?? []) as TrainRow[]
    // 实际查的是哪个站：后端会返回匹配到的站名 + 该城市所有可选车站
    const fromStation = (data.from_station as string) || fromName
    const toStation = (data.to_station as string) || toName
    trainFromStation.value = fromStation
    trainToStation.value = toStation
    trainFromOptions.value = Array.from(
      new Set([...(data.from_options ?? []), fromStation])
    )
    trainToOptions.value = Array.from(new Set([...(data.to_options ?? []), toStation]))
    trainMeta.value = `${data.date} · 共 ${data.total} 趟`
    if (trains.value.length) trainHint.value = ''
    if (!trains.value.length) trainError.value = '这天没有查到车次，换个日期试试'
  } catch {
    trainError.value = '动车查询失败，检查一下网络'
  } finally {
    trainLoading.value = false
  }
}

function reloadTrains() {
  if (trainQuery.value) void loadTrains(trainQuery.value.from, trainQuery.value.to)
}

/** 下拉换了车站：直接用选中的站名重查 */
function applyStationChange() {
  if (!trainFromStation.value || !trainToStation.value) return
  void loadTrains(trainFromStation.value, trainToStation.value)
}

function pickStation(side: 'from' | 'to', station: string) {
  stationOpen.value = null
  if (side === 'from') {
    if (trainFromStation.value === station) return
    trainFromStation.value = station
  } else {
    if (trainToStation.value === station) return
    trainToStation.value = station
  }
  applyStationChange()
}

// ---- 输入框下拉建议：点城市/出发地/目的地，列出以前查过的内容 ----
type Field = 'city' | 'origin' | 'destination'

const openField = ref<Field | null>(null)
const history = ref<RouteSearch[]>([])
const historyLoaded = ref(false)


// 出发地/目的地按当前填的城市过滤，避免把别的城市的地名混进来
function sameCity(item: RouteSearch, name: string): boolean {
  const target = name.trim()
  if (!target) return true
  return (item.city ?? '').trim() === target
}

interface Suggestion {
  id: number
  label: string
}

// 同名只留一条（用最近那条的 id，删的时候删它）
function uniqueSuggestions(items: RouteSearch[], pick: (item: RouteSearch) => string): Suggestion[] {
  const seen = new Set<string>()
  const out: Suggestion[] = []
  for (const item of items) {
    const label = (pick(item) ?? '').trim()
    if (!label || seen.has(label)) continue
    seen.add(label)
    if (typeof item.id === 'number') out.push({ id: item.id, label })
    if (out.length >= 8) break
  }
  return out
}

const citySuggestions = computed(() =>
  uniqueSuggestions(history.value, (h) => h.city ?? '')
)
const originSuggestions = computed(() =>
  uniqueSuggestions(
    history.value.filter((h) => sameCity(h, city.value)),
    (h) => h.origin ?? ''
  )
)
const destinationSuggestions = computed(() =>
  uniqueSuggestions(
    history.value
      .filter((h) => sameCity(h, city.value))
      .filter((h) => !origin.value.trim() || h.origin === origin.value.trim()),
    (h) => h.destination ?? ''
  )
)

async function removeSuggestion(id: number) {
  const ok = await deleteRouteSearch(id)
  if (ok) {
    history.value = await fetchRecentSearches(20)
    historyLoaded.value = true
  }
}

async function openSuggest(field: Field) {
  openField.value = field
  if (historyLoaded.value) return
  history.value = await fetchRecentSearches(20)
  historyLoaded.value = true
}

function closeSuggest() {
  openField.value = null
}

/** 选中一条历史：填进对应输入框，两个地址都齐了就直接查路线 */
function pickSuggestion(field: Field, value: string) {
  if (field === 'city') city.value = value
  else if (field === 'origin') origin.value = value
  else destination.value = value

  closeSuggest()

  if (origin.value.trim() && destination.value.trim()) {
    void plan()
  }
}

function onDocumentDown(event: PointerEvent) {
  const target = event.target as HTMLElement | null

  if (stationOpen.value && !(target && target.closest('.station-pick'))) {
    stationOpen.value = null
  }
  if (!openField.value) return
  if (target && target.closest('.route-field')) return
  closeSuggest()
}

// Key 由后端内置（server/config.py），前端只负责读一次；
// 读不到时显示兜底提示（正常不会发生）
const needKey = computed(() => !hasAmapKey())
const configLoading = ref(true)

const mapEl = ref<HTMLElement | null>(null)
let AMap: any = null
let map: any = null
let service: any = null

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

let initTask: Promise<void> | null = null

async function initMap() {
  if (!mapEl.value || map) return
  if (initTask) return initTask

  initTask = (async () => {
    try {
    AMap = await loadAmap()
    await nextTick()
    if (map) {
      map.destroy()
      map = null
    }
    map = new AMap.Map(mapEl.value, {
      zoom: 5,
      center: [108.9, 34.3], // 默认看个全国，规划完会自动 fitView
      resizeEnable: true,
    })
      error.value = ''
    } catch (err) {
      error.value = messageOf(err)
    } finally {
      initTask = null
    }
  })()

  return initTask
}


interface Place {
  location: any
  city: string
  province: string
  name: string
}

/**
 * 先用 POI 检索（PlaceSearch），再退回地理编码（Geocoder）。
 *
 * 为什么不能只用 Geocoder：
 *   "福州南站"这种车站/景点/商场，Geocoder 常常给一个泛化坐标
 *   （实测会落到几公里外的学校附近），画出来的终点就错了。
 *   PlaceSearch 是查地图上的 POI，名字对得上时非常准。
 */
function searchPoi(address: string): Promise<Place | null> {
  return new Promise((resolve) => {
    // 填了城市就限定在本市搜（详细地址更准），没填才全国范围
    const hint = city.value.trim()
    const searcher = hint
      ? new AMap.PlaceSearch({ city: hint, citylimit: true, pageSize: 10 })
      : new AMap.PlaceSearch({ citylimit: false, pageSize: 10 })
    searcher.search(address, (status: string, result: any) => {
      const pois: any[] = result?.poiList?.pois ?? []
      if (status !== 'complete' || !pois.length) {
        resolve(null)
        return
      }
      const norm = address.replace(/\s/g, '')
      // 名字完全一致 / 互相包含的那个最可信，否则取第一条
      const hit =
        pois.find((poi) => {
          const name = String(poi.name ?? '').replace(/\s/g, '')
          return name === norm || (norm.length >= 3 && name.includes(norm))
        }) ?? pois[0]
      resolve({
        location: hit.location,
        city: hit.cityname ?? '',
        province: hit.pname ?? '',
        name: String(hit.name ?? address),
      })
    })
  })
}

function geocode(address: string): Promise<Place | null> {
  return new Promise((resolve) => {
    const geocoder = new AMap.Geocoder({ city: city.value.trim() || '全国' })
    geocoder.getLocation(address, (status: string, result: any) => {
      const first = result?.geocodes?.[0]
      if (status === 'complete' && first?.location) {
        const part = first.addressComponent ?? {}
        resolve({
          location: first.location,
          city: part.city || part.province || '',
          province: part.province || '',
          name: String(first.formattedAddress ?? address),
        })
      } else {
        resolve(null)
      }
    })
  })
}

/** 经纬度 → 城市 + 省份：很多 POI 没有 cityname/pname，公交和跨城判断都要用 */
function regeoArea(location: any): Promise<{ city: string; province: string }> {
  return new Promise((resolve) => {
    const geocoder = new AMap.Geocoder({ city: '全国' })
    geocoder.getAddress(location, (status: string, result: any) => {
      const part = result?.regeocode?.addressComponent
      if (status === 'complete' && part) {
        // 直辖市 city 为空，退回 province（如「北京市」）
        resolve({ city: part.city || part.province || '', province: part.province || '' })
      } else {
        resolve({ city: '', province: '' })
      }
    })
  })
}

/** 经纬度 → 两地直线距离（公里） */
function lngLatOf(loc: any): { lng: number; lat: number } | null {
  if (!loc) return null
  const lng = typeof loc.getLng === 'function' ? loc.getLng() : loc.lng
  const lat = typeof loc.getLat === 'function' ? loc.getLat() : loc.lat
  return Number.isFinite(lng) && Number.isFinite(lat) ? { lng, lat } : null
}

function distanceKm(a: any, b: any): number {
  const p1 = lngLatOf(a)
  const p2 = lngLatOf(b)
  if (!p1 || !p2) return 0
  const rad = Math.PI / 180
  const dLat = (p2.lat - p1.lat) * rad
  const dLng = (p2.lng - p1.lng) * rad
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(p1.lat * rad) * Math.cos(p2.lat * rad) * Math.sin(dLng / 2) ** 2
  return Math.round(6371 * 2 * Math.asin(Math.min(1, Math.sqrt(h))))
}

/** 去掉「省 / 市 / 自治区」这类后缀，方便比较是不是同一个地方 */
function normArea(name: string): string {
  return (name || '').replace(/(特别行政区|自治区|省|市)$/u, '').trim()
}

/** 从地址文字里抠城市名：xx市 / xx自治州 / xx地区 / xx盟 */
function cityFromText(text: string): string {
  const match = text.match(/^(.{2,8}?(?:市|自治州|地区|盟))/)
  return match?.[1] ?? ''
}

/** 地址 → { 经纬度, 城市, 实际匹配到的名字 } */
async function resolvePlace(address: string): Promise<Place> {
  const found = (await searchPoi(address)) ?? (await geocode(address))
  if (!found) {
    throw new Error(`找不到「${address}」这个地点，换个写法试试（加城市名更准）`)
  }

  // 兜底顺序：输入框里的城市 → POI 自带 cityname（上面已带） → 反向地理编码 → 从文字里抠
  if (!found.city || !found.province) {
    const area = await regeoArea(found.location)
    found.city = found.city || area.city || cityFromText(address)
    found.province = found.province || area.province
  }
  found.city = found.city || city.value.trim()
  return found
}

/**
 * 判断这一段是什么交通工具。
 * 高德返回的线路名里通常带线索（"动车三明站"、"地铁1号线"、"机场巴士"），
 * 所以先看名字关键词，再退回按 name 兜底成"公交车"。
 */
function classifyLine(line: any): string {
  const name = String(line?.name ?? '')
  const type = String(line?.type ?? '')

  // 顺序很重要：高德的公交线路名里经常夹着站名，
  // 比如「D51路(体育场馆南)--动车三明站)」其实是公交，只是终点在动车站。
  if (/地铁|轨道交通|磁浮/.test(name) || /地铁|轨道/.test(type)) return '地铁'
  if (/轮渡|渡轮/.test(name)) return '轮渡'
  if (/机场巴士|机场专线|空港快线/.test(name)) return '公交车'
  if (/飞机|航班|航空/.test(name) || /飞机|航空/.test(type)) return '飞机'
  if (/路|公交|巴士|专线/.test(name)) return '公交车'
  if (/动车|高铁|城际|列车|火车/.test(name) || /火车|动车|高铁/.test(type)) return '动车'

  return '公交车'
}

/** 从 Transfer 结果里抽出每条方案的线路和站点 */
function parseTransitPlans(result: any): TransitOption[] {
  const plans: any[] = result?.plans ?? []
  const options: TransitOption[] = []

  for (const plan of plans) {
    const segments: any[] = plan?.segments ?? []
    const lines: TransitLine[] = []

    for (const seg of segments) {
      // 跨城时高德会在结果里给 railway 段（动车/高铁/普速），
      // 以前这里只认 transit，railway 被整段丢掉了，所以看不到动车方案。
      const railway = seg?.railway
      if (railway) {
        const trainName = String(railway.name ?? railway.trip ?? '列车').trim()
        lines.push({
          kind: '动车',
          name: trainName || '列车',
          from: String(railway.departure_stop?.name ?? ''),
          to: String(railway.arrival_stop?.name ?? ''),
          stops: [],
        })
        continue
      }

      const transit = seg?.transit
      if (!transit) continue

      // 纯步行段在高德结果里也可能挂一个空 transit（lines 为空），
      // 以前会被当成一条叫"公交"的线路，展示成"公交 → 1路环线 → 公交"。
      const line = transit.lines?.[0]
      const lineName = String(line?.name ?? line?.id ?? '').trim()
      if (!lineName) continue

      lines.push({
        kind: classifyLine(line),
        name: lineName,
        from: String(transit.on_station?.name ?? ''),
        to: String(transit.off_station?.name ?? ''),
        stops: (line?.via_stops ?? []).map((stop: any) => String(stop?.name ?? '')).filter(Boolean),
      })
    }

    if (!lines.length) continue

    options.push({
      direct: lines.length === 1,
      recommended: options.length === 0, // 第一条就是高德推荐、也是地图上画的
      lines,
      distance: Number(plan?.distance ?? 0),
      time: Number(plan?.time ?? 0),
      cost: plan?.cost != null ? String(plan.cost) : '',
    })
  }

  // 直达优先，其次按耗时短
  options.sort((a, b) => {
    if (a.direct !== b.direct) return a.direct ? -1 : 1
    return a.time - b.time
  })
  return options.slice(0, 3)
}

/**
 * 跨市 / 跨省时补提示：
 *   跨市 + 高德没给 railway → 提示可以把目的地写成火车站再查
 *   跨省且距离够远 → 给一张"飞机（参考）"卡（没有航班数据源，只给距离和估算）
 */
function applyIntercityHints(start: Place, end: Place) {
  const sameCity = normArea(start.city) === normArea(end.city)
  const sameProvince = normArea(start.province) === normArea(end.province)

  if (sameCity) return

  const hasTrain = transitOptions.value.some((opt) => opt.lines.some((l) => l.kind === '动车'))
  if (!hasTrain) {
    trainHint.value =
      '这是跨市行程，但高德这次没返回动车班次。可以把出发地/目的地写成「XX站」（如「三明北站」→「福州站」）再查一次。'
  }

  if (sameProvince) return

  const km = distanceKm(start.location, end.location)
  if (km < 300) return

  // 直飞时间按 800km/h 估，另外加约 0.6 小时起降/滑行
  const hours = (km / 800 + 0.6).toFixed(1)
  flightTip.value = {
    fromCity: start.city || start.province,
    toCity: end.city || end.province,
    km,
    hours,
  }
}

/** 第一条的"上车站 → 最后一条的下车站" */
function optionRoute(opt: TransitOption): string {
  const first = opt.lines[0]
  const last = opt.lines[opt.lines.length - 1]
  if (!first || !last) return ''
  return `${first.from || '起点'} → ${last.to || '终点'}`
}

/** 余票文案 → 颜色：有=绿，无=灰，数字=橙 */
function seatClass(value: string): string {
  const text = (value || '').trim()
  if (!text || text === '--' || text === '无') return 'seat--none'
  if (text === '有') return 'seat--ok'
  return 'seat--few'
}

function formatKm(meters: number): string {
  return `${(Number(meters) / 1000).toFixed(1)} 公里`
}

function formatMinutes(seconds: number): string {
  return `${Math.max(1, Math.round(Number(seconds) / 60))} 分钟`
}

function formatSummary(result: any): string {
  let distance = 0
  let duration = 0

  if (mode.value === 'transit') {
    const plan = result?.plans?.[0]
    distance = plan?.distance ?? 0
    duration = plan?.time ?? 0
  } else {
    const route = result?.routes?.[0]
    distance = route?.distance ?? 0
    duration = route?.time ?? 0
  }

  const label = mode.value === 'driving' ? '驾车' : mode.value === 'walking' ? '步行' : '公交'
  const km = (Number(distance) / 1000).toFixed(1)
  const minutes = Math.max(1, Math.round(Number(duration) / 60))
  return `${label}全程 ${km} 公里 · 约 ${minutes} 分钟`
}

async function plan() {
  if (!map) {
    await initMap()
    if (!map) return
  }

  const from = origin.value.trim()
  const to = destination.value.trim()
  if (!from || !to) {
    error.value = '出发地和目的地都要填'
    return
  }

  loading.value = true
  error.value = ''
  summary.value = ''
  resolved.value = ''
  transitOptions.value = []
  trainHint.value = ''
  flightTip.value = null
  // 动车卡片用 trainQuery 控制显隐：换了出行方式还留着它就会串味
  // （先查公交出现车次，再切驾车，车次卡片还在）
  trainQuery.value = null
  trainFromOptions.value = []
  trainToOptions.value = []
  trains.value = []
  trainError.value = ''
  trainMeta.value = ''

  try {
    const start = await resolvePlace(from)
    const end = await resolvePlace(to)
    resolved.value = `起点：${start.name}　终点：${end.name}`

    if (service) {
      service.clear?.()
      service = null
    }

    await new Promise<void>((resolve, reject) => {
      const done = (status: string, result: any) => {
        if (status !== 'complete' || !result) {
          reject(new Error('没有规划出路线，换个地址或换种出行方式试试'))
          return
        }
        summary.value = formatSummary(result)
        if (mode.value === 'transit') {
          transitOptions.value = parseTransitPlans(result)
          applyIntercityHints(start, end)
          // 跨市就去 12306 查动车/高铁班次
          if (normArea(start.city) !== normArea(end.city)) {
            void loadTrains(stationNameOf(start, from), stationNameOf(end, to))
          }
        }
        map.setFitView()
        // 记一下这次搜索（后端会按账号存，完全重复的不会重复写）
        void saveRouteSearch({
          city: city.value.trim(),
          origin: from,
          destination: to,
          mode: mode.value,
        })
        // 下次点输入框要能看到这次的记录
        historyLoaded.value = false
        resolve()
      }

      if (mode.value === 'driving') {
        service = new AMap.Driving({ map, policy: AMap.DrivingPolicy?.LEAST_TIME ?? 0 })
        service.search(start.location, end.location, done)
      } else if (mode.value === 'walking') {
        service = new AMap.Walking({ map })
        service.search(start.location, end.location, done)
      } else {
        const cityName = city.value.trim() || start.city || end.city
        if (!cityName) {
          reject(new Error('公交规划需要知道城市：在最左边的「城市」框里填一下就行'))
          return
        }
        // city = 出发城市，cityd = 到达城市（跨城公交时才有区别）
        service = new AMap.Transfer({ map, city: cityName, cityd: end.city || cityName })
        service.search(start.location, end.location, done)
      }
    })
  } catch (err) {
    error.value = messageOf(err)
  } finally {
    loading.value = false
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

/** 把上次的搜索填回表单（没有记录就什么都不做） */
async function restoreLastSearch() {
  const last: RouteSearch | null = await fetchLastSearch()
  if (!last) return
  city.value = last.city ?? ''
  origin.value = last.origin ?? ''
  destination.value = last.destination ?? ''
  if ((TRAVEL_MODES as readonly string[]).includes(last.mode)) {
    mode.value = last.mode as TravelMode
  }

  // 地址齐全就自动重跑一次：关掉面板再打开，地图和公交方案直接回到上次的样子，
  // 不用再点一次「查路线」。（失败会显示错误，输入框里的内容不动）
  if (origin.value.trim() && destination.value.trim() && !needKey.value) {
    await plan()
  }
}

// 切换出行方式：动车卡片只属于「公交」的结果，切走就立刻收起
watch(mode, () => {
  if (trainQuery.value) {
    trainQuery.value = null
    trains.value = []
    trainError.value = ''
    trainMeta.value = ''
    trainFromOptions.value = []
    trainToOptions.value = []
  }
  if (mode.value !== 'transit') {
    trainHint.value = ''
    flightTip.value = null
  }
})

// 配置异步到位之后（首次进面板会读 /api/map），自动初始化地图并补一次查询
watch(needKey, async (missing: boolean) => {
  if (missing) return
  await nextTick()
  await initMap()
  if (origin.value.trim() && destination.value.trim() && !loading.value) {
    await plan()
  }
})

onMounted(async () => {
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('pointerdown', onDocumentDown)

  await loadAmapConfig()
  configLoading.value = false

  if (!needKey.value) await initMap()
  await restoreLastSearch()
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('pointerdown', onDocumentDown)
  if (map) map.destroy()
  map = null
  service = null
})
</script>

<template>
  <div class="route-layer">
    <div class="route-backdrop" @click="emit('close')"></div>

    <div class="route-panel" role="dialog" aria-label="行程路线">
      <header class="route-head">
        <span class="route-title">行程</span>
        <span class="route-badge">高德地图</span>

        <button class="route-close" type="button" aria-label="关闭" @click="emit('close')">×</button>
      </header>

      <p v-if="configLoading" class="route-loading">读取地图配置…</p>

      <!-- ---- 配置没读到的兜底（正常情况下不会出现）---- -->
      <div v-else-if="needKey" class="key-form">
        <p class="key-form__intro">
          地图配置没读到。Key 是固定在后端的（<strong>server/config.py</strong> 的
          AMAP_JS_KEY），刷新页面再试；如果一直这样，检查后端有没有启动。
        </p>
      </div>

      <!-- ---- 地图 + 查询 ---- -->
      <template v-else>
        <div class="route-form">
          <!-- 城市：点一下列出以前查过的城市 -->
          <div class="route-field route-field--city">
            <input
              v-model="city"
              class="route-input route-input--city"
              type="text"
              placeholder="城市"
              title="点一下可以选以前查过的城市"
              @focus="openSuggest('city')"
              @keyup.enter="plan"
              @keydown.esc="closeSuggest"
            />
            <ul v-if="openField === 'city' && citySuggestions.length" class="suggest">
              <li v-for="item in citySuggestions" :key="item.id">
                <button
                  type="button"
                  class="suggest__pick"
                  @mousedown.prevent="pickSuggestion('city', item.label)"
                >
                  {{ item.label }}
                </button>
                <button
                  type="button"
                  class="suggest__del"
                  title="删除这条记录"
                  @mousedown.prevent="removeSuggestion(item.id)"
                >
                  <svg class="suggest__del-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 L18 18 M18 6 L6 18" /></svg>
                </button>
              </li>
            </ul>
          </div>

          <!-- 出发地 -->
          <div class="route-field">
            <input
              v-model="origin"
              class="route-input"
              type="text"
              placeholder="出发地，如 八中 / 湖滨路 12 号"
              title="点一下可以选以前查过的出发地"
              @focus="openSuggest('origin')"
              @keyup.enter="plan"
              @keydown.esc="closeSuggest"
            />
            <ul v-if="openField === 'origin' && originSuggestions.length" class="suggest">
              <li v-for="item in originSuggestions" :key="item.id">
                <button
                  type="button"
                  class="suggest__pick"
                  @mousedown.prevent="pickSuggestion('origin', item.label)"
                >
                  {{ item.label }}
                </button>
                <button
                  type="button"
                  class="suggest__del"
                  title="删除这条记录"
                  @mousedown.prevent="removeSuggestion(item.id)"
                >
                  <svg class="suggest__del-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 L18 18 M18 6 L6 18" /></svg>
                </button>
              </li>
            </ul>
          </div>

          <span class="route-arrow" aria-hidden="true">→</span>

          <!-- 目的地 -->
          <div class="route-field">
            <input
              v-model="destination"
              class="route-input"
              type="text"
              placeholder="目的地，如 万达广场 / 第一医院"
              title="点一下可以选以前查过的目的地"
              @focus="openSuggest('destination')"
              @keyup.enter="plan"
              @keydown.esc="closeSuggest"
            />
            <ul
              v-if="openField === 'destination' && destinationSuggestions.length"
              class="suggest"
            >
              <li v-for="item in destinationSuggestions" :key="item.id">
                <button
                  type="button"
                  class="suggest__pick"
                  @mousedown.prevent="pickSuggestion('destination', item.label)"
                >
                  {{ item.label }}
                </button>
                <button
                  type="button"
                  class="suggest__del"
                  title="删除这条记录"
                  @mousedown.prevent="removeSuggestion(item.id)"
                >
                  <svg class="suggest__del-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 L18 18 M18 6 L6 18" /></svg>
                </button>
              </li>
            </ul>
          </div>

          <select v-model="mode" class="route-select">
            <option value="driving">驾车</option>
            <option value="walking">步行</option>
            <option value="transit">公交</option>
          </select>
          <button class="route-btn" type="button" :disabled="loading" @click="plan">
            {{ loading ? '规划中…' : '查路线' }}
          </button>
        </div>

        <div ref="mapEl" class="route-map"></div>

        <p v-if="resolved" class="route-resolved">{{ resolved }}</p>
        <p v-if="summary" class="route-summary">{{ summary }}</p>

        <!-- 公交方案：直达的排前面，列出线路和途经站点 -->
        <section v-if="transitOptions.length" class="transit-box">
          <p class="transit-box__head">
            公交方案
            <span class="transit-box__note">地图上画的是标「推荐」的那条</span>
            <span class="transit-box__legend">标签：公交车 / 地铁 / 动车 / 飞机</span>
          </p>

          <ul class="transit-list">
            <li v-for="(opt, i) in transitOptions" :key="i" class="transit-opt">
              <p class="transit-opt__title">
                <span v-if="opt.recommended" class="transit-tag transit-tag--rec">推荐</span>
                <span class="transit-tag" :class="{ 'transit-tag--direct': opt.direct }">
                  {{ opt.direct ? '直达' : `换乘 ${opt.lines.length - 1} 次` }}
                </span>
                <span class="transit-opt__lines">{{ optionRoute(opt) }}</span>
                <span class="transit-opt__meta">
                  {{ formatKm(opt.distance) }} · 约 {{ formatMinutes(opt.time) }}
                  <template v-if="opt.cost"> · 票价 {{ opt.cost }} 元</template>
                </span>
              </p>

              <div v-for="(line, k) in opt.lines" :key="k" class="transit-line">
                <p class="transit-line__route">
                  <span class="leg-kind" :data-kind="line.kind">{{ line.kind }}</span>
                  {{ line.name }} → {{ line.to }}
                  <span v-if="line.stops.length" class="transit-line__count">
                    （{{ line.stops.length }} 站）
                  </span>
                </p>
                <p v-if="line.stops.length" class="transit-line__stops">
                  {{ line.stops.join(' · ') }}
                </p>
              </div>
            </li>
          </ul>
        </section>

        <p v-if="trainHint" class="route-train-hint">{{ trainHint }}</p>

        <!-- 跨省：飞机参考（没有接入航班数据，只给距离和估算时间） -->
        <section v-if="flightTip" class="flight-box">
          <p class="flight-box__head">
            <span class="leg-kind" data-kind="飞机">飞机</span>
            <span class="flight-box__route">{{ flightTip.fromCity }} → {{ flightTip.toCity }}</span>
            <span class="flight-box__tag">参考</span>
          </p>
          <p class="flight-box__meta">
            直线距离约 {{ flightTip.km }} 公里 · 直飞约 {{ flightTip.hours }} 小时（含起降估算）
          </p>
          <p class="flight-box__note">
            目前没有接入航班实时数据，仅提示"跨省可以考虑飞"；班次和票价请查航司或票务平台，
            机场往返 + 安检通常还要留 2 小时。
          </p>
        </section>

        <!-- 跨市：12306 动车/高铁班次 -->
        <section v-if="trainQuery" class="train-box">
          <div class="train-box__head">
            <span class="leg-kind" data-kind="动车">动车</span>
            <div class="station-pick">
              <button
                type="button"
                class="station-btn"
                :class="{ 'station-btn--open': stationOpen === 'from' }"
                title="选择出发车站"
                @click="stationOpen = stationOpen === 'from' ? null : 'from'"
              >
                {{ trainFromStation }}站<span class="station-caret">▾</span>
              </button>
              <ul v-if="stationOpen === 'from'" class="station-list">
                <li v-for="s in trainFromOptions" :key="s">
                  <button
                    type="button"
                    :class="{ 'is-on': s === trainFromStation }"
                    @mousedown.prevent="pickStation('from', s)"
                  >
                    {{ s }}站
                  </button>
                </li>
              </ul>
            </div>

            <span class="train-box__arrow">→</span>

            <div class="station-pick">
              <button
                type="button"
                class="station-btn"
                :class="{ 'station-btn--open': stationOpen === 'to' }"
                title="选择到达车站"
                @click="stationOpen = stationOpen === 'to' ? null : 'to'"
              >
                {{ trainToStation }}站<span class="station-caret">▾</span>
              </button>
              <ul v-if="stationOpen === 'to'" class="station-list">
                <li v-for="s in trainToOptions" :key="s">
                  <button
                    type="button"
                    :class="{ 'is-on': s === trainToStation }"
                    @mousedown.prevent="pickStation('to', s)"
                  >
                    {{ s }}站
                  </button>
                </li>
              </ul>
            </div>
            <input
              v-model="trainDate"
              class="train-box__date"
              type="date"
              :min="trainMinDate"
              :max="trainMaxDate"
              :title="'查哪天的车'"
              @change="reloadTrains"
            />
          </div>

          <p v-if="trainLoading" class="train-box__note">正在查 12306…</p>
          <p v-else-if="trainError" class="train-box__err">{{ trainError }}</p>
          <template v-else>
            <p class="train-box__meta">{{ trainMeta }}</p>
            <ul class="train-list">
              <li v-for="t in trains" :key="t.code + t.depart" class="train-row">
                <span class="train-row__kind">{{ t.kind }}</span>
                <span class="train-row__code">{{ t.code }}</span>
                <span class="train-row__route">
                  {{ t.from_station }}站 → {{ t.to_station }}站
                </span>
                <span class="train-row__time">{{ t.depart }} → {{ t.arrive }}</span>
                <span class="train-row__dur">用时 {{ t.duration }}</span>
                <span class="train-row__seats">
                  <span class="seat" :class="seatClass(t.second)">二等座 {{ t.second || '—' }}</span>
                  <span class="seat" :class="seatClass(t.first)">一等座 {{ t.first || '—' }}</span>
                  <span class="seat" :class="seatClass(t.wuzuo)">无座 {{ t.wuzuo || '—' }}</span>
                </span>
              </li>
            </ul>
            <p class="train-box__note">数据来自 12306 余票查询，仅供参考；票价以购票页为准。</p>
          </template>
        </section>

        <p v-if="error" class="route-error">{{ error }}</p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.route-layer {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
}

.route-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(4, 24, 24, 0.5);
  backdrop-filter: blur(3px);
}

.route-panel {
  position: relative;
  z-index: 1;
  width: min(780px, 94vw);
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

.route-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.route-title {
  font-size: 1rem;
  font-weight: 500;
  letter-spacing: 0.04em;
}
.route-badge {
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(255, 253, 248, 0.12);
  color: rgba(255, 253, 248, 0.7);
  font-size: 0.66rem;
}
.route-close {
  margin-left: auto;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 253, 248, 0.85);
  font-size: 1.2rem;
  line-height: 1;
  cursor: pointer;
}
.route-close:hover { background: rgba(255, 253, 248, 0.16); }

/* ---- 查询条 ---- */
.route-form {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.route-arrow {
  color: rgba(255, 253, 248, 0.4);
  font-size: 0.9rem;
  flex: 0 0 auto;
}

.route-input {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 12px;
  box-sizing: border-box;
  border: 1px solid rgba(255, 253, 248, 0.32);
  border-radius: 10px;
  background: rgba(255, 253, 248, 0.1);
  color: #fffdf8;
  font-size: 0.82rem;
  font-family: inherit;
  outline: none;
  transition: border-color 0.2s;
}
.route-field {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
}
.route-field .route-input { width: 100%; }
.route-field--city {
  flex: 0 0 96px;
  width: 96px;
}

/* ---- 输入框的历史下拉 ---- */
.suggest {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 90;
  margin: 0;
  padding: 4px;
  list-style: none;
  max-height: 190px;
  overflow-y: auto;
  border: 1px solid rgba(255, 253, 248, 0.32);
  border-radius: 10px;
  background: rgba(12, 46, 46, 0.98);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.45);
}
.suggest li {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 1px 2px;
}
.suggest button {
  border: none;
  border-radius: 8px;
  background: transparent;
  color: rgba(255, 253, 248, 0.85);
  font-family: inherit;
  cursor: pointer;
}
/* 文字那一侧 */
.suggest__pick {
  flex: 1 1 auto;
  min-width: 0;
  padding: 7px 8px;
  font-size: 0.78rem;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.suggest__pick:hover {
  background: rgba(255, 253, 248, 0.14);
  color: #fffdf8;
}
/* 删除按钮：做成 30×30 的方块，整块都能点，符号居中 */
.suggest__del {
  flex: 0 0 30px;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  padding: 0;
  color: rgba(255, 138, 122, 0.9);
  font-size: 1.05rem;
  line-height: 1;
  transition: background 0.15s ease, color 0.15s ease;
}
.suggest__del:hover {
  background: rgba(255, 138, 122, 0.22);
  color: #ffe3dc;
}
/* 用 SVG 画 ×，居中绝对准确，不受字体影响 */
.suggest__del-icon {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
}

.route-input--city {
  flex: 0 0 96px;
  width: 96px;
}
.route-input--wide { width: 100%; flex: none; margin-bottom: 2px; }
.route-input::placeholder { color: rgba(255, 253, 248, 0.38); }
.route-input:focus { border-color: rgba(255, 253, 248, 0.78); }

.route-select {
  height: 32px;
  padding: 0 8px;
  border: 1px solid rgba(255, 253, 248, 0.32);
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.22);
  color: #eafff5;
  font-size: 0.8rem;
  font-family: inherit;
  outline: none;
  cursor: pointer;
}
.route-select option { background: #0b2f2f; color: #eafff5; }

.route-btn {
  flex: 0 0 auto;
  height: 32px;
  padding: 0 16px;
  border: none;
  border-radius: 10px;
  background: #fffdf8;
  color: #2f7d6e;
  font-size: 0.84rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: opacity 0.2s;
}
.route-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ---- 地图 ---- */
.route-map {
  width: 100%;
  height: min(46vh, 380px);
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255, 253, 248, 0.06);
}

.route-resolved {
  margin: 10px 2px 0;
  font-size: 0.72rem;
  color: rgba(255, 253, 248, 0.5);
}

.route-loading {
  margin: 18px 2px;
  font-size: 0.8rem;
  color: rgba(255, 253, 248, 0.6);
}

.route-train-hint {
  margin: 10px 2px 0;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(255, 214, 153, 0.12);
  border: 1px solid rgba(255, 214, 153, 0.28);
  font-size: 0.72rem;
  line-height: 1.55;
  color: #ffdca8;
}

.flight-box {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px dashed rgba(196, 152, 255, 0.45);
  border-radius: 12px;
  background: rgba(196, 152, 255, 0.08);
}
.flight-box__head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
}
.flight-box__route {
  font-size: 0.8rem;
  font-weight: 500;
  color: #fffdf8;
}
.flight-box__tag {
  margin-left: auto;
  padding: 1px 7px;
  border-radius: 9px;
  background: rgba(255, 253, 248, 0.12);
  color: rgba(255, 253, 248, 0.6);
  font-size: 0.62rem;
}
.flight-box__meta {
  margin: 6px 0 0;
  font-size: 0.74rem;
  color: rgba(255, 253, 248, 0.8);
}
.flight-box__note {
  margin: 6px 0 0;
  font-size: 0.68rem;
  line-height: 1.55;
  color: rgba(255, 253, 248, 0.45);
}

/* ---- 动车班次 ---- */
.train-box {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid rgba(255, 176, 102, 0.35);
  border-radius: 12px;
  background: rgba(255, 176, 102, 0.07);
}
.train-box__head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
}
.train-box__title {
  font-size: 0.78rem;
  color: #fffdf8;
}
/* ---- 车站下拉（自己画的，原生 select 的下拉框太丑） ---- */
.station-pick {
  position: relative;
}
.station-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 9px;
  border: 1.5px solid rgba(159, 232, 196, 0.55);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.28);
  color: #fffdf8;
  font-size: 0.76rem;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}
.station-btn:hover,
.station-btn--open {
  border-color: rgba(159, 232, 196, 0.95);
  box-shadow: 0 0 0 2px rgba(159, 232, 196, 0.18);
  background: rgba(24, 64, 58, 0.55);
}
.station-caret {
  font-size: 0.6rem;
  opacity: 0.75;
}
.station-list {
  position: absolute;
  top: calc(100% + 5px);
  left: 0;
  z-index: 95;
  margin: 0;
  padding: 5px;
  list-style: none;
  min-width: 118px;
  border: 1.5px solid rgba(159, 232, 196, 0.55);
  border-radius: 10px;
  background: rgba(9, 38, 38, 0.99);
  box-shadow: 0 14px 32px rgba(0, 0, 0, 0.55);
}
.station-list button {
  display: block;
  width: 100%;
  padding: 7px 9px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: rgba(255, 253, 248, 0.72);
  font-size: 0.78rem;
  font-family: inherit;
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
}
.station-list button:hover {
  background: rgba(255, 253, 248, 0.12);
  color: #fffdf8;
}
.station-list button.is-on {
  background: #2f6b5c;
  color: #ffffff;
  font-weight: 600;
  box-shadow: inset 0 0 0 1.5px rgba(159, 232, 196, 0.9);
}
.train-box__arrow {
  color: rgba(255, 253, 248, 0.6);
  font-size: 0.74rem;
}
.train-box__date {
  margin-left: auto;
  height: 24px;
  padding: 0 6px;
  border: 1px solid rgba(255, 253, 248, 0.3);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.22);
  color: #eafff5;
  font-size: 0.7rem;
  font-family: inherit;
  outline: none;
  color-scheme: dark;
}
.train-box__meta {
  margin: 0 0 6px;
  font-size: 0.66rem;
  color: rgba(255, 253, 248, 0.45);
}
.train-box__note {
  margin: 8px 0 0;
  font-size: 0.66rem;
  line-height: 1.5;
  color: rgba(255, 253, 248, 0.42);
}
.train-box__err {
  margin: 6px 0 0;
  font-size: 0.72rem;
  color: #ffb4a8;
}

.train-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 4px;
  max-height: 176px;
  overflow-y: auto;
}
.train-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 6px;
  padding: 5px 8px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.16);
  font-size: 0.7rem;
  font-variant-numeric: tabular-nums;
}
.train-row__kind {
  padding: 1px 5px;
  border-radius: 6px;
  background: rgba(255, 176, 102, 0.22);
  color: #ffd9b0;
  font-size: 0.62rem;
}
.train-row__code {
  font-weight: 600;
  color: #fffdf8;
  min-width: 46px;
}
.train-row__route {
  color: rgba(255, 253, 248, 0.62);
  font-size: 0.68rem;
  white-space: nowrap;
}
.train-row__time { color: #e9fff7; white-space: nowrap; }
.train-row__dur {
  color: rgba(255, 253, 248, 0.5);
  font-size: 0.66rem;
  white-space: nowrap;
}

.train-row__seats {
  margin-left: auto;
  display: flex;
  gap: 8px;
  white-space: nowrap;
}
.seat {
  font-size: 0.66rem;
  color: rgba(255, 253, 248, 0.6);
}
.seat--ok { color: #9fe8c4; }
.seat--few { color: #ffd08a; }
.seat--none { color: rgba(255, 253, 248, 0.32); }

/* ---- 公交方案列表 ---- */
.transit-box {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid rgba(255, 253, 248, 0.16);
  border-radius: 12px;
  background: rgba(255, 253, 248, 0.05);
}
.transit-box__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0 0 8px;
  font-size: 0.78rem;
  color: rgba(255, 253, 248, 0.75);
}
.transit-box__note {
  font-size: 0.66rem;
  color: rgba(255, 253, 248, 0.35);
}

.transit-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
  max-height: 190px;
  overflow-y: auto;
}
.transit-opt {
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.16);
}
.transit-opt__title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  font-size: 0.8rem;
}
.transit-tag {
  padding: 1px 7px;
  border-radius: 9px;
  background: rgba(255, 253, 248, 0.12);
  color: rgba(255, 253, 248, 0.75);
  font-size: 0.64rem;
}
.transit-tag--direct {
  background: rgba(143, 214, 186, 0.24);
  color: #b9ecd4;
}
.transit-tag--rec {
  background: rgba(255, 214, 153, 0.22);
  color: #ffdca8;
}
.transit-opt__lines {
  color: #fffdf8;
  font-weight: 500;
}
.transit-opt__meta {
  margin-left: auto;
  font-size: 0.68rem;
  color: rgba(255, 253, 248, 0.55);
}

.leg-kind {
  display: inline-block;
  margin-right: 4px;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(255, 253, 248, 0.14);
  color: rgba(255, 253, 248, 0.8);
  font-size: 0.62rem;
  vertical-align: 1px;
}
.leg-kind[data-kind='地铁'] { background: rgba(110, 165, 255, 0.26); color: #cfe0ff; }
.leg-kind[data-kind='动车'] { background: rgba(255, 176, 102, 0.24); color: #ffd9b0; }
.leg-kind[data-kind='飞机'] { background: rgba(196, 152, 255, 0.26); color: #e2d1ff; }
.leg-kind[data-kind='轮渡'] { background: rgba(110, 216, 220, 0.24); color: #c8f4f5; }

.transit-box__legend {
  margin-left: auto;
  font-size: 0.64rem;
  color: rgba(255, 253, 248, 0.35);
}

.transit-line {
  margin-top: 6px;
  padding-left: 2px;
}
.transit-line__route {
  margin: 0;
  font-size: 0.74rem;
  color: rgba(255, 253, 248, 0.85);
}
.transit-line__count {
  font-size: 0.66rem;
  color: rgba(255, 253, 248, 0.45);
}
.transit-line__stops {
  margin: 3px 0 0;
  font-size: 0.68rem;
  line-height: 1.55;
  color: rgba(255, 253, 248, 0.5);
}

.route-summary {
  margin: 10px 2px 0;
  font-size: 0.84rem;
  color: #b9ecd4;
}
.route-error {
  margin: 10px 2px 0;
  font-size: 0.8rem;
  line-height: 1.5;
  color: #ffb4a8;
}

/* ---- Key 表单 ---- */
.key-form__intro {
  margin: 0 0 12px;
  font-size: 0.78rem;
  line-height: 1.65;
  color: rgba(255, 253, 248, 0.7);
}
.key-form__intro a { color: #b9ecd4; }
.key-form__intro strong { font-weight: 500; color: #fffdf8; }

.route-label {
  display: block;
  margin: 8px 0 5px;
  font-size: 0.74rem;
  color: rgba(255, 253, 248, 0.66);
}

.route-hint {
  margin: 10px 0 0;
  font-size: 0.68rem;
  line-height: 1.55;
  color: rgba(255, 253, 248, 0.45);
}

@media (prefers-reduced-motion: reduce) {
  .route-panel { animation: none; }
}
</style>
