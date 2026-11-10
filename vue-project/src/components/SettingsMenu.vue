<!-- ====================================================================
  SettingsMenu —— 右上角齿轮弹出的设置面板（多套 Key / 多个模型）
  两个视图在同一块面板里切换：
    · 列表：看所有提供商（打码 Key + 当前模型），可切换使用 / 切模型 / 编辑
    · 表单：新增或编辑一套 Key，可填多个候选模型并选当前模型
  数据与请求见 composables/useProviders.ts（后端 routers/providers.py）。
  注意：完整 Key 不会再发回前端，想改只能重新填一套。
==================================================================== -->

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  activateProvider,
  createProvider,
  ProviderError,
  loadProviders,
  providers,
  providerDefaults,
  removeProvider,
  setProviderModel,
  updateProvider,
} from '../composables/useProviders'
import type { Provider } from '../composables/useProviders'

const props = withDefaults(
  defineProps<{
    // AI 正在回复时为 true：不允许切换提供商 / 模型 / 改配置
    locked?: boolean
  }>(),
  { locked: false }
)

const emit = defineEmits<{
  close: []
}>()

// 所有会改数据的操作都先看这个
const blocked = computed(() => props.locked || saving.value)

type View = 'list' | 'form'

const view = ref<View>('list')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const tip = ref('')
// 保存失败时后端会告诉我们是哪一项写错了（api_key / base_url / model）
const fieldError = ref<{ field: string; message: string } | null>(null)
// 保存成功（含测试结论）的绿色提示
const success = ref('')

// 正在编辑的提供商（null = 新增）
const editingId = ref<number | null>(null)
const draftName = ref('DeepSeek')
const draftKey = ref('')          // 留空 = 不改 Key
const draftBase = ref('')
const draftModels = ref('')       // 逗号分隔
const draftModel = ref('')        // 当前模型
const reveal = ref(false)
const deleteArmed = ref(false)

let tipTimer: ReturnType<typeof setTimeout> | null = null

const hasAny = computed(() => providers.value.length > 0)
const activeProvider = computed(() => providers.value.find((p) => p.isActive) ?? null)

// 表单里"可用模型"解析成数组（中英文逗号都认，去重保序）
const draftModelList = computed(() => {
  const out: string[] = []
  for (const piece of draftModels.value.replace(/，/g, ',').split(',')) {
    const name = piece.trim()
    if (name && !out.includes(name)) out.push(name)
  }
  return out
})

function flash(message: string) {
  tip.value = message
  if (tipTimer) clearTimeout(tipTimer)
  tipTimer = setTimeout(() => (tip.value = ''), 2000)
}

onMounted(async () => {
  document.addEventListener('keydown', onKeydown)
  await refresh()
  loading.value = false
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  if (tipTimer) clearTimeout(tipTimer)
})

async function refresh() {
  error.value = ''
  try {
    await loadProviders()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '读取失败'
  }

  await loadTts()
}

// ---------------- 语音（Qwen-TTS） ----------------
const ttsKeyDraft = ref('')
const ttsModel = ref('qwen3-tts-flash')
const ttsModels = ref<string[]>(['qwen3-tts-flash', 'qwen-tts'])
const ttsHasKey = ref(false)
const ttsKeyMasked = ref('')
const ttsSaving = ref(false)
const ttsMsg = ref('')
const ttsLocal = ref<{ url: string; ready: boolean; ref_audio: string } | null>(null)

async function loadTts() {
  try {
    const res = await fetch('/api/tts/settings')
    if (!res.ok) return
    const data = await res.json()
    ttsHasKey.value = Boolean(data.has_key)
    ttsKeyMasked.value = data.key_masked ?? ''
    ttsModel.value = data.model || 'qwen3-tts-flash'
    if (data.local) ttsLocal.value = data.local
    if (Array.isArray(data.models) && data.models.length) ttsModels.value = data.models
  } catch {
    // 读不到就先按未配置处理
  }
}

