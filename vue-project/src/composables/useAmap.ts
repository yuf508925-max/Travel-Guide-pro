// =====================================================================
// useAmap —— 按需加载高德地图 JS API（2.0），Key 按账号存数据库
// ---------------------------------------------------------------------
// Key 存哪：后端 user_map_settings 表（/api/map），一个账号一份。
//   以前放 localStorage，同一个浏览器换账号会串用别人的 Key；
//   现在登录后从后端读，保存也写后端，退出换账号自然就换 Key。
//
// 兼容：后端还没有 Key 时，读一次 localStorage 里的旧 Key 作为预填，
//       用户保存后就把本地那份清掉。
// =====================================================================

import { ref } from 'vue'

declare global {
  interface Window {
    AMap?: any
    _AMapSecurityConfig?: { securityJsCode?: string }
  }
}

const LEGACY_KEY = 'amap-js-key'
const LEGACY_CODE = 'amap-security-code'
const SCRIPT_ID = 'amap-jsapi'

function readLegacy(name: string): string {
  try {
    return localStorage.getItem(name) ?? ''
  } catch {
    return ''
  }
}

function clearLegacy() {
  try {
    localStorage.removeItem(LEGACY_KEY)
    localStorage.removeItem(LEGACY_CODE)
  } catch {
    // 忽略
  }
}

export const amapKey = ref('')
export const amapSecurityCode = ref('')

let configLoaded = false

export function hasAmapKey(): boolean {
  return amapKey.value.trim().length > 0
}

/** 从后端读当前账号的高德配置（只读一次） */
export async function loadAmapConfig(): Promise<void> {
  if (configLoaded) return
  configLoaded = true

  try {
    const res = await fetch('/api/map')
    if (res.ok) {
      const data = (await res.json()) as { amap_key?: string; security_code?: string }
      amapKey.value = data.amap_key ?? ''
      amapSecurityCode.value = data.security_code ?? ''
      // 后端没有、本地有旧值 → 作为预填（保存时会写到后端）
      if (!amapKey.value) amapKey.value = readLegacy(LEGACY_KEY)
      if (!amapSecurityCode.value) amapSecurityCode.value = readLegacy(LEGACY_CODE)
      return
    }
  } catch {
    // 后端不可用，退回本地旧值，至少地图还能用
  }

  amapKey.value = readLegacy(LEGACY_KEY)
  amapSecurityCode.value = readLegacy(LEGACY_CODE)
}

/** 保存到后端（失败静默，不影响本次使用） */
export async function saveAmapConfig(key: string, securityCode: string): Promise<void> {
  amapKey.value = key.trim()
  amapSecurityCode.value = securityCode.trim()
  resetAmap()

  try {
    await fetch('/api/map', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        amap_key: amapKey.value,
        security_code: amapSecurityCode.value,
      }),
    })
    clearLegacy()
  } catch {
    // 存不进去也先让本次会话可用
  }
}

/** 退出登录时调用：清掉内存里的配置，换账号后会重新从后端读 */
export function resetAmapConfig() {
  configLoaded = false
  amapKey.value = ''
  amapSecurityCode.value = ''
  resetAmap()
}

/** 清掉已加载的脚本，让下次 loadAmap 用新 Key 重新加载 */
export function resetAmap() {
  loading = null
  const script = document.getElementById(SCRIPT_ID)
  if (script) script.remove()
  delete window.AMap
}

let loading: Promise<any> | null = null

/** 加载高德地图脚本，返回 window.AMap */
export async function loadAmap(): Promise<any> {
  if (window.AMap) return window.AMap
  if (loading) return loading

  await loadAmapConfig()

  const key = amapKey.value.trim()
  if (!key) throw new Error('还没有填高德地图 Key')

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
