<script setup lang="ts">
// =====================================================================
// MemoryPanel.vue —— 记忆可视化（全屏浮层）
//   左：统计 + 类型构成；右上：知识图谱；右下：记忆清单（可搜索/删除）
// =====================================================================

import { computed, onMounted, ref, watch } from 'vue'
import SearchBar from './SearchBar.vue'
import {
  fetchGraph,
  fetchMemories,
  removeMemory,
  type GraphEdge,
  type GraphNode,
  type MemoryConversation,
  type MemoryItem,
  type MemoryStats,
} from '../composables/useMemory'

const props = defineProps<{ initialConversation?: number | null }>()
const emit = defineEmits<{ close: [] }>()

const loading = ref(true)
const graphLoading = ref(true)
const error = ref('')

const memories = ref<MemoryItem[]>([])
const conversations = ref<MemoryConversation[]>([])
/** null = 全部对话 */
const activeConv = ref<number | null>(props.initialConversation ?? null)
/** 点开的记忆点（右侧详情卡） */
const selected = ref<GraphNode & Record<string, any> | null>(null)
const stats = ref<MemoryStats>({ total: 0, conversations: 0, by_kind: [] })
const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])

const query = ref('')
const deleting = ref<number | null>(null)

// 图谱用 1000x560 的坐标系，等比缩放
const VW = 1000
const VH = 560
const CENTER = { x: VW / 2, y: VH / 2 }

interface Placed extends GraphNode {
  x: number
  y: number
  /** 标签相对圆点的纵向偏移：相邻的标签一上一下，避免挤成一排 */
  dy: number
}

const placed = computed<Placed[]>(() => {
  const hubs = nodes.value.filter((n) => n.type === 'conversation')
  const mems = nodes.value.filter((n) => n.type === 'memory')
  const out: Placed[] = []

  const hubRadius = hubs.length <= 1 ? 0 : Math.min(250, 130 + hubs.length * 34)
  const pos = new Map<string, { x: number; y: number }>()

  hubs.forEach((hub, i) => {
    let x: number
    let y: number
    if (hubs.length <= 3) {
      // 少量对话：横着排，比围成一圈更像「一簇一簇」
      x = (VW * (i + 1)) / (hubs.length + 1)
      y = CENTER.y
    } else {
      const angle = (Math.PI * 2 * i) / hubs.length - Math.PI / 2
      x = CENTER.x + Math.cos(angle) * hubRadius
      y = CENTER.y + Math.sin(angle) * hubRadius
    }
    pos.set(hub.id, { x, y })
    out.push({ ...hub, x, y, dy: -22 })
  })

  // 每条记忆挂到自己的对话枢纽旁边：归属关系看后端给的边（hub -> mem）
  const hubOf = new Map<string, string>()
  edges.value.forEach((e) => {
    if (e.source.startsWith('conv-')) hubOf.set(e.target, e.source)
  })

  const byHub = new Map<string, GraphNode[]>()
  mems.forEach((m) => {
    const hubId = hubOf.get(m.id) ?? 'orphan'
    const list = byHub.get(hubId) ?? []
    list.push(m)
    byHub.set(hubId, list)
  })

  byHub.forEach((list, hubId) => {
    const center = pos.get(hubId) ?? CENTER
    list.forEach((m, i) => {
      const ring = i < 8 ? 0 : 1
      const countInRing = ring === 0 ? Math.min(list.length, 8) : list.length - 8
      const idx = ring === 0 ? i : i - 8
      const angle = (Math.PI * 2 * idx) / Math.max(countInRing, 1) + ring * 0.4
      const radius = 130 + ring * 78 + (idx % 2 ? 34 : 0)
      const x = center.x + Math.cos(angle) * radius
      const y = center.y + Math.sin(angle) * radius * 0.9
      out.push({ ...m, x, y, dy: idx % 2 ? 20 : -16 })
    })
  })

  return out
})

