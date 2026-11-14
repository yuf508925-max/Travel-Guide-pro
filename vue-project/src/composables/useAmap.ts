// =====================================================================
// useAmap —— 按需加载高德地图 JS API（2.0）
// ---------------------------------------------------------------------
// Key 从哪来：管理员在后台「地图 Key」里配，存后端 app_settings 表，
//   前端通过 GET /api/map 取一次。普通用户不用填，也没有输入框。
//   换 Key 只改后端配置，前端不用动。
//
// 为什么放后端而不写死在前端：这样换 Key 不用重新构建前端；
//   而且这个值本来就是公开的（会出现在 script 地址里），不存在泄露问题。
// =====================================================================

import { ref } from 'vue'

declare global {
  interface Window {
    AMap?: any
    _AMapSecurityConfig?: { securityJsCode?: string }
  }
}

const SCRIPT_ID = 'amap-jsapi'

export const amapKey = ref('')
export const amapSecurityCode = ref('')

let configLoaded = false
let loading: Promise<any> | null = null

export function hasAmapKey(): boolean {
  return amapKey.value.trim().length > 0
}

/** 从后端读内置的高德配置（只读一次） */
export async function loadAmapConfig(): Promise<void> {
  if (configLoaded) return
  configLoaded = true

  try {
    const res = await fetch('/api/map')
    if (!res.ok) return
    const data = (await res.json()) as { amap_key?: string; security_code?: string }
    amapKey.value = data.amap_key ?? ''
    amapSecurityCode.value = data.security_code ?? ''
  } catch {
    // 后端不可用：保持为空，调用方会给出"地图没配置"的提示
  }
}

/** 退出登录时清掉内存里的配置，下次进页面重新取 */
export function resetAmapConfig() {
  configLoaded = false
  amapKey.value = ''
  amapSecurityCode.value = ''
  resetAmap()
}

/** 清掉已加载的脚本，让下次 loadAmap 重新加载 */
export function resetAmap() {
  loading = null
  const script = document.getElementById(SCRIPT_ID)
  if (script) script.remove()
  delete window.AMap
}

/** 加载高德地图脚本，返回 window.AMap */
export async function loadAmap(): Promise<any> {
  if (window.AMap) return window.AMap
  if (loading) return loading

  await loadAmapConfig()

  const key = amapKey.value.trim()
  if (!key) {
    throw new Error('管理员还没在后台配置高德地图 Key（后台 → 地图 Key）')
  }

  if (amapSecurityCode.value.trim()) {
    window._AMapSecurityConfig = { securityJsCode: amapSecurityCode.value.trim() }
  }

  loading = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.id = SCRIPT_ID
    script.async = true
    script.src =
      'https://webapi.amap.com/maps?v=2.0' +
      `&key=${encodeURIComponent(key)}` +
      '&plugin=AMap.Geocoder,AMap.PlaceSearch,AMap.Driving,AMap.Walking,AMap.Transfer'
    script.onload = () => {
      if (window.AMap) {
        resolve(window.AMap)
        return
      }
      loading = null
      reject(
        new Error(
          '高德地图没有初始化成功：多半是 Key 无效、Key 类型不是「Web端 (JS API)」，或者缺少安全密钥'
        )
      )
    }
    script.onerror = () => {
      loading = null
      reject(new Error('高德地图脚本加载失败，检查网络或 Key 是否正确'))
    }
    document.head.appendChild(script)
  })

  return loading
}
