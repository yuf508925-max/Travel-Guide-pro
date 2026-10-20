<script setup lang="ts">
const props = defineProps({
  src: { type: String, default: '/ocean.mp4' },   // 视频路径
  poster: { type: String, default: '/ocean.png' },  // 加载完成前的兜底图
  brightness: { type: Number, default: 0.8 },       // 亮度，越小越暗
  showWaves: { type: Boolean, default: true }       // 是否叠加海浪
})
</script>

<template>
  <div class="ocean-bg">
    <video
      class="ocean-bg__video"
      :src="props.src"
      :poster="props.poster"
      :style="{ filter: `brightness(${props.brightness}) saturate(1.05)` }"
      autoplay muted loop playsinline preload="auto"
      disablepictureinpicture
      controlslist="nodownload noplaybackrate nofullscreen"
    ></video>

    <div class="ocean-bg__mask"></div>

    <template v-if="props.showWaves">
      <div class="ocean-bg__wave ocean-bg__wave--front"></div>
      <div class="ocean-bg__wave ocean-bg__wave--back"></div>
    </template>
  </div>
</template>

<style scoped>
.ocean-bg {
  position: fixed;
  inset: 0;
  z-index: -2;               /* 沉在最底层，不影响任何页面内容 */
  pointer-events: none;      /* 不拦截鼠标 */
  overflow: hidden;
  background: url('/ocean.png') center / cover no-repeat;  /* 视频加载前的底图 */
}

.ocean-bg__video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;         /* 铺满不变形 */
}

/* 压暗一层，让登录框和文字更清楚 */
.ocean-bg__mask {
  position: absolute;
  inset: 0;
  background: rgba(6, 40, 66, 0.22);
}

/* ===== 两层海浪 ===== */
/* .ocean-bg__wave {
  position: absolute;
  left: 0;
  right: 0;
  background-repeat: repeat-x;
  background-position: 0 bottom;
} */

.ocean-bg__wave--front {
  bottom: 0;
  height: 180px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 120' preserveAspectRatio='none'%3E%3Cpath d='M0,60 C150,120 350,0 600,60 C850,120 1050,0 1200,60 L1200,120 L0,120 Z' fill='%23ffffff' fill-opacity='0.28'/%3E%3C/svg%3E");
  background-size: 1200px 160px;
  animation: wave-slide 10s linear infinite;
}

.ocean-bg__wave--back {
  bottom: 24px;
  height: 180px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 120' preserveAspectRatio='none'%3E%3Cpath d='M0,60 C150,120 350,0 600,60 C850,120 1050,0 1200,60 L1200,120 L0,120 Z' fill='%23ffffff' fill-opacity='0.16'/%3E%3C/svg%3E");
  background-size: 1200px 120px;
  animation: wave-slide 16s linear infinite reverse;
}

@keyframes wave-slide {
  from { background-position-x: 0; }
  to   { background-position-x: -1200px; }
}

@media (prefers-reduced-motion: reduce) {
  .ocean-bg__wave { animation: none; }
}

/* 手机端省流量：不加载视频，只显示底图 */
@media (max-width: 768px) {
  .ocean-bg__video { display: none; }
}
</style>
