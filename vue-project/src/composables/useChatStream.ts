// =====================================================================
// useChatStream —— 聊天数据的核心逻辑（组合式函数 / composable）
// ---------------------------------------------------------------------
// 为什么单独抽一个文件？
//   ChatView.vue 只管"长什么样"（布局、颜色），
//   这里只管"怎么聊"（发消息、收回复、维护消息列表）。
//   以后接真后端时只改这一个文件，界面一行都不用动。
// =====================================================================

import { onBeforeUnmount, ref } from 'vue'

// 导出给组件复用（MessageList.vue 用它标注 props 类型）
export interface Message {
  role: 'user' | 'ai'
  text: string
}

// ----------------------------------------------------------------------
// 逐字输出的节奏（关键！）
//   后端是一段一段推过来的（实测平均每段 7~8 字、间隔 0.1 秒），
//   直接追加会"成块刷屏"，没有打字机感。
//   所以这里改成：先存进队列，再按固定速度一个字一个字放出来。
//   将来接 TTS 时，只要在"放出每个字"的钩子上同时触发朗读，
//   就能做到"说一个字、显示一个字"。
// ----------------------------------------------------------------------
const TICK_MS = 50          // 每 50ms 放一次字
const CHARS_PER_TICK = 1    // 正常速度：每次 1 字 → 约 20 字/秒
const QUEUE_SLACK = 60      // 队列积压超过这个数就自动加速，避免长回复等太久

