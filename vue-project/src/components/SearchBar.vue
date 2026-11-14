<script setup lang="ts">
// =====================================================================
// SearchBar —— 全站统一的搜索框（天气 / 行程 / 观看 vlog / 记忆都用它）
// ---------------------------------------------------------------------
// 一个组件负责四件事：
//   1. 输入框（可带放大镜、清空 ×、右侧「搜索」按钮，按钮不传就不显示）
//   2. 点一下弹出「最近搜过」下拉（带单条删除），样式和行程面板一致
//   3. 回车 / 点按钮 → 抛 search 事件，同时把词按 kind 存进 route_searches 表
//   4. 父组件自己算好建议时，用 suggestions 传进来就不去读接口了
//
// kind 分类：route / vlog / vlog-region / weather / memory，互不干扰。
// =====================================================================

import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { deleteRouteSearch, fetchRecentSearches, saveSearchHistory } from '../composables/useRouteHistory'

export interface SearchSuggestion {
  id: number
  label: string
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    maxlength?: number
    /** 历史记录分类；不传就没有下拉、也不记录 */
    kind?: string
    /** 父组件自己算好的建议（给了就不再读接口的历史） */
    suggestions?: SearchSuggestion[]
    /** 按钮文字；不传就不显示按钮 */
    buttonLabel?: string
    disabled?: boolean
    title?: string
    /** 是否显示左边的放大镜 */
    icon?: boolean
    limit?: number
  }>(),
  {
    placeholder: '',
    maxlength: 40,
    kind: '',
    suggestions: undefined,
    buttonLabel: '',
    disabled: false,
    title: '',
    icon: false,
    limit: 8,
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  search: [value: string]
  pick: [value: string]
  remove: [id: number]
}>()

const open = ref(false)
const history = ref<SearchSuggestion[]>([])

const text = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
})

const items = computed<SearchSuggestion[]>(() => props.suggestions ?? history.value)
const showMenu = computed(() => open.value && items.value.length > 0)
const canSubmit = computed(() => !props.disabled && props.modelValue.trim().length > 0)

async function loadHistory() {
  if (!props.kind || props.suggestions) return
  const rows = await fetchRecentSearches(props.limit, props.kind)
  // 同一个词可能被存过多次（换着东西搜过、大小写不同），这里按下拉里显示的顺序去重
  const seen = new Set<string>()
  const list: SearchSuggestion[] = []
  for (const row of rows) {
    const label = (row.origin ?? '').trim()
    const id = row.id ?? 0
    if (!id || !label) continue
    const key = label.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    list.push({ id, label })
  }
  history.value = list
}

function onFocus() {
  open.value = true
  void loadHistory()
}

/** 回车 / 点按钮：抛出去让父组件搜，顺手记一笔历史 */
function submit() {
  const value = props.modelValue.trim()
  if (!value) {
    open.value = false
    return
  }
  emit('search', value)
  if (props.kind) void saveSearchHistory(props.kind, value).then(loadHistory)
  open.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    event.preventDefault()
    submit()
  } else if (event.key === 'Escape') {
    open.value = false
  }
}

/** 点一条历史：填进来、抛 pick（父组件决定要不要立刻搜） */
function pick(item: SearchSuggestion) {
  open.value = false
  emit('update:modelValue', item.label)
  emit('pick', item.label)
  if (props.kind) void saveSearchHistory(props.kind, item.label).then(loadHistory)
}

/** 删一条历史（只删自己的） */
async function remove(item: SearchSuggestion) {
  history.value = history.value.filter((row) => row.id !== item.id)
  emit('remove', item.id)
  await deleteRouteSearch(item.id)
}

function clear() {
  emit('update:modelValue', '')
  open.value = false
}

/** 点外面收起下拉 */
function onDocPointerDown(event: PointerEvent) {
  if (!open.value) return
  const target = event.target as HTMLElement | null
  if (!target?.closest?.('.search-bar')) open.value = false
}

onMounted(() => window.addEventListener('pointerdown', onDocPointerDown))
onBeforeUnmount(() => window.removeEventListener('pointerdown', onDocPointerDown))
</script>

