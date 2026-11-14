<!-- 折线图（SVG 手写，不引第三方图表库）——带 Y 轴刻度、悬停/点击查看数值 -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

interface Series {
  name: string
  color: string
  data: number[]
}

const props = withDefaults(
  defineProps<{
    labels: string[]
    series: Series[]
    height?: number
    showLegend?: boolean
  }>(),
  { height: 150, showLegend: true },
)

const H = computed(() => props.height)
const PAD_TOP = 8
const PAD_BOTTOM = 18

const maxValue = computed(() => {
  const all = props.series.flatMap((s) => s.data)
  const max = Math.max(1, ...all)
  const pow = Math.pow(10, Math.floor(Math.log10(max)))
  const step = [1, 2, 5, 10].map((m) => m * pow).find((v) => v * 3 >= max) ?? max
  return Math.ceil(max / step) * step
})

/** Y 轴刻度：0 / 1/3 / 2/3 / 最大值 */
const yTicks = computed(() => {
  const max = maxValue.value
  return [0, 1, 2, 3].map((k) => {
    const value = Math.round((max * k) / 3)
    return { value, top: (1 - value / max) * 100 }
  })
})

function x(index: number): number {
  const n = Math.max(1, props.labels.length - 1)
  return (index / n) * 100
}

function y(value: number): number {
  const usable = H.value - PAD_TOP - PAD_BOTTOM
  return PAD_TOP + usable - (value / maxValue.value) * usable
}