export function useChatStream(options?: {
  // 每放出一个字就回调一次 —— 接 TTS 时把朗读逻辑挂在这里
  onChar?: (ch: string) => void
}) {
  // ------------------------------------------------------------------
  // messages：聊天记录数组，MessageList.vue 直接拿着渲染
  // ------------------------------------------------------------------
  const messages = ref<Message[]>([])

  // isTyping：整轮回复是否还没结束（决定输入框能不能用）
  const isTyping = ref(false)

  // isThinking：模型是否还在"思考"（推理模型会先思考几秒才吐正文）
  //   true 时前端显示"芙芙正在思考…"，避免开头几秒一片空白
  const isThinking = ref(false)

  // 思考过程的原文（默认不展示，留着调试或以后做"展开思考过程"）
  const thinkingText = ref('')

  // ---- 逐字输出的内部状态 ----
  let queue: string[] = []                  // 待显示的字符队列
  let target: Message | null = null         // 当前正在"长出来"的那条 AI 消息
  let timer: ReturnType<typeof setInterval> | null = null
  let drained: (() => void) | null = null   // 队列放完后的通知

  // 把一段文字排进队列，并启动消费
  function enqueue(text: string, into: Message) {
    if (!text) return
    target = into
    for (const ch of text) queue.push(ch)
    startConsumer()
  }

  function startConsumer() {
    if (timer) return
    timer = setInterval(() => {
      // 队列空了：收工，并通知等待方
      if (queue.length === 0 || !target) {
        stopConsumer()
        const cb = drained
        drained = null
        cb?.()
        return
      }
      // 积压太多就自动加速，保证 1 秒左右能追上，不至于让人干等
      let n = CHARS_PER_TICK
      if (queue.length > QUEUE_SLACK) {
        n = Math.ceil((queue.length - QUEUE_SLACK) / 20) + CHARS_PER_TICK
      }
      let out = ''
      for (let i = 0; i < n && queue.length > 0; i++) out += queue.shift()
      if (out) {
        target.text += out          // 一个字一个字长进气泡
        options?.onChar?.(out)      // ← 接 TTS 就用这个钩子
      }
    }, TICK_MS)
  }

  function stopConsumer() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  // 等队列里的字全部显示完（供 sendMessage 收尾用）
  function waitDrained(done: () => void) {
    if (queue.length === 0 && !timer) return done()
    drained = done
  }

  // 组件卸载时清掉定时器，避免内存泄漏
  onBeforeUnmount(stopConsumer)

  // ------------------------------------------------------------------
  // sendMessage：用户发一条消息（MessageInput 触发 @send 时调用）
  // ------------------------------------------------------------------
  async function sendMessage(text: string) {
    const content = text.trim()
    if (!content || isTyping.value) return   // 空消息 / 正在回复中，直接忽略

    // 1. 先把这轮之前的聊天记录打包 —— 发给后端，模型才知道前面聊了什么。
    //    必须在下面 push 当前这条之前取，否则会把用户刚说的话重复发一遍。
    const history = messages.value.map((m) => ({
      role: m.role === 'ai' ? 'assistant' : 'user',
      text: m.text,
    }))

    // 2. 把用户这条消息加进列表（气泡立刻出现在右侧）
    messages.value.push({ role: 'user', text: content })

    // 3. 塞一条"空的 AI 消息"占位，后面一个字一个字往里填
    //    ★ 关键：必须把"响应式代理"取出来再改！
    //      直接改 push 进去的那个原始对象不会触发重新渲染
    //      （原始对象没有走 Proxy 的 set 陷阱），表现就是气泡一直是空的。
    //      从 messages.value 里读出来的才是被代理过的对象。
    messages.value.push({ role: 'ai', text: '' })
    const aiMsg = messages.value[messages.value.length - 1] as Message

    isTyping.value = true
    isThinking.value = true       // 立刻进入"思考中"，前端马上有反馈
    thinkingText.value = ''
    queue = []

    // ==================================================================
    // 4. 向后端要 AI 回复
    //    后端：POST /api/chat，SSE（text/event-stream）流式返回
    //    每帧：data: {"type": "...", "text": "一小段文字"}
    //      type = 'status'（开始思考）/ 'thinking'（思考过程）/ 'text'（正文）
    //    最后一帧：data: [DONE]
    //    /api 由 vite.config.ts 的 proxy 转发到 http://127.0.0.1:8000
    // ==================================================================
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        // 不用在这里带 Key：后端会根据 Session Cookie 找到当前账号，
        // 再用该账号在 user_providers 表里激活的那套 Key / Base URL / 模型（见 llm_settings.py）
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, history }),
      })
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()   // 拿到流的"读取器"
      const decoder = new TextDecoder()     // 二进制 → 文本
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break                     // 流读完了

        // 一次收到的可能是"半帧"或"好几帧"，先拼到缓冲区再按空行切开
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split('\n\n')
        buffer = frames.pop() ?? ''         // 最后一段可能不完整，留给下一轮

        for (const frame of frames) {
          const line = frame.trim()
          if (!line.startsWith('data:')) continue
          const payload = line.slice(5).trim()
          if (payload === '[DONE]') continue

          const data = JSON.parse(payload)
          if (data.error) throw new Error(data.error)

          if (data.type === 'text') {
            isThinking.value = false        // 正文来了，收起"思考中"
            enqueue(String(data.text ?? ''), aiMsg)
          } else if (data.type === 'thinking') {
            thinkingText.value += String(data.text ?? '')
          }
          // 'status' 帧不用处理：isThinking 一开始就是 true
        }
      }

      // 正文全部收完，等队列把字慢慢放完再解锁输入框
      await new Promise<void>((resolve) => {
        waitDrained(resolve)
        setTimeout(resolve, 120_000)        // 兜底：最多等 2 分钟
      })

      if (!aiMsg.text) aiMsg.text = '（芙芙这次什么也没说…）'
    } catch (err) {
      // 后端没起 / Key 没配 / 代理写错，都会走到这里
      const reason = err instanceof Error ? err.message : String(err)
      stopConsumer()
      queue = []
      aiMsg.text =
        `芙芙这边好像断线了：${reason}\n` +
        '检查一下：① 后端 uvicorn server.app:app --port 8000 起了吗 ' +
        '② 右上角「设置」里添加并启用一套 API Key 了吗'
    } finally {
      isTyping.value = false                // 无论成败都要解锁输入框
      isThinking.value = false
    }
  }

  return { messages, isTyping, isThinking, thinkingText, sendMessage }
}
