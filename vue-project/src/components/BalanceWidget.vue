<!-- ====================================================================
  BalanceWidget —— 顶部导航条上的余额小胶囊（音量 和 设置 中间）
    · 显示当前使用中那套 Key 的余额，点一下弹出详情
    · 支持多家：DeepSeek 官方 / OpenRouter / Kimi / 硅基流动
      （每家路径不同，分流在 server/balance_check.py）
    · 展开面板底部列出了「哪些接口能查余额」，不用去猜
    · 数据 60 秒缓存一次；切 Key、点 ↻ 或每 5 分钟会刷新
==================================================================== -->

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { providers } from '../composables/useProviders'

interface Detail {
  label: string
  value: string | null
}

interface Balance {
  ok: boolean
  vendor?: string
  message?: string
  currency?: string
  total?: string
  details?: Detail[]
  provider?: string
  checked_at?: string
}

const open = ref(false)
const data = ref<Balance | null>(null)
const loading = ref(false)
const rootRef = ref<HTMLElement | null>(null)

const activeProvider = computed(
  () => providers.value.find((p) => p.isActive) ?? providers.value[0] ?? null
)

const symbol = computed(() => (data.value?.currency === 'USD' ? '$' : '¥'))

function formatAmount(raw?: string | null): string {
  if (raw == null || raw === '') return '--'
  const num = Number(raw)
  return Number.isFinite(num) ? num.toFixed(2) : String(raw)
}

const shortText = computed(() => {
  if (!data.value) return loading.value ? '查询中' : '余额'
  if (!data.value.ok) return '余额 —'
  return `${symbol.value}${formatAmount(data.value.total)}`
})

const detailRows = computed(() => {
  const rows: Detail[] = []
  if (data.value?.details) rows.push(...data.value.details)
  if (data.value?.checked_at) rows.push({ label: '更新', value: data.value.checked_at })
  return rows
})

async function load() {
  if (!activeProvider.value) return
  loading.value = true
  try {
    const res = await fetch('/api/providers/balance')
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      data.value = {
        ok: false,
        message: (body && typeof body.detail === 'string' && body.detail) || '余额查询失败',
      }
      return
    }
    data.value = (await res.json()) as Balance
  } catch {
    data.value = { ok: false, message: '网络错误，查不到余额' }
  } finally {
    loading.value = false
  }
}

// 换了当前使用的那套 Key 就重查
watch(
  () => activeProvider.value?.id,
  () => {
    data.value = null
    load()
  }
)

function onPointerDown(event: PointerEvent) {
  if (!open.value) return
  const el = rootRef.value
  if (el && !el.contains(event.target as Node)) open.value = false
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && open.value) open.value = false
}

let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  load()
  timer = setInterval(load, 5 * 60 * 1000)
  document.addEventListener('pointerdown', onPointerDown)
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  document.removeEventListener('pointerdown', onPointerDown)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="rootRef" class="balance">
    <button
      class="chip"
      type="button"
      :title="data?.ok ? `${data.provider} · 点击查看明细` : data?.message || '点击查看余额'"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="chip__icon" aria-hidden="true">💰</span>
      <span class="chip__text">{{ shortText }}</span>
    </button>

    <div v-if="open" class="pop" role="dialog" aria-label="账户余额">
      <div class="pop__head">
        <span class="pop__title">余额</span>
        <span class="pop__provider">{{ data?.provider || '当前 Key' }}</span>
        <button
          class="pop__refresh"
          type="button"
          :disabled="loading"
          :title="loading ? '查询中…' : '刷新余额'"
          @click="load"
        >
          ↻
        </button>
      </div>

      <p v-if="loading && !data" class="pop__hint">查询中…</p>

      <template v-else-if="data?.ok">
        <p class="pop__total">{{ symbol }}{{ formatAmount(data.total) }}</p>
        <dl v-if="detailRows.length" class="pop__details">
          <div v-for="row in detailRows" :key="row.label">
            <dt>{{ row.label }}</dt>
            <dd>{{ row.value ?? '—' }}</dd>
          </div>
        </dl>
      </template>

      <p v-else class="pop__error">{{ data?.message || '查不到余额' }}</p>

      <p class="pop__note-title">哪些接口支持余额查询</p>
      <ul class="pop__note">
        <li><span class="ok">✅</span> DeepSeek 官方</li>
        <li><span class="ok">✅</span> OpenRouter</li>
        <li><span class="ok">✅</span> Kimi / Moonshot</li>
        <li><span class="ok">✅</span> 硅基流动</li>
        <li><span class="no">❌</span> 其它中转 / 兼容接口（如 dashscope 兼容模式）</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.balance {
  position: relative;   /* 弹层以它为定位参照 */
  display: inline-flex;
}

/* ---- 导航条上的小胶囊 ---- */
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  box-sizing: border-box;
  border: none;
  border-radius: 14px;
  background: transparent;
  color: #fff;
  font-size: 0.78rem;
  font-family: inherit;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: background 0.18s;
}
.chip:hover { background: rgba(255, 255, 255, 0.16); }
.chip[aria-expanded='true'] { background: rgba(255, 255, 255, 0.24); }

.chip__icon { font-size: 0.82rem; line-height: 1; }
.chip__text { white-space: nowrap; }

/* ---- 弹出面板 ---- */
.pop {
  position: absolute;
  top: calc(100% + 12px);
  right: 0;
  z-index: 70;
  width: 258px;
  padding: 12px 14px;
  box-sizing: border-box;
  border: 1.5px solid rgba(255, 253, 248, 0.4);
  border-radius: 13px;
  background: rgba(12, 46, 46, 0.95);
  backdrop-filter: blur(14px);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.42);
  color: #fffdf8;
  animation: pop-in 0.18s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes pop-in {
  from { opacity: 0; transform: translateY(-6px) scale(0.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.pop__head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.pop__title {
  font-size: 0.86rem;
  font-weight: 500;
}
.pop__provider {
  font-size: 0.68rem;
  color: rgba(255, 253, 248, 0.5);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pop__refresh {
  margin-left: auto;
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 253, 248, 0.85);
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.18s, transform 0.3s;
}
.pop__refresh:hover:not(:disabled) {
  background: rgba(255, 253, 248, 0.16);
  transform: rotate(90deg);
}
.pop__refresh:disabled { opacity: 0.45; cursor: progress; }

.pop__total {
  margin: 8px 0 2px;
  font-size: 1.5rem;
  font-weight: 500;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.pop__details {
  margin: 6px 0 0;
  display: grid;
  gap: 3px;
  font-size: 0.72rem;
}
.pop__details > div {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.pop__details dt { color: rgba(255, 253, 248, 0.45); }
.pop__details dd {
  margin: 0;
  color: rgba(255, 253, 248, 0.85);
  font-variant-numeric: tabular-nums;
}

.pop__hint {
  margin: 10px 0;
  font-size: 0.78rem;
  color: rgba(255, 253, 248, 0.6);
}
.pop__error {
  margin: 10px 0 2px;
  font-size: 0.74rem;
  line-height: 1.45;
  color: #ffd9d0;
}

.pop__note-title {
  margin: 12px 0 5px;
  padding-top: 9px;
  border-top: 1px solid rgba(255, 253, 248, 0.14);
  font-size: 0.66rem;
  color: rgba(255, 253, 248, 0.42);
}
.pop__note {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 3px;
  font-size: 0.68rem;
  line-height: 1.5;
  color: rgba(255, 253, 248, 0.7);
}

.pop__note .no { color: #ffb4a8; }

@media (prefers-reduced-motion: reduce) {
  .pop { animation: none; }
}
</style>
