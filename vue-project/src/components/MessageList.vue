<!-- ====================================================================
  MessageList —— 消息列表（红框里的上半部分）
  职责只有两件事：
    1. 把 messages 数组渲染成一左一右的气泡
    2. 内容变化时自动滚到最底部（像微信那样）
==================================================================== -->

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { Message } from '../composables/useChatStream'

// messages 从父组件（ChatView）传进来，是聊天的完整记录
const props = withDefaults(
  defineProps<{
    messages?: Message[]
    isTyping?: boolean
    // 模型还在思考（正文一个字都没出来）时显示"芙芙正在思考…"
    isThinking?: boolean
  }>(),
  {
    messages: () => [],
    isTyping: false,
    isThinking: false,
  }
)

// 整个滚动区域的 DOM 引用，用来控制滚动位置
const listRef = ref<HTMLElement | null>(null)

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
      v-for="(msg, i) in messages"
      :key="i"
      class="msg-row"
      :class="msg.role === 'user' ? 'msg-row--user' : 'msg-row--ai'"
    >
      <!-- AI 消息带个头像，用户消息就不放了（空间留给文字） -->
      <img v-if="msg.role === 'ai'" class="msg-avatar" src="/1790414746809.png" alt="" />

      <div class="msg-bubble" :class="msg.role === 'user' ? 'msg-bubble--user' : 'msg-bubble--ai'">
        {{ msg.text }}
        <!-- AI 正在输出且轮到最后一条 AI 消息时，末尾闪一个光标 -->
        <span
          v-if="msg.role === 'ai' && isTyping && i === messages.length - 1"
          class="msg-cursor"
        ></span>
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
        芙芙正在思考
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

/* ---- AI 打字时的闪烁光标 ---- */
.msg-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 3px;
  vertical-align: -0.15em;
  background: #2f3e46;
  animation: cursor-blink 0.8s steps(1) infinite;
}
@keyframes cursor-blink {
  50% { opacity: 0; }
}
</style>
