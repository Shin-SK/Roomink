<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const castName = ref('')
const avatarUrl = ref('')
const shift = ref(null)
const orders = ref([])
const totalOrders = ref(0)
const unconfirmedCount = ref(0)

function today() {
  return new Date().toISOString().slice(0, 10)
}

onMounted(async () => {
  try {
    const data = await api.getCastToday(today())
    castName.value = data.cast_name
    avatarUrl.value = data.avatar_url
    shift.value = data.shift
    orders.value = data.orders
    totalOrders.value = data.total_orders
    unconfirmedCount.value = data.unconfirmed_count
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

async function doAck(order) {
  try {
    const updated = await api.ackOrder(order.id)
    const idx = orders.value.findIndex(o => o.id === order.id)
    if (idx !== -1) orders.value[idx] = updated
    unconfirmedCount.value = orders.value.filter(o => o.is_unconfirmed).length
  } catch (e) {
    alert(e.message)
  }
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function durationMin(order) {
  const s = new Date(order.start)
  const e = new Date(order.end)
  return Math.round((e - s) / 60000)
}

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}

const hours = computed(() => {
  const startH = shift.value ? parseInt(shift.value.start_time) : 12
  const endH = shift.value ? parseInt(shift.value.end_time) : 20
  const arr = []
  for (let h = startH; h <= endH; h++) {
    arr.push(`${String(h).padStart(2, '0')}:00`)
  }
  return arr
})

const startHour = computed(() => shift.value ? parseInt(shift.value.start_time) : 12)
const endHour = computed(() => shift.value ? parseInt(shift.value.end_time) : 20)

function parseTimeToMin(t) {
  const [h, m] = String(t).split(':').map(Number)
  return h * 60 + m
}

const gridRef = ref(null)

function layoutBlocks() {
  if (!gridRef.value) return
  const grid = gridRef.value
  const hourH = 80
  const startMin = startHour.value * 60

  const totalH = (endHour.value - startHour.value + 1)
  grid.style.height = `${hourH * totalH}px`

  grid.querySelectorAll('.rk-block').forEach(el => {
    const s = parseTimeToMin(el.dataset.start)
    const e = parseTimeToMin(el.dataset.end)
    const top = ((s - startMin) / 60) * hourH
    const height = Math.max(24, ((e - s) / 60) * hourH)
    el.style.top = `${top + 6}px`
    el.style.height = `${height - 12}px`
  })
}

onMounted(() => {
  setTimeout(layoutBlocks, 100)
})
</script>

<template>
  <div class="cast-layout">
    <header class="cast-header">
      <div class="cast-nav">
        <a href="/cast/today"><img src="/icon.svg" alt="" style="width: 24px;"></a>
      </div>
    </header>

    <main class="cast-content container">

      <div v-if="loading" class="text-center py-5">
        <div class="spinner-border text-primary"></div>
      </div>

      <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

      <template v-else>
        <!-- ページヘッダー -->
        <div class="ca-page-header d-flex align-items-center gap-3 mb-4">
          <div
            v-if="!avatarUrl"
            class="rounded-circle flex-shrink-0 d-flex align-items-center justify-content-center bg-light"
            style="width: 72px; aspect-ratio: 1/1;"
          >
            <i class="ti ti-user" style="font-size: 28px; color: var(--rk-primary)"></i>
          </div>
          <img
            v-else
            :src="avatarUrl"
            class="rounded-circle flex-shrink-0"
            style="width: 72px; aspect-ratio: 1/1; object-fit: cover;"
            alt=""
          >
          <div class="flex-grow-1">
            <div class="ca-page-header__title">{{ castName }}様</div>
            <div class="ca-page-header__sub" v-if="shift">
              <span class="time">
                <i class="ti ti-calendar-event"></i>{{ shift.start_time }}-{{ shift.end_time }}</span>
              <span class="room">
                <i class="ti ti-door"></i>{{ shift.room_name }}</span>
            </div>
          </div>
        </div>

        <!-- サマリーカード -->
        <div class="row g-2 mb-3">
          <div class="col-6">
            <div class="card text-center mb-0">
              <div class="card-body p-3">
                <div class="small text-muted mb-2">本日の予約</div>
                <div class="fs-4 fw-bold">{{ totalOrders }}本</div>
              </div>
            </div>
          </div>
          <div class="col-6">
            <div class="card text-center mb-0">
              <div class="card-body p-3">
                <div class="small text-muted mb-2">未確認</div>
                <div class="fs-4 fw-bold" :class="unconfirmedCount > 0 ? 'text-danger' : ''">{{ unconfirmedCount }}本</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 未確認警告カード -->
        <div v-if="unconfirmedCount > 0" class="alert alert-warning d-flex align-items-center gap-3 mb-4">
          <i class="ti ti-alert-triangle fs-4 flex-shrink-0"></i>
          <div class="flex-grow-1">
            <div class="fw-bold mb-1">未確認の予約があります</div>
            <div class="small">予約内容を確認して「確認する」ボタンを押してください</div>
          </div>
        </div>

        <div id="res-list" class="rk-section-header"><i class="ti ti-calendar-event"></i> 予約一覧</div>

        <!-- 予約カード -->
        <div
          v-for="order in orders"
          :key="order.id"
          class="card mb-3"
          :class="order.is_unconfirmed ? 'border-warning border-2' : ''"
        >
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-start mb-2">
              <div>
                <div class="fw-bold fs-5">{{ formatTime(order.start) }} – {{ formatTime(order.end) }}</div>
                <div class="small text-muted">{{ durationMin(order) }}分</div>
              </div>
              <span
                class="badge"
                :class="order.is_unconfirmed ? 'badge-unconfirmed' : 'badge-approved'"
              >{{ order.is_unconfirmed ? '未確認' : '確認済' }}</span>
            </div>
            <div class="small text-muted mb-2">
              <div><i class="ti ti-door"></i> {{ order.room_name }}</div>
              <div><i class="ti ti-currency-yen"></i> {{ formatYen(order.course_price) }}</div>
            </div>
            <div class="bg-light p-2 rounded small mb-3">
              <i class="ti ti-note"></i> {{ order.memo || '備考なし' }}
            </div>
            <button
              v-if="order.is_unconfirmed"
              class="btn btn-sm btn-warning w-100"
              @click="doAck(order)"
            >
              <i class="ti ti-check"></i> 確認する
            </button>
            <button
              v-else
              class="btn btn-sm btn-outline-primary w-100"
              disabled
            >
              <i class="ti ti-check"></i> 確認済
            </button>
          </div>
        </div>

        <div v-if="orders.length === 0" class="text-muted text-center py-4">
          本日の予約はありません
        </div>

        <!-- タイムライン -->
        <div id="timeline" class="rk-section-header mt-4"><i class="ti ti-timeline-event"></i> タイムライン</div>

        <section class="ca-schedule mb-4">
          <div class="rk-sheet-scroll">
            <div class="rk-sheet" data-cols="1" :data-start="`${String(startHour).padStart(2,'0')}:00`" :data-end="`${String(endHour).padStart(2,'0')}:00`">

              <div class="rk-timecol">
                <div v-for="hour in hours" :key="hour" class="rk-time">{{ hour }}</div>
              </div>

              <div ref="gridRef" class="rk-grid" data-cols="1">
                <a
                  v-for="order in orders"
                  :key="'tl-' + order.id"
                  class="rk-block is-approved"
                  :class="order.is_unconfirmed ? 'is-unconfirmed' : ''"
                  href="#"
                  @click.prevent
                  data-col="0"
                  :data-start="formatTime(order.start)"
                  :data-end="formatTime(order.end)"
                >
                  <div class="rk-block__title">{{ formatTime(order.start) }} – {{ formatTime(order.end) }} / {{ durationMin(order) }}分</div>
                  <div class="rk-block__meta">{{ order.room_name }} / {{ order.is_unconfirmed ? '未確認' : '確認済' }}</div>
                </a>
              </div>

            </div>
          </div>
        </section>

        <!-- 注意事項 -->
        <div class="card mb-3">
          <button class="card-header btn btn-link w-100 text-start d-flex justify-content-between align-items-center" data-bs-toggle="collapse" data-bs-target="#castNotes" aria-expanded="false">
            <span><i class="ti ti-info-circle"></i> 注意事項</span>
            <i class="ti ti-chevron-down"></i>
          </button>
          <div class="collapse" id="castNotes">
            <div class="card-body">
              <ul class="mb-0 ps-3">
                <li>予約内容を確認したら「確認する」ボタンを押してください</li>
                <li>予約開始15分前までに準備を完了してください</li>
                <li>遅刻やキャンセルの連絡があった場合は、すぐに運営に報告してください</li>
                <li>顧客情報は絶対に外部に漏らさないでください</li>
              </ul>
            </div>
          </div>
        </div>

        <a href="tel:03-1234-5678" class="card text-decoration-none text-reset mb-4 mt-4">
          <div class="card-body d-flex align-items-center gap-3">
            <div class="flex-shrink-0">
              <div class="rounded-circle d-flex align-items-center justify-content-center bg-light" style="width: 44px; height: 44px;">
                <i class="ti ti-phone" style="color: var(--rk-primary); font-size: 22px;"></i>
              </div>
            </div>
            <div class="flex-grow-1">
              <div class="fw-bold mb-1">困ったときは運営へ</div>
              <div class="small text-muted">タップして電話する</div>
            </div>
            <i class="ti ti-chevron-right text-muted"></i>
          </div>
        </a>

        <!-- フッターメッセージ -->
        <div class="text-center mb-5">
          <p class="text-muted" style="font-size: 0.8125rem;">本日もよろしくお願いします！</p>
        </div>

      </template>
    </main>

    <!-- フッター -->
    <footer class="footer position-fixed bottom-0 w-100 p-3 bg-white border-top">
      <div class="container d-flex align-items-center justify-content-between">
        <button class="btn border-0 p-0">
          <a href="/cast/today" class="nav-link active">
            <i class="ti ti-home"></i>
            <small>マイページ</small>
          </a>
        </button>
        <button class="btn border-0 p-0">
          <a href="/cast/today#res-list" class="nav-link">
            <i class="ti ti-timeline-event-exclamation"></i>
            <small>予約リスト</small>
          </a>
        </button>
        <button class="btn border-0 p-0">
          <a href="/cast/today#timeline" class="nav-link">
            <i class="ti ti-users"></i>
            <small>タイムライン</small>
          </a>
        </button>
      </div>
    </footer>
  </div>
</template>