<template>
  <div class="search-bar" :class="{ 'search-bar--disabled': disabled }">
    <div class="search-bar__box">
      <label class="search-bar__field">
        <svg
          v-if="icon"
          viewBox="0 0 24 24"
          width="15"
          height="15"
          aria-hidden="true"
          class="search-bar__icon"
        >
          <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="1.8" />
          <path d="M16 16l4.5 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
        </svg>
        <input
          v-model="text"
          class="search-bar__input"
          type="search"
          :maxlength="maxlength"
          :placeholder="placeholder"
          :title="title"
          :disabled="disabled"
          @focus="onFocus"
          @keydown="onKeydown"
        />
        <button
          v-if="modelValue"
          class="search-bar__clear"
          type="button"
          aria-label="清空"
          @mousedown.prevent
          @click="clear"
        >×</button>
      </label>

      <ul v-if="showMenu" class="search-bar__menu">
        <li v-for="item in items" :key="`${item.id}-${item.label}`">
          <button type="button" class="search-bar__pick" @mousedown.prevent="pick(item)">
            {{ item.label }}
          </button>
          <button
            type="button"
            class="search-bar__del"
            title="删除这条记录"
            @mousedown.prevent="remove(item)"
          >
            <svg class="search-bar__del-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 6 L18 18 M18 6 L6 18" />
            </svg>
          </button>
        </li>
      </ul>
    </div>

    <button
      v-if="buttonLabel"
      class="search-bar__go"
      type="button"
      :disabled="!canSubmit"
      @click="submit"
    >{{ buttonLabel }}</button>
  </div>
</template>

<style scoped>
.search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 auto;
  min-width: 0;
}
.search-bar--disabled { opacity: 0.6; }

.search-bar__box {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
}

.search-bar__field {
  display: flex;
  align-items: center;
  gap: 7px;
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 10px;
  box-sizing: border-box;
  border: 1px solid rgba(255, 253, 248, 0.32);
  border-radius: 10px;
  background: rgba(255, 253, 248, 0.1);
  transition: border-color 0.2s;
}
.search-bar__field:focus-within { border-color: rgba(255, 253, 248, 0.78); }

.search-bar__icon { flex: none; color: rgba(255, 253, 248, 0.5); display: block; }

.search-bar__input {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: none;
  background: transparent;
  color: #fffdf8;
  font-size: 0.82rem;
  font-family: inherit;
  outline: none;
}
.search-bar__input::placeholder { color: rgba(255, 253, 248, 0.38); }
/* 输入框自带的那个小 × 不要，我们自己画 */
.search-bar__input::-webkit-search-cancel-button,
.search-bar__input::-webkit-search-decoration { display: none; }

.search-bar__clear {
  flex: none;
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(255, 253, 248, 0.16);
  color: #fffdf8;
  font-size: 0.7rem;
  line-height: 1;
  cursor: pointer;
}
.search-bar__clear:hover { background: rgba(255, 120, 120, 0.5); }

.search-bar__go {
  flex: none;
  height: 32px;
  box-sizing: border-box;
  padding: 0 14px;
  border: 1px solid rgba(159, 232, 196, 0.4);
  border-radius: 10px;
  background: rgba(159, 232, 196, 0.16);
  color: #d9f6e6;
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
}
.search-bar__go:hover:not(:disabled) { background: rgba(159, 232, 196, 0.28); }
.search-bar__go:disabled { opacity: 0.45; cursor: default; }

/* ---- 历史下拉：和行程面板的 .suggest 同一套外观 ---- */
.search-bar__menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 95;
  margin: 0;
  padding: 4px;
  list-style: none;
  max-height: 190px;
  overflow-y: auto;
  border: 1px solid rgba(255, 253, 248, 0.32);
  border-radius: 10px;
  background: rgba(12, 46, 46, 0.98);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.45);
}
.search-bar__menu li {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 1px 2px;
}
.search-bar__menu button {
  border: none;
  border-radius: 8px;
  background: transparent;
  color: rgba(255, 253, 248, 0.85);
  font-family: inherit;
  cursor: pointer;
}
.search-bar__pick {
  flex: 1 1 auto;
  min-width: 0;
  padding: 7px 8px;
  font-size: 0.78rem;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.search-bar__pick:hover {
  background: rgba(255, 253, 248, 0.14);
  color: #fffdf8;
}
.search-bar__del {
  flex: 0 0 30px;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  padding: 0;
  color: rgba(255, 138, 122, 0.9);
  line-height: 1;
  transition: background 0.15s ease, color 0.15s ease;
}
.search-bar__del:hover {
  background: rgba(255, 138, 122, 0.22);
  color: #ffe3dc;
}
.search-bar__del-icon {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
}
</style>
