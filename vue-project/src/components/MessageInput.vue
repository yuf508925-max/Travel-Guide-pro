<!-- ====================================================================
  MessageInput —— 输入框 + 发送按钮
  两种模式，用右侧的小按钮切换（放在模型切换旁边）：
    · 打字（默认）：普通 textarea，Enter 发送
    · 说话：左边变成一个「点击说话」按钮，点一下开始识别，说完自动发送
==================================================================== -->

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import ModelSwitcher from './ModelSwitcher.vue'

const emit = defineEmits(['send'])

const props = defineProps({
  disabled: { type: Boolean, default: false },
})

const draft = ref('')
const mode = ref<'text' | 'voice'>('text')
const listening = ref(false)
const hint = ref('')

let recognition: any = null

function handleSend() {
  if (props.disabled) return
  const text = draft.value.trim()
  if (!text) return
  emit('send', text)
  draft.value = ''
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// ---------------- 语音说话：第一下开始，第二下结束 ----------------
// 浏览器经常在"停一下"的时候自己结束识别（静音 5 秒左右），
// 所以这里用一个 shouldListen 标记：只要用户没点第二下，就自动重启继续录，
// 真正结束时（第二下点击）才把整段文字发出去。
const voiceText = ref('')
let shouldListen = false

function buildRecognition(Recognition: any) {
  const rec = new Recognition()
  rec.lang = 'zh-CN'
  rec.interimResults = true
  rec.continuous = true

  rec.onresult = (event: any) => {
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i]
      if (result.isFinal) voiceText.value += result[0]?.transcript ?? ''
    }
  }

  // 浏览器自己结束：还在录就重启，保证"第二下"才是终点
  rec.onend = () => {
    if (shouldListen) {
      try {
        rec.start()
        return
      } catch {
        // 重启失败就走结束流程
      }
    }
    finishTalk()
  }

  rec.onerror = (event: any) => {
    const code = String(event?.error ?? '')
    // 没有声音就继续听，不算错误
    if (code === 'no-speech' && shouldListen) {
      try {
        rec.start()
      } catch {
        finishTalk()
      }
      return
    }
    if (voiceText.value.trim()) {
      finishTalk()
      return
    }
    shouldListen = false
    listening.value = false
    recognition = null
    const messages: Record<string, string> = {
      'not-allowed': '浏览器拒绝了麦克风权限：点地址栏的锁允许麦克风，或改用打字',
      'service-not-allowed': '这个页面不允许用语音识别（需要 https 或 localhost）',
      network: '语音识别服务连不上（Chrome 的识别要访问 Google，国内网络常失败），改用打字吧',
      'audio-capture': '没找到麦克风设备',
      'no-speech': '没听到声音，点一下再说一次',
      aborted: '',
    }
    hint.value = messages[code] ?? `语音识别出错（${code || '未知'}），改用打字吧`
  }

  return rec
}

function finishTalk() {
  if (!listening.value) return
  shouldListen = false
  listening.value = false
  const text = voiceText.value.trim()
  voiceText.value = ''
  recognition = null
  if (text) emit('send', text)
}

/** 第一下开始，第二下结束（结束就把听到的话发出去） */
function toggleTalk() {
  if (props.disabled) return

  if (listening.value) {
    shouldListen = false
    try {
      recognition?.stop()
    } catch {
      finishTalk()
    }
    return
  }

  const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!Recognition) {
    hint.value = '这个浏览器不支持语音识别，切回打字吧'
    return
  }

  hint.value = ''
  voiceText.value = ''
  shouldListen = true
  listening.value = true
  recognition = buildRecognition(Recognition)
  try {
    recognition.start()
  } catch (err) {
    shouldListen = false
    listening.value = false
    recognition = null
    hint.value = '麦克风没启动起来，检查一下浏览器权限'
  }
}

function stopListening() {
  shouldListen = false
  if (recognition) {
    try { recognition.abort() } catch { /* ignore */ }
    recognition = null
  }
  listening.value = false
  voiceText.value = ''
}

function toggleMode() {
  if (props.disabled) return
  if (mode.value === 'text') {
    mode.value = 'voice'
    hint.value = ''
  } else {
    stopListening()
    mode.value = 'text'
  }
}