const placedById = computed(() => {
  const map = new Map<string, Placed>()
  placed.value.forEach((n) => map.set(n.id, n))
  return map
})

const lines = computed(() => {
  const out: {
    id: string
    x1: number
    y1: number
    x2: number
    y2: number
    kind: 'hub' | 'rel'
    source: string
    target: string
  }[] = []
  edges.value.forEach((e) => {
    const a = placedById.value.get(e.source)
    const b = placedById.value.get(e.target)
    if (!a || !b) return
    out.push({
      id: `${e.source}-${e.target}`,
      x1: a.x,
      y1: a.y,
      x2: b.x,
      y2: b.y,
      kind: e.source.startsWith('conv-') ? 'hub' : 'rel',
      source: e.source,
      target: e.target,
    })
  })
  return out
})

interface Curve {
  id: string
  d: string
  kind: 'hub' | 'rel'
  hot: boolean
}

/**
 * 把直线换成二次贝塞尔：中点往法线方向偏一点，看着像神经突触而不是蜘蛛网。
 * 偏移量随两端距离变化，短连线几乎保持笔直。
 */
const curves = computed<Curve[]>(() => {
  return lines.value.map((l) => {
    const dx = l.x2 - l.x1
    const dy = l.y2 - l.y1
    const len = Math.hypot(dx, dy) || 1
    const bend = Math.min(38, len * 0.16) * (l.kind === 'hub' ? 1 : 0.55)
    const mx = (l.x1 + l.x2) / 2 - (dy / len) * bend
    const my = (l.y1 + l.y2) / 2 + (dx / len) * bend
    const hot = !!selected.value && (l.source === selected.value.id || l.target === selected.value.id)
    return {
      id: l.id,
      d: `M ${l.x1.toFixed(1)} ${l.y1.toFixed(1)} Q ${mx.toFixed(1)} ${my.toFixed(1)} ${l.x2.toFixed(1)} ${l.y2.toFixed(1)}`,
      kind: l.kind,
      hot,
    }
  })
})

interface Particle {
  id: string
  pathId: string
  kind: 'hub' | 'rel'
  dur: number
  begin: number
}

/** 沿连线流动的小光点：只给归属线放，太多会吵 */
const particles = computed<Particle[]>(() => {
  const out: Particle[] = []
  curves.value.forEach((c, i) => {
    if (c.kind !== 'hub') return
    if (out.length >= 18) return
    for (let k = 0; k < 2; k++) {
      out.push({
        id: `${c.id}-${k}`,
        pathId: c.id,
        kind: 'hub',
        dur: 3.4 + (i % 3) * 0.6,
        begin: k * 1.7 + (i % 4) * 0.35,
      })
    }
  })
  return out
})

const KIND_COLORS: Record<string, string> = {
  fact: '#6ee7c8',
  preference: '#f2c14e',
  plan: '#7fb8e8',
  place: '#f78da7',
  event: '#b794f6',
  summary: '#9ad3b8',
}

function colorOf(kind: string) {
  return KIND_COLORS[kind] ?? '#8fb8c8'
}

const kindLegend = computed(() => stats.value.by_kind ?? [])

async function loadMemory() {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchMemories(query.value, activeConv.value)
    memories.value = data.memories
    stats.value = data.stats
    conversations.value = data.conversations
    const firstConv = data.conversations[0]
    if (activeConv.value === null && firstConv) {
      activeConv.value = firstConv.id
      await loadGraph()
      return
    }
  } catch (err) {
    error.value = '记忆加载失败：' + (err as Error).message
  } finally {
    loading.value = false
  }
}

async function loadGraph() {
  graphLoading.value = true
  try {
    const data = await fetchGraph(activeConv.value)
    nodes.value = data.nodes
    edges.value = data.edges
  } catch {
    nodes.value = []
    edges.value = []
  } finally {
    graphLoading.value = false
  }
}

