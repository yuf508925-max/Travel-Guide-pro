<!-- ====================================================================
  MessageList —— 消息列表（红框里的上半部分）
  职责只有三件事：
    1. 把 messages 数组渲染成一左一右的气泡
    2. 每句话用 BubbleText 逐字"冒"出来
    3. 内容变化时自动滚到最底部（像微信那样）
==================================================================== -->

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import type { Message } from '../composables/useChatStream'
import BubbleText from './BubbleText.vue'

// messages 从父组件（ChatView）传进来，是聊天的完整记录
const props = withDefaults(
  defineProps<{
    messages?: Message[]
    // 整轮回复是否还没结束。现在没有闪烁光标了，所以界面暂时不读它，
    // 留着给以后做"正在输出"的视觉状态（比如气泡呼吸 / 暂停动画）
    isTyping?: boolean
    // 模型还在思考（正文一个字都没出来）时显示"芙芙正在思考…"
    isThinking?: boolean
    // 正在调工具时的一句提示（"正在查天气…"），有它就顶掉"正在思考"
    toolHint?: string
    // 切对话后的一整屏文字：全部直接显示，连最后一条也不要冒泡
    suppressAnimation?: boolean
  }>(),
  {
    messages: () => [],
    isTyping: false,
    isThinking: false,
    toolHint: '',
    suppressAnimation: false,
  }
)

// 整个滚动区域的 DOM 引用，用来控制滚动位置
const listRef = ref<HTMLElement | null>(null)

// ------------------------------------------------------------------
// 要渲染的消息：把"空的 AI 占位气泡"过滤掉。
//   useChatStream 在等后端第一个字时会先 push 一条 text 为空的 AI 消息，
//   如果直接渲染，用户会先看见一个空气泡闪一下。
//   这里等第一个字到了才让这一行挂载，气泡就能带着"啵"的动画从无到有。
//   index 当作 :key 用，保证追加文字时这一行不会被重建、动画不会重播。
// ------------------------------------------------------------------
const visibleMessages = computed(() =>
  props.messages
    .map((msg, index) => ({ msg, index }))
    .filter(({ msg }) => msg.role === 'user' || msg.text.length > 0)
)

// ------------------------------------------------------------------
// 滚到底部：只要有新内容（消息增加 / AI 文字变长）就执行
// nextTick：等 Vue 把新内容真正渲染到页面上之后再滚，否则滚不到位
// ------------------------------------------------------------------
watch(
  () => [props.messages.length, props.messages[props.messages.length - 1]?.text],
  async () => {
    await nextTick()
    const el = listRef.value
    if (el) el.scrollTop = el.scrollHeight   // 直接拉到最底
  }
)
</script>

<template>
  <div ref="listRef" class="msg-list">
    <!-- 还没聊过天时给一句引导，避免页面空荡荡 -->
    <p v-if="messages.length === 0" class="msg-empty">
      和芙芙打个招呼吧～
    </p>

    <!-- 每条消息一个气泡：role 决定靠左还是靠右 -->
    <div
      v-for="item in visibleMessages"
      :key="item.index"
      class="msg-row"
      :class="item.msg.role === 'user' ? 'msg-row--user' : 'msg-row--ai'"
    >
      <!-- AI 消息带个头像，用户消息就不放了（空间留给文字） -->
      <img v-if="item.msg.role === 'ai'" class="msg-avatar" src="/1790414746809.png" alt="" />

      <div class="msg-bubble" :class="item.msg.role === 'user' ? 'msg-bubble--user' : 'msg-bubble--ai'">
        <!-- 只有最新那条做「冒泡」；历史消息直接显示，
             否则切对话时整屏文字会把动画重播一遍，又卡又闪 -->
        <BubbleText
          :text="item.msg.text"
          :animated="!props.suppressAnimation && item.index >= props.messages.length - 1"
        />
      </div>
    </div>
    <!--
      思考中：推理模型会先"想"好几秒才吐正文，
      这段时间如果不给反馈，用户会以为卡死了。
      等第一个正文片段到达，isThinking 转 false，这个气泡自动消失。
    -->
    <div v-if="props.isThinking" class="msg-row msg-row--ai">
      <img class="msg-avatar" src="/1790414746809.png" alt="" />
      <div class="msg-bubble msg-bubble--ai msg-bubble--thinking">
        {{ props.toolHint || '芙芙正在思考' }}
        <span class="msg-dots"><i></i><i></i><i></i></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.msg-list {
  flex: 1;                 /* 吃掉聊天面板里除输入框以外的高度 */
  overflow-y: auto;        /* 消息多了纵向滚动 */
  padding: 20px 18px;
  display: flex;
  flex-direction: column;  /* 从上往下排 */
  gap: 14px;
}