onBeforeUnmount(stopListening)
</script>

<template>
  <div class="msg-input">
    <div class="msg-input__field">
      <textarea
        v-if="mode === 'text'"
        v-model="draft"
        class="msg-input__box"
        rows="3"
        placeholder="和芙芙聊聊你的旅行计划…（Enter 发送，Shift+Enter 换行）"
        :disabled="props.disabled"
        @keydown="onKeydown"
      ></textarea>

      <button
        v-else
        class="msg-input__talk"
        :class="{ 'msg-input__talk--on': listening }"
        type="button"
        :disabled="props.disabled"
        @click="toggleTalk"
      >
        <span class="msg-input__talk-icon" aria-hidden="true">🎤</span>
        <span class="msg-input__talk-text">
          {{ listening ? (voiceText || '正在听…（点第二下结束）') : '点击说话' }}
        </span>
      </button>
    </div>

    <div class="msg-input__actions">
      <div class="msg-input__tools">
        <button
          class="msg-input__mode"
          type="button"
          :class="{ 'msg-input__mode--voice': mode === 'voice' }"
          :title="mode === 'text' ? '切换到语音说话' : '切换回打字'"
          :disabled="props.disabled"
          @click="toggleMode"
        >
          {{ mode === 'text' ? '🎤' : '⌨️' }}
        </button>
        <ModelSwitcher :disabled="props.disabled" />
      </div>

      <button
        v-if="mode === 'text'"
        class="msg-input__send"
        :disabled="props.disabled"
        @click="handleSend"
      >
        {{ props.disabled ? '芙芙输入中…' : '发送' }}
      </button>
    </div>

    <p v-if="hint" class="msg-input__hint">{{ hint }}</p>
  </div>
</template>

<style scoped>
.msg-input {
  position: relative;
  flex: 0 0 auto;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 12px 14px;
  border-top: 1.5px solid #dfe7e2;
}

.msg-input__field {
  flex: 1;
  min-width: 0;
  display: flex;
}

/* ---- 输入框 ---- */
.msg-input__box {
  flex: 1;
  box-sizing: border-box;
  resize: none;
  border: 1px solid #c9d2cd;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 0.95rem;
  font-family: inherit;
  color: #2f3e46;
  outline: none;
  transition: border-color 0.2s;
}
.msg-input__box:focus { border-color: #2f7d6e; }
.msg-input__box:disabled { background: #f2f5f3; cursor: not-allowed; }

/* ---- 语音模式的大按钮 ---- */
.msg-input__talk {
  flex: 1;
  min-height: 84px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1.5px dashed #9dc4b8;
  border-radius: 10px;
  background: #f5faf8;
  color: #2f7d6e;
  font-size: 0.95rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}
.msg-input__talk:hover:not(:disabled) { background: #ebf6f1; }
.msg-input__talk--on {
  border-color: #2f7d6e;
  border-style: solid;
  background: #e3f3ec;
  color: #1f5c50;
}
.msg-input__talk:disabled { opacity: 0.55; cursor: not-allowed; }
.msg-input__talk-icon { font-size: 1.1rem; flex: 0 0 auto; }
.msg-input__talk-text {
  max-width: 80%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.9rem;
}

/* ---- 右侧操作列 ---- */
.msg-input__actions {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}
.msg-input__tools {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 切换「说话 / 打字」的小按钮：就放在模型切换旁边 */
.msg-input__mode {
  flex: 0 0 auto;
  width: 38px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 1px solid #c9d2cd;
  border-radius: 9px;
  background: #fff;
  font-size: 0.95rem;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}
.msg-input__mode:hover:not(:disabled) { background: #f2f5f3; }
.msg-input__mode--voice {
  border-color: #2f7d6e;
  background: #e3f3ec;
}
.msg-input__mode:disabled { opacity: 0.55; cursor: not-allowed; }

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

/* ---- 提示 ---- */
.msg-input__hint {
  position: absolute;
  left: 14px;
  bottom: 4px;
  margin: 0;
  font-size: 0.68rem;
  color: #b4553f;
}
</style>