async function saveTts() {
  if (blocked.value) return
  ttsSaving.value = true
  ttsMsg.value = ''
  error.value = ''
  try {
    const res = await fetch('/api/tts/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: ttsKeyDraft.value.trim(),
        model: ttsModel.value.trim(),
      }),
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) throw new Error((data && data.detail) || '保存失败')
    ttsHasKey.value = Boolean(data.has_key)
    ttsKeyMasked.value = data.key_masked ?? ''
    ttsKeyDraft.value = ''
    ttsMsg.value = '语音 Key 已保存'
    flash(ttsMsg.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    ttsSaving.value = false
  }
}
// ---------------- 表单 ----------------
function startCreate() {
  if (blocked.value) return
  editingId.value = null
  draftName.value = 'DeepSeek'
  draftKey.value = ''
  draftBase.value = ''
  draftModels.value = providerDefaults.value.model || ''
  draftModel.value = providerDefaults.value.model || ''
  reveal.value = false
  deleteArmed.value = false
  error.value = ''
  fieldError.value = null
  success.value = ''
  view.value = 'form'
}

function startEdit(provider: Provider) {
  if (blocked.value) return
  editingId.value = provider.id
  draftName.value = provider.name
  draftKey.value = ''
  draftBase.value = provider.baseUrl
  draftModels.value = provider.models.join(', ')
  draftModel.value = provider.model
  reveal.value = false
  deleteArmed.value = false
  error.value = ''
  fieldError.value = null
  success.value = ''
  view.value = 'form'
}

function backToList() {
  view.value = 'list'
  error.value = ''
  fieldError.value = null
  deleteArmed.value = false
}

/** 用户一改输入就把"哪一项错"的标记清掉，别一直红着 */
function clearFieldError() {
  fieldError.value = null
  error.value = ''
}

async function save() {
  if (blocked.value) return
  const name = draftName.value.trim() || 'DeepSeek'
  const models = draftModelList.value
  const model = draftModel.value.trim() || models[0] || ''

  if (editingId.value === null && !draftKey.value.trim()) {
    error.value = '新增提供商必须填 API Key'
    return
  }

  saving.value = true
  error.value = ''
  fieldError.value = null
  success.value = ''
  try {
    const payload = {
      name,
      apiKey: draftKey.value.trim() || undefined,
      baseUrl: draftBase.value.trim(),
      models,
      model,
    }
    // 后端会先用这套配置真的请求一次接口，通了才写入，并把测试结论带回来
    const tested =
      editingId.value === null
        ? await createProvider(payload)
        : await updateProvider(editingId.value, payload)

    success.value = tested || '测试通过，已保存'
    view.value = 'list'
    flash('已保存')
  } catch (err) {
    // ProviderError 带 field：把对应的输入框标红 + 单独提示
    if (err instanceof ProviderError && err.field) {
      fieldError.value = { field: err.field, message: err.message }
    } else {
      error.value = err instanceof Error ? err.message : '保存失败'
    }
  } finally {
    saving.value = false
  }
}

async function destroy() {
  if (editingId.value === null || blocked.value) return
  if (!deleteArmed.value) {
    deleteArmed.value = true
    return
  }

  saving.value = true
  error.value = ''
  try {
    await removeProvider(editingId.value)
    deleteArmed.value = false
    view.value = 'list'
    flash('已删除')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败'
  } finally {
    saving.value = false
  }
}

// ---------------- 列表上的快捷操作 ----------------
async function use(provider: Provider) {
  if (provider.isActive || blocked.value) return
  saving.value = true
  error.value = ''
  try {
    await activateProvider(provider.id)
    flash(`聊天已切换到「${provider.name}」`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '切换失败'
  } finally {
    saving.value = false
  }
}

async function changeModel(provider: Provider, event: Event) {
  const model = (event.target as HTMLSelectElement).value
  if (model === provider.model) return
  if (blocked.value) return
  saving.value = true
  error.value = ''
  try {
    await setProviderModel(provider.id, model)
    flash('模型已切换')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '切换模型失败'
    await refresh()   // 失败时把下拉框拉回真实状态
  } finally {
    saving.value = false
  }
}

function modelOptions(provider: Provider): string[] {
  const list = [...provider.models]
  if (provider.model && !list.includes(provider.model)) list.unshift(provider.model)
  if (!list.length && providerDefaults.value.model) list.push(providerDefaults.value.model)
  return list
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    if (view.value === 'form') backToList()
    else emit('close')
  }
}
</script>

