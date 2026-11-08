<!-- ====================================================================
  VolumeMenu —— 点右上角小喇叭弹出的音量面板
  两条独立的滑块：
    · 语音通话（芙芙说话的音量，作用于电话窗口里的 <audio>）
    · 背景音乐（public 下的 BGM，作用于 ChatView 的 <audio>）
  两者互不影响，静音只作用于背景音乐。
==================================================================== -->

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'

const props = defineProps<{
  bgmVolume: number
  voiceVolume: number
  bgmMuted: boolean
  voiceMuted: boolean
}>()

const emit = defineEmits<{
  'update:bgmVolume': [value: number]
  'update:voiceVolume': [value: number]
  'update:bgmMuted': [value: boolean]
  'update:voiceMuted': [value: boolean]
  close: []
}>()

const bgmSlider = computed({
  get: () => props.bgmVolume,
  set: (value: number) => emit('update:bgmVolume', value),
})

const voiceSlider = computed({
  get: () => props.voiceVolume,
  set: (value: number) => emit('update:voiceVolume', value),
})


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
      </div>

      <div class="menu-row">
        <button
          class="menu-ico menu-ico--btn"
          type="button"
          :class="{ 'menu-ico--off': voiceMuted }"
          :title="voiceMuted ? '点一下打开语音' : '点一下静音语音'"
          @click="emit('update:voiceMuted', !voiceMuted)"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.62 10.79a15.05 15.05 0 0 0 6.59 6.59l2.2-2.2a1 1 0 0 1 1.02-.24c1.12.37 2.33.57 3.57.57a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1C10.61 21 3 13.39 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.24.2 2.45.57 3.57a1 1 0 0 1-.25 1.02l-2.2 2.2z"/></svg>
        </button>
        <span class="menu-label">语音</span>
        <input
          v-model.number="voiceSlider"
          class="menu-slider"
          type="range"
          min="0"
          max="100"
          step="1"
          :disabled="voiceMuted"
          :aria-label="`语音音量 ${voiceVolume}%`"
        />
        <span class="menu-value">{{ voiceMuted ? '静音' : `${voiceVolume}%` }}</span>
      </div>

      <div class="menu-row">
        <button
          class="menu-ico menu-ico--btn"
          type="button"
          :class="{ 'menu-ico--off': bgmMuted }"
          :title="bgmMuted ? '点一下打开音乐' : '点一下静音音乐'"
          @click="emit('update:bgmMuted', !bgmMuted)"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z"/></svg>
        </button>
        <span class="menu-label">音乐</span>
        <input
          v-model.number="bgmSlider"
          class="menu-slider"
          type="range"
          min="0"
          max="100"
          step="1"
          :disabled="bgmMuted"
          :aria-label="`背景音乐音量 ${bgmVolume}%`"
        />
        <span class="menu-value">{{ bgmMuted ? '静音' : `${bgmVolume}%` }}</span>
      </div>

      <p class="menu-hint">点左边的图标可以单独静音语音或音乐。</p>
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
  width: 268px;
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

.menu-row {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 8px;
}
.menu-ico {
  display: grid;
  place-items: center;
  font-size: 0.9rem;
}
.menu-ico--btn {
  width: 26px;
  height: 26px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #46c98c;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, opacity 0.15s ease;
}
.menu-ico--btn svg {
  width: 16px;
  height: 16px;
  fill: currentColor;
}
.menu-ico--btn:hover { background: rgba(255, 253, 248, 0.14); }
/* 静音：图标变灰 + 一道斜杠 */
.menu-ico--btn.menu-ico--off {
  color: rgba(255, 253, 248, 0.35);
  position: relative;
}
.menu-ico--btn.menu-ico--off::after {
  content: '';
  position: absolute;
  left: 4px;
  right: 4px;
  top: 50%;
  height: 1.5px;
  background: #ff8f7a;
  transform: rotate(-45deg);
  border-radius: 1px;
}
.menu-label {
  width: 28px;
  font-size: 0.72rem;
  color: rgba(255, 253, 248, 0.7);
}

.menu-slider {
  flex: 1;
  min-width: 0;
  accent-color: #fffdf8;
  cursor: pointer;
}
.menu-slider:disabled { opacity: 0.45; cursor: not-allowed; }

.menu-value {
  width: 42px;
  text-align: right;
  font-size: 0.76rem;
  color: rgba(255, 253, 248, 0.8);
  font-variant-numeric: tabular-nums;
}

.menu-hint {
  margin: 10px 0 0;
  font-size: 0.66rem;
  line-height: 1.5;
  color: rgba(255, 253, 248, 0.45);
}

@media (prefers-reduced-motion: reduce) {
  .menu-pop { animation: none; }
}
</style>