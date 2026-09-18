<script setup>
import { ref, computed, onMounted } from 'vue'
import LayoutCast from '../../components/LayoutCast.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const shift = ref(null)
const orders = ref([])
const totalOrders = ref(0)
const unconfirmedCount = ref(0)
const availableOptions = ref([])
const processingOrderId = ref(null)
const optionEditorId = ref(null)
const optionDraftIds = ref([])
const actionErrors = ref({})

onMounted(async () => {
  try {
    const data = await api.getCastToday()
    shift.value = data.shift
    orders.value = data.orders
    totalOrders.value = data.total_orders
    unconfirmedCount.value = data.unconfirmed_count
    availableOptions.value = data.available_options || []
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

function replaceOrder(updated) {
  const idx = orders.value.findIndex(order => order.id === updated.id)
  if (idx !== -1) orders.value[idx] = updated
  unconfirmedCount.value = orders.value.filter(order => order.is_unconfirmed).length
}

function openOptionEditor(order) {
  actionErrors.value[order.id] = ''
  if (optionEditorId.value === order.id) {
    optionEditorId.value = null
    return
  }
  optionEditorId.value = order.id
  optionDraftIds.value = [...(order.option_ids || [])]
}

async function saveOptions(order) {
  processingOrderId.value = order.id
  actionErrors.value[order.id] = ''
  try {
    const updated = await api.updateCastOrderOptions(order.id, optionDraftIds.value)
    replaceOrder(updated)
    optionEditorId.value = null
  } catch (e) {
    actionErrors.value[order.id] = e.message
  } finally {
    processingOrderId.value = null
  }
}

async function startService(order) {
  processingOrderId.value = order.id
  actionErrors.value[order.id] = ''
  try {
    replaceOrder(await api.startCastOrder(order.id))
  } catch (e) {
    actionErrors.value[order.id] = e.message
  } finally {
    processingOrderId.value = null
  }
}

async function completeService(order) {
  if (!window.confirm('接客を終了し、売上・給与へ反映します。よろしいですか？')) return
  processingOrderId.value = order.id
  actionErrors.value[order.id] = ''
  try {
    await api.completeCastOrder(order.id)
    orders.value = orders.value.filter(item => item.id !== order.id)
    totalOrders.value = orders.value.length
    unconfirmedCount.value = orders.value.filter(item => item.is_unconfirmed).length
  } catch (e) {
    actionErrors.value[order.id] = e.message
  } finally {
    processingOrderId.value = null
  }
}

function statusLabel(order) {
  if (order.customer_reservation_state === 'PAYMENT_REQUIRED') return 'カード決済待ち'
  return {
    REQUESTED: '店舗確認待ち',
    CONFIRMED: '接客前',
    IN_PROGRESS: '接客中',
    PENDING_FINALIZE: '終了待ち',
  }[order.status] || order.status
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function displayStartTime(order) {
  return order.start_time_extended || formatTime(order.start)
}

function displayEndTime(order) {
  return order.end_time_extended || formatTime(order.end)
}

function durationMin(order) {
  const s = new Date(order.start)
  const e = new Date(order.end)
  return Math.round((e - s) / 60000)
}

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}

const startHour = computed(() => shift.value ? parseInt(shift.value.start_time) : 12)
const endHour = computed(() => shift.value ? parseInt(shift.value.end_time_extended || shift.value.end_time) : 20)

const hours = computed(() => {
  const arr = []
  for (let h = startHour.value; h <= endHour.value; h++) {
    arr.push(`${String(h).padStart(2, '0')}:00`)
  }
  return arr
})

function parseTimeToMin(t) {
  const [h, m] = String(t).split(':').map(Number)
  return h * 60 + m
}

const gridRef = ref(null)

function layoutBlocks() {
  if (!gridRef.value) return
  const grid = gridRef.value
  const cssVar = parseInt(getComputedStyle(grid).getPropertyValue('--rk-row-hour-h'))
  const hourH = Number.isFinite(cssVar) && cssVar > 0 ? cssVar : 80
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
  <LayoutCast>
    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

    <template v-else>
      <!-- サマリー -->
      <div class="row g-2 mb-3">
        <div class="col-6">
          <div class="card text-center mb-0">
            <div class="card-body p-3">
              <div class="small text-muted mb-1">本日の予約</div>
              <div class="fs-4 fw-bold">{{ totalOrders }}本</div>
            </div>
          </div>
        </div>
        <div class="col-6">
          <div class="card text-center mb-0">
            <div class="card-body p-3">
              <div class="small text-muted mb-1">未確認</div>
              <div class="fs-4 fw-bold" :class="unconfirmedCount > 0 ? 'text-danger' : ''">{{ unconfirmedCount }}本</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 未確認警告 -->
      <div v-if="unconfirmedCount > 0" class="alert alert-warning d-flex align-items-center gap-3 mb-4">
        <i class="ti ti-alert-triangle fs-4 flex-shrink-0"></i>
        <div class="flex-grow-1">
          <div class="fw-bold mb-1">未確認の予約があります</div>
          <div class="small">予約一覧から「確認する」ボタンを押してください</div>
        </div>
      </div>

      <!-- 予約カード一覧 -->
      <div class="rk-section-header"><i class="ti ti-calendar-event"></i> 予約一覧</div>

      <div
        v-for="order in orders"
        :key="order.id"
        class="card ca-order mb-3"
        :class="order.is_unconfirmed ? 'ca-order--unconfirmed' : ''"
      >
        <div class="card-body">
          <div class="ca-order__head">
            <div class="ca-order__time">
              <span class="ca-order__hours">{{ displayStartTime(order) }} – {{ displayEndTime(order) }}</span>
              <span class="ca-order__dur">{{ durationMin(order) }}分</span>
            </div>
            <span
              class="badge"
              :class="order.is_unconfirmed ? 'badge-unconfirmed' : order.customer_reservation_state === 'PAYMENT_REQUIRED' ? 'text-bg-warning' : 'badge-approved'"
            >{{ order.is_unconfirmed ? '未確認' : statusLabel(order) }}</span>
          </div>

          <div class="ca-order__info flex-column align-items-stretch gap-2">
            <div class="ca-order__row">
              <i class="ti ti-user"></i><span><span class="text-muted">予約名：</span><strong>{{ order.reservation_name }}</strong></span>
            </div>
            <div class="ca-order__row">
              <i class="ti ti-door"></i><span>{{ order.room_name }}</span>
            </div>
            <div class="ca-order__row">
              <i class="ti ti-receipt"></i><span>{{ order.course_name }} / {{ formatYen(order.course_price) }}</span>
            </div>
            <div class="ca-order__row">
              <i class="ti ti-sparkles"></i>
              <span>オプション：{{ order.options?.length ? order.options.map(option => option.name).join('、') : 'なし' }}</span>
            </div>
            <div class="ca-order__row" v-if="order.nomination_fee_name">
              <i class="ti ti-heart"></i><span>{{ order.nomination_fee_name }} / {{ formatYen(order.nomination_fee_price) }}</span>
            </div>
            <div class="ca-order__row">
              <i class="ti ti-credit-card"></i><span>支払い：<strong>{{ order.payment_method_label }}</strong></span>
            </div>
            <div class="ca-order__row">
              <i class="ti ti-currency-yen"></i><span>合計：<strong>{{ formatYen(order.total_price) }}</strong></span>
            </div>
          </div>

          <button
            v-if="availableOptions.length"
            class="btn btn-sm btn-outline-secondary w-100 mb-2"
            :disabled="processingOrderId === order.id"
            @click="openOptionEditor(order)"
          >
            <i class="ti ti-adjustments"></i> オプションを選択・変更
          </button>
          <div v-if="optionEditorId === order.id" class="border rounded p-2 mb-3 bg-light">
            <label v-for="option in availableOptions" :key="option.id" class="form-check py-1">
              <input v-model="optionDraftIds" class="form-check-input" type="checkbox" :value="option.id">
              <span class="form-check-label">{{ option.name }}（{{ formatYen(option.price) }}）</span>
            </label>
            <button
              class="btn btn-sm btn-primary w-100 mt-2"
              :disabled="processingOrderId === order.id"
              @click="saveOptions(order)"
            >選択内容を保存</button>
          </div>

          <div class="ca-order__memo" :class="order.memo ? '' : 'ca-order__memo--empty'">
            <i class="ti ti-note"></i><span>{{ order.memo || '備考なし' }}</span>
          </div>

          <div v-if="actionErrors[order.id]" class="alert alert-danger py-2 small mb-2">
            {{ actionErrors[order.id] }}
          </div>

          <button
            v-if="order.is_unconfirmed"
            class="btn btn-warning w-100 fw-bold"
            @click="doAck(order)"
          >
            <i class="ti ti-check"></i> 確認する
          </button>
          <button v-else-if="order.status === 'REQUESTED'" class="btn btn-light w-100 ca-order__done" disabled>
            <i class="ti ti-clock"></i> 店舗確認待ち
          </button>
          <button
            v-else-if="order.status === 'CONFIRMED'"
            class="btn btn-primary w-100 fw-bold"
            :disabled="processingOrderId === order.id"
            @click="startService(order)"
          ><i class="ti ti-player-play"></i> 接客開始</button>
          <button
            v-else-if="order.status === 'IN_PROGRESS' || order.status === 'PENDING_FINALIZE'"
            class="btn btn-success w-100 fw-bold"
            :disabled="processingOrderId === order.id"
            @click="completeService(order)"
          ><i class="ti ti-check"></i> 接客終了・売上へ反映</button>
        </div>
      </div>

      <div v-if="orders.length === 0" class="text-muted text-center py-4">
        本日の予約はありません
      </div>

      <!-- タイムライン -->
      <div class="rk-section-header mt-4"><i class="ti ti-timeline-event"></i> タイムライン</div>

      <section class="ca-schedule ca-schedule--single mb-4">
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
              :data-start="displayStartTime(order)"
              :data-end="displayEndTime(order)"
            >
              <div class="rk-block__title">{{ displayStartTime(order) }} – {{ displayEndTime(order) }} / {{ durationMin(order) }}分</div>
              <div class="rk-block__meta">{{ order.room_name }} / {{ order.is_unconfirmed ? '未確認' : '確認済' }}</div>
            </a>
          </div>
        </div>
      </section>
    </template>
  </LayoutCast>
</template>