let searchTimer = 0
function onSearch() {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(loadMemory, 260)
}

// 边输边搜（Enter 会直接触发 onSearch，这里管输入过程中的防抖）
watch(query, () => onSearch())

function pickConv(id: number) {
  if (activeConv.value === id) return
  activeConv.value = id
  selected.value = null
  loadMemory()
  loadGraph()
}

function pickNode(node: GraphNode) {
  selected.value = node.type === 'memory' ? (node as GraphNode & Record<string, any>) : null
}

const convTotal = computed(() => conversations.value.reduce((sum, c) => sum + c.count, 0))

async function drop(item: MemoryItem) {
  if (!window.confirm(`删掉这条记忆？\n\n${item.content}`)) return
  deleting.value = item.id
  try {
    await removeMemory(item.id)
    memories.value = memories.value.filter((m) => m.id !== item.id)
    stats.value = {
      ...stats.value,
      total: Math.max(0, stats.value.total - 1),
      by_kind: stats.value.by_kind
        .map((k) => (k.kind === item.kind ? { ...k, count: k.count - 1 } : k))
        .filter((k) => k.count > 0),
    }
    await loadGraph()
  } catch (err) {
    error.value = '删除失败：' + (err as Error).message
  } finally {
    deleting.value = null
  }
}

function close() {
  emit('close')
}

onMounted(() => {
  loadMemory()
  loadGraph()
})
</script>

