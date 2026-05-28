<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api.js'

const POLL_INTERVAL_MS = 2000
const POLL_INTERVAL_HIDDEN_MS = 10000

const router = useRouter()
const calls = ref([])
const busyIds = ref(new Set())
const isOpen = ref(false)
const pollStopped = ref(false)
const prevNewCount = ref(0)
const autoOpenSuppressed = ref(false)

let timerId = null

function formatTime(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return ''
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    return `${hh}:${mm}`
  } catch {
    return ''
  }
}

function formatPhone(raw) {
  if (!raw) return ''
  const s = String(raw)
  if (s.length === 11 && s.startsWith('0')) {
    return `${s.slice(0, 3)}-${s.slice(3, 7)}-${s.slice(7)}`
  }
  if (s.length === 10 && s.startsWith('0')) {
    return `${s.slice(0, 2)}-${s.slice(2, 6)}-${s.slice(6)}`
  }
  return s
}

const newCount = computed(() => calls.value.filter((c) => c.status === 'NEW').length)
const totalCount = computed(() => calls.value.length)

async function fetchQueue() {
  if (pollStopped.value) return
  try {
    const res = await api.getCtiQueue()
    const list = Array.isArray(res?.calls) ? res.calls : []
    const currentNewCount = list.filter((c) => c.status === 'NEW').length
    const shouldAutoOpen =
      !isOpen.value &&
      !autoOpenSuppressed.value &&
      prevNewCount.value === 0 &&
      currentNewCount >= 1 &&
      document.visibilityState === 'visible'
    calls.value = list
    prevNewCount.value = currentNewCount
    if (shouldAutoOpen) {
      isOpen.value = true
    }
  } catch (err) {
    const code = err?.status ?? err?.response?.status
    if (code === 401 || code === 403) {
      pollStopped.value = true
      return
    }
    console.warn('[CTI] queue fetch failed:', err)
  }
}

function scheduleNext() {
  if (pollStopped.value) return
  const delay = document.visibilityState === 'hidden'
    ? POLL_INTERVAL_HIDDEN_MS
    : POLL_INTERVAL_MS
  timerId = setTimeout(runPollCycle, delay)
}

async function runPollCycle() {
  await fetchQueue()
  scheduleNext()
}

function onVisibilityChange() {
  if (pollStopped.value) return
  if (document.visibilityState === 'visible') {
    if (timerId) clearTimeout(timerId)
    runPollCycle()
  }
}

async function onStart(call) {
  if (busyIds.value.has(call.id)) return
  busyIds.value.add(call.id)
  try {
    await api.ctiCallStart(call.id)
    await fetchQueue()
  } catch (err) {
    console.warn('[CTI] start failed:', err)
  } finally {
    busyIds.value.delete(call.id)
  }
}

async function onDone(call) {
  if (busyIds.value.has(call.id)) return
  busyIds.value.add(call.id)
  try {
    await api.ctiCallDone(call.id)
    await fetchQueue()
  } catch (err) {
    console.warn('[CTI] done failed:', err)
  } finally {
    busyIds.value.delete(call.id)
  }
}

function onCreateOrder(call) {
  router.push({ path: '/op/phone', query: { phone: call.from_phone } })
}

function onOpenCustomer(call) {
  if (!call.customer_id) return
  router.push(`/op/customers/${call.customer_id}`)
}

function openPanel() {
  isOpen.value = true
}

function closePanel() {
  isOpen.value = false
  autoOpenSuppressed.value = true
}

onMounted(() => {
  runPollCycle()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(() => {
  pollStopped.value = true
  if (timerId) clearTimeout(timerId)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <!-- 折りたたみ時のトグルボタン(着信ゼロでも常時表示) -->
  <button
    v-if="!isOpen"
    type="button"
    class="cti-toggle"
    :class="{ 'cti-toggle--new': newCount > 0 }"
    aria-label="着信を表示"
    @click="openPanel"
  >
    <i class="ti ti-phone-incoming"></i>
    <span v-if="totalCount > 0" class="cti-toggle__badge">{{ totalCount }}</span>
  </button>

  <!-- 右サイドバー本体 -->
  <aside
    class="cti-sidebar"
    :class="{ 'cti-sidebar--open': isOpen }"
    aria-label="着信パネル"
  >
    <button
      type="button"
      class="cti-sidebar__close"
      aria-label="閉じる"
      @click="closePanel"
    >
      <i class="ti ti-x"></i>
    </button>

    <header class="cti-sidebar__header">
      <div class="cti-sidebar__title">
        <i class="ti ti-phone-incoming"></i>
        <span>着信</span>
      </div>
      <span v-if="newCount > 0" class="cti-sidebar__count">{{ newCount }}件未対応</span>
      <span v-else-if="totalCount > 0" class="cti-sidebar__count cti-sidebar__count--in-progress">対応中</span>
    </header>

    <div class="cti-sidebar__list">
      <div v-if="calls.length === 0" class="cti-sidebar__empty">
        現在、着信はありません
      </div>
      <article
        v-for="call in calls"
        :key="call.id"
        class="cti-item"
        :class="{ 'cti-item--in-progress': call.status === 'IN_PROGRESS' }"
      >
        <div class="cti-item__top">
          <span
            class="cti-item__status"
            :class="call.status === 'IN_PROGRESS' ? 'cti-item__status--in-progress' : 'cti-item__status--new'"
          >
            {{ call.status === 'IN_PROGRESS' ? '対応中' : '新規' }}
          </span>
          <span v-if="call.is_repeat" class="cti-item__badge cti-item__badge--repeat">リピート</span>
          <span v-if="call.assigned_to" class="cti-item__badge cti-item__badge--assigned">{{ call.assigned_to }}</span>
          <span class="cti-item__time">{{ formatTime(call.created_at) }}</span>
        </div>

        <div class="cti-item__customer">
          <template v-if="call.customer_id">
            <a
              href="#"
              class="cti-item__customer-link"
              @click.prevent="onOpenCustomer(call)"
            >{{ call.customer_name || '顧客' }}</a>
          </template>
          <template v-else>
            <span class="cti-item__customer-unknown">未登録顧客</span>
          </template>
        </div>
        <div class="cti-item__phone">{{ formatPhone(call.from_phone) }}</div>

        <div class="cti-item__actions">
          <button
            v-if="call.status === 'NEW'"
            type="button"
            class="btn btn-primary btn-sm"
            :disabled="busyIds.has(call.id)"
            @click="onStart(call)"
          >
            対応開始
          </button>
          <button
            v-if="call.status === 'IN_PROGRESS'"
            type="button"
            class="btn btn-success btn-sm"
            :disabled="busyIds.has(call.id)"
            @click="onDone(call)"
          >
            対応完了
          </button>
          <button
            type="button"
            class="btn btn-outline-primary btn-sm"
            @click="onCreateOrder(call)"
          >
            予約作成
          </button>
        </div>
      </article>
    </div>
  </aside>
</template>
