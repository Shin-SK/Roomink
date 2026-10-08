<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api.js'

const router = useRouter()
const announcements = ref([])
const unreadCount = ref(0)
const open = ref(false)
const expandedId = ref(null)

const latest = computed(() => announcements.value[0] || null)

function kindIcon(kind) {
  if (kind === 'IMPORTANT') return 'ti-alert-circle'
  if (kind === 'MAINTENANCE') return 'ti-tools'
  return 'ti-sparkles'
}

function kindClass(kind) {
  if (kind === 'IMPORTANT') return 'is-important'
  if (kind === 'MAINTENANCE') return 'is-maintenance'
  return 'is-update'
}

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('ja-JP', { year: 'numeric', month: 'numeric', day: 'numeric' }).format(date)
}

async function load() {
  try {
    const data = await api.getSystemAnnouncements()
    announcements.value = Array.isArray(data.announcements) ? data.announcements : []
    unreadCount.value = Number(data.unread_count) || 0
    if (announcements.value.some(item => !item.is_read && item.kind === 'IMPORTANT')) open.value = true
  } catch {
    // お知らせ取得の一時的な失敗で本来の業務画面は止めない。
  }
}

async function markRead(item) {
  if (item.is_read) return
  try {
    const data = await api.markSystemAnnouncementsRead([item.id])
    item.is_read = true
    unreadCount.value = Number(data.unread_count) || 0
  } catch { /* 次回表示時に再試行 */ }
}

async function toggleItem(item) {
  expandedId.value = expandedId.value === item.id ? null : item.id
  await markRead(item)
}

async function markAllRead() {
  try {
    const data = await api.markSystemAnnouncementsRead([], true)
    announcements.value = announcements.value.map(item => ({ ...item, is_read: true }))
    unreadCount.value = Number(data.unread_count) || 0
  } catch { /* keep visible state */ }
}

async function follow(item) {
  await markRead(item)
  if (item.target_path) await router.push(item.target_path)
}

onMounted(load)
</script>

<template>
  <section v-if="announcements.length" class="system-announcements" :class="kindClass(latest?.kind)">
    <button class="system-announcements__summary" type="button" :aria-expanded="open" @click="open = !open">
      <span class="system-announcements__summary-icon"><i class="ti" :class="kindIcon(latest?.kind)"></i></span>
      <span class="system-announcements__summary-copy">
        <strong>Roominkからのお知らせ</strong>
        <small>{{ latest?.title }}</small>
      </span>
      <span v-if="unreadCount" class="system-announcements__badge">未読 {{ unreadCount }}</span>
      <i class="ti" :class="open ? 'ti-chevron-up' : 'ti-chevron-down'"></i>
    </button>

    <div v-if="open" class="system-announcements__panel">
      <div class="system-announcements__panel-head">
        <strong>更新情報</strong>
        <button v-if="unreadCount" type="button" @click="markAllRead">すべて既読</button>
      </div>
      <article v-for="item in announcements" :key="item.id" class="system-announcements__item" :class="{ unread: !item.is_read }">
        <button type="button" class="system-announcements__item-title" @click="toggleItem(item)">
          <span><i class="ti" :class="kindIcon(item.kind)"></i>{{ item.title }}</span>
          <small>{{ formatDate(item.published_at) }}</small>
        </button>
        <div v-if="expandedId === item.id" class="system-announcements__detail">
          <p>{{ item.body }}</p>
          <button v-if="item.target_path" type="button" class="btn btn-sm btn-outline-primary" @click="follow(item)">
            詳細を見る
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.system-announcements {
  margin: 0 0 1rem;
  border: 1px solid #dbe6e3;
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}
.system-announcements.is-important { border-color: #f3c6c6; }
.system-announcements.is-maintenance { border-color: #f1d39d; }
.system-announcements__summary {
  width: 100%;
  min-height: 58px;
  padding: .7rem .85rem;
  border: 0;
  background: transparent;
  display: flex;
  align-items: center;
  gap: .7rem;
  text-align: left;
}
.system-announcements__summary-icon {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #177f70;
  background: #eaf7f4;
  flex: 0 0 auto;
}
.is-important .system-announcements__summary-icon { color: #b42318; background: #fef0ef; }
.is-maintenance .system-announcements__summary-icon { color: #9a6700; background: #fff7e6; }
.system-announcements__summary-copy { display: grid; gap: 2px; min-width: 0; flex: 1; }
.system-announcements__summary-copy strong { font-size: .9rem; }
.system-announcements__summary-copy small { color: #64748b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.system-announcements__badge { padding: .18rem .5rem; border-radius: 999px; color: #fff; background: #d92d20; font-size: .72rem; white-space: nowrap; }
.system-announcements__panel { border-top: 1px solid #e8efed; }
.system-announcements__panel-head { padding: .65rem .85rem; display: flex; justify-content: space-between; align-items: center; background: #f8faf9; }
.system-announcements__panel-head button { border: 0; color: #177f70; background: transparent; font-size: .8rem; }
.system-announcements__item { border-top: 1px solid #eef2f1; }
.system-announcements__item.unread { background: #f4fbf9; }
.system-announcements__item-title { width: 100%; padding: .75rem .85rem; border: 0; background: transparent; display: flex; justify-content: space-between; gap: 1rem; text-align: left; }
.system-announcements__item-title span { display: flex; align-items: center; gap: .45rem; font-weight: 600; }
.system-announcements__item-title small { color: #94a3b8; white-space: nowrap; }
.system-announcements__detail { padding: 0 .85rem .9rem 2.25rem; }
.system-announcements__detail p { margin: 0 0 .7rem; color: #475569; white-space: pre-line; line-height: 1.65; }
@media (max-width: 575px) {
  .system-announcements__summary { padding: .65rem .7rem; }
  .system-announcements__badge { font-size: 0; width: 9px; height: 9px; padding: 0; }
  .system-announcements__item-title { align-items: flex-start; }
}
</style>
