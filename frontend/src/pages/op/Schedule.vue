<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import TimelineGrid from '../../components/TimelineGrid.vue'
import CustomerInfoCard from '../../components/CustomerInfoCard.vue'
import OrderForm from '../../components/OrderForm.vue'
import UnavailableTimeModal from '../../components/UnavailableTimeModal.vue'
import { api, normalizePhone } from '../../api.js'
import { getAuthRole } from '../../router.js'
import { selectedStoreId } from '../../storeSelection.js'

const router = useRouter()
const route = useRoute()
const businessDayBoundaryHour = ref(5)
const selectedDate = ref(route.query.date || today())
const highlightId = ref(route.query.highlight ? Number(route.query.highlight) : null)
const casts = ref([])
const orders = ref([])
const unavailableTimes = ref([])
const kpi = ref({ total_orders: 0, confirmed: 0, requested: 0, estimated_sales: 0 })
const loading = ref(true)
const toolbarOpen = ref(false)
const canViewAllocation = computed(() => ['manager', 'superuser'].includes(getAuthRole()))
const showAllocation = ref(false)
const allocationLoading = ref(false)
const allocationError = ref('')
const allocationDate = ref('')
const allocationRows = ref([])
const allocationTotals = ref({})
const allocationStatus = ref('OPEN')

function yen(value) {
  return `¥${Number(value || 0).toLocaleString()}`
}

async function openAllocation() {
  allocationDate.value = selectedDate.value
  showAllocation.value = true
  allocationLoading.value = true
  allocationError.value = ''
  try {
    const data = await api.getDailySettlement(allocationDate.value)
    allocationRows.value = data.rows || []
    allocationTotals.value = data.totals || {}
    allocationStatus.value = data.settlement_status || 'OPEN'
  } catch (error) {
    allocationRows.value = []
    allocationError.value = error.message || '売上配分を読み込めませんでした'
  } finally {
    allocationLoading.value = false
  }
}
const absenceUpdatingCastId = ref(null)
let orderEntryWindow = null

// 表示モード切り替え（キャスト別 / 部屋別）
const viewMode = ref('cast')
const rooms = ref([])
const roomOrders = ref([])

// rooms → casts 形式に変換（TimelineGrid 流用、RoomSchedule.vue と同様の変換）
const roomCastsAdapter = computed(() =>
  rooms.value.map(r => ({
    id: r.id,
    name: r.name,
    avatar_url: '',
    shifts: [],
  }))
)

// orders の room_id → cast_id にリネーム（TimelineGrid が cast_id で列を決めるため）
const roomOrdersAdapter = computed(() =>
  roomOrders.value.map(o => ({
    id: o.id,
    cast_id: o.room_id,
    customer_label: `${o.cast_name}`,
    course_name: o.course_name,
    start: o.start,
    end: o.end,
    start_time_extended: o.start_time_extended,
    end_time_extended: o.end_time_extended,
    status: o.status,
    timeline_status: o.timeline_status,
    timeline_status_label: o.timeline_status_label,
    options: o.options,
    is_unconfirmed: o.is_unconfirmed,
  }))
)

const displayCasts = computed(() => viewMode.value === 'room' ? roomCastsAdapter.value : casts.value)
const displayOrders = computed(() => viewMode.value === 'room' ? roomOrdersAdapter.value : orders.value)
const displayUnavailableTimes = computed(() => viewMode.value === 'room' ? [] : unavailableTimes.value)
const showLegend = ref(false)
const showPhoneSearch = ref(false)

// 予約作成モーダル
const showCreateModal = ref(false)
const showUnavailableTimeModal = ref(false)
const modalCast = ref('')
const modalStartTime = ref('')
const modalStartDate = ref('')
const modalCustomerId = ref('')

// 出勤セラピスト並び替えモーダル（キャスト別表示のみ）
const showOrderModal = ref(false)
const orderRows = ref([])
const orderLoading = ref(false)
const orderSaving = ref(false)
const orderError = ref('')

