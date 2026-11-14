<script setup lang="ts">
// =====================================================================
// AnnouncementPanel —— 前台「公告」面板
// ---------------------------------------------------------------------
// 管理员在后台「发布公告」里写的东西都在这里；打开即把全部标为已读。
// =====================================================================

import { onBeforeUnmount, onMounted } from 'vue'
import { useAnnouncements } from '../composables/useAnnouncements'

const emit = defineEmits<{ (one: 'close'): void }>()

const { notices, loading, loadNotices, markAllRead } = useAnnouncements()

function fmtTime(raw: string): string {
  // 后端存的是 UTC 的 "YYYY-MM-DD HH:MM:SS"，补个 Z 再按本地时间显示
  const text = raw.trim()
  if (!text) return ''
  const iso = text.includes('T') ? text : text.replace(' ', 'T') + 'Z'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return text
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

onMounted(async () => {
  await loadNotices(true)
  markAllRead()
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="notice-layer" @click.self="emit('close')">
    <section class="notice-panel" role="dialog" aria-label="公告">
      <header class="notice-head">
        <h2>公告</h2>
        <span class="notice-count">{{ notices.length }} 条</span>
        <button class="notice-close" type="button" title="关闭" @click="emit('close')">×</button>
      </header>

      <div class="notice-body">
        <p v-if="loading && !notices.length" class="notice-empty">正在加载公告…</p>
        <p v-else-if="!notices.length" class="notice-empty">
          还没有公告。管理员在后台「发布公告」里发的东西会出现在这里。
        </p>

        <article
          v-for="item in notices"
          :key="item.id"
          class="notice-item"
          :class="{ 'notice-item--pinned': item.pinned }"
        >
          <div class="notice-item__head">
            <span v-if="item.pinned" class="notice-pin">置顶</span>
            <h3 class="notice-item__title">{{ item.title }}</h3>
          </div>
          <p v-if="item.content" class="notice-item__text">{{ item.content }}</p>
          <div class="notice-item__meta">
            <span v-if="item.publisher">{{ item.publisher }}</span>
            <span>{{ fmtTime(item.created_at) }}</span>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.notice-layer {
  position: fixed;
  inset: 0;
  z-index: 94;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(2, 14, 18, 0.55);
  backdrop-filter: blur(6px);
}

.notice-panel {
  width: min(640px, 94vw);
  max-height: min(80vh, 760px);
  display: flex;
  flex-direction: column;
  border-radius: 18px;
  border: 1px solid rgba(126, 240, 214, 0.18);
  background: rgba(8, 34, 36, 0.97);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
  color: #dff6f6;
  overflow: hidden;
}

.notice-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 18px;
  border-bottom: 1px solid rgba(126, 240, 214, 0.12);
}

.notice-head h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 500;
  letter-spacing: 0.06em;
}

.notice-count {
  font-size: 0.72rem;
  color: #7fb6b6;
}

.notice-close {
  margin-left: auto;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.06);
  color: #a8cccc;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.notice-close:hover {
  background: rgba(255, 120, 140, 0.22);
  color: #ffd9e0;
}

.notice-body {
  padding: 6px 18px 18px;
  overflow-y: auto;
}

.notice-empty {
  padding: 26px 6px;
  text-align: center;
  font-size: 0.82rem;
  color: #7fb6b6;
}

.notice-item {
  padding: 14px 0;
  border-bottom: 1px dashed rgba(126, 240, 214, 0.12);
}

.notice-item:last-child {
  border-bottom: none;
}

.notice-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.notice-item__title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 500;
  color: #eafcf6;
}

.notice-pin {
  flex: none;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid rgba(255, 200, 120, 0.5);
  color: #ffd79a;
  font-size: 0.66rem;
  letter-spacing: 0.04em;
}

.notice-item__text {
  margin: 8px 0 0;
  font-size: 0.82rem;
  line-height: 1.7;
  color: #bfe3e3;
  white-space: pre-wrap;
  word-break: break-word;
}

.notice-item__meta {
  display: flex;
  gap: 12px;
  margin-top: 8px;
  font-size: 0.7rem;
  color: #6f9c9c;
}
</style>
