<!-- 环形图（SVG stroke-dasharray 拼弧）——调用构成占比 -->
<script setup lang="ts">
import { computed } from 'vue'

interface Item {
  label: string
  count: number
  color?: string
}

const props = withDefaults(
  defineProps<{
    items: Item[]
    /** 环的外径（px） */
    size?: number
    centerLabel?: string
  }>(),
  {
    size: 120,
    centerLabel: '总计',
    colors: undefined as unknown as string[],
  },
)

const palette = ['#7ee7cd', '#7fc3e8', '#ffc478', '#c8a6ff', '#ff9fa8', '#9ae6a0', '#f2d97f']

const total = computed(() => props.items.reduce((sum, i) => sum + i.count, 0))

const R = 42
const CIRC = 2 * Math.PI * R

const arcs = computed(() => {
  let offset = 0
  return props.items.map((item, index) => {
    const ratio = total.value ? item.count / total.value : 0
    const length = ratio * CIRC
    const arc = {
      label: item.label,
      count: item.count,
      ratio,
      color: item.color ?? palette[index % palette.length],
      dash: `${length} ${CIRC - length}`,
      offset: -offset,
    }
    offset += length
    return arc
  })
})
</script>

<template>
  <div class="donut">
    <svg :width="size" :height="size" viewBox="0 0 100 100" class="donut__svg">
      <circle cx="50" cy="50" :r="R" class="donut__track" />

      <circle
        v-for="arc in arcs"
        :key="arc.label"
        cx="50"
        cy="50"
        :r="R"
        fill="none"
        :stroke="arc.color"
        stroke-width="12"
        :stroke-dasharray="arc.dash"
        :stroke-dashoffset="arc.offset"
        class="donut__arc"
      />

      <text x="50" y="47" text-anchor="middle" class="donut__value">{{ total }}</text>
      <text x="50" y="61" text-anchor="middle" class="donut__caption">{{ centerLabel }}</text>
    </svg>

    <ul class="donut__legend">
      <li v-for="arc in arcs" :key="arc.label">
        <i :style="{ background: arc.color }" />
        <span class="donut__name">{{ arc.label }}</span>
        <span class="donut__count">{{ arc.count }}</span>
        <span class="donut__percent">{{ total ? Math.round(arc.ratio * 100) : 0 }}%</span>
      </li>
      <li v-if="!arcs.length" class="donut__empty">还没有数据</li>
    </ul>
  </div>
</template>

<style scoped>
.donut {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.donut__svg {
  transform: rotate(-90deg);
  flex: none;
}

.donut__track {
  fill: none;
  stroke: rgba(126, 231, 205, 0.12);
  stroke-width: 12;
}

.donut__arc {
  transition: stroke-dasharray 0.35s ease;
}

.donut__value {
  transform: rotate(90deg);
  transform-origin: 50px 50px;
  fill: #d9fbf2;
  font-size: 15px;
  font-weight: 700;
}

.donut__caption {
  transform: rotate(90deg);
  transform-origin: 50px 50px;
  fill: #7fb3ab;
  font-size: 8px;
}

.donut__legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 0.74rem;
  color: #b9e3da;
  min-width: 120px;
}

.donut__legend li {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) 34px 34px;
  align-items: center;
  gap: 6px;
}

.donut__legend i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}

.donut__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.donut__count,
.donut__percent {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: #8fc0b8;
}

.donut__empty {
  grid-template-columns: 1fr;
  color: #7fa8a3;
}
</style>