<template>
  <div class="mem-layer" @click.self="close">
    <div class="mem-page">
      <header class="mem-head">
        <div class="mem-title">
          <h2>记忆</h2>
          <span class="mem-sub">芙芙记得的关于你的事</span>
        </div>
        <SearchBar
          v-model="query"
          class="mem-search-bar"
          kind="memory"
          icon
          :maxlength="60"
          :limit="8"
          placeholder="搜记忆里记下的事…"
          title="搜过的词点一下就能选回来"
          @search="onSearch"
          @pick="onSearch"
        />
        <button type="button" class="mem-close" title="关闭" @click="close">
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path
              d="M6 6l12 12M18 6L6 18"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            />
          </svg>
        </button>
      </header>

      <p v-if="error" class="mem-error">{{ error }}</p>

      <div class="mem-convs">
        <button
          v-for="c in conversations"
          :key="c.id"
          type="button"
          class="mem-conv"
          :class="{ 'mem-conv--on': activeConv === c.id }"
          @click="pickConv(c.id)"
        >
          {{ c.title }}
          <b>{{ c.count }}</b>
        </button>
      </div>

      <div class="mem-body">
        <!-- 左：统计 -->
        <aside class="mem-stats">
          <div class="mem-stat">
            <strong>{{ stats.total }}</strong>
            <span>总记忆</span>
          </div>
          <div class="mem-stat">
            <strong>{{ stats.conversations }}</strong>
            <span>关联对话</span>
          </div>
          <div class="mem-stat">
            <strong>{{ lines.length }}</strong>
            <span>关系</span>
          </div>

          <div class="mem-kinds">
            <h3>类型构成</h3>
            <ul>
              <li v-for="k in kindLegend" :key="k.kind">
                <i :style="{ background: colorOf(k.kind) }" />
                <span>{{ k.label }}</span>
                <b>{{ k.count }}</b>
              </li>
              <li v-if="!kindLegend.length" class="mem-empty">还没有记忆</li>
            </ul>
          </div>
        </aside>

        <!-- 右：图谱 + 清单 -->
        <section class="mem-main">
          <div class="mem-graph">
            <div class="mem-graph__head">
              <h3>记忆图谱</h3>
              <span class="mem-graph__hint">
                每个对话是一簇，连线表示「这条记忆属于哪段对话」
              </span>
            </div>
            <div class="mem-graph__canvas">
              <svg
                :viewBox="`0 0 ${VW} ${VH}`"
                class="mem-svg"
                :class="{ 'mem-svg--focus': !!selected }"
                @click.self="selected = null"
              >
                <defs>
                  <radialGradient id="memGlowCyan">
                    <stop offset="0%" stop-color="#7ef0d6" stop-opacity="0.55" />
                    <stop offset="60%" stop-color="#7ef0d6" stop-opacity="0.12" />
                    <stop offset="100%" stop-color="#7ef0d6" stop-opacity="0" />
                  </radialGradient>
                  <radialGradient id="memGlowCore">
                    <stop offset="0%" stop-color="#bffcff" stop-opacity="0.9" />
                    <stop offset="100%" stop-color="#7ef0d6" stop-opacity="0" />
                  </radialGradient>
                  <pattern id="memGrid" width="46" height="46" patternUnits="userSpaceOnUse">
                    <path d="M46 0H0V46" fill="none" stroke="rgba(126,240,214,0.07)" stroke-width="1" />
                    <circle cx="0" cy="0" r="1.2" fill="rgba(126,240,214,0.14)" />
                  </pattern>
                </defs>

                <!-- 背景：点阵网格 + 两层缓慢旋转的虚线环（点空白处取消选中） -->
                <rect :width="VW" :height="VH" fill="url(#memGrid)" @click="selected = null" />
                <g class="mem-orbit">
                  <ellipse :cx="CENTER.x" :cy="CENTER.y" rx="250" ry="150" class="mem-orbit__ring" />
                  <ellipse
                    :cx="CENTER.x"
                    :cy="CENTER.y"
                    rx="360"
                    ry="210"
                    class="mem-orbit__ring mem-orbit__ring--slow"
                  />
                </g>

                <!-- 连线：二次贝塞尔，看起来像突触 -->
                <g class="mem-links">
                  <path
                    v-for="c in curves"
                    :id="`mem-path-${c.id}`"
                    :key="c.id"
                    :d="c.d"
                    :class="[
                      'mem-link',
                      c.kind === 'hub' ? 'mem-link--hub' : 'mem-link--rel',
                      { 'mem-link--on': c.hot },
                    ]"
                  />
                </g>

                <!-- 沿连线流动的信号点 -->
                <g class="mem-signals">
                  <circle
                    v-for="p in particles"
                    :key="p.id"
                    r="2.4"
                    class="mem-signal"
                    :class="`mem-signal--${p.kind}`"
                  >
                    <animateMotion
                      :dur="`${p.dur}s`"
                      :begin="`${p.begin}s`"
                      repeatCount="indefinite"
                      rotate="auto"
                    >
                      <mpath :href="`#mem-path-${p.pathId}`" />
                    </animateMotion>
                  </circle>
                </g>

                <g
                  v-for="n in placed"
                  :key="n.id"
                  class="mem-node-g"
                  :class="{ 'mem-node-g--on': selected?.id === n.id }"
                  @click="pickNode(n)"
                >
                  <circle
                    v-if="selected?.id === n.id"
                    :cx="n.x"
                    :cy="n.y"
                    :r="n.type === 'conversation' ? 22 : 16"
                    class="mem-halo"
                  />
                  <circle
                    v-if="selected?.id === n.id"
                    :cx="n.x"
                    :cy="n.y"
                    :r="n.type === 'conversation' ? 24 : 18"
                    class="mem-halo mem-halo--late"
                  />

                  <!-- 外发光 -->
                  <circle
                    :cx="n.x"
                    :cy="n.y"
                    :r="n.type === 'conversation' ? 44 : 26"
                    fill="url(#memGlowCyan)"
                    class="mem-glow"
                    :class="{ 'mem-glow--hub': n.type === 'conversation' }"
                  />

                  <circle :cx="n.x" :cy="n.y" r="16" class="mem-hit" />

                  <circle
                    :cx="n.x"
                    :cy="n.y"
                    :r="n.type === 'conversation' ? 13 : 7"
                    :fill="n.type === 'conversation' ? '#eafcff' : colorOf(n.kind ?? 'fact')"
                    :class="n.type === 'conversation' ? 'mem-node--hub' : 'mem-node'"
                  >
                    <title>{{ n.label }}</title>
                  </circle>

                  <circle
                    :cx="n.x"
                    :cy="n.y"
                    :r="n.type === 'conversation' ? 17 : 11"
                    class="mem-ring"
                    :class="{ 'mem-ring--hub': n.type === 'conversation' }"
                  />

                  <text
                    :x="n.x"
                    :y="n.y + n.dy"
                    :class="n.type === 'conversation' ? 'mem-label mem-label--hub' : 'mem-label'"
                  >
                    {{ n.label.length > 10 ? n.label.slice(0, 10) + '…' : n.label }}
                  </text>
                </g>
              </svg>
              <aside v-if="selected" class="mem-detail">
                <button type="button" class="mem-detail__close" @click="selected = null">×</button>
                <span class="mem-detail__kind">{{ selected.kind_label || selected.kind }}</span>
                <h4 class="mem-detail__title">{{ selected.label }}</h4>
                <dl class="mem-detail__grid">
                  <div><dt>连接度</dt><dd>{{ selected.degree }}</dd></div>
                  <div><dt>条目</dt><dd>{{ selected.items }}</dd></div>
                  <div><dt>权重</dt><dd>{{ Number(selected.weight).toFixed(2) }}</dd></div>
                </dl>
                <p class="mem-detail__sub">关联记忆</p>
                <ul class="mem-detail__list">
                  <li v-for="nb in selected.neighbors" :key="nb.id">
                    <b>{{ nb.label }}</b>
                    <span>权重 {{ Number(nb.weight).toFixed(2) }}</span>
                  </li>
                  <li v-if="!selected.neighbors?.length" class="mem-empty">这段对话里没有同类记忆</li>
                </ul>
              </aside>

              <p v-if="graphLoading" class="mem-graph__empty">图谱加载中…</p>
              <p v-else-if="!nodes.length" class="mem-graph__empty">还没有记忆，聊几句就会长出来</p>
            </div>
          </div>

          <div class="mem-list">
            <div class="mem-list__head">
              <h3>记忆清单</h3>
              <span>{{ memories.length }} 条<span v-if="query">（搜索：{{ query }}）</span></span>
            </div>
            <ul>
              <li v-for="m in memories" :key="m.id">
                <span class="mem-kind" :style="{ color: colorOf(m.kind), borderColor: colorOf(m.kind) }">
                  {{ m.kind_label }}
                </span>
                <span class="mem-content">{{ m.content }}</span>
                <span class="mem-from">{{ m.conversation_title }}</span>
                <button
                  type="button"
                  class="mem-del"
                  :disabled="deleting === m.id"
                  title="删除这条记忆"
                  @click="drop(m)"
                >
                  {{ deleting === m.id ? '…' : '删除' }}
                </button>
              </li>
              <li v-if="!loading && !memories.length" class="mem-empty">
                {{ query ? '没有匹配的记忆' : '还没有记忆' }}
              </li>
            </ul>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mem-layer {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 26px;
  background: rgba(2, 12, 16, 0.72);
  backdrop-filter: blur(6px);
}