.msg-empty {
  margin: auto;            /* 居中 */
  color: #7b8a85;
  font-size: 0.95rem;
}

/* ---- 每一行：决定气泡靠左还是靠右 ---- */
.msg-row {
  display: flex;
  align-items: flex-end;   /* 气泡和头像底对齐，更自然 */
  gap: 8px;
}
.msg-row--ai   { justify-content: flex-start; }  /* AI 在左 */
.msg-row--user { justify-content: flex-end; }    /* 用户在右 */

/* ---- AI 头像 ---- */
.msg-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid #fffdf8;
  flex: 0 0 auto;
  animation: avatar-pop 0.34s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes avatar-pop {
  from { opacity: 0; transform: scale(0.5) translateY(6px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}

/* ---- 气泡"啵"地弹出来 ----
   只在挂载时播一次；之后文字变长不会再重播（元素没重建）。
   左边尖角 → 从左下发散，右边尖角 → 从右下发散，方向感才对。 */
.msg-row--ai .msg-bubble {
  transform-origin: bottom left;
  animation: bubble-pop-left 0.44s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
.msg-row--user .msg-bubble {
  transform-origin: bottom right;
  animation: bubble-pop-right 0.44s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes bubble-pop-left {
  0%   { opacity: 0; transform: translate(-6px, 10px) scale(0.82); }
  60%  { opacity: 1; transform: translate(2px, -2px) scale(1.03); }
  100% { opacity: 1; transform: translate(0, 0) scale(1); }
}
@keyframes bubble-pop-right {
  0%   { opacity: 0; transform: translate(6px, 10px) scale(0.82); }
  60%  { opacity: 1; transform: translate(-2px, -2px) scale(1.03); }
  100% { opacity: 1; transform: translate(0, 0) scale(1); }
}

/* ---- 气泡本体 ---- */
.msg-bubble {
  max-width: 72%;                       /* 别撑满整行，留点呼吸感 */
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 0.95rem;
  line-height: 1.55;
  word-break: break-word;               /* 长英文/网址也能正常换行 */
  white-space: pre-wrap;                /* 保留换行符 */
}

/* AI 气泡：米白底、深字，和你登录页的卡片一个色系 */
.msg-bubble--ai {
  background: #fffdf8;
  color: #2f3e46;
  border: 1.5px solid #dfe7e2;
  border-top-left-radius: 4px;          /* 左上尖一点，表示"从这说话" */
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

/* 用户气泡：青绿底白字，和登录按钮同色 */
.msg-bubble--user {
  background: #2f7d6e;
  color: #fff;
  border-top-right-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.10);
}

/* ---- 思考中气泡：半透明的，和正式回复区分开 ---- */
.msg-bubble--thinking {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #7b8a85;
  background: rgba(255, 253, 248, 0.72);
  font-size: 0.92rem;
}

/* 三个跳动的小圆点 */
.msg-dots {
  display: inline-flex;
  gap: 3px;
  margin-left: 2px;
}
.msg-dots i {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #7b8a85;
  animation: dot-bounce 1.2s infinite ease-in-out;
}
.msg-dots i:nth-child(2) { animation-delay: 0.15s; }
.msg-dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes dot-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30%           { transform: translateY(-3px); opacity: 1; }
}

/* 系统开了"减少动态效果"：气泡直接出现，不要弹跳 */
@media (prefers-reduced-motion: reduce) {
  .msg-bubble,
  .msg-avatar {
    animation: none;
  }
}
</style>
