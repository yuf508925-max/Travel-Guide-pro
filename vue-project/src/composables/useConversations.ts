// =====================================================================
// useConversations —— 「多个对话 + 每个对话一份记忆」
// ---------------------------------------------------------------------
//   · 后端只存摘要（conversations.summary），不存聊天全文
//   · 全文只活在前端；关网页 / 切换对话时调一次 summarize 存成摘要
//   · 记忆按对话隔离：换对话 → 后端换一段 summary 喂给模型
// =====================================================================

import { ref } from 'vue'

export interface Conversation {
  id: number
  title: string
  summary: string
  /** 已经总结过多少条消息（后端的 conversations.summarized_upto） */
  summarized_upto?: number
  created_at: string
  updated_at: string
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`)
  }
  return (await res.json()) as T
}

export function useConversations() {
  const conversations = ref<Conversation[]>([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      const data = await jsonFetch<{ conversations: Conversation[] }>('/api/conversations')
      conversations.value = data.conversations
      return data.conversations
    } finally {
      loading.value = false
    }
  }

  async function create(title = '') {
    const item = await jsonFetch<Conversation>('/api/conversations', {
      method: 'POST',
      body: JSON.stringify({ title }),
    })
    conversations.value = [item, ...conversations.value]
    return item
  }

  async function rename(id: number, title: string) {
    const item = await jsonFetch<Conversation>(`/api/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    })
    conversations.value = conversations.value.map((c) => (c.id === id ? item : c))
    return item
  }

  async function remove(id: number) {
    await jsonFetch<{ ok: boolean }>(`/api/conversations/${id}`, { method: 'DELETE' })
    conversations.value = conversations.value.filter((c) => c.id !== id)
  }

  /**
   * 把当前这段对话压成摘要存库。
   * keepalive=true 时用 keepalive，关页面也能发出去。
   */
  async function summarize(id: number, messages: { role: string; text: string }[], keepalive = false) {
    const body = JSON.stringify({ messages })
    const res = await fetch(`/api/conversations/${id}/summarize`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive,
    })
    if (!res.ok) return ''
    const data = (await res.json()) as {
      summary: string
      added?: { kind: string; content: string }[]
      summarized_upto?: number
    }
    // 后端会回传累计总结条数，前端据此只发「还没总结过的那一段」
    const target = conversations.value.find((c) => c.id === id)
    if (target && typeof data.summarized_upto === 'number') {
      target.summarized_upto = data.summarized_upto
    }
    return data.summary || ''
  }

  return { conversations, loading, load, create, rename, remove, summarize }
}
