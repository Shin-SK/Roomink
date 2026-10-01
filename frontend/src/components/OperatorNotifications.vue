<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api.js'

const router = useRouter()
const open = ref(false)
const notifications = ref([])
const unreadCount = ref(0)
const toastNotification = ref(null)
const root = ref(null)
let pollTimer = null
let toastTimer = null
let initialized = false
let highestKnownId = 0

function shownIds() {
  try {
    return new Set(JSON.parse(sessionStorage.getItem('roomink-shown-notification-ids') || '[]'))
  } catch {
    return new Set()
  }
}

function rememberShown(id) {
  const ids = shownIds()
  ids.add(id)
  sessionStorage.setItem(
    'roomink-shown-notification-ids',
    JSON.stringify([...ids].slice(-100)),
  )
}

function showToast(item) {
  if (!item || shownIds().has(item.id)) return
  rememberShown(item.id)
  toastNotification.value = item
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastNotification.value = null
  }, 7000)
}

async function loadNotifications() {
  try {
    const data = await api.getOperatorNotifications()
    const items = Array.isArray(data.notifications) ? data.notifications : []
    const latestId = items.reduce((max, item) => Math.max(max, Number(item.id) || 0), 0)
    if (initialized) {
      const latestNew = items.find(item => !item.is_read && Number(item.id) > highestKnownId)
      showToast(latestNew)
    } else {
      const recentUnread = items.find(item => {
        if (item.is_read) return false
        const createdAt = new Date(item.created_at).getTime()
        return Number.isFinite(createdAt) && Date.now() - createdAt < 120000
      })
      showToast(recentUnread)
      initialized = true
    }
    highestKnownId = Math.max(highestKnownId, latestId)
    notifications.value = items
    unreadCount.value = Number(data.unread_count) || 0
  } catch {
    // 一時的な通信失敗では画面操作を止めず、次回pollで再試行する。
  }
}

async function markRead(item) {
  if (!item.is_read) {
    try {
      const data = await api.markOperatorNotificationsRead([item.id])
      item.is_read = true
      unreadCount.value = Number(data.unread_count) || 0
    } catch { /* next poll will retry the visible state */ }
  }
}

async function openNotification(item) {
  await markRead(item)
  open.value = false
  toastNotification.value = null
  if (item.target_path) await router.push(item.target_path)
}

async function markAllRead() {
  try {
    const data = await api.markOperatorNotificationsRead([], true)
    notifications.value = notifications.value.map(item => ({ ...item, is_read: true }))
    unreadCount.value = Number(data.unread_count) || 0
  } catch { /* keep the existing unread state */ }
}

