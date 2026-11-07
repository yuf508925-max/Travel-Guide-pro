<!-- ====================================================================
  ModelSwitcher —— 输入框右侧的小胶囊：快速切换「用哪套 Key + 哪个模型」
  参考 DSH 底部那个模型选择器：
    点一下向上弹出面板，按"提供商（API Key）"分组列出模型，
    点某一行就切过去（没激活的会先激活那套 Key，再切模型）。
  数据与请求复用 composables/useProviders.ts（和右上角「设置」同一份状态，
  所以在设置里改了东西，这里会同步刷新）。
==================================================================== -->

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  activateProvider,
  loadProviders,
  providers,
  providerDefaults,
  setProviderModel,
} from '../composables/useProviders'
import type { Provider } from '../composables/useProviders'

const props = withDefaults(
  defineProps<{
    // AI 正在回复时禁止切换，避免一轮回复中途换了模型
    disabled?: boolean
  }>(),
  { disabled: false }
)

const open = ref(false)
const loading = ref(true)
const busy = ref(false)
const error = ref('')

const rootRef = ref<HTMLElement | null>(null)

const active = computed(() => providers.value.find((p) => p.isActive) ?? providers.value[0] ?? null)
const label = computed(() => (active.value ? active.value.model || '未选模型' : '未配置模型'))

function options(provider: Provider): string[] {
  const list = [...provider.models]
  if (provider.model && !list.includes(provider.model)) list.unshift(provider.model)
  if (!list.length && providerDefaults.value.model) list.push(providerDefaults.value.model)
  return list
}

async function refresh() {
  try {
    await loadProviders()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '读取配置失败'
  } finally {
    loading.value = false
  }
}

async function choose(provider: Provider, model: string) {
  if (busy.value || props.disabled) return
  busy.value = true
  error.value = ''
  try {
    // 先确保这套 Key 是当前使用的那套，再切模型
    if (!provider.isActive) await activateProvider(provider.id)
    if (model !== provider.model) await setProviderModel(provider.id, model)
    open.value = false
  } catch (err) {
    error.value = err instanceof Error ? err.message : '切换失败'
  } finally {
    busy.value = false
  }
}

// 点面板外面 / Esc 关闭
function onPointerDown(event: PointerEvent) {
  if (!open.value) return
  const el = rootRef.value
  if (el && !el.contains(event.target as Node)) open.value = false
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && open.value) open.value = false
}

onMounted(() => {
  refresh()
  document.addEventListener('pointerdown', onPointerDown)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onPointerDown)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="rootRef" class="switcher">
    <button
      class="chip"
      type="button"
      :disabled="props.disabled"
      :title="active ? `${active.name} · ${label}（点这里切换）` : '还没有配置 API Key'"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="chip__dot" :class="{ 'chip__dot--off': !active }"></span>
      <span class="chip__text">{{ label }}</span>
      <svg class="chip__caret" viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
        <path
          d="M6 15l6-6 6 6"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <!-- 向上弹出的选择面板 -->
    <div v-if="open" class="pop" role="dialog" aria-label="切换 API 和模型">
      <div class="pop__panel">
        <p class="pop__title">切换 API / 模型</p>

        <p v-if="loading" class="pop__hint">读取中…</p>

        <template v-else-if="providers.length">
          <div v-for="p in providers" :key="p.id" class="group">
            <p class="group__head">
              <span class="group__dot" :class="{ 'group__dot--off': !p.isActive }"></span>
              <span class="group__name">{{ p.name }}</span>
              <span v-if="p.isActive" class="group__badge">使用中</span>
            </p>

            <button
              v-for="m in options(p)"
              :key="m"
              class="model"
              :class="{ 'model--active': p.isActive && m === p.model }"
              type="button"
              :disabled="busy"
              @click="choose(p, m)"
            >
              <span class="model__name">{{ m }}</span>
              <span v-if="p.isActive && m === p.model" class="model__check">✓</span>
            </button>
          </div>
        </template>

        <div v-else class="empty">
          <p class="empty__title">还没有配置 API Key</p>
          <p class="empty__hint">点右上角齿轮 →「添加模型提供商」先填一套</p>
        </div>

        <p v-if="error" class="pop__error">{{ error }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.switcher {
  position: relative;
  display: flex;
}

/* ---- 小胶囊 ---- */
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 200px;
  height: 28px;
  padding: 0 10px;
  box-sizing: border-box;
  border: 1px solid rgba(255, 253, 248, 0.3);
  border-radius: 14px;
  background: rgba(255, 253, 248, 0.1);
  color: #fffdf8;
  font-size: 0.74rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.18s, border-color 0.18s;
}
.chip:hover:not(:disabled) {
  background: rgba(255, 253, 248, 0.18);
  border-color: rgba(255, 253, 248, 0.5);
}
.chip:disabled { opacity: 0.5; cursor: not-allowed; }

.chip__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #46d18a;
  box-shadow: 0 0 6px rgba(70, 209, 138, 0.7);
  flex: 0 0 auto;
}
.chip__dot--off { background: rgba(255, 253, 248, 0.35); box-shadow: none; }

