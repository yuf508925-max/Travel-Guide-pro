// =====================================================================
// useUsage —— 前端主动打点（高德地图调用）
// ---------------------------------------------------------------------
// 高德 JS API 的请求是浏览器直接发到高德服务器的，不经过我们的后端，
// 所以「高德调用量」只能由前端在真正发起请求时上报一次。
// 失败静默：统计不该影响用户操作。
// =====================================================================

export type AmapAction =
  | 'map-init'
  | 'place-search'
  | 'geocode'
  | 'transfer'
  | 'driving'
  | 'walking'

export function reportAmap(action: AmapAction): void {
  fetch('/api/usage/amap', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  }).catch(() => {
    /* 打点失败就算了 */
  })
}
