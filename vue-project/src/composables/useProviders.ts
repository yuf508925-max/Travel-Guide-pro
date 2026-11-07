// =====================================================================
// useProviders —— 账号下的多套 API Key（提供商）
// ---------------------------------------------------------------------
// 一个账号可以有多套 Key，每套带多个候选模型 + 一个当前模型；
// 其中 is_active 的那套就是聊天正在用的。
//
// 后端：server/routers/providers.py
//   GET    /api/providers                列表
//   POST   /api/providers                新增
//   PUT    /api/providers/{id}           修改整套
//   DELETE /api/providers/{id}           删除
//   POST   /api/providers/{id}/activate  切换聊天使用的那套
//   POST   /api/providers/{id}/model     只切模型
//
// Key 永远是打码回来的（sk-ab••••wxyz），想换只能重新填一套。
// =====================================================================

import { ref } from 'vue'

export interface Provider {
  id: number
  name: string
  apiKeyMasked: string
  hasApiKey: boolean
  baseUrl: string
  models: string[]
  model: string
  isActive: boolean
  updatedAt: string
}

export interface ProviderDefaults {
  baseUrl: string
  model: string
}

interface ProviderRaw {
  id: number
  name: string
  api_key_masked: string
  has_api_key: boolean
  base_url: string
  models: string[]
  model: string
  is_active: boolean
  updated_at: string
}

function toProvider(raw: ProviderRaw): Provider {
  return {
    id: raw.id,
    name: raw.name,
    apiKeyMasked: raw.api_key_masked,
    hasApiKey: raw.has_api_key,
    baseUrl: raw.base_url,
    models: raw.models ?? [],
    model: raw.model,
    isActive: raw.is_active,
    updatedAt: raw.updated_at,
  }
}

/** 后端校验失败时带的错误：field 指出是哪一项写错了 */
export class ProviderError extends Error {
  field: string

  constructor(message: string, field = '') {
    super(message)
    this.name = 'ProviderError'
    this.field = field
  }
}

async function readError(res: Response): Promise<ProviderError> {
  const body = await res.json().catch(() => null)
  const detail = body && (body as { detail?: unknown }).detail

  // 保存失败时 detail 是 { message, field }
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: unknown; field?: unknown }
    const message = typeof d.message === 'string' ? d.message : ''
    const field = typeof d.field === 'string' ? d.field : ''
    if (message) return new ProviderError(message, field)
  }
  if (typeof detail === 'string') return new ProviderError(detail)
  if (res.status === 401) return new ProviderError('登录已过期，请重新登录')
  return new ProviderError(`请求失败（HTTP ${res.status}）`)
}

/** 后端保存成功后会把测试结论带回来，这里取出来给界面提示 */
async function readVerification(res: Response): Promise<string> {
  const body = (await res.json().catch(() => null)) as
    | { verification?: { message?: string } }
    | null
  return body?.verification?.message ?? ''
}

// 共享状态：列表 + 内置默认值（用户留空时用）
export const providers = ref<Provider[]>([])
export const providerDefaults = ref<ProviderDefaults>({ baseUrl: '', model: '' })

export interface ProviderPayload {
  name: string
  // 新增时必填；编辑时留空表示"不改 Key"
  apiKey?: string
  baseUrl?: string
  models?: string[]
  model?: string
}

export async function loadProviders(): Promise<void> {
  const res = await fetch('/api/providers')
  if (!res.ok) throw await readError(res)
  const data = (await res.json()) as {
    providers: ProviderRaw[]
    defaults: { base_url: string; model: string }
  }
  providers.value = data.providers.map(toProvider)
  providerDefaults.value = {
    baseUrl: data.defaults?.base_url ?? '',
    model: data.defaults?.model ?? '',
  }
}

/** 把前端字段翻成后端要的 snake_case */
function toBody(payload: ProviderPayload): Record<string, unknown> {
  const body: Record<string, unknown> = {
    name: payload.name,
    base_url: payload.baseUrl ?? '',
    models: payload.models ?? [],
    model: payload.model ?? '',
  }
  // 编辑时留空 = 不改 Key，就不要把空字符串传上去（后端会当成没填而报错）
  if (payload.apiKey) body.api_key = payload.apiKey
  return body
}

export async function createProvider(payload: ProviderPayload): Promise<string> {
  const res = await fetch('/api/providers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toBody(payload)),
  })
  if (!res.ok) throw await readError(res)
  const message = await readVerification(res)
  await loadProviders()
  return message
}

export async function updateProvider(id: number, payload: ProviderPayload): Promise<string> {
  const res = await fetch(`/api/providers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toBody(payload)),
  })
  if (!res.ok) throw await readError(res)
  const message = await readVerification(res)
  await loadProviders()
  return message
}

export async function removeProvider(id: number): Promise<void> {
  const res = await fetch(`/api/providers/${id}`, { method: 'DELETE' })
  if (!res.ok) throw await readError(res)
  await loadProviders()
}

export async function activateProvider(id: number): Promise<void> {
  const res = await fetch(`/api/providers/${id}/activate`, { method: 'POST' })
  if (!res.ok) throw await readError(res)
  await loadProviders()
}

/** 快速切模型（列表里那个下拉框） */
export async function setProviderModel(id: number, model: string): Promise<void> {
  const res = await fetch(`/api/providers/${id}/model`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  })
  if (!res.ok) throw await readError(res)
  await loadProviders()
}