// 電話番号検索 → 顧客情報カード
const phoneInput = ref('')
const showCustomerCard = ref(false)
const cardLoading = ref(false)
const cardError = ref('')
const cardCustomer = ref(null)
const cardOrders = ref([])
const cardSearchedPhone = ref('')

// 架電履歴
const callLogs = ref([])
const callLogsLoading = ref(false)
const callLogsError = ref('')
const savingMemo = ref(false)

function today() {
  const d = new Date()
  if (d.getHours() < businessDayBoundaryHour.value) d.setDate(d.getDate() - 1)
  return formatLocalDate(d)
}

function tomorrow() {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return formatLocalDate(d)
}

function formatLocalDate(d) {
  const pad = value => String(value).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

async function fetchSchedule() {
  loading.value = true
  try {
    const data = await api.getSchedule(selectedDate.value)
    casts.value = data.casts
    orders.value = data.orders
    unavailableTimes.value = data.unavailable_times || []
    kpi.value = data.kpi

    if (highlightId.value) {
      nextTick(() => {
        const el = document.querySelector(`.rk-block[data-order-id="${highlightId.value}"]`)
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' })
          el.classList.add('rk-block--highlight')
          setTimeout(() => el.classList.remove('rk-block--highlight'), 3000)
        }
        highlightId.value = null
      })
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function fetchRoomSchedule() {
  loading.value = true
  try {
    const data = await api.getRoomSchedule(selectedDate.value)
    rooms.value = data.rooms
    roomOrders.value = data.orders
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function loadSchedule() {
  if (viewMode.value === 'room') {
    fetchRoomSchedule()
  } else {
    fetchSchedule()
  }
}

function onBlockClick(order) {
  router.push(`/op/orders/${order.id}`)
}

// ── 出勤セラピスト並び替え ──────────────────
// 1キャストが同日に複数シフトを持つ場合があるため、キャスト単位の行にまとめ、
// 保存時はそのキャストの全シフトへ同じ display_order を書き込む。
async function openOrderModal() {
  showOrderModal.value = true
  orderError.value = ''
  orderLoading.value = true
  try {
    const data = await api.getScheduleCastOrder(selectedDate.value)
    const byCast = new Map()
    for (const item of data.items) {
      if (!byCast.has(item.cast_id)) {
        byCast.set(item.cast_id, {
          cast_id: item.cast_id,
          cast_name: item.cast_name,
          shift_ids: [],
          shifts: [],
        })
      }
      const row = byCast.get(item.cast_id)
      row.shift_ids.push(item.shift_assignment_id)
      row.shifts.push({
        id: item.shift_assignment_id,
        room_name: item.room_name || 'ルーム未定',
        time: `${item.start_time_extended || String(item.start_time).slice(0, 5)}〜${item.end_time_extended || String(item.end_time).slice(0, 5)}`,
      })
    }
    orderRows.value = Array.from(byCast.values())
  } catch (e) {
    orderError.value = e.message || '出勤セラピストの取得に失敗しました'
    orderRows.value = []
  } finally {
    orderLoading.value = false
  }
}

function closeOrderModal() {
  showOrderModal.value = false
}

function moveRow(index, delta) {
  const target = index + delta
  if (target < 0 || target >= orderRows.value.length) return
  const rows = orderRows.value
  ;[rows[index], rows[target]] = [rows[target], rows[index]]
}

async function saveOrder() {
  orderSaving.value = true
  orderError.value = ''
  try {
    const items = []
    orderRows.value.forEach((row, i) => {
      row.shift_ids.forEach(id => {
        items.push({ shift_assignment_id: id, display_order: i + 1 })
      })
    })
    await api.saveScheduleCastOrder({ date: selectedDate.value, items })
    showOrderModal.value = false
    await fetchSchedule()
  } catch (e) {
    orderError.value = e.message || '並び順の保存に失敗しました'
  } finally {
    orderSaving.value = false
  }
}

function openCreateModal({ cast = '', customer = '', startTime = '', startDate = '' } = {}) {
  modalCast.value = cast
  modalCustomerId.value = customer
  modalStartTime.value = startTime || '15:00'
  modalStartDate.value = startDate || selectedDate.value
  const query = {
    store: selectedStoreId(),
    popup: '1',
    date: modalStartDate.value,
    start: modalStartTime.value,
  }
  if (modalCast.value) query.cast = String(modalCast.value)
  if (modalCustomerId.value) query.customer = String(modalCustomerId.value)
  const url = router.resolve({ path: '/op/phone', query }).href
  // ブラウザ標準の別タブで開く。元のタイムラインを残したまま入力できる。
  orderEntryWindow = window.open(url, '_blank')
  if (orderEntryWindow) {
    orderEntryWindow.focus()
    return
  }
  // ブラウザでポップアップが拒否された場合も予約作成を止めない。
  showCreateModal.value = true
}

function resolveTimelineStart(startTime) {
  const [hour, minute] = String(startTime).split(':').map(Number)
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) {
    return { date: selectedDate.value, time: startTime }
  }
  const d = new Date(`${selectedDate.value}T12:00:00`)
  d.setDate(d.getDate() + Math.floor(hour / 24))
  const pad = value => String(value).padStart(2, '0')
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${pad(hour % 24)}:${pad(minute)}`,
  }
}

function onCreateOrder(payload) {
  // 部屋別モードでは予約作成は未対応（表示切り替えのみ対応）
  if (viewMode.value === 'room') return
  // payload: { cast, start_time, room_id, room_name }（タイムライン空セルクリック）
  // または cast 単体（後方互換）
  const cast = payload && payload.cast ? payload.cast : payload
  const startTime = (payload && payload.start_time) || ''
  if (!cast || !cast.id) return
  const resolved = resolveTimelineStart(startTime)
  openCreateModal({ cast: cast.id, startTime: resolved.time, startDate: resolved.date })
}

function onOrderCreated({ order }) {
  showCreateModal.value = false
  highlightId.value = order.id
  fetchSchedule()
}

function onOrderWindowMessage(event) {
  if (event.origin !== window.location.origin) return
  if (event.data?.type !== 'roomink-order-created') return
  const order = event.data.order
  if (String(event.data.storeId) !== selectedStoreId()) return
  const startDate = event.data.startDate || selectedDate.value
  if (!order?.id) return
  highlightId.value = order.id
  if (startDate !== selectedDate.value) {
    selectedDate.value = startDate
  } else {
    fetchSchedule()
  }
}

function onWindowFocus() {
  if (orderEntryWindow && orderEntryWindow.closed) {
    orderEntryWindow = null
    loadSchedule()
  }
}

function onOrderCancel() {
  showCreateModal.value = false
}

async function toggleCastAbsence(cast) {
  if (!cast?.id || absenceUpdatingCastId.value !== null) return
  const shifts = Array.isArray(cast.shifts) ? cast.shifts : []
  if (!shifts.length) return
  const isAbsent = shifts.some(shift => shift.is_absent)
  const nextAbsent = !isAbsent
  const activeOrderCount = orders.value.filter(order => (
    order.cast_id === cast.id && order.status !== 'CANCELLED'
  )).length
  let message = nextAbsent
    ? `「${cast.name}」を当欠にしますか？`
    : `「${cast.name}」の当欠を解除しますか？`
  if (nextAbsent && activeOrderCount > 0) {
    message += `\n\nこの日の予約が${activeOrderCount}件あります。予約は自動キャンセルされません。振替またはキャンセル対応を別途行ってください。`
  }
  if (!window.confirm(message)) return

  absenceUpdatingCastId.value = cast.id
  try {
    await Promise.all(shifts.map(shift => (
      api.updateShift(shift.id, { is_absent: nextAbsent })
    )))
    await fetchSchedule()
  } catch (e) {
    window.alert(e.message || '当欠状態を更新できませんでした')
  } finally {
    absenceUpdatingCastId.value = null
  }
}

async function onUnavailableTimeSaved() {
  await fetchSchedule()
}

// 電話番号 → 顧客検索（CTI自動入力時もこの関数を呼ぶ）
async function searchByPhone(rawPhone) {
  const phone = normalizePhone(rawPhone)
  if (!phone || phone.length < 6) {
    cardError.value = '電話番号が短すぎます'
    cardCustomer.value = null
    cardOrders.value = []
    cardSearchedPhone.value = String(rawPhone || '').trim()
    callLogs.value = []
    callLogsError.value = ''
    showCustomerCard.value = true
    return
  }
  cardError.value = ''
  cardSearchedPhone.value = phone
  cardCustomer.value = null
  cardOrders.value = []
  callLogs.value = []
  callLogsError.value = ''
  cardLoading.value = true
  showCustomerCard.value = true
  try {
    const list = await api.searchCustomerByPhone(phone)
    const found = Array.isArray(list) && list.length ? list[0] : null
    cardCustomer.value = found
    if (found) {
      const orders = await api.getOrders(`customer=${found.id}&ordering=-start&limit=20`)
      cardOrders.value = Array.isArray(orders) ? orders : []
    }
    await fetchCallLogs()
  } catch (e) {
    cardError.value = e.message || '検索に失敗しました'
  } finally {
    cardLoading.value = false
  }
}

async function fetchCallLogs() {
  callLogsError.value = ''
  callLogsLoading.value = true
  try {
    const params = cardCustomer.value
      ? `customer=${cardCustomer.value.id}`
      : `phone=${encodeURIComponent(cardSearchedPhone.value)}`
    const list = await api.getCallLogs(params)
    callLogs.value = Array.isArray(list) ? list : []
  } catch (e) {
    callLogsError.value = e.message || '架電履歴の取得に失敗しました'
    callLogs.value = []
  } finally {
    callLogsLoading.value = false
  }
}

async function onAddMemo(body) {
  if (!body || savingMemo.value) return
  savingMemo.value = true
  try {
    const payload = {
      from_phone: cardSearchedPhone.value,
      customer: cardCustomer.value ? cardCustomer.value.id : null,
      note_body: body,
    }
    const created = await api.createCallLog(payload)
    if (created && created.id) {
      callLogs.value = [created, ...callLogs.value]
    } else {
      await fetchCallLogs()
    }
  } catch (e) {
    callLogsError.value = e.message || 'メモの保存に失敗しました'
  } finally {
    savingMemo.value = false
  }
}

function onPhoneSearchSubmit() {
  searchByPhone(phoneInput.value)
}

function closeCustomerCard() {
  showCustomerCard.value = false
}

function onSelectCustomerForOrder(customer) {
  if (!customer || !customer.id) return
  showCustomerCard.value = false
  openCreateModal({ customer: customer.id })
}

function onCreateNewCustomer(phone) {
  // 既存の顧客新規作成画面へ電話番号付きで遷移し、戻り先にスケジュールを指定
  showCustomerCard.value = false
  const params = new URLSearchParams()
  if (phone) params.set('phone', phone)
  params.set('return', `/op/schedule?date=${selectedDate.value}`)
  router.push(`/op/customers/new?${params.toString()}`)
}

function setToday() {
  selectedDate.value = today()
}

function setTomorrow() {
  selectedDate.value = tomorrow()
}

function toggleToolbar(e) {
  e.stopPropagation()
  toolbarOpen.value = !toolbarOpen.value
}

function toggleLegend(e) {
  e.stopPropagation()
  showLegend.value = !showLegend.value
}

watch(selectedDate, () => {
  loadSchedule()
})
watch(viewMode, () => {
  loadSchedule()
})
onMounted(async () => {
  try {
    const settings = await api.getBusinessDaySettings()
    businessDayBoundaryHour.value = settings.business_day_boundary_hour
    if (!route.query.date) selectedDate.value = today()
  } catch (e) {
    console.error(e)
  }
  loadSchedule()
  window.addEventListener('message', onOrderWindowMessage)
  window.addEventListener('focus', onWindowFocus)
})
onBeforeUnmount(() => {
  window.removeEventListener('message', onOrderWindowMessage)
  window.removeEventListener('focus', onWindowFocus)
})
</script>

<template>
  <LayoutOperator>
    <template #title>予約タイムライン</template>

    <!-- Setting area (matches mock's position-absolute toolbar) -->
    <div class="setting-area position-absolute">
      <button class="toolbar-toggle btn btn-sm border-0 shadow-sm bg-white" @click="toggleToolbar">
        <i class="ti ti-adjustments-horizontal" style="font-size: 24px;"></i>
      </button>
      <div v-show="toolbarOpen" class="rk-schedule__toolbar">
        <div class="rk-toolbar shadow-sm p-3 bg-white rounded">
          <div class="row g-2">
            <div class="col-6">
              <button
                class="btn btn-sm w-100"
                :class="selectedDate === today() ? 'btn-primary' : 'btn-outline-secondary'"
                @click="setToday"
              >今日</button>
            </div>
            <div class="col-6">
              <button
                class="btn btn-sm w-100"
                :class="selectedDate === tomorrow() ? 'btn-primary' : 'btn-outline-secondary'"
                @click="setTomorrow"
              >明日</button>
            </div>
            <div class="col-12">
              <input
                type="date"
                class="form-control form-control-sm"
                v-model="selectedDate"
              >
            </div>
            <div class="col-12">
              <div class="btn-group w-100" role="group">
                <button
                  type="button"
                  class="btn btn-sm"
                  :class="viewMode === 'cast' ? 'btn-primary' : 'btn-outline-secondary'"
                  @click="viewMode = 'cast'"
                >キャスト別</button>
                <button
                  type="button"
                  class="btn btn-sm"
                  :class="viewMode === 'room' ? 'btn-primary' : 'btn-outline-secondary'"
                  @click="viewMode = 'room'"
                >部屋別</button>
              </div>
            </div>
            <div class="col-12">
              <button class="btn btn-sm btn-outline-secondary w-100" @click="toggleLegend">
                <i class="ti ti-info-circle me-1"></i>{{ showLegend ? '凡例を非表示' : '凡例を表示' }}
              </button>
              <div v-show="showLegend" class="wrap d-flex flex-wrap align-items-center gap-2 mt-2">
                <span class="d-flex align-items-center gap-1 me-3">
                  <span class="badge badge-approved">確定済</span> <small class="text-muted">確定した予約</small>
                </span>
                <span class="d-flex align-items-center gap-1">
                  <span class="badge badge-pending">確定待ち</span> <small class="text-muted">確定待ちの予約</small>
                </span>
                <span class="d-flex align-items-center gap-1 me-3">
                  <span class="badge badge-attention">要注意</span> <small class="text-muted">要注意フラグ</small>
                </span>
                <span class="d-flex align-items-center gap-1">
                  <span class="badge badge-unconfirmed">キャスト未確認</span> <small class="text-muted">キャストが未確認</small>
                </span>
                <span class="d-flex align-items-center gap-1">
                  <span class="rk-legend-iv"></span> <small class="text-muted">インターバル</small>
                </span>
                <span class="d-flex align-items-center gap-1">
                  <span class="badge text-bg-secondary">休憩</span> <small class="text-muted">予約不可時間</small>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 新規予約 / 番号検索 -->
    <div class="rk-actions mb-2">
      <div class="rk-actions__buttons">
        <button type="button" class="btn btn-sm btn-primary" @click="openCreateModal()">
          <i class="ti ti-plus me-1"></i>新規予約
        </button>
        <button
          type="button"
          class="btn btn-sm btn-outline-primary"
          @click="openCreateModal()"
        >
          <i class="ti ti-calendar-plus me-1"></i>予約追加
        </button>
        <button
          type="button"
          class="btn btn-sm"
          :class="showPhoneSearch ? 'btn-secondary' : 'btn-outline-secondary'"
          @click="showPhoneSearch = !showPhoneSearch"
        >
          <i class="ti ti-search me-1"></i>番号検索
        </button>
        <button
          v-if="viewMode === 'cast'"
          type="button"
          class="btn btn-sm btn-outline-secondary"
          @click="openOrderModal"
        >
          <i class="ti ti-arrows-sort me-1"></i>並び替え
        </button>
        <button
          v-if="viewMode === 'cast'"
          type="button"
          class="btn btn-sm btn-outline-secondary"
          @click="showUnavailableTimeModal = true"
        >
          <i class="ti ti-clock-pause me-1"></i>予約不可時間
        </button>
        <button v-if="canViewAllocation" type="button" class="btn btn-sm btn-outline-primary" @click="openAllocation">
          <i class="ti ti-calculator me-1"></i>売上配分
        </button>
      </div>

      <!-- 検索アコーディオン -->
      <form
        v-if="showPhoneSearch"
        class="rk-actions__search"
        @submit.prevent="onPhoneSearchSubmit"
      >
        <input
          v-model="phoneInput"
          type="tel"
          inputmode="tel"
          class="form-control form-control-sm"
          placeholder="例: 09012345678"
          autocomplete="off"
          autofocus
        />
        <button type="submit" class="btn btn-sm btn-primary flex-shrink-0">
          検索
        </button>
      </form>
    </div>

    <!-- タイムライン -->
    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else class="position-relative">
      <TimelineGrid
        :casts="displayCasts"
        :orders="displayOrders"
        :unavailable-times="displayUnavailableTimes"
        :absence-updating-cast-id="absenceUpdatingCastId"
        @block-click="onBlockClick"
        @create-order="onCreateOrder"
        @toggle-absence="toggleCastAbsence"
      />
      <div v-if="displayCasts.length === 0" class="position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center" style="pointer-events: none; z-index: 9999;">
        <span class="text-muted bg-white px-3 py-2 rounded shadow-sm text-center" style="max-width: 240px;">{{ viewMode === 'room' ? '部屋が登録されていません' : 'この日にシフトが登録されたキャストがいません' }}</span>
      </div>
    </div>

    <UnavailableTimeModal
      v-if="showUnavailableTimeModal"
      :date="selectedDate"
      :casts="casts"
      :items="unavailableTimes"
      @close="showUnavailableTimeModal = false"
      @saved="onUnavailableTimeSaved"
    />

    <!-- 予約作成モーダル（OrderForm 雛形を利用） -->
    <div v-if="showCreateModal" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showCreateModal = false">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="ti ti-plus me-1"></i>予約作成（{{ modalStartDate || selectedDate }}）
            </h5>
            <button type="button" class="btn-close" @click="showCreateModal = false"></button>
          </div>
          <div class="modal-body">
            <OrderForm
              :initial-date="modalStartDate"
              :initial-cast="modalCast"
              :initial-customer-id="modalCustomerId"
              :initial-start-time="modalStartTime"
              :embedded="true"
              :show-flow-hint="false"
              @created="onOrderCreated"
              @cancel="onOrderCancel"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- 出勤セラピスト並び替え -->
    <div v-if="showOrderModal" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="closeOrderModal">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="ti ti-arrows-sort me-1"></i>出勤セラピストの並び替え（{{ selectedDate }}）
            </h5>
            <button type="button" class="btn-close" @click="closeOrderModal"></button>
          </div>
          <div class="modal-body">
            <div class="alert alert-info py-2 px-3 small">
              タイムライン（キャスト別表示）の表示順のみ変更します。
              シフトの時間・部屋は変更されません。
            </div>

            <div v-if="orderError" class="alert alert-danger py-2 px-3 small">{{ orderError }}</div>

            <div v-if="orderLoading" class="text-center py-3">
              <div class="spinner-border text-primary"></div>
            </div>
            <div v-else-if="!orderRows.length" class="text-muted text-center py-3 small">
              この日の出勤セラピストはいません
            </div>
            <div v-else class="order-list">
              <div v-for="(row, i) in orderRows" :key="row.cast_id" class="order-row">
                <span class="order-row__no">{{ i + 1 }}</span>
                <div class="flex-grow-1">
                  <div class="fw-bold">{{ row.cast_name }}</div>
                  <div class="order-row__shifts">
                    <small v-for="shift in row.shifts" :key="shift.id" class="order-row__shift">
                      <span class="order-row__room"><i class="ti ti-door me-1"></i>{{ shift.room_name }}</span>
                      <span class="text-muted">{{ shift.time }}</span>
                    </small>
                  </div>
                </div>
                <div class="btn-group">
                  <button
                    class="btn btn-sm btn-outline-secondary"
                    :disabled="i === 0"
                    @click="moveRow(i, -1)"
                  ><i class="ti ti-arrow-up"></i></button>
                  <button
                    class="btn btn-sm btn-outline-secondary"
                    :disabled="i === orderRows.length - 1"
                    @click="moveRow(i, 1)"
                  ><i class="ti ti-arrow-down"></i></button>
                </div>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-outline-secondary" @click="closeOrderModal">キャンセル</button>
            <button
              class="btn btn-primary"
              :disabled="orderSaving || orderLoading || !orderRows.length"
              @click="saveOrder"
            >{{ orderSaving ? '保存中...' : '保存' }}</button>
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showAllocation" class="allocation-backdrop" @click.self="showAllocation = false">
        <section class="allocation-panel" role="dialog" aria-modal="true" :aria-label="`${allocationDate}の売上配分`">
          <header class="allocation-header">
            <div><div class="fw-bold">売上配分</div><div class="small text-muted">{{ allocationDate }} <span v-if="allocationStatus === 'LOCKED'" class="badge bg-success">確定済</span><span v-else class="badge bg-secondary">見込み</span></div></div>
            <button type="button" class="btn btn-sm btn-light" aria-label="閉じる" @click="showAllocation = false"><i class="ti ti-x"></i></button>
          </header>
          <div class="allocation-body">
            <div v-if="allocationLoading" class="text-center py-5"><div class="spinner-border text-primary"></div></div>
            <div v-else-if="allocationError" class="alert alert-danger">{{ allocationError }}</div>
            <div v-else-if="!allocationRows.length" class="text-center text-muted py-5">この日に出勤したセラピストはいません</div>
            <div v-else-if="allocationRows.some(row => row.compensation === undefined)" class="alert alert-info">この日は旧形式で確定されています。日給一覧で内容を確認してください。</div>
            <template v-else>
              <div class="allocation-summary">
                <div><span>売上</span><strong>{{ yen(allocationTotals.total_sales) }}</strong></div>
                <div><span>報酬</span><strong class="text-primary">{{ yen(allocationTotals.compensation) }}</strong></div>
                <div><span>店舗配分</span><strong>{{ yen(allocationTotals.store_allocation) }}</strong></div>
              </div>
              <details v-for="row in allocationRows" :key="row.cast_id" class="allocation-row">
                <summary><strong>{{ row.cast_name }}</strong><span>売上 {{ yen(row.total_sales) }}</span><span class="text-primary">報酬 {{ yen(row.compensation) }}</span><span>店舗配分 {{ yen(row.store_allocation) }}</span><i class="ti ti-chevron-down"></i></summary>
                <div class="allocation-details">
                  <span>完了済み {{ row.order_count }}本</span><span>コース {{ yen(row.course_sales) }}</span><span>オプション {{ yen(row.options_sales) }}</span>
                  <span>給与見込み {{ yen(row.back_amount) }}</span><span>固定雑費 -{{ yen(row.fixed_expense_total) }}</span><span>当日雑費 -{{ yen(row.daily_expense_total) }}</span><span>カード加算 +{{ yen(row.customer_payment_surcharge) }}</span><span>店舗側決済手数料（参考）-{{ yen(row.payment_fee_estimate) }}</span>
                </div>
              </details>
              <p class="small text-muted mt-3 mb-0">報酬＝給与見込み−雑費。店舗配分＝お客様決済額−店舗側決済手数料−報酬。カードの上乗せ分は店舗配分に含まれます。振込額は現金預りなどを反映するため別の金額です。</p>
            </template>
          </div>
          <footer class="allocation-footer"><router-link :to="{ path: '/op/daily-settlement', query: { date: allocationDate } }" class="btn btn-outline-primary btn-sm" @click="showAllocation = false">日給一覧を見る</router-link><button class="btn btn-primary btn-sm" @click="showAllocation = false">閉じる</button></footer>
        </section>
      </div>
    </Teleport>

    <!-- 顧客情報カード -->
    <CustomerInfoCard
      v-if="showCustomerCard"
      :customer="cardCustomer"
      :recent-orders="cardOrders"
      :loading="cardLoading"
      :searched-phone="cardSearchedPhone"
      :error="cardError"
      :call-logs="callLogs"
      :call-logs-loading="callLogsLoading"
      :call-logs-error="callLogsError"
      :saving-memo="savingMemo"
      @close="closeCustomerCard"
      @select="onSelectCustomerForOrder"
      @create-new="onCreateNewCustomer"
      @add-memo="onAddMemo"
    />
  </LayoutOperator>
</template>

<style scoped lang="scss">
.order-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid #f0f0f0;

  &:last-child {
    border-bottom: none;
  }

  &__no {
    width: 1.5rem;
    text-align: center;
    color: #888;
    font-size: 0.8rem;
  }

  &__shifts {
    display: grid;
    gap: 0.2rem;
    margin-top: 0.2rem;
  }

  &__shift {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    flex-wrap: wrap;
  }

  &__room {
    color: #257c70;
    font-weight: 700;
  }
}

.rk-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;

  &__buttons {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  &__search {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1 1 240px;
    max-width: 360px;
    min-width: 0;

    input {
      flex: 1 1 auto;
      min-width: 0;
    }
  }
}

/* スマホは検索フォームを次行いっぱい */
@media (max-width: 575.98px) {
  .rk-actions__search {
    flex-basis: 100%;
    max-width: 100%;
  }
}

.modal-dialog.modal-lg {
  max-width: 720px;
}

.allocation-backdrop { position: fixed; inset: 0; z-index: 2100; display: flex; align-items: flex-end; justify-content: center; background: rgba(14, 32, 30, .52); }
.allocation-panel { width: min(760px, 100%); max-height: min(90dvh, 850px); display: flex; flex-direction: column; background: #fff; border-radius: 18px 18px 0 0; box-shadow: 0 18px 60px rgba(0, 0, 0, .18); }
.allocation-header, .allocation-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 20px; border-bottom: 1px solid #e7eeeb; }
.allocation-footer { justify-content: flex-end; border-top: 1px solid #e7eeeb; border-bottom: 0; }
.allocation-body { overflow-y: auto; padding: 18px 20px 24px; }
.allocation-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 18px; }
.allocation-summary > div { padding: 12px; border-radius: 10px; background: #f1f7f4; text-align: center; }
.allocation-summary span, .allocation-summary strong { display: block; }
.allocation-summary span { color: #687873; font-size: .75rem; }
.allocation-summary strong { font-size: clamp(.9rem, 2.5vw, 1.25rem); }
.allocation-row { border-bottom: 1px solid #e7eeeb; }
.allocation-row summary { display: grid; grid-template-columns: 1.1fr repeat(3, 1fr) 18px; align-items: center; gap: 8px; padding: 14px 4px; cursor: pointer; list-style: none; font-size: .82rem; }
.allocation-row summary::-webkit-details-marker { display: none; }
.allocation-details { display: flex; flex-wrap: wrap; gap: 5px 14px; padding: 0 8px 14px; color: #61716b; font-size: .77rem; }
@media (min-width: 768px) { .allocation-backdrop { align-items: center; } .allocation-panel { border-radius: 18px; } }
@media (max-width: 575px) { .rk-actions__buttons { flex-wrap: wrap; } .allocation-header, .allocation-footer { padding: 13px 15px; } .allocation-body { padding: 15px; } .allocation-row summary { grid-template-columns: 1fr 1fr; } .allocation-row summary strong { grid-column: 1 / -1; } .allocation-row summary i { display: none; } }
</style>