.chip__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip__caret {
  flex: 0 0 auto;
  opacity: 0.7;
  transition: transform 0.18s;
}
.chip[aria-expanded='true'] .chip__caret { transform: rotate(180deg); }

/* ---- 弹出面板 ---- */
.pop {
  position: absolute;
  right: 0;
  bottom: calc(100% + 8px);
  z-index: 70;
  width: 268px;
}

.pop__panel {
  max-height: 320px;
  overflow-y: auto;
  padding: 10px;
  box-sizing: border-box;
  border: 1.5px solid rgba(255, 253, 248, 0.4);
  border-radius: 13px;
  background: rgba(12, 46, 46, 0.96);
  backdrop-filter: blur(14px);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.42);
  color: #fffdf8;
  animation: pop-in 0.18s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
.pop__panel::-webkit-scrollbar { width: 6px; }
.pop__panel::-webkit-scrollbar-thumb {
  background: rgba(255, 253, 248, 0.25);
  border-radius: 3px;
}

@keyframes pop-in {
  from { opacity: 0; transform: translateY(6px) scale(0.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.pop__title {
  margin: 0 0 6px;
  padding: 0 4px;
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  color: rgba(255, 253, 248, 0.45);
}

.pop__hint {
  margin: 8px 4px;
  font-size: 0.76rem;
  color: rgba(255, 253, 248, 0.6);
}

.group + .group { margin-top: 6px; }

.group__head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 6px 6px 4px;
  font-size: 0.72rem;
  color: rgba(255, 253, 248, 0.65);
}
.group__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #46d18a;
  flex: 0 0 auto;
}
.group__dot--off { background: rgba(255, 253, 248, 0.3); }

.group__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group__badge {
  margin-left: auto;
  padding: 1px 7px;
  border-radius: 9px;
  background: rgba(143, 214, 186, 0.22);
  color: #b9ecd4;
  font-size: 0.62rem;
  flex: 0 0 auto;
}

/* ---- 模型行 ---- */
.model {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 30px;
  padding: 0 8px;
  box-sizing: border-box;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: rgba(255, 253, 248, 0.82);
  font-size: 0.76rem;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.model:hover:not(:disabled) { background: rgba(255, 253, 248, 0.12); color: #fffdf8; }
.model:disabled { opacity: 0.5; cursor: not-allowed; }

.model--active {
  background: rgba(255, 253, 248, 0.92);
  color: #2f7d6e;
  font-weight: 500;
}
.model--active:hover:not(:disabled) { background: rgba(255, 253, 248, 0.92); color: #2f7d6e; }

.model__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model__check {
  margin-left: auto;
  flex: 0 0 auto;
  font-size: 0.8rem;
}

.empty {
  padding: 10px 6px;
}
.empty__title {
  margin: 0;
  font-size: 0.78rem;
  color: rgba(255, 253, 248, 0.8);
}
.empty__hint {
  margin: 4px 0 0;
  font-size: 0.68rem;
  line-height: 1.5;
  color: rgba(255, 253, 248, 0.45);
}

.pop__error {
  margin: 8px 4px 2px;
  font-size: 0.7rem;
  color: #ffd9d0;
}

@media (prefers-reduced-motion: reduce) {
  .pop__panel { animation: none; }
}
</style>