.mem-page {
  display: flex;
  flex-direction: column;
  width: min(1240px, 96vw);
  max-height: 92vh;
  padding: 20px 24px 18px;
  border: 1px solid rgba(126, 240, 214, 0.22);
  border-radius: 18px;
  background: linear-gradient(165deg, #07242b, #04181f 60%, #04141a);
  box-shadow: 0 30px 70px rgba(0, 0, 0, 0.55);
  overflow: hidden;
}

.mem-head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.mem-title h2 {
  margin: 0;
  font-size: 1.15rem;
  letter-spacing: 0.06em;
  color: #e8fbff;
}

.mem-sub {
  font-size: 0.76rem;
  color: #7fa6b0;
}

/* 记忆里的搜索框：公共 SearchBar，只约束宽度和配色 */
.mem-search-bar {
  flex: 1;
  min-width: 0;
  max-width: 320px;
  margin-left: auto;
}
.mem-search-bar :deep(.search-bar__field) {
  border-color: rgba(126, 240, 214, 0.22);
  border-radius: 10px;
  background: rgba(4, 24, 30, 0.9);
}
.mem-search-bar :deep(.search-bar__field:focus-within) {
  border-color: rgba(126, 240, 214, 0.6);
}
.mem-search-bar :deep(.search-bar__input) {
  color: #dff6f6;
  font-size: 0.8rem;
}
.mem-search-bar :deep(.search-bar__input::placeholder) { color: #628891; }
.mem-search-bar :deep(.search-bar__menu) {
  background: rgba(4, 24, 30, 0.98);
  border-color: rgba(126, 240, 214, 0.22);
}

.mem-close {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid rgba(126, 240, 214, 0.22);
  border-radius: 9px;
  background: rgba(6, 30, 36, 0.9);
  color: #bfe9e4;
  cursor: pointer;
}

.mem-close:hover {
  border-color: rgba(126, 240, 214, 0.5);
  color: #fff;
}

.mem-error {
  margin: 10px 0 0;
  color: #ff9aa5;
  font-size: 0.78rem;
}

.mem-convs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.mem-conv {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 200px;
  padding: 5px 12px;
  border: 1px solid rgba(126, 240, 214, 0.22);
  border-radius: 999px;
  background: rgba(6, 30, 36, 0.7);
  color: #bfe4e2;
  font-size: 0.76rem;
  cursor: pointer;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  transition: background 0.16s ease, border-color 0.16s ease, color 0.16s ease;
}

.mem-conv b {
  font-weight: 500;
  color: #7fa6b0;
}

.mem-conv:hover {
  border-color: rgba(126, 240, 214, 0.45);
  color: #eafcff;
}

.mem-conv--on {
  border-color: rgba(126, 240, 214, 0.75);
  background: rgba(126, 240, 214, 0.16);
  color: #eafcff;
}

.mem-conv--on b {
  color: #9ff0d9;
}

.mem-body {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 18px;
  margin-top: 14px;
  min-height: 0;
  flex: 1;
}

.mem-stats {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(126, 240, 214, 0.14);
  border-radius: 14px;
  background: rgba(5, 26, 32, 0.55);
}

.mem-stat strong {
  display: block;
  font-size: 2rem;
  line-height: 1.05;
  color: #9ff0d9;
}

.mem-stat span {
  font-size: 0.74rem;
  color: #7fa6b0;
}

.mem-kinds {
  margin-top: auto;
}

.mem-kinds h3 {
  margin: 0 0 8px;
  font-size: 0.78rem;
  font-weight: 600;
  color: #a8ccd2;
}

.mem-kinds ul {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.mem-kinds li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.76rem;
  color: #cde7e4;
}

.mem-kinds i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.mem-kinds b {
  margin-left: auto;
  color: #7fa6b0;
  font-weight: 500;
}

.mem-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.mem-graph {
  padding: 12px 14px 4px;
  border: 1px solid rgba(126, 240, 214, 0.14);
  border-radius: 14px;
  background: rgba(4, 22, 28, 0.6);
}

.mem-graph__head {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.mem-graph__head h3 {
  margin: 0;
  font-size: 0.86rem;
  color: #dff6f6;
}

.mem-graph__hint {
  font-size: 0.7rem;
  color: #6d939c;
}

.mem-graph__canvas {
  position: relative;
  height: 320px;
}

.mem-svg {
  width: 100%;
  height: 100%;
}

.mem-svg--focus .mem-node-g:not(.mem-node-g--on) .mem-node,
.mem-svg--focus .mem-node-g:not(.mem-node-g--on) .mem-glow {
  opacity: 0.25;
}

.mem-svg--focus .mem-link:not(.mem-link--on) {
  opacity: 0.18;
}

.mem-label {
  font-size: 15px;
  fill: #cfe9ec;
  text-anchor: middle;
}

.mem-label--hub {
  font-size: 16px;
  font-weight: 600;
}

.mem-svg--focus .mem-label {
  opacity: 0.6;
}

.mem-svg--focus .mem-node-g--on .mem-label {
  opacity: 1;
}

.mem-link {
  fill: none;
  stroke-linecap: round;
}

.mem-link--hub {
  stroke: rgba(126, 240, 214, 0.45);
  stroke-width: 1.4;
  animation: mem-breath 4.2s ease-in-out infinite;
}

.mem-link--rel {
  stroke: rgba(160, 190, 255, 0.3);
  stroke-width: 1.1;
  stroke-dasharray: 4 6;
  animation: mem-dash 1.6s linear infinite;
}

.mem-link--on {
  stroke: rgba(255, 132, 150, 0.9);
  stroke-width: 2;
  animation: none;
  stroke-dasharray: none;
  filter: drop-shadow(0 0 5px rgba(255, 120, 140, 0.65));
}

@keyframes mem-dash {
  to {
    stroke-dashoffset: -20;
  }
}

@keyframes mem-breath {
  0%,
  100% {
    opacity: 0.5;
  }
  50% {
    opacity: 1;
  }
}

.mem-signal {
  fill: #9ff0d9;
  filter: drop-shadow(0 0 4px rgba(126, 240, 214, 0.9));
  opacity: 0.85;
}

.mem-orbit__ring {
  pointer-events: none;
  fill: none;
  stroke: rgba(126, 240, 214, 0.12);
  stroke-width: 1;
  stroke-dasharray: 6 10;
  transform-box: fill-box;
  transform-origin: center;
  animation: mem-spin 42s linear infinite;
}

.mem-orbit__ring--slow {
  stroke: rgba(126, 240, 214, 0.07);
  animation-duration: 78s;
  animation-direction: reverse;
}

@keyframes mem-spin {
  to {
    transform: rotate(360deg);
  }
}

.mem-node-g {
  cursor: pointer;
}

.mem-hit {
  fill: transparent;
}

.mem-glow {
  pointer-events: none;
  transition: opacity 0.25s ease;
}

.mem-glow--hub {
  animation: mem-glow-pulse 5s ease-in-out infinite;
}

@keyframes mem-glow-pulse {
  0%,
  100% {
    opacity: 0.55;
  }
  50% {
    opacity: 1;
  }
}

.mem-node,
.mem-node--hub {
  transition: filter 0.18s ease, opacity 0.25s ease;
}

.mem-node-g:hover .mem-node {
  filter: drop-shadow(0 0 7px rgba(126, 240, 214, 0.9));
}

.mem-node-g--on .mem-node {
  filter: drop-shadow(0 0 12px rgba(255, 122, 140, 1));
}

.mem-ring {
  fill: none;
  stroke: rgba(126, 240, 214, 0.5);
  stroke-width: 1;
  pointer-events: none;
  animation: mem-ring-pulse 3.2s ease-out infinite;
  transform-box: fill-box;
  transform-origin: center;
}

.mem-ring--hub {
  stroke: rgba(234, 252, 255, 0.55);
  animation-duration: 4.4s;
}

@keyframes mem-ring-pulse {
  0% {
    transform: scale(0.9);
    opacity: 0.7;
  }
  70% {
    transform: scale(1.5);
    opacity: 0;
  }
  100% {
    opacity: 0;
  }
}

.mem-halo {
  fill: none;
  stroke: rgba(255, 122, 140, 0.85);
  stroke-width: 1.8;
  transform-box: fill-box;
  transform-origin: center;
  animation: mem-halo 1.6s ease-out infinite;
  pointer-events: none;
}

.mem-halo--late {
  animation-delay: 0.8s;
}

@keyframes mem-halo {
  0% {
    transform: scale(0.55);
    opacity: 0.95;
  }
  70% {
    transform: scale(1.45);
    opacity: 0.12;
  }
  100% {
    transform: scale(1.6);
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .mem-link--hub,
  .mem-link--rel,
  .mem-orbit__ring,
  .mem-ring,
  .mem-halo,
  .mem-glow--hub,
  .mem-signal {
    animation: none;
  }
}

.mem-detail {
  position: absolute;
  top: 0;
  right: 0;
  width: 260px;
  max-height: 100%;
  padding: 12px 14px;
  border: 1px solid rgba(126, 240, 214, 0.3);
  border-radius: 12px;
  background: rgba(4, 26, 32, 0.96);
  box-shadow: 0 16px 34px rgba(0, 0, 0, 0.45);
  overflow-y: auto;
}

.mem-detail__close {
  position: absolute;
  top: 8px;
  right: 10px;
  border: 0;
  background: transparent;
  color: #8fb8c0;
  font-size: 1rem;
  cursor: pointer;
}

.mem-detail__kind {
  display: inline-block;
  padding: 1px 8px;
  border: 1px solid rgba(126, 240, 214, 0.4);
  border-radius: 999px;
  color: #9ff0d9;
  font-size: 0.66rem;
}

.mem-detail__title {
  margin: 8px 0 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(126, 240, 214, 0.18);
  font-size: 0.88rem;
  line-height: 1.45;
  color: #eafcff;
}

.mem-detail__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 0 0 10px;
}

.mem-detail__grid dt {
  font-size: 0.66rem;
  color: #7fa6b0;
}

.mem-detail__grid dd {
  margin: 2px 0 0;
  font-size: 0.92rem;
  color: #dff6f6;
}

.mem-detail__sub {
  margin: 0 0 6px;
  font-size: 0.68rem;
  color: #7fa6b0;
}

.mem-detail__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.mem-detail__list li {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  border: 1px solid rgba(126, 240, 214, 0.16);
  border-radius: 8px;
  font-size: 0.72rem;
  color: #cfe7e6;
}

.mem-detail__list span {
  color: #7fa6b0;
  font-size: 0.66rem;
}

.mem-graph__empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  margin: 0;
  color: #6d939c;
  font-size: 0.78rem;
}

.mem-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid rgba(126, 240, 214, 0.14);
  border-radius: 14px;
  background: rgba(4, 22, 28, 0.6);
  overflow: hidden;
}

.mem-list__head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(126, 240, 214, 0.12);
}

.mem-list__head h3 {
  margin: 0;
  font-size: 0.86rem;
  color: #dff6f6;
}

.mem-list__head span {
  font-size: 0.72rem;
  color: #6d939c;
}

.mem-list ul {
  margin: 0;
  padding: 4px 6px 8px;
  list-style: none;
  overflow-y: auto;
}

.mem-list li {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr) 110px 52px;
  align-items: center;
  gap: 10px;
  padding: 8px 8px;
  border-radius: 9px;
  font-size: 0.8rem;
  color: #d6eeee;
}

.mem-list li:hover {
  background: rgba(126, 240, 214, 0.06);
}

.mem-kind {
  padding: 2px 8px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 0.68rem;
  text-align: center;
}

.mem-content {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mem-from {
  color: #6d939c;
  font-size: 0.72rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mem-del {
  padding: 4px 0;
  border: 1px solid rgba(255, 130, 140, 0.35);
  border-radius: 8px;
  background: transparent;
  color: #ff9aa5;
  font-size: 0.72rem;
  cursor: pointer;
}

.mem-del:hover {
  background: rgba(255, 130, 140, 0.12);
}

.mem-empty {
  padding: 10px 8px;
  color: #6d939c;
  font-size: 0.78rem;
}
</style>
