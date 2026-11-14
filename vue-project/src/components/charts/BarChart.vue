<!-- 横向条形图（纯 CSS，宽度按最大值百分比）——各接口调用量对比 -->
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
    /** 柱子配色循环；item.color 优先 */
    colors?: string[]
  }>(),
  {
    colors: () => ['#7ee7cd', '#7fc3e8', '#ffc478', '#c8a6ff', '#ff9fa8', '#9ae6a0'],
  },
)

const max = computed(() => Math.max(1, ...props.items.map((i) => i.count)))

function color(item: Item, index: number): string {
  const palette = props.colors ?? []
  return item.color ?? palette[index % Math.max(1, palette.length)] ?? '#7ee7cd'
}
</script>

<template>
  <div class="bar-chart">
    <div v-for="(item, index) in items" :key="item.label" class="bar-chart__row">
      <span class="bar-chart__label" :title="item.label">{{ item.label }}</span>

      <div class="bar-chart__track">
        <div
          class="bar-chart__fill"
          :style="{
            width: `${Math.max(2, (item.count / max) * 100)}%`,
            background: `linear-gradient(90deg, ${color(item, index)}55, ${color(item, index)})`,
          }"
        />
      </div>

      <span class="bar-chart__count">{{ item.count }}</span>
    </div>

    <p v-if="!items.length" class="bar-chart__empty">还没有调用记录</p>
  </div>
</template>

<style scoped>
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bar-chart__row {
  display: grid;
  grid-template-columns: 74px minmax(0, 1fr) 44px;
  align-items: center;
  gap: 10px;
}

.bar-chart__label {
  font-size: 0.76rem;
  color: #a6d6cd;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bar-chart__track {
  height: 10px;
  border-radius: 999px;
  background: rgba(126, 231, 205, 0.1);
  overflow: hidden;
}

.bar-chart__fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.35s ease;
}

.bar-chart__count {
  text-align: right;
  font-size: 0.76rem;
  color: #d6f4ec;
  font-variant-numeric: tabular-nums;
}

.bar-chart__empty {
  margin: 6px 0;
  font-size: 0.76rem;
  color: #7fa8a3;
}
</style>
