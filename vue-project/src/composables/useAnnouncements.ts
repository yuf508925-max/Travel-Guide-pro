// =====================================================================
// useAnnouncements —— 公告（前台顶栏「公告」+ 后台「发布公告」共用一份状态）
// ---------------------------------------------------------------------
// 接口：GET    /api/notices        看列表（登录后可用）
//       POST   /api/notices        发一条（仅管理员）
//       PATCH  /api/notices/{id}   改内容 / 置顶（仅管理员）
//       DELETE /api/notices/{id}   删除（仅管理员）
//
// 已读状态：后端不记，前端把「最后一次看过的公告 id」存在 localStorage，
// 比它大的就算没看过 —— 这样换设备不会串，也不需要给每个用户存一张已读表。
// =====================================================================

import { computed, ref } from 'vue'

export interface Announcement {
  id: number
  title: string
  content: string
  pinned: boolean
  publisher: string
  created_at: string
}

const SEEN_KEY = 'fufu-notice-seen-id'

const notices = ref<Announcement[]>([])
const loading = ref(false)
const loaded = ref(false)

function readSeen(): number {
  try {
    const value = Number(localStorage.getItem(SEEN_KEY))
    return Number.isFinite(value) && value > 0 ? value : 0
  } catch {
    return 0
  }
}

const seenId = ref(readSeen())

/** 没看过的条数（顶栏小红点用） */
const unreadCount = computed(
  () => notices.value.filter((item) => item.id > seenId.value).length,
)

async function loadNotices(force = false): Promise<Announcement[]> {
  if (loaded.value && !force) return notices.value
  loading.value = true
  try {
    const res = await fetch('/api/notices?limit=50')
    if (!res.ok) return notices.value
    const data = (await res.json()) as { notices?: Announcement[] }
    notices.value = Array.isArray(data.notices) ? data.notices : []
    loaded.value = true
  } catch {
    /* 拉不到就当没有公告，不影响主界面 */
  } finally {
    loading.value = false
  }
  return notices.value
}

/** 把当前最新的公告之前全部标记为看过 */
function markAllRead() {
  const maxId = notices.value.reduce((max, item) => Math.max(max, item.id), 0)
  if (maxId <= seenId.value) return
  seenId.value = maxId
  try {
    localStorage.setItem(SEEN_KEY, String(maxId))
  } catch {
    /* 隐身模式写不进去，忽略 */
  }
}

async function createNotice(
  title: string,
  content: string,
  pinned = false,
): Promise<Announcement | null> {
  const res = await fetch('/api/notices', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, content, pinned }),
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: unknown } | null
    throw new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`)
  }
  const created = (await res.json()) as Announcement
  notices.value = [created, ...notices.value]
  loaded.value = true
  return created
}

async function updateNotice(
  id: number,
  patch: { title?: string; content?: string; pinned?: boolean },
): Promise<Announcement | null> {
  const res = await fetch(`/api/notices/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: unknown } | null
    throw new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`)
  }
  const fresh = (await res.json()) as Announcement
  notices.value = notices.value.map((item) => (item.id === fresh.id ? fresh : item))
  return fresh
}

async function deleteNotice(id: number): Promise<boolean> {
  const res = await fetch(`/api/notices/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: unknown } | null
    throw new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`)
  }
  notices.value = notices.value.filter((item) => item.id !== id)
  return true
}

export function useAnnouncements() {
  return {
    notices,
    loading,
    unreadCount,
    loadNotices,
    markAllRead,
    createNotice,
    updateNotice,
    deleteNotice,
  }
}