function linePath(data: number[]): string {
  return data
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(2)},${y(v).toFixed(2)}`)
    .join(' ')
}

function areaPath(data: number[]): string {
  const bottom = H.value - PAD_BOTTOM
  return `${linePath(data)} L${x(data.length - 1).toFixed(2)},${bottom} L0,${bottom} Z`
}

const ticks = computed(() => {
  const n = props.labels.length
  if (n <= 4) return props.labels.map((label, i) => ({ i, label }))

  // 大约 5 个刻度就够，别让横轴挤成一团
  const step = Math.max(1, Math.ceil(n / 5))
  const picked: number[] = []
  for (let i = 0; i < n; i += step) picked.push(i)

  // 末尾那个点单独处理：离前一个太近就替换掉它，避免两个日期粘一起
  const last = n - 1
  const tail = picked[picked.length - 1] ?? 0
  if (tail !== last) {
    if (last - tail >= step / 2) picked.push(last)
    else picked[picked.length - 1] = last
  }

  return picked.map((i) => ({ i, label: props.labels[i] }))
})

// ---------------------------------------------------------------
// 悬停 / 点击读数：hover 临时显示，click 固定住（再点一下取消）
// ---------------------------------------------------------------
const rootEl = ref<HTMLElement | null>(null)
const hoverIndex = ref<number | null>(null)
const pinnedIndex = ref<number | null>(null)
const activeIndex = computed(() => pinnedIndex.value ?? hoverIndex.value)

const activeLabel = computed(() =>
  activeIndex.value === null ? '' : (props.labels[activeIndex.value] ?? ''),
)

const activeRows = computed(() => {
  const i = activeIndex.value
  if (i === null) return []
  return props.series.map((s) => ({ name: s.name, color: s.color, value: s.data[i] ?? 0 }))
})

const tooltipLeft = computed(() => {
  const i = activeIndex.value
  if (i === null) return '0%'
  return `${x(i)}%`
})

/** 靠右时把读数框翻到左边，靠左时贴左，避免被图表边缘裁掉 */
const tooltipFlip = computed(() => {
  const i = activeIndex.value
  return i !== null && x(i) > 62
})
const tooltipStart = computed(() => {
  const i = activeIndex.value
  return i !== null && x(i) < 14
})

function pick(event: MouseEvent) {
  const el = event.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const ratio = (event.clientX - rect.left) / Math.max(1, rect.width)
  const n = Math.max(1, props.labels.length - 1)
  hoverIndex.value = Math.min(props.labels.length - 1, Math.max(0, Math.round(ratio * n)))
}

function clearHover() {
  hoverIndex.value = null
}

function togglePin() {
  pinnedIndex.value = pinnedIndex.value === hoverIndex.value ? null : hoverIndex.value
}

/** 点到图表外面就把固定住的读数关掉 */
function closeOnOutside(event: PointerEvent) {
  if (pinnedIndex.value === null && hoverIndex.value === null) return
  const target = event.target as Node | null
  if (target && rootEl.value?.contains(target)) return
  // 点图表外面：固定的和悬停的都清掉，读数框立刻消失
  pinnedIndex.value = null
  hoverIndex.value = null
}

onMounted(() => document.addEventListener('pointerdown', closeOnOutside))
onBeforeUnmount(() => document.removeEventListener('pointerdown', closeOnOutside))
</script>

<template>
  <div ref="rootEl" class="line-chart">
    <div class="line-chart__y" :style="{ height: `${H}px` }">
      <span
        v-for="t in yTicks"
        :key="t.value"
        :style="{ top: `${PAD_TOP + ((H - PAD_TOP - PAD_BOTTOM) * t.top) / 100}px` }"
      >
        {{ t.value }}
      </span>
    </div>

    <div class="line-chart__plot" :style="{ height: `${H}px` }">
      <svg
        :viewBox="`0 0 100 ${H}`"
        preserveAspectRatio="none"
        class="line-chart__svg"
        @mousemove="pick"
        @mouseleave="clearHover"
        @click="togglePin"
      >
        <line
          v-for="ratio in [0, 0.5, 1]"
          :key="ratio"
          x1="0"
          x2="100"
          :y1="PAD_TOP + (H - PAD_TOP - PAD_BOTTOM) * ratio"
          :y2="PAD_TOP + (H - PAD_TOP - PAD_BOTTOM) * ratio"
          class="line-chart__grid"
        />

        <g v-for="s in series" :key="s.name">
          <path :d="areaPath(s.data)" :fill="s.color" class="line-chart__area" />
          <path :d="linePath(s.data)" :stroke="s.color" class="line-chart__line" />
        </g>

        <!-- 选中列的竖线 + 数据点 -->
        <g v-if="activeIndex !== null">
          <line
            :x1="x(activeIndex)"
            :x2="x(activeIndex)"
            :y1="PAD_TOP"
            :y2="H - PAD_BOTTOM"
            class="line-chart__cursor"
          />
          <line
            v-for="s in series"
            :key="`h-${s.name}`"
            x1="0"
            :x2="x(activeIndex)"
            :y1="y(s.data[activeIndex] ?? 0)"
            :y2="y(s.data[activeIndex] ?? 0)"
            :stroke="s.color"
            class="line-chart__guide"
          />
        </g>
      </svg>

      <span
        v-for="(s, si) in activeIndex === null ? [] : series"
        :key="`dot-${si}`"
        class="line-chart__dot"
        :style="{
          left: `${x(activeIndex as number)}%`,
          top: `${y(s.data[activeIndex as number] ?? 0)}px`,
        }"
      />

      <div
        v-if="activeIndex !== null"
        class="line-chart__tip"
        :class="{
          'line-chart__tip--flip': tooltipFlip,
          'line-chart__tip--start': tooltipStart,
        }"
        :style="{ left: tooltipLeft }"
      >
        <b>{{ activeLabel }}</b>
        <span v-for="row in activeRows" :key="row.name">
          <i :style="{ background: row.color }" />{{ row.name }}
          <em>{{ row.value }}</em>
        </span>
      </div>
    </div>

    <div class="line-chart__x">
      <span
        v-for="tick in ticks"
        :key="tick.i"
        :class="{
          'line-chart__x-first': tick.i === 0,
          'line-chart__x-last': tick.i === labels.length - 1,
        }"
        :style="{ left: `${(tick.i / Math.max(1, labels.length - 1)) * 100}%` }"
      >
        {{ tick.label }}
      </span>
    </div>

    <div v-if="showLegend" class="line-chart__legend">
      <span v-for="s in series" :key="s.name" class="line-chart__legend-item">
        <i :style="{ background: s.color }" />
        {{ s.name }}
      </span>
      <span class="line-chart__max">峰值 {{ maxValue }}</span>
    </div>
  </div>
</template>

<style scoped>
.line-chart {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  width: 100%;
}

.line-chart__y {
  position: relative;
  width: 30px;
  flex: 0 0 30px;
}

.line-chart__y span {
  position: absolute;
  right: 6px;
  transform: translateY(-50%);
  font-size: 0.62rem;
  color: #6f9b95;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.line-chart__plot {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
}

.line-chart__svg {
  width: 100%;
  height: 100%;
  display: block;
  overflow: visible;
  cursor: crosshair;
}

.line-chart__grid {
  stroke: rgba(126, 231, 205, 0.14);
  stroke-width: 0.25;
  stroke-dasharray: 1 1.4;
  vector-effect: non-scaling-stroke;
}

.line-chart__area {
  opacity: 0.14;
}

.line-chart__line {
  fill: none;
  stroke-width: 2;
  stroke-linejoin: round;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
}

.line-chart__guide {
  stroke-width: 1;
  stroke-dasharray: 2.5 2.5;
  opacity: 0.55;
  vector-effect: non-scaling-stroke;
}

.line-chart__dot {
  position: absolute;
  width: 7px;
  height: 7px;
  margin: -3.5px 0 0 -3.5px;
  border-radius: 50%;
  background: #ff5a68;
  box-shadow: 0 0 0 2px rgba(255, 90, 104, 0.25), 0 0 6px rgba(255, 90, 104, 0.6);
  pointer-events: none;
  z-index: 2;
}

.line-chart__cursor {
  stroke: rgba(126, 231, 205, 0.5);
  stroke-width: 1;
  stroke-dasharray: 2 2;
  vector-effect: non-scaling-stroke;
}

.line-chart__tip {
  position: absolute;
  top: 4px;
  transform: translateX(-50%);
  min-width: 96px;
  padding: 6px 9px;
  border-radius: 8px;
  background: rgba(8, 32, 38, 0.96);
  border: 1px solid rgba(126, 231, 205, 0.3);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
  font-size: 0.68rem;
  color: #cfe9e4;
  pointer-events: none;
  z-index: 3;
  white-space: nowrap;
}

.line-chart__tip--flip {
  transform: translateX(-100%);
  margin-left: -8px;
}

.line-chart__tip--start {
  transform: translateX(0);
}

.line-chart__tip b {
  display: block;
  margin-bottom: 3px;
  color: #7fb3ab;
  font-weight: 600;
}

.line-chart__tip span {
  display: flex;
  align-items: center;
  gap: 5px;
  line-height: 1.5;
}

.line-chart__tip i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex: 0 0 auto;
}

.line-chart__tip em {
  margin-left: auto;
  font-style: normal;
  color: #7ee7cd;
  font-variant-numeric: tabular-nums;
}

.line-chart__x {
  position: relative;
  width: calc(100% - 30px);
  margin-left: 30px;
  height: 16px;
  margin-top: 2px;
}

.line-chart__x span {
  position: absolute;
  transform: translateX(-50%);
  font-size: 0.66rem;
  color: #7fb3ab;
  white-space: nowrap;
}

/* 首尾刻度贴边，避免被裁掉半个日期 */
.line-chart__x-first {
  transform: translateX(0);
}

.line-chart__x-last {
  transform: translateX(-100%);
}

.line-chart__legend {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 4px;
  padding-left: 30px;
  font-size: 0.72rem;
  color: #9fc9c2;
}

.line-chart__legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.line-chart__legend-item i {
  width: 14px;
  height: 3px;
  border-radius: 2px;
}

.line-chart__max {
  margin-left: auto;
  color: #6f9b95;
}
</style>
