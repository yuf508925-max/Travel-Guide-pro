<!-- ====================================================================
  VolumeMenu —— 点右上角小喇叭弹出的音量面板
  以前滑块直接摆在导航条里，太占地方；现在收进这个小窗口。
  只负责"调数值"，真正的音量由 ChatView 的 applyVolume() 写进 <audio>。
==================================================================== -->

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'

const props = defineProps<{
  volume: number
  muted: boolean
}>()

const emit = defineEmits<{
  'update:volume': [value: number]
  'update:muted': [value: boolean]
  close: []
}>()

// 用 computed 当 v-model 的桥：滑块动一下就把新值 emit 给父组件
const slider = computed({
  get: () => props.volume,
  set: (value: number) => emit('update:volume', value),
})

function toggleMute() {
  emit('update:muted', !props.muted)
}

// Esc 关闭，和别的弹窗保持一致
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="menu-layer">
    <div class="menu-backdrop" @click="emit('close')"></div>

    <div class="menu-pop" role="dialog" aria-label="音量">
      <div class="menu-head">
        <span class="menu-title">音量</span>
        <button
          class="menu-mute"
          type="button"
          :class="{ 'menu-mute--on': muted }"
          @click="toggleMute"
        >
          {{ muted ? '取消静音' : '静音' }}
        </button>
      </div>

      <div class="menu-row">
        <span class="menu-ico" aria-hidden="true">{{ muted ? '🔇' : '🔊' }}</span>
        <input
          v-model.number="slider"
          class="menu-slider"
          type="range"
          min="0"
          max="100"
          step="1"
          :disabled="muted"
          :aria-label="`音量 ${volume}%`"
        />
        <span class="menu-value">{{ muted ? '静音' : `${volume}%` }}</span>
      </div>

      <p class="menu-hint">现在控制的是背景音乐；以后接上语音通话，同一个数值也管那边的声音。</p>
    </div>
  </div>
</template>

<style scoped>
.menu-layer {
  position: absolute;
  top: calc(100% + 14px);
  right: 0;
  z-index: 60;
}

.menu-backdrop {
  position: fixed;
  inset: 0;
  z-index: 0;
}

.menu-pop {
  position: relative;
  z-index: 1;
  width: 260px;
  padding: 12px 14px;
  box-sizing: border-box;
  border: 1.5px solid rgba(255, 253, 248, 0.4);
  border-radius: 14px;
  background: rgba(12, 46, 46, 0.94);
  backdrop-filter: blur(14px);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.38);
  color: #fffdf8;
  animation: menu-in 0.2s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes menu-in {
  from { opacity: 0; transform: translateY(-6px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.menu-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.menu-title {
  font-size: 0.95rem;
  font-weight: 500;
  letter-spacing: 0.04em;
}
.menu-mute {
  height: 24px;
  padding: 0 10px;
  border: 1px solid rgba(255, 253, 248, 0.35);
  border-radius: 12px;
  background: transparent;
  color: rgba(255, 253, 248, 0.85);
  font-size: 0.76rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}
.menu-mute:hover { background: rgba(255, 253, 248, 0.14); }
.menu-mute--on {
  background: rgba(255, 253, 248, 0.9);
  border-color: transparent;
  color: #2f7d6e;
}

.menu-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.menu-ico { font-size: 0.95rem; }

.menu-slider {
  flex: 1;
  min-width: 0;
  accent-color: #fffdf8;
  cursor: pointer;
}
.menu-slider:disabled { opacity: 0.45; cursor: not-allowed; }

.menu-value {
  width: 40px;
  text-align: right;
  font-size: 0.8rem;
  color: rgba(255, 253, 248, 0.8);
}

.menu-hint {
  margin: 10px 0 0;
  font-size: 0.68rem;
  line-height: 1.5;
  color: rgba(255, 253, 248, 0.45);
}

@media (prefers-reduced-motion: reduce) {
  .menu-pop { animation: none; }
}
</style>
