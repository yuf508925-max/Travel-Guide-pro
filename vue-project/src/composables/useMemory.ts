// =====================================================================
// useMemory.ts —— 「记忆」页面的数据层
//   后端：server/routers/memory.py
//   · GET  /api/memories?q=      记忆条目 + 统计
//   · GET  /api/memories/graph   图谱节点 / 边
//   · DELETE /api/memories/{id}  删一条
// =====================================================================

export interface MemoryItem {
  id: number
  kind: string
  kind_label: string
  content: string
  created_at: string
  conversation_id: number
  conversation_title: string
}

export interface MemoryConversation {
  id: number
  title: string
  count: number
}

export interface MemoryStats {
  total: number
  conversations: number
  by_kind: { kind: string; label: string; count: number }[]
}

export interface GraphNode {
  id: string
  label: string
  type: 'conversation' | 'memory'
  kind?: string
  size?: number
}

export interface GraphEdge {
  source: string
  target: string
}

export interface MemoryGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as T
}

export async function fetchMemories(query = '', conversationId: number | null = null) {
  const params = new URLSearchParams()
  const q = query.trim()
  if (q) params.set('q', q)
  if (conversationId !== null) params.set('conversation_id', String(conversationId))
  const qs = params.toString()
  const data = await getJson<{
    memories: MemoryItem[]
    stats: MemoryStats
    conversations: MemoryConversation[]
  }>(`/api/memories${qs ? `?${qs}` : ''}`)
  return {
    memories: data.memories ?? [],
    stats: data.stats ?? { total: 0, conversations: 0, by_kind: [] },
    conversations: data.conversations ?? [],
  }
}

export async function fetchGraph(conversationId: number | null = null) {
  const qs = conversationId === null ? '' : `?conversation_id=${conversationId}`
  const data = await getJson<MemoryGraph>(`/api/memories/graph${qs}`)
  return { nodes: data.nodes ?? [], edges: data.edges ?? [] }
}

export async function removeMemory(id: number) {
  const res = await fetch(`/api/memories/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}