function formatTime(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('ja-JP', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function onDocumentClick(event) {
  if (open.value && root.value && !root.value.contains(event.target)) open.value = false
}

onMounted(async () => {
  document.addEventListener('click', onDocumentClick)
  await loadNotifications()
  pollTimer = setInterval(loadNotifications, 10000)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  if (pollTimer) clearInterval(pollTimer)
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <div ref="root" class="operator-notifications">
    <button
      type="button"
      class="operator-notifications__bell"
      aria-label="通知"
      :aria-expanded="open"
      @click.stop="open = !open"
    >
      <i class="ti ti-bell"></i>
      <span v-if="unreadCount" class="operator-notifications__count">
        {{ unreadCount > 99 ? '99+' : unreadCount }}
      </span>
    </button>

    <section v-if="open" class="operator-notifications__panel">
      <header>
        <strong>通知</strong>
        <button v-if="unreadCount" type="button" @click="markAllRead">すべて既読</button>
      </header>
      <div v-if="notifications.length" class="operator-notifications__list">
        <button
          v-for="item in notifications"
          :key="item.id"
          type="button"
          class="operator-notifications__item"
          :class="{ unread: !item.is_read }"
          @click="openNotification(item)"
        >
          <span class="operator-notifications__icon"><i class="ti ti-calendar-plus"></i></span>
          <span class="operator-notifications__body">
            <strong>{{ item.title }}</strong>
            <span>{{ item.message }}</span>
            <small>{{ formatTime(item.created_at) }}</small>
          </span>
        </button>
      </div>
      <div v-else class="operator-notifications__empty">新しい通知はありません</div>
    </section>

    <button
      v-if="toastNotification"
      type="button"
      class="operator-booking-toast"
      @click="openNotification(toastNotification)"
    >
      <span class="operator-booking-toast__icon"><i class="ti ti-calendar-plus"></i></span>
      <span>
        <strong>Web予約が入りました</strong>
        <small>{{ toastNotification.message }}</small>
      </span>
      <i class="ti ti-chevron-right"></i>
    </button>
  </div>
</template>

<style scoped>
.operator-notifications {
  position: fixed;
  top: 14px;
  right: 22px;
  z-index: 1080;
}

.operator-notifications__bell {
  width: 44px;
  height: 44px;
  border: 1px solid #dbe6e3;
  border-radius: 50%;
  background: #fff;
  color: #334155;
  box-shadow: 0 4px 16px rgba(15, 23, 42, .12);
  display: grid;
  place-items: center;
  position: relative;
}

.operator-notifications__bell .ti { font-size: 22px; }

.operator-notifications__count {
  position: absolute;
  top: -5px;
  right: -5px;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: 999px;
  background: #ef4444;
  color: #fff;
  border: 2px solid #fff;
  font-size: 11px;
  font-weight: 700;
  display: grid;
  place-items: center;
}

.operator-notifications__panel {
  position: absolute;
  top: 52px;
  right: 0;
  width: min(380px, calc(100vw - 24px));
  max-height: min(560px, calc(100vh - 90px));
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid #dbe6e3;
  border-radius: 14px;
  box-shadow: 0 16px 44px rgba(15, 23, 42, .2);
}

.operator-notifications__panel header {
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e2e8f0;
}

.operator-notifications__panel header button {
  border: 0;
  background: transparent;
  color: #2a9d8f;
  font-size: 13px;
}

.operator-notifications__list { overflow-y: auto; }

.operator-notifications__item {
  width: 100%;
  padding: 13px 15px;
  border: 0;
  border-bottom: 1px solid #edf2f1;
  background: #fff;
  color: #0f172a;
  display: flex;
  gap: 11px;
  text-align: left;
}

.operator-notifications__item.unread { background: #effaf7; }

.operator-notifications__icon,
.operator-booking-toast__icon {
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  border-radius: 50%;
  background: #dff5ef;
  color: #21897e;
  display: grid;
  place-items: center;
}

.operator-notifications__body { display: grid; gap: 3px; min-width: 0; }
.operator-notifications__body strong { font-size: 14px; }
.operator-notifications__body span { color: #475569; font-size: 12px; line-height: 1.5; }
.operator-notifications__body small { color: #94a3b8; font-size: 11px; }
.operator-notifications__empty { padding: 28px 16px; text-align: center; color: #64748b; }

.operator-booking-toast {
  position: fixed;
  right: 22px;
  top: 72px;
  width: min(420px, calc(100vw - 24px));
  padding: 14px;
  border: 1px solid #b9e5da;
  border-radius: 14px;
  background: #fff;
  color: #0f172a;
  box-shadow: 0 18px 50px rgba(15, 23, 42, .22);
  display: flex;
  align-items: center;
  gap: 12px;
  text-align: left;
}

.operator-booking-toast > span:nth-child(2) { flex: 1; display: grid; gap: 3px; }
.operator-booking-toast strong { font-size: 15px; }
.operator-booking-toast small { color: #475569; line-height: 1.45; }

@media (max-width: 767.98px) {
  .operator-notifications { top: 68px; right: 12px; }
  .operator-notifications__panel { top: 50px; }
  .operator-booking-toast { top: 124px; right: 12px; }
}
</style>
