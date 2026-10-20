<!-- ====================================================================
  MessageInput —— 输入框 + 发送按钮（红框里的下半部分）
  职责：
    1. 收集用户输入的文字
    2. 回车（或点发送）时把内容抛给父组件 —— 自己不发请求
==================================================================== -->

<script setup lang="ts">
import { ref } from 'vue'

// 父组件用 @send="sendMessage" 来接这里抛出去的内容
const emit = defineEmits(['send'])

// disabled：AI 正在回复时为 true，此时输入框和按钮都不可用，防止连发
const props = defineProps({
  disabled: { type: Boolean, default: false },
})

// 输入框里当前的文字（v-model 双向绑定到 textarea）
const draft = ref('')

// ------------------------------------------------------------------
// handleSend：真正发送的动作
// ------------------------------------------------------------------
function handleSend() {
  if (props.disabled) return                 // 正在回复中，不允许发送
  const text = draft.value.trim()
  if (!text) return                          // 空白内容不发送
  emit('send', text)                         // 把文字交给父组件
  draft.value = ''                           // 清空输入框，准备下一句
}

// ------------------------------------------------------------------
// 键盘事件：Enter 发送，Shift + Enter 换行（聊天软件的通用习惯）
// ------------------------------------------------------------------
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()      // 拦掉 textarea 默认的"回车=换行"
    handleSend()
  }
  // 按住 Shift 的回车不拦，走 textarea 原生的换行
}
</script>

<template>
  <div class="msg-input">
    <!--
      想做成"输入多少行就长多高"的话：
      在 @input 里量一下 scrollHeight，再赋给 style.height 即可
    -->
    <textarea
      v-model="draft"
      class="msg-input__box"
      rows="3"
      placeholder="和芙芙聊聊你的旅行计划…（Enter 发送，Shift+Enter 换行）"
      :disabled="props.disabled"
      @keydown="onKeydown"
    ></textarea>

    <button class="msg-input__send" :disabled="props.disabled" @click="handleSend">
      {{ props.disabled ? '芙芙输入中…' : '发送' }}
    </button>
  </div>
</template>

<style scoped>
.msg-input {
  flex: 0 0 auto;          /* 高度固定，不参与滚动（滚动是消息列表的事） */
  display: flex;
  align-items: flex-end;   /* 按钮贴着输入框底部 */
  gap: 10px;
  padding: 12px 14px;
  border-top: 1.5px solid #dfe7e2;   /* 和消息列表之间一条分隔线 */
}

/* ---- 输入框 ---- */
.msg-input__box {
  flex: 1;                 /* 占满除按钮以外的宽度 */
  box-sizing: border-box;
  resize: none;            /* 禁止拖右下角调整大小（会破坏布局） */
  border: 1px solid #c9d2cd;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 0.95rem;
  font-family: inherit;    /* textarea 默认不是页面字体，手动统一 */
  color: #2f3e46;
  outline: none;
  transition: border-color 0.2s;
}
.msg-input__box:focus { border-color: #2f7d6e; }
.msg-input__box:disabled { background: #f2f5f3; cursor: not-allowed; }

/* ---- 发送按钮 ---- */
.msg-input__send {
  flex: 0 0 auto;
  height: 42px;
  padding: 0 20px;
  border: none;
  border-radius: 10px;
  background: #2f7d6e;
  color: #fff;
  font-size: 0.98rem;
  cursor: pointer;
  transition: background 0.2s;
}
.msg-input__send:hover:not(:disabled) { background: #256354; }
.msg-input__send:disabled { opacity: 0.55; cursor: not-allowed; }
</style>