<template>
  <div class="menu-layer">
    <div class="menu-backdrop" @click="emit('close')"></div>

    <div class="menu-pop" role="dialog" aria-label="设置">
      <div class="menu-head">
        <span class="menu-title">设置</span>
        <span class="menu-badge" :class="{ 'menu-badge--off': !hasAny }">
          {{ hasAny ? `${providers.length} 套 Key` : '未配置 Key' }}
        </span>
      </div>

      <p v-if="loading" class="menu-hint">读取中…</p>

      <!-- ================= 列表 ================= -->
      <template v-else-if="view === 'list'">
        <p class="menu-intro">填入各提供商的 API 密钥即可使用其模型；点「使用」切换聊天当前使用的那套。</p>

        <p v-if="props.locked" class="locked-hint">芙芙正在回复，等这一轮说完再调整～</p>

        <div v-if="!hasAny" class="empty">
          <p class="empty__text">还没有配置任何 API Key</p>
          <button class="menu-save" type="button" @click="startCreate">添加模型提供商</button>
        </div>

        <ul v-else class="providers">
          <li
            v-for="p in providers"
            :key="p.id"
            class="provider"
            :class="{ 'provider--active': p.isActive }"
          >
            <div class="provider__head">
              <span class="provider__dot" :class="{ 'provider__dot--off': !p.isActive }"></span>
              <span class="provider__name">{{ p.name }}</span>
              <span v-if="p.isActive" class="provider__active">使用中</span>
              <button
                class="provider__edit"
                type="button"
                :disabled="blocked"
                @click="startEdit(p)"
              >
                编辑
              </button>
            </div>

            <p class="provider__key">{{ p.apiKeyMasked }}</p>

            <div class="provider__row">
              <select
                class="provider__select"
                :value="p.model"
                :disabled="blocked"
                :aria-label="`${p.name} 使用的模型`"
                @change="changeModel(p, $event)"
              >
                <option v-for="m in modelOptions(p)" :key="m" :value="m">{{ m }}</option>
              </select>

              <button
                v-if="!p.isActive"
                class="mini mini--use"
                type="button"
                :disabled="blocked"
                @click="use(p)"
              >
                使用
              </button>
            </div>
          </li>
        </ul>

        <button v-if="hasAny" class="add" type="button" :disabled="blocked" @click="startCreate">
          <span class="add__plus">＋</span> 添加模型提供商
        </button>
        <!-- 语音（Qwen-TTS）：放在聊天 Key 下面 -->
        <section class="map-box">
          <p class="map-box__title">
            语音（电话）
            <span class="map-box__tag" :class="{ 'map-box__tag--off': !ttsHasKey }">
              {{ ttsHasKey ? '已配置' : '未配置' }}
            </span>
          </p>
          <p class="map-box__desc">
            优先用本地 GPT-SoVITS 的芙宁娜音色；本地服务没起来时，才会退回云端的 Qwen-TTS。
          </p>
          <p v-if="ttsLocal" class="tts-local">
            本地音色：<strong>Furina</strong>
            · 服务 {{ ttsLocal.url }}
            · 参考音频{{ ttsLocal.ready ? '已就绪' : '缺失（需要 models/Furina_GPT_SoVITS/ref.wav）' }}
          </p>
          <input
            v-model="ttsKeyDraft"
            class="menu-input menu-input--wide"
            type="text"
            spellcheck="false"
            :placeholder="ttsHasKey ? `已保存 ${ttsKeyMasked}（留空 = 不修改）` : 'DashScope API Key（sk-…）'"
          />
          <label class="tts-field">
            <span class="tts-field__label">模型</span>
            <select v-model="ttsModel" class="menu-input tts-select">
              <option v-for="m in ttsModels" :key="m" :value="m">{{ m }}</option>
            </select>
          </label>
          <button
            class="menu-save"
            type="button"
            :disabled="blocked || ttsSaving"
            @click="saveTts"
          >
            {{ ttsSaving ? '保存中…' : '保存语音 Key' }}
          </button>
        </section>
                <p v-if="success" class="success-hint">✅ {{ success }}</p>
        <p v-if="tip" class="menu-tip">{{ tip }}</p>
        <p v-if="error" class="menu-error">{{ error }}</p>

        <p class="menu-hint">
          每个账号可以放多套 Key，各自带多个模型；当前使用中的那套会被聊天接口读取。
        </p>
      </template>

      <!-- ================= 表单 ================= -->
      <template v-else>
        <button class="back" type="button" @click="backToList">← 返回列表</button>

        <label class="menu-label" for="p-name">名称</label>
        <input
          id="p-name"
          v-model="draftName"
          class="menu-input menu-input--wide"
          maxlength="40"
          @input="clearFieldError"
        />

        <label class="menu-label" for="p-key">API Key</label>
        <div class="menu-field">
          <input
            id="p-key"
            v-model="draftKey"
            class="menu-input"
            :class="{ 'menu-input--bad': fieldError?.field === 'api_key' }"
            :type="reveal ? 'text' : 'password'"
            :placeholder="editingId === null ? 'sk-xxxxxx' : '留空 = 不修改'"
            autocomplete="off"
            spellcheck="false"
            @input="clearFieldError"
          />
          <button
            class="menu-eye"
            type="button"
            :title="reveal ? '隐藏' : '显示'"
            @click="reveal = !reveal"
          >
            {{ reveal ? '🙈' : '👁' }}
          </button>
        </div>
        <p v-if="fieldError?.field === 'api_key'" class="field-error">{{ fieldError.message }}</p>
        <p v-if="editingId !== null" class="menu-sub">
          当前：{{ providers.find((x) => x.id === editingId)?.apiKeyMasked }}
        </p>

        <label class="menu-label" for="p-base">Base URL</label>
        <input
          id="p-base"
          v-model="draftBase"
          class="menu-input menu-input--wide"
          :class="{ 'menu-input--bad': fieldError?.field === 'base_url' }"
          type="text"
          spellcheck="false"
          :placeholder="providerDefaults.baseUrl"
          @input="clearFieldError"
        />
        <p v-if="fieldError?.field === 'base_url'" class="field-error">{{ fieldError.message }}</p>

        <label class="menu-label" for="p-models">可用模型（逗号分隔，可填多个）</label>
        <input
          id="p-models"
          v-model="draftModels"
          class="menu-input menu-input--wide"
          :class="{ 'menu-input--bad': fieldError?.field === 'model' }"
          type="text"
          spellcheck="false"
          :placeholder="providerDefaults.model"
          @input="clearFieldError"
        />

        <label class="menu-label" for="p-model">当前模型</label>
        <select
          id="p-model"
          v-model="draftModel"
          class="menu-input menu-input--wide provider__select"
          :class="{ 'menu-input--bad': fieldError?.field === 'model' }"
          @change="clearFieldError"
        >
          <option v-for="m in draftModelList" :key="m" :value="m">{{ m }}</option>
          <option v-if="draftModel && !draftModelList.includes(draftModel)" :value="draftModel">
            {{ draftModel }}
          </option>
        </select>
        <p v-if="fieldError?.field === 'model'" class="field-error">{{ fieldError.message }}</p>

        <div class="menu-actions">
          <button class="menu-save" type="button" :disabled="blocked" @click="save">
            {{ saving ? '测试中…' : '测试并保存' }}
          </button>
          <button
            v-if="editingId !== null"
            class="menu-clear"
            type="button"
            :disabled="blocked"
            @click="destroy"
          >
            {{ deleteArmed ? '再点一次确认删除' : '删除' }}
          </button>
        </div>

        <p v-if="success" class="success-hint">✅ {{ success }}</p>
        <p v-if="error" class="menu-error">{{ error }}</p>
        <p class="menu-hint">
          新增时必须填 Key，编辑时留空表示不改。点保存会先用这套配置真实请求一次接口，
          测试通过才写入；不通过会标红具体输入框并说明原因。
        </p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.menu-layer {
  position: absolute;
  top: calc(100% + 14px);
  right: 0;
  z-index: 60;
}

