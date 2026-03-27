<script setup>
import { ref, computed, onMounted } from 'vue'
import LayoutCast from '../../components/LayoutCast.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const castName = ref('')
const avatarUrl = ref('')
const shift = ref(null)
const orders = ref([])
const totalOrders = ref(0)
const unconfirmedCount = ref(0)
const lineLinked = ref(false)
const lineLinkCode = ref('')

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
    lineLinked.value = data.line_linked || false
    lineLinkCode.value = data.line_link_code || ''
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

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}

function durationMin(order) {
  const s = new Date(order.start)
  const e = new Date(order.end)
  return Math.round((e - s) / 60000)
}
</script>

<template>
  <LayoutCast>
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

        <!-- LINE連携カード -->
        <div class="card mb-3" :class="lineLinked ? 'border-success' : 'border-warning border-2'">
          <div class="card-body">
            <div class="d-flex align-items-center gap-3">
              <div class="flex-shrink-0">
                <div
                  class="rounded-circle d-flex align-items-center justify-content-center"
                  :class="lineLinked ? 'bg-success' : 'bg-warning'"
                  style="width: 40px; height: 40px;"
                >
                  <i class="ti ti-brand-line" style="font-size: 20px; color: #fff;"></i>
                </div>
              </div>
              <div class="flex-grow-1">
                <div class="fw-bold mb-1">LINE連携</div>
                <div v-if="lineLinked" class="small text-success">
                  <i class="ti ti-check"></i> 連携済み — リマインド通知が届きます
                </div>
                <template v-else>
                  <div class="small text-muted mb-2">公式LINEに以下のコードを送信してください</div>
                  <div class="bg-light rounded p-2 text-center">
                    <span class="fw-bold fs-4 font-monospace letter-spacing-2">{{ lineLinkCode }}</span>
                  </div>
                </template>
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

        <!-- 予約一覧 -->
        <div class="rk-section-header"><i class="ti ti-calendar-event"></i> 予約一覧</div>

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
              <div class="small text-muted">タップして電話する<i class="ti ti-chevron-right text-muted"></i>
              </div>
            </div>
          </div>
        </a>

        <!-- フッターメッセージ -->
        <div class="text-center mb-5">
          <p class="text-muted" style="font-size: 0.8125rem;">本日もよろしくお願いします！</p>
        </div>

      </template>
  </LayoutCast>
</template>
