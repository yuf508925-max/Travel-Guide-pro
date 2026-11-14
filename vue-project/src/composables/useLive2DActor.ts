// =====================================================================
// useLive2DActor.ts —— AI 控制模式：让大模型自己挑表情和动作
// ---------------------------------------------------------------------
// 两种触发时机，都由 ChatView 决定，这里只负责"问"：
//   1. 一轮回复结束：把这一轮的上下文（最近几条消息）发上去，问该怎么演；
//   2. 挂机一分钟：没新消息时，让她自己根据刚才聊的内容换个小表情。
//
// 隔离：request() 永远只属于调用它的那个对话——调用方把对话 id 一起带进
// 来，返回后自己比对；切换对话时 ChatView 会调 cancel()，把在路上的请求掐掉。
// 开关存在 localStorage，刷新页面还保持上次的选择。
// =====================================================================

import { ref, watch } from 'vue'

const STORAGE_KEY = 'fufu-live2d-ai-mode'

export interface Live2DAction {
  /** 动作组名：Idle / TapBody / 变芒 / 变荒 */
  motion: string | null
  /** 表情名：呆毛电风扇 / 哭 / 小脸红… */
  expression: string | null
  /** 大模型给的理由，只做提示用 */
  reason: string
}

/** 一问一答的上下文（只取当前对话里的，别串台） */
export interface ChatTurn {
  role: 'user' | 'ai'
  text: string
}

interface ActResponse {
  motion?: string | null
  expression?: string | null
  reason?: string | null
}

export function useLive2DActor() {
  const aiMode = ref(false)
  const lastAction = ref<Live2DAction | null>(null)

  try {
    aiMode.value = localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    // 隐私模式拿不到 localStorage，就当没开过
  }

  /** 请求序号：只认最后一次，前面慢回来的直接扔掉 */
  let seq = 0
  let controller: AbortController | null = null

  /** 掐掉在路上的请求（关模式 / 切对话时用） */
  function cancel() {
    controller?.abort()
    controller = null
    seq += 1
  }

  watch(aiMode, (on) => {
    try {
      localStorage.setItem(STORAGE_KEY, on ? '1' : '0')
    } catch {
      // 存不下就算了，不影响本次会话
    }
    if (!on) {
      cancel()
      lastAction.value = null
    }
  })

  /**
   * 请大模型挑一个表情/动作。
   * @param payload.history 当前对话最近几条消息（调用方负责只传本对话的）
   * @param payload.idle    true = 挂机模式：没有新台词，让她自己找点小表情
   */
  async function request(payload: {
    reply?: string
    user?: string
    history?: ChatTurn[]
    idle?: boolean
    /** 这条对话上一次演过的动作/表情，让模型别再挑同一个 */
    previous?: { motion?: string | null; expression?: string | null } | null
  }): Promise<Live2DAction | null> {
    if (!aiMode.value) return null

    const reply = (payload.reply ?? '').trim()
    const history = (payload.history ?? [])
      .filter((t) => t.text.trim())
      .slice(-8)
    const idle = payload.idle === true

    // 既没新台词、也没上下文（新对话还没聊过），就没什么可挑的
    if (!idle && reply.length < 2) return null
    if (!reply && history.length === 0) return null

    const mine = (seq += 1)
    controller?.abort()
    const ac = new AbortController()
    controller = ac

    try {
      const res = await fetch('/api/live2d/act', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reply,
          user: payload.user ?? '',
          history,
          idle,
          previous: payload.previous ?? null,
        }),
        signal: ac.signal,
      })
      if (!res.ok) return null
      const data = (await res.json()) as ActResponse
      if (mine !== seq || !aiMode.value) return null

      const action: Live2DAction = {
        motion: data.motion ?? null,
        expression: data.expression ?? null,
        reason: data.reason ?? '',
      }
      if (!action.motion && !action.expression) return null
      lastAction.value = action
      return action
    } catch {
      // 网络抖动 / abort：保持当前表情就好
      return null
    }
  }

  return { aiMode, lastAction, request, cancel }
}