.menu-backdrop {
  position: fixed;
  inset: 0;
  z-index: 0;
}

.menu-pop {
  position: relative;
  z-index: 1;
  width: 344px;
  max-height: min(78vh, 620px);
  overflow-y: auto;
  padding: 14px 16px 12px;
  box-sizing: border-box;
  border: 1.5px solid rgba(255, 253, 248, 0.4);
  border-radius: 14px;
  background: rgba(12, 46, 46, 0.94);
  backdrop-filter: blur(14px);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.38);
  color: #fffdf8;
  animation: menu-in 0.2s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
.menu-pop::-webkit-scrollbar { width: 6px; }
.menu-pop::-webkit-scrollbar-thumb {
  background: rgba(255, 253, 248, 0.25);
  border-radius: 3px;
}
@keyframes menu-in {
  from { opacity: 0; transform: translateY(-6px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.menu-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.menu-title {
  font-size: 0.95rem;
  font-weight: 500;
  letter-spacing: 0.04em;
}
.menu-badge {
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(143, 214, 186, 0.22);
  color: #b9ecd4;
  font-size: 0.68rem;
}
.menu-badge--off {
  background: rgba(255, 253, 248, 0.1);
  color: rgba(255, 253, 248, 0.6);
}

.success-hint {
  margin: 0 0 10px;
  padding: 7px 10px;
  border-radius: 9px;
  background: rgba(143, 214, 186, 0.16);
  border: 1px solid rgba(143, 214, 186, 0.42);
  color: #b9ecd4;
  font-size: 0.72rem;
  line-height: 1.45;
}

.menu-input--bad {
  border-color: #ff8a7a;
  background: rgba(255, 138, 122, 0.12);
  box-shadow: 0 0 0 2px rgba(255, 138, 122, 0.28);
}

.field-error {
  margin: 5px 2px 0;
  font-size: 0.7rem;
  line-height: 1.45;
  color: #ffb4a8;
}

.locked-hint {
  margin: 0 0 10px;
  padding: 7px 10px;
  border-radius: 9px;
  background: rgba(255, 214, 153, 0.14);
  border: 1px solid rgba(255, 214, 153, 0.3);
  color: #ffdca8;
  font-size: 0.7rem;
  line-height: 1.45;
}

.menu-intro {
  margin: 0 0 10px;
  font-size: 0.7rem;
  line-height: 1.55;
  color: rgba(255, 253, 248, 0.5);
}

/* ---- 列表 ---- */
.providers {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.provider {
  padding: 10px 12px;
  border: 1px solid rgba(255, 253, 248, 0.16);
  border-radius: 12px;
  background: rgba(255, 253, 248, 0.05);
}
.provider--active {
  border-color: rgba(143, 214, 186, 0.5);
  background: rgba(143, 214, 186, 0.1);
}
.provider__head {
  display: flex;
  align-items: center;
  gap: 7px;
}
.provider__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #46d18a;
  box-shadow: 0 0 6px rgba(70, 209, 138, 0.7);
  flex: 0 0 auto;
}
.provider__dot--off { background: rgba(255, 253, 248, 0.35); box-shadow: none; }
.provider__name {
  font-size: 0.86rem;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.provider__active {
  padding: 1px 7px;
  border-radius: 9px;
  background: rgba(143, 214, 186, 0.25);
  color: #b9ecd4;
  font-size: 0.64rem;
}
.provider__edit {
  margin-left: auto;
  height: 24px;
  padding: 0 12px;
  border: 1px solid rgba(255, 253, 248, 0.4);
  border-radius: 12px;
  background: transparent;
  color: #fffdf8;
  font-size: 0.72rem;
  font-family: inherit;
  cursor: pointer;
  flex: 0 0 auto;
}
.provider__edit:hover:not(:disabled) { background: rgba(255, 253, 248, 0.14); }
.provider__edit:disabled { opacity: 0.45; cursor: not-allowed; }

.provider__key {
  margin: 6px 0 0;
  font-size: 0.72rem;
  color: rgba(255, 253, 248, 0.55);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.provider__row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}

.provider__select {
  flex: 1;
  min-width: 0;
  height: 26px;
  padding: 0 8px;
  box-sizing: border-box;
  border: 1px solid rgba(255, 253, 248, 0.28);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.24);
  color: #eafff5;
  font-size: 0.72rem;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  outline: none;
  cursor: pointer;
}
.provider__select:focus { border-color: rgba(255, 253, 248, 0.7); }
.provider__select option {
  background: #0b2f2f;
  color: #eafff5;
}

.mini {
  height: 24px;
  padding: 0 10px;
  border: 1px solid rgba(255, 253, 248, 0.3);
  border-radius: 12px;
  background: transparent;
  color: rgba(255, 253, 248, 0.85);
  font-size: 0.7rem;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
}
.mini:hover { background: rgba(255, 253, 248, 0.14); }
.mini:disabled { opacity: 0.45; cursor: not-allowed; }
.mini--use {
  border-color: rgba(143, 214, 186, 0.55);
  color: #b9ecd4;
}

.add {
  width: 100%;
  margin-top: 10px;
  height: 34px;
  border: 1px dashed rgba(255, 253, 248, 0.32);
  border-radius: 12px;
  background: transparent;
  color: rgba(255, 253, 248, 0.8);
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.18s, border-color 0.18s;
}
.add:hover:not(:disabled) {
  background: rgba(255, 253, 248, 0.08);
  border-color: rgba(255, 253, 248, 0.6);
}
.add:disabled { opacity: 0.45; cursor: not-allowed; }
.add__plus { margin-right: 2px; }

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 18px 12px;
  border: 1px dashed rgba(255, 253, 248, 0.25);
  border-radius: 12px;
}
.empty__text {
  margin: 0;
  font-size: 0.8rem;
  color: rgba(255, 253, 248, 0.7);
}

/* ---- 表单 ---- */
.back {
  margin-bottom: 8px;
  padding: 0;
  border: none;
  background: transparent;
  color: rgba(255, 253, 248, 0.65);
  font-size: 0.74rem;
  font-family: inherit;
  cursor: pointer;
}
.back:hover { color: #fffdf8; }

.menu-label {
  display: block;
  margin: 8px 0 5px;
  font-size: 0.74rem;
  color: rgba(255, 253, 248, 0.68);
}

.menu-field { position: relative; display: flex; }

.menu-input {
  flex: 1;
  min-width: 0;
  width: 100%;
  height: 30px;
  padding: 0 36px 0 11px;
  box-sizing: border-box;
  border: 1px solid rgba(255, 253, 248, 0.3);
  border-radius: 9px;
  background: rgba(255, 253, 248, 0.1);
  color: #fffdf8;
  font-size: 0.78rem;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  outline: none;
  transition: border-color 0.2s;
}
.menu-input--wide { padding: 0 11px; }
.menu-input::placeholder {
  color: rgba(255, 253, 248, 0.38);
  font-family: inherit;
}
.menu-input:focus { border-color: rgba(255, 253, 248, 0.75); }

.menu-eye {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 7px;
  background: transparent;
  font-size: 0.76rem;
  cursor: pointer;
}
.menu-eye:hover { background: rgba(255, 253, 248, 0.14); }

.menu-sub {
  margin: 6px 0 0;
  font-size: 0.68rem;
  color: rgba(255, 253, 248, 0.5);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.menu-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
}
.map-box__tag--off {
  background: rgba(255, 253, 248, 0.12);
  color: rgba(255, 253, 248, 0.55);
}
.tts-local {
  margin: 0 0 2px;
  font-size: 0.66rem;
  line-height: 1.5;
  color: rgba(255, 253, 248, 0.62);
}
.tts-local strong { color: #9fe8c4; }
.tts-row {
  display: flex;
  gap: 8px;
}
.tts-field {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 3px;
}
.tts-field__label {
  font-size: 0.64rem;
  color: rgba(255, 253, 248, 0.45);
}
.tts-select {
  height: 30px;
  padding: 0 6px;
  color-scheme: dark;
}
.tts-select option {
  background: #0b2b2b;
  color: #fffdf8;
}
/* ---- 高德地图 Key 区块 ---- */
.map-box {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid rgba(255, 253, 248, 0.14);
  border-radius: 12px;
  background: rgba(255, 253, 248, 0.04);
  display: grid;
  gap: 7px;
}
.map-box__title {
  margin: 0;
  font-size: 0.8rem;
  color: #fffdf8;
  display: flex;
  align-items: center;
  gap: 6px;
}
.map-box__tag {
  padding: 0 6px;
  border-radius: 8px;
  background: rgba(159, 232, 196, 0.18);
  color: #9fe8c4;
  font-size: 0.62rem;
}
.map-box__desc {
  margin: 0 0 2px;
  font-size: 0.68rem;
  line-height: 1.5;
  color: rgba(255, 253, 248, 0.45);
}
.menu-save {
  height: 30px;
  padding: 0 18px;
  border: none;
  border-radius: 15px;
  background: #fffdf8;
  color: #2f7d6e;
  font-size: 0.82rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: opacity 0.2s;
}
.menu-save:disabled { opacity: 0.45; cursor: not-allowed; }

.menu-clear {
  height: 30px;
  padding: 0 14px;
  border: 1px solid rgba(255, 253, 248, 0.35);
  border-radius: 15px;
  background: transparent;
  color: rgba(255, 253, 248, 0.85);
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
}
.menu-clear:hover { background: rgba(255, 253, 248, 0.14); }
.menu-clear:disabled { opacity: 0.4; cursor: not-allowed; }

.menu-tip {
  margin: 8px 0 0;
  font-size: 0.72rem;
  color: #b9ecd4;
}
.menu-error {
  margin: 8px 0 0;
  font-size: 0.72rem;
  color: #ffd9d0;
}
.menu-hint {
  margin: 10px 0 0;
  font-size: 0.66rem;
  line-height: 1.55;
  color: rgba(255, 253, 248, 0.45);
}

@media (prefers-reduced-motion: reduce) {
  .menu-pop { animation: none; }
}
</style>
