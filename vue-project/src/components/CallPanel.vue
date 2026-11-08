<!-- ====================================================================
  CallPanel —— 点「和芙芙打电话」弹出的准备窗口（风格同天气小窗）
  只有在这里点「拨出电话」才会真正开始通话；
  下面固定一行提示：语音会让 AI 回复变慢。
==================================================================== -->

<script setup lang="ts">
const emit = defineEmits<{
  dial: []
  close: []
}>()
</script>

<template>
  <div class="call-layer">
    <!-- 透明遮罩：点窗口外面就关掉 -->
    <div class="call-backdrop" @click="emit('close')"></div>

    <div class="call-pop" role="dialog" aria-label="和芙芙打电话">
      <header class="call-head">
        <span class="call-title">和芙芙打电话</span>
        <button class="call-close" type="button" aria-label="关闭" @click="emit('close')">
          ×
        </button>
      </header>

      <div class="call-body">
        <div class="call-avatar" aria-hidden="true">芙</div>
        <p class="call-name">芙宁娜</p>
        <p class="call-desc">
          拨出之后可以和芙芙聊天。
        </p>

        <button class="call-dial" type="button" @click="emit('dial')">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6.62 10.79a15.05 15.05 0 0 0 6.59 6.59l2.2-2.2a1 1 0 0 1 1.02-.24c1.12.37 2.33.57 3.57.57a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1C10.61 21 3 13.39 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.24.2 2.45.57 3.57a1 1 0 0 1-.25 1.02l-2.2 2.2z" />
          </svg>
          拨出电话
        </button>

        <p class="call-note">使用语音功能会使芙芙回复变慢</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 定位在顶部导航条下方（父组件 .chat-nav-wrap 是 relative） */
.call-layer {
  position: absolute;
  top: calc(100% + 12px);
  left: 0;
  z-index: 60;
}

.call-backdrop {
  position: fixed;
  inset: 0;
  z-index: 0;
}

.call-pop {
  position: relative;
  z-index: 1;
  width: min(380px, calc(100vw - 40px));
  padding: 14px 16px 12px;
  box-sizing: border-box;
  border: 1.5px solid rgba(255, 253, 248, 0.4);
  border-radius: 16px;
  background: rgba(12, 46, 46, 0.92);
  backdrop-filter: blur(14px);
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.38);
  color: #fffdf8;
  animation: call-in 0.22s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes call-in {
  from { opacity: 0; transform: translateY(-8px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.call-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.call-title {
  font-size: 1rem;
  font-weight: 500;
  letter-spacing: 0.04em;
}
.call-close {
  margin-left: auto;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 253, 248, 0.85);
  font-size: 1.05rem;
  line-height: 1;
  cursor: pointer;
}
.call-close:hover { background: rgba(255, 253, 248, 0.14); }

.call-body {
  text-align: center;
  padding: 4px 2px 2px;
}

.call-avatar {
  width: 68px;
  height: 68px;
  margin: 6px auto 8px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 1.5rem;
  color: #fffdf8;
  background: radial-gradient(circle at 32% 28%, #7fc3e8, #2f6b8a 62%, #1d3f57);
  box-shadow: 0 0 0 3px rgba(255, 253, 248, 0.18);
}

.call-name {
  margin: 0;
  font-size: 0.95rem;
}
.call-desc {
  margin: 6px auto 12px;
  max-width: 300px;
  font-size: 0.74rem;
  line-height: 1.6;
  color: rgba(255, 253, 248, 0.55);
}

.call-dial {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: 38px;
  padding: 0 22px;
  border: none;
  border-radius: 19px;
  background: #2f7d6e;
  color: #ffffff;
  font-size: 0.88rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.18s ease;
}
.call-dial:hover { background: #256354; }
.call-dial svg {
  width: 16px;
  height: 16px;
  fill: currentColor;
}

.call-note {
  margin: 10px 0 0;
  font-size: 0.68rem;
  color: rgba(255, 253, 248, 0.42);
}

@media (prefers-reduced-motion: reduce) {
  .call-pop { animation: none; }
}
</style>