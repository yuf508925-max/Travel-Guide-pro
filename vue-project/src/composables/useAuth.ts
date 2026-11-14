// =====================================================================
// useAuth —— 登录态管理（组合式函数）
// ---------------------------------------------------------------------
// 和后端 /api/auth/* 打交道：
//   login    登录，成功后后端会 Set-Cookie（HttpOnly），user 被赋值
//   register 注册并自动登录
//   fetchMe  刷新页面后恢复登录态（靠 Cookie）
//   logout   删掉服务端 session + 清 Cookie
// user 是模块级 ref：任何组件调用 useAuth() 拿到的都是同一份状态。
// =====================================================================

import { computed, ref } from 'vue'

interface AuthResult {
  username: string
  role: 'user' | 'admin'
}

// 当前登录的用户名；null 表示未登录
export const user = ref<string | null>(null)

// 当前账号的角色：只有 admin 会看到「后台管理」入口
export const role = ref<'user' | 'admin'>('user')

export const isAdmin = computed(() => role.value === 'admin')

// 把后端返回的错误体转成一句可读的话。
// FastAPI 的 detail 有三种可能：
//   字符串            → 401/409 这种业务错误
//   数组              → 422 参数校验错误（[{ loc, msg, ... }]）
//   对象 / 其它       → 兜底成 JSON，绝不显示 [object Object]
function extractDetail(data: unknown, status: number): string {
  if (!data || typeof data !== 'object') return `HTTP ${status}`

  const detail = (data as { detail?: unknown }).detail
  if (typeof detail === 'string' && detail) return detail

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) {
          const msg = (item as { msg?: unknown }).msg
          return typeof msg === 'string' ? msg : ''
        }
        return ''
      })
      .filter(Boolean)
    return messages.length ? messages.join('；') : `HTTP ${status}`
  }

  if (detail && typeof detail === 'object') {
    try {
      return JSON.stringify(detail)
    } catch {
      return `HTTP ${status}`
    }
  }

  return `HTTP ${status}`
}

// 统一处理 fetch：非 2xx 时抛出可读的错误信息
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    const data: unknown = await res.json().catch(() => null)
    throw new Error(extractDetail(data, res.status))
  }
  return res.json() as Promise<T>
}

export function useAuth() {
  async function login(username: string, password: string): Promise<string> {
    const data = await request<AuthResult>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    user.value = data.username
    role.value = data.role
    return data.username
  }

  async function register(username: string, password: string): Promise<string> {
    const data = await request<AuthResult>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    user.value = data.username
    role.value = data.role
    return data.username
  }

  // 刷新页面后：Cookie 还在就恢复登录态
  async function fetchMe(): Promise<void> {
    try {
      const data = await request<AuthResult>('/api/auth/me')
      user.value = data.username
      role.value = data.role
    } catch {
      user.value = null
      role.value = 'user'
    }
  }

  async function logout(): Promise<void> {
    try {
      await fetch('/api/auth/logout', { method: 'POST' })
    } finally {
      user.value = null
      role.value = 'user'
    }
  }

  return { user, role, isAdmin, login, register, fetchMe, logout }
}
