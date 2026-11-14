<script setup lang="ts">
// =====================================================================
// ClockWidget —— 左上角的数字时钟
//   大字：时:分      小字：秒（贴着基线右下）
//   下面一行：2026/11/11 星期三
// 只显示，不交互，所以整块 pointer-events: none，不会挡住 Live2D 的点击。
// =====================================================================

import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const now = ref(new Date())
let intervalId = 0
let timeoutId = 0

const pad = (n: number) => String(n).padStart(2, '0')

const hhmm = computed(() => `${pad(now.value.getHours())}:${pad(now.value.getMinutes())}`)
const seconds = computed(() => pad(now.value.getSeconds()))

const dateText = computed(() => {
  const d = now.value
  const week = '日一二三四五六'[d.getDay()]
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} 星期${week}`
})

function tick() {
  now.value = new Date()
}

onMounted(() => {
  tick()
  // 先对齐到下一个整秒再开 interval，避免秒数跳得忽快忽慢
  timeoutId = window.setTimeout(() => {
    tick()
    intervalId = window.setInterval(tick, 1000)
  }, 1000 - (Date.now() % 1000))
})

onBeforeUnmount(() => {
  window.clearTimeout(timeoutId)
  window.clearInterval(intervalId)
})
</script>

<template>
  <div class="clock" aria-hidden="true">
    <p class="clock__time">
      <span class="clock__hm">{{ hhmm }}</span>
      <span class="clock__sec">{{ seconds }}</span>
    </p>
    <p class="clock__date">{{ dateText }}</p>
  </div>
</template>

<style scoped>
.clock {
  position: absolute;
  left: 30px;
  top: 22px;
  z-index: 6;
  pointer-events: none;
  user-select: none;
  color: #b7f3ff;
  font-family: 'DIN Alternate', 'Bahnschrift', 'Segoe UI Variable Display', 'Segoe UI', system-ui,
    sans-serif;
  font-variant-numeric: tabular-nums;
  text-shadow:
    0 0 14px rgba(120, 232, 255, 0.55),
    0 0 34px rgba(74, 196, 255, 0.35);
}

.clock__time {
  margin: 0;
  display: flex;
  align-items: baseline;
  gap: 6px;
  line-height: 1;
}

.clock__hm {
  font-size: clamp(34px, 3.4vw, 48px);
  font-weight: 500;
  letter-spacing: 0.02em;
}

/* 秒数小一截，和数字底部对齐，像图里那样挂在右下角 */
.clock__sec {
  font-size: clamp(12px, 1.05vw, 15px);
  font-weight: 500;
  letter-spacing: 0.08em;
  color: rgba(183, 243, 255, 0.82);
  transform: translateY(-2px);
}

.clock__date {
  margin: 6px 0 0 2px;
  font-size: clamp(11px, 0.92vw, 13.5px);
  letter-spacing: 0.08em;
  color: rgba(200, 246, 255, 0.72);
  text-shadow: 0 0 12px rgba(120, 232, 255, 0.35);
}

@media (max-width: 900px) {
  .clock {
    left: 16px;
    top: 14px;
  }
}
</style>
