// =====================================================================
// useRouteHistory —— 行程面板的「上次搜索」记录
// ---------------------------------------------------------------------
// 存哪：后端 route_searches 表，按 user_id 隔离（每个账号只看自己的），
//       每个账号最多留 20 条，面板打开时回填最近一条。
// 接口：GET /api/routes/last、POST /api/routes（见 server/routers/routes.py）
//
// 读失败一律当成"没有记录"，不能让历史记录影响查路线这个主功能。
// =====================================================================

export interface RouteSearch {
  id?: number
  city: string
  origin: string
  destination: string
  mode: string
  created_at?: string
}

export const TRAVEL_MODES = ['driving', 'walking', 'transit'] as const

export async function fetchLastSearch(kind = 'route'): Promise<RouteSearch | null> {
  try {
    const res = await fetch(`/api/routes/last?kind=${kind}`)
    if (!res.ok) return null
    const data = (await res.json()) as { found?: boolean; search?: RouteSearch }
    return data.found && data.search ? data.search : null
  } catch {
    return null
  }
}

/** 取最近 N 条（给输入框的下拉建议用）；kind=vlog 取的是「观看 vlog」的搜索词 */
export async function fetchRecentSearches(limit = 20, kind = 'route'): Promise<RouteSearch[]> {
  try {
    const res = await fetch(`/api/routes?limit=${limit}&kind=${kind}`)
    if (!res.ok) return []
    const data = (await res.json()) as { searches?: RouteSearch[] }
    return Array.isArray(data.searches) ? data.searches : []
  } catch {
    return []
  }
}

/** 删除一条搜索记录（只能删自己的） */
export async function deleteRouteSearch(id: number): Promise<boolean> {
  try {
    const res = await fetch(`/api/routes/${id}`, { method: 'DELETE' })
    return res.ok
  } catch {
    return false
  }
}

/** 存一次搜索（失败静默，不影响查路线） */
export async function saveRouteSearch(search: RouteSearch): Promise<void> {
  try {
    await fetch('/api/routes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        city: search.city,
        origin: search.origin,
        destination: search.destination,
        mode: search.mode,
      }),
    })
  } catch {
    // 记录失败就算了，下次再存
  }
}

// ---------------------------------------------------------------------
// 「观看 vlog」的搜索词：和行程记录存在同一张 route_searches 表里（kind=vlog），
// 关键词放在 origin 字段。这样两边共用一套存储和「最近搜过」的下拉。
// ---------------------------------------------------------------------

/** 最近搜过的关键词（给 vlog 搜索框下拉用） */
export async function fetchRecentVlogSearches(limit = 8): Promise<RouteSearch[]> {
  return fetchRecentSearches(limit, 'vlog')
}

/** 存一次 vlog 搜索词（失败静默，不影响搜索本身） */
export async function saveVlogSearch(keyword: string): Promise<void> {
  return saveSearchHistory('vlog', keyword)
}

/**
 * 存一次搜索词 / 地名，按 kind 分类存进同一张 route_searches 表（关键词放 origin）。
 * kind：route=行程、vlog=看视频的关键词、vlog-region=看视频的地区、
 *       weather=天气里查过的城市、memory=记忆面板搜过的词
 */
export async function saveSearchHistory(kind: string, keyword: string): Promise<void> {
  const word = keyword.trim()
  if (!word) return
  try {
    await fetch('/api/routes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, origin: word, city: '', destination: '', mode: '' }),
    })
  } catch {
    // 记不上就算了
  }
}
