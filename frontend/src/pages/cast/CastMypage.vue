<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import LayoutCast from '../../components/LayoutCast.vue'
import { api } from '../../api.js'
import { sanitizeNoteHtml } from '../../noteContent.js'
import { roomMapHref } from '../../roomMap.js'

const loading = ref(true)
const error = ref('')
const castName = ref('')
const avatarUrl = ref('')
const shift = ref(null)
const todayBusinessDate = ref('')
const orders = ref([])
const totalOrders = ref(0)
const unconfirmedCount = ref(0)
const lineLinked = ref(false)
const lineLinkCode = ref('')
const lineAddFriendUrl = ref('')
const showLineModal = ref(false)
const codeCopied = ref(false)
const totalPoints = ref(0)
const pointHistory = ref([])
const todaySales = ref(null)
const availableOptions = ref([])
const processingOrderId = ref(null)
const optionEditorId = ref(null)
const optionDraftIds = ref([])
const actionErrors = ref({})
const expandedOrderDetails = ref({})
const activeInfoTab = ref('earnings')

// 調整金（Phase 3-E）
const adjustments = ref({ open_total: 0, open: [], resolved_recent: [] })
const adjustmentsLoading = ref(true)
const showResolvedAdjustments = ref(false)

// ノート/施術マニュアル（Phase 4）
const notes = ref({ categories: [], pinned: [], recent: [] })
const notesLoading = ref(true)
const showAllNotes = ref(false)
const selectedNote = ref(null)
const selectedNoteImage = ref('')

function noteHtml(note) {
  return sanitizeNoteHtml(note?.body || '', note?.image_urls || [])
}

function openNoteImage(event) {
  const image = event.target instanceof Element ? event.target.closest('img') : null
  if (image?.src) selectedNoteImage.value = image.src
}

// 出勤確認（Phase 3-B-1）
const shiftConfirm = ref(null)
const shiftConfirmLoading = ref(true)
const confirmingShift = ref(false)
const confirmShiftError = ref('')
const headerShift = computed(() => shiftConfirm.value?.shift || shift.value)
const headerShiftDate = computed(() => headerShift.value?.date || todayBusinessDate.value)
const headerShiftIsToday = computed(() => headerShiftDate.value === todayBusinessDate.value)

// 退勤（Phase 3-A）
const CHECKLIST_ITEMS = [
  { key: 'room_cleaned', label: '部屋の片付け・清掃をした' },
  { key: 'items_returned', label: '備品を返却した' },
  { key: 'cash_confirmed', label: '現金・売上を確認した' },
  { key: 'report_done', label: '特記事項があれば運営へ報告した' },
]

const checkoutData = ref(null)
const showCheckoutModal = ref(false)
const checkoutForm = ref(emptyCheckoutForm())
const checkoutSaving = ref(false)
const checkoutError = ref('')

function emptyCheckoutForm() {
  return {
    actual_take_home_amount: 0,
    cast_memo: '',
    checklist_json: Object.fromEntries(CHECKLIST_ITEMS.map(i => [i.key, false])),
  }
}

const checkoutIsReadOnly = computed(() => {
  const co = checkoutData.value?.checkout
  return !!co && co.status !== 'RETURNED'
})

// 決済手数料見込み（参考値）。提出済みならスナップショット値、未提出なら現在の見込みを表示
const feeEstimate = computed(() => {
  const co = checkoutData.value?.checkout
  if (co) {
    return { fee: co.payment_fee_estimate ?? 0, net: co.net_sales_after_payment_fee ?? 0 }
  }
  return {
    fee: checkoutData.value?.payment_fee_estimate ?? 0,
    net: checkoutData.value?.net_sales_after_payment_fee ?? 0,
  }
})

function checkoutStatusLabel(s) {
  return { SUBMITTED: '提出済み（未確認）', REVIEWED: '確認済み', RETURNED: '差戻し' }[s] || s
}

onMounted(async () => {
  try {
    const data = await api.getCastToday()
    castName.value = data.cast_name
    avatarUrl.value = data.avatar_url
    shift.value = data.shift
    todayBusinessDate.value = data.date
    orders.value = data.orders
    totalOrders.value = data.total_orders
    unconfirmedCount.value = data.unconfirmed_count
    availableOptions.value = data.available_options || []
    lineLinked.value = data.line_linked || false
    lineLinkCode.value = data.line_link_code || ''
    lineAddFriendUrl.value = data.line_add_friend_url || ''
    if (!lineLinked.value) showLineModal.value = true
    // ポイント取得
    try {
      const pts = await api.getCastPoints()
      totalPoints.value = pts.total_points || 0
      pointHistory.value = pts.history || []
    } catch (_) { /* ポイント取得失敗は致命的でない */ }
    // 本日の売上/給与見込み取得
    try {
      todaySales.value = await api.getCastTodaySales()
    } catch (_) { /* 取得失敗は致命的でない */ }
    // 退勤状況取得
    await loadCheckout()
    // 出勤確認状況取得
    await loadShiftConfirm()
    // 調整金取得
    await loadAdjustments()
    // ノート取得
    await loadNotes()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

async function loadCheckout() {
  try {
    checkoutData.value = await api.getCastCheckout()
  } catch (_) { /* 取得失敗は致命的でない */ }
}

async function loadShiftConfirm() {
  shiftConfirmLoading.value = true
  try {
    shiftConfirm.value = await api.getCastShiftConfirm()
  } catch (_) { /* 取得失敗は致命的でない */ } finally {
    shiftConfirmLoading.value = false
  }
}

async function loadAdjustments() {
  adjustmentsLoading.value = true
  try {
    adjustments.value = await api.getCastAdjustmentsMypage()
  } catch (_) { /* 取得失敗は致命的でない */ } finally {
    adjustmentsLoading.value = false
  }
}

async function loadNotes() {
  notesLoading.value = true
  try {
    const data = await api.getCastNotesMypage()
    notes.value = {
      categories: data?.categories || [],
      pinned: Array.isArray(data?.pinned) ? data.pinned : [],
      recent: Array.isArray(data?.recent) ? data.recent : [],
    }
  } catch (_) { /* 取得失敗は致命的でない */ } finally {
    notesLoading.value = false
  }
}

function openNote(n) {
  selectedNote.value = n
  selectedNoteImage.value = ''
}

async function onConfirmShift() {
  if (!shiftConfirm.value?.shift?.id || confirmingShift.value) return
  confirmingShift.value = true
  confirmShiftError.value = ''
  try {
    shiftConfirm.value = await api.confirmCastShift(shiftConfirm.value.shift.id)
  } catch (e) {
    confirmShiftError.value = e.message
  } finally {
    confirmingShift.value = false
  }
}

const WEEK_LABELS = ['日', '月', '火', '水', '木', '金', '土']
function formatShiftDateLabel(dateStr) {
  if (!dateStr) return ''
  const [y, m, d] = dateStr.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  return `${m}月${d}日(${WEEK_LABELS[dt.getDay()]})`
}

function selectInfoTab(tab, focus = false) {
  activeInfoTab.value = tab
  if (focus) nextTick(() => document.getElementById(`ca-info-tab-${tab}`)?.focus())
}

function openCheckoutModal() {
  const co = checkoutData.value?.checkout
  if (co && co.status === 'RETURNED') {
    checkoutForm.value = {
      actual_take_home_amount: co.actual_take_home_amount,
      cast_memo: co.cast_memo,
      checklist_json: { ...emptyCheckoutForm().checklist_json, ...(co.checklist_json || {}) },
    }
  } else if (!co) {
    checkoutForm.value = emptyCheckoutForm()
  }
  checkoutError.value = ''
  showCheckoutModal.value = true
}

async function submitCheckout() {
  checkoutSaving.value = true
  checkoutError.value = ''
  try {
    const body = {
      actual_take_home_amount: Number(checkoutForm.value.actual_take_home_amount) || 0,
      cast_memo: checkoutForm.value.cast_memo,
      checklist_json: checkoutForm.value.checklist_json,
    }
    await api.submitCastCheckout(body)
    await loadCheckout()
    showCheckoutModal.value = false
  } catch (e) {
    checkoutError.value = e.message
  } finally {
    checkoutSaving.value = false
  }
}

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

function toggleOrderDetails(orderId) {
  expandedOrderDetails.value[orderId] = !expandedOrderDetails.value[orderId]
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
    todaySales.value = await api.getCastTodaySales()
    await loadCheckout()
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

function copyCode() {
  navigator.clipboard.writeText(lineLinkCode.value)
  codeCopied.value = true
  setTimeout(() => { codeCopied.value = false }, 2000)
}

function openLineFriend() {
  window.open(lineAddFriendUrl.value, '_blank')
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
            <div v-if="headerShift" class="ca-home-next">
              <div class="ca-home-next__date">{{ headerShiftIsToday ? '今日の出勤' : '次回の出勤' }} · {{ formatShiftDateLabel(headerShiftDate) }}</div>
              <div class="ca-home-next__time"><i class="ti ti-clock"></i> {{ headerShift.start_time }}–{{ headerShift.end_time_extended || headerShift.end_time }}</div>
              <div v-if="headerShift.room_name" class="ca-home-next__room">
                <span><i class="ti ti-door"></i> {{ headerShift.room_name }}</span>
                <a v-if="roomMapHref(headerShift)" :href="roomMapHref(headerShift)" target="_blank" rel="noopener noreferrer" class="ca-home-map" :aria-label="`${headerShift.room_name}の地図を開く`"><i class="ti ti-map-pin"></i> 地図</a>
              </div>
              <div v-if="headerShift.room_address" class="ca-home-next__address">{{ headerShift.room_address }}</div>
            </div>
          </div>
        </div>

        <!-- 出勤確認（Phase 3-B-1） -->
        <div class="rk-section-header"><i class="ti ti-calendar-check"></i> 出勤確認</div>
        <div class="card mb-3">
          <div class="card-body">
            <div v-if="shiftConfirmLoading" class="text-muted text-center py-2 small">読み込み中...</div>
            <div v-else-if="!shiftConfirm || !shiftConfirm.shift" class="text-muted text-center py-2 small">
              本日の出勤予定はありません
            </div>
            <template v-else>
              <div v-if="confirmShiftError" class="alert alert-danger py-2 small">{{ confirmShiftError }}</div>
              <div class="d-flex justify-content-between align-items-center mb-2">
                <div>
                  <div class="fw-bold">
                    {{ formatShiftDateLabel(shiftConfirm.shift.date) }}
                    <span class="small text-muted">{{ shiftConfirm.is_today ? '（本日）' : '（次回シフト）' }}</span>
                  </div>
                  <div class="small text-muted">
                    <i class="ti ti-clock"></i> {{ shiftConfirm.shift.start_time }}–{{ shiftConfirm.shift.end_time_extended || shiftConfirm.shift.end_time }}
                    <span v-if="shiftConfirm.shift.room_name"><i class="ti ti-door"></i> {{ shiftConfirm.shift.room_name }}</span>
                  </div>
                </div>
              </div>
              <div v-if="shiftConfirm.shift.confirmed_at" class="alert alert-success py-2 px-3 small mb-0">
                <i class="ti ti-circle-check"></i> 出勤確認済み（{{ formatTime(shiftConfirm.shift.confirmed_at) }}）
              </div>
              <template v-else>
                <button
                  class="btn btn-primary w-100 mb-2"
                  :disabled="confirmingShift"
                  @click="onConfirmShift"
                >
                  {{ confirmingShift ? '送信中...' : '出勤確認する' }}
                </button>
                <div class="small text-muted">
                  出勤2時間前までに確認してください。未確認のまま1時間前を過ぎると店舗側に表示されます。
                </div>
              </template>
            </template>
          </div>
        </div>

        <router-link to="/cast/schedule" class="btn btn-outline-primary w-100 mb-3 fw-bold">
          <i class="ti ti-calendar-week"></i> 出勤・予約予定を見る
        </router-link>

        <div class="rk-section-header ca-bookings-heading">
          <span><i class="ti ti-calendar-event"></i> 本日の予約</span>
          <span class="ca-bookings-count">{{ totalOrders }}件<span v-if="unconfirmedCount > 0" class="ca-bookings-unconfirmed">未確認 {{ unconfirmedCount }}件</span></span>
        </div>

        <!-- 未確認の予約は他の情報より先に確認する -->
        <div v-if="unconfirmedCount > 0" class="alert alert-warning ca-bookings-alert mb-3">
          <i class="ti ti-alert-triangle"></i> 下の予約から「確認する」を押してください。
        </div>

        <div
          v-for="order in orders"
          :key="order.id"
          class="card ca-booking-card mb-3"
        >
          <div class="card-body ca-booking-card__body">
            <div class="ca-booking-card__header">
              <div>
                <div class="ca-booking-card__time">{{ displayStartTime(order) }}–{{ displayEndTime(order) }}</div>
                <div class="ca-booking-card__duration">{{ durationMin(order) }}分</div>
              </div>
              <span
                class="badge"
                :class="order.is_unconfirmed ? 'badge-unconfirmed' : order.customer_reservation_state === 'PAYMENT_REQUIRED' ? 'text-bg-warning' : 'badge-approved'"
              >{{ order.is_unconfirmed ? '未確認' : statusLabel(order) }}</span>
            </div>

            <div class="ca-booking-card__primary">
              <div><i class="ti ti-user" aria-hidden="true"></i><strong>{{ order.reservation_name }}</strong></div>
              <div><i class="ti ti-door" aria-hidden="true"></i><span>{{ order.room_name }}</span></div>
            </div>

            <div class="ca-booking-card__facts">
              <div class="ca-booking-card__fact">
                <span>コース</span>
                <strong>{{ order.course_name }}</strong>
                <small>{{ formatYen(order.course_price) }}</small>
              </div>
              <div class="ca-booking-card__fact">
                <span>お支払い</span>
                <strong>{{ order.payment_method_label }}</strong>
                <small>合計 {{ formatYen(order.total_price) }}</small>
              </div>
            </div>

            <button
              type="button"
              class="ca-booking-card__disclosure"
              :aria-expanded="!!expandedOrderDetails[order.id]"
              :aria-controls="`ca-booking-details-${order.id}`"
              @click="toggleOrderDetails(order.id)"
            >
              <span>{{ expandedOrderDetails[order.id] ? 'オプション・備考を閉じる' : 'オプション・備考を見る' }}</span>
              <span v-if="order.memo && !expandedOrderDetails[order.id]" class="ca-booking-card__memo-flag">備考あり</span>
              <span v-else-if="order.options?.length && !expandedOrderDetails[order.id]" class="ca-booking-card__memo-flag">オプションあり</span>
              <i class="ti" :class="expandedOrderDetails[order.id] ? 'ti-chevron-up' : 'ti-chevron-down'" aria-hidden="true"></i>
            </button>

            <div v-show="expandedOrderDetails[order.id]" :id="`ca-booking-details-${order.id}`" class="ca-booking-card__details">
              <div><i class="ti ti-sparkles" aria-hidden="true"></i> オプション：{{ order.options?.length ? order.options.map(option => option.name).join('、') : 'なし' }}</div>
              <div v-if="order.nomination_fee_name"><i class="ti ti-heart" aria-hidden="true"></i> {{ order.nomination_fee_name }} / {{ formatYen(order.nomination_fee_price) }}</div>
              <div><i class="ti ti-note" aria-hidden="true"></i> 備考：{{ order.memo || 'なし' }}</div>
              <button
                v-if="availableOptions.length"
                type="button"
                class="btn btn-sm btn-outline-secondary w-100 mt-2"
                :disabled="processingOrderId === order.id"
                @click="openOptionEditor(order)"
              ><i class="ti ti-adjustments"></i> オプションを選択・変更</button>
              <div v-if="optionEditorId === order.id" class="border rounded p-2 mt-2 bg-light">
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
            </div>

            <div v-if="actionErrors[order.id]" class="alert alert-danger py-2 small mb-2">
              {{ actionErrors[order.id] }}
            </div>

            <button
              v-if="order.is_unconfirmed"
              class="btn btn-sm btn-warning w-100"
              @click="doAck(order)"
            ><i class="ti ti-check"></i> 確認する</button>
            <button v-else-if="order.status === 'REQUESTED'" class="btn btn-sm btn-light w-100" disabled>
              <i class="ti ti-clock"></i> 店舗確認待ち
            </button>
            <button
              v-else-if="order.status === 'CONFIRMED'"
              class="btn btn-sm btn-primary w-100 fw-bold"
              :disabled="processingOrderId === order.id"
              @click="startService(order)"
            ><i class="ti ti-player-play"></i> 接客開始</button>
            <button
              v-else-if="order.status === 'IN_PROGRESS' || order.status === 'PENDING_FINALIZE'"
              class="btn btn-sm btn-success w-100 fw-bold"
              :disabled="processingOrderId === order.id"
              @click="completeService(order)"
            ><i class="ti ti-check"></i> 接客終了・売上へ反映</button>
          </div>
        </div>

        <div v-if="orders.length === 0" class="text-muted text-center py-4">本日の予約はありません</div>

        <div class="ca-info-tabs" role="tablist" aria-label="売上・調整金・ノート">
          <button id="ca-info-tab-earnings" type="button" role="tab" aria-controls="ca-info-earnings" :aria-selected="activeInfoTab === 'earnings'" :tabindex="activeInfoTab === 'earnings' ? 0 : -1" :class="{ 'is-active': activeInfoTab === 'earnings' }" @click="selectInfoTab('earnings')" @keydown.right.prevent="selectInfoTab('adjustments', true)">売上・ポイント</button>
          <button id="ca-info-tab-adjustments" type="button" role="tab" aria-controls="ca-info-adjustments" :aria-selected="activeInfoTab === 'adjustments'" :tabindex="activeInfoTab === 'adjustments' ? 0 : -1" :class="{ 'is-active': activeInfoTab === 'adjustments' }" @click="selectInfoTab('adjustments')" @keydown.left.prevent="selectInfoTab('earnings', true)" @keydown.right.prevent="selectInfoTab('notes', true)">調整金</button>
          <button id="ca-info-tab-notes" type="button" role="tab" aria-controls="ca-info-notes" :aria-selected="activeInfoTab === 'notes'" :tabindex="activeInfoTab === 'notes' ? 0 : -1" :class="{ 'is-active': activeInfoTab === 'notes' }" @click="selectInfoTab('notes')" @keydown.left.prevent="selectInfoTab('adjustments', true)">ノート</button>
        </div>

        <section id="ca-info-earnings" v-show="activeInfoTab === 'earnings'" role="tabpanel" aria-labelledby="ca-info-tab-earnings" tabindex="0" class="ca-info-panel">
        <!-- 本日の売上/給与見込みカード -->
        <div v-if="todaySales" class="card mb-3">
          <div class="card-body">
            <div class="fw-bold mb-2"><i class="ti ti-currency-yen text-primary"></i> 本日の売上/給与見込み</div>
            <div class="row g-2 text-center mb-2">
              <div class="col-4">
                <div class="small text-muted mb-1">完了済み</div>
                <div class="fw-bold">{{ todaySales.done_count }}本</div>
              </div>
              <div class="col-4">
                <div class="small text-muted mb-1">売上</div>
                <div class="fw-bold">{{ formatYen(todaySales.total_sales) }}</div>
              </div>
              <div class="col-4">
                <div class="small text-muted mb-1">給与見込み</div>
                <div class="fw-bold text-primary">{{ formatYen(todaySales.estimated_pay) }}</div>
              </div>
            </div>
            <div class="small text-muted">セラピスト側で「接客終了・売上へ反映」まで完了した予約を元にした見込みです。予約時間を過ぎただけでは反映されません。</div>
          </div>
        </div>

        <!-- ポイントカード -->
        <div v-if="totalPoints !== 0 || pointHistory.length" class="card mb-3">
          <div class="card-body">
            <div class="d-flex align-items-center justify-content-between mb-2">
              <div class="fw-bold"><i class="ti ti-star text-warning"></i> ポイント</div>
              <div class="fs-4 fw-bold">{{ totalPoints }} pt</div>
            </div>
            <div v-if="pointHistory.length" class="small">
              <div v-for="p in pointHistory.slice(0, 5)" :key="p.id" class="d-flex justify-content-between text-muted border-bottom py-1">
                <span>{{ p.date }} {{ p.reason || '' }}</span>
                <span :class="p.points >= 0 ? 'text-success' : 'text-danger'" class="fw-bold">{{ p.points >= 0 ? '+' : '' }}{{ p.points }}</span>
              </div>
            </div>
          </div>
        </div>
        </section>

        <section id="ca-info-adjustments" v-show="activeInfoTab === 'adjustments'" role="tabpanel" aria-labelledby="ca-info-tab-adjustments" tabindex="0" class="ca-info-panel">
        <!-- 調整金（Phase 3-E） -->
        <div class="rk-section-header"><i class="ti ti-cash-banknote"></i> 調整金</div>
        <div class="card mb-3">
          <div class="card-body">
            <div v-if="adjustmentsLoading" class="text-muted text-center py-2 small">読み込み中...</div>
            <template v-else>
              <div class="d-flex justify-content-between align-items-center mb-2">
                <span class="fw-bold">未解消合計</span>
                <span class="fs-5 fw-bold" :class="adjustments.open_total >= 0 ? 'text-success' : 'text-danger'">
                  {{ adjustments.open_total >= 0 ? '+' : '' }}{{ formatYen(adjustments.open_total) }}
                </span>
              </div>

              <div v-if="adjustments.open?.length">
                <div v-for="a in adjustments.open" :key="a.id" class="d-flex justify-content-between border-bottom py-2 small">
                  <div>
                    <div class="fw-bold">{{ a.title }}</div>
                    <div class="text-muted">{{ a.date }}<span v-if="a.memo"> ・ {{ a.memo }}</span></div>
                  </div>
                  <div class="fw-bold flex-shrink-0 ms-2" :class="a.amount >= 0 ? 'text-success' : 'text-danger'">
                    {{ a.amount >= 0 ? '+' : '' }}{{ formatYen(a.amount) }}
                  </div>
                </div>
              </div>
              <div v-else class="text-muted small text-center py-2">未解消の調整金はありません</div>

              <div v-if="adjustments.resolved_recent?.length" class="mt-2">
                <button
                  class="btn btn-link btn-sm p-0 text-muted"
                  @click="showResolvedAdjustments = !showResolvedAdjustments"
                >
                  解消済み履歴（{{ adjustments.resolved_recent.length }}件）{{ showResolvedAdjustments ? 'を閉じる' : 'を見る' }}
                </button>
                <div v-if="showResolvedAdjustments" class="mt-2">
                  <div
                    v-for="a in adjustments.resolved_recent"
                    :key="a.id"
                    class="d-flex justify-content-between border-bottom py-2 small text-muted"
                  >
                    <div>
                      <div>{{ a.title }}</div>
                      <div>{{ a.date }} 解消済</div>
                    </div>
                    <div class="flex-shrink-0 ms-2">{{ a.amount >= 0 ? '+' : '' }}{{ formatYen(a.amount) }}</div>
                  </div>
                </div>
              </div>

              <div class="small text-muted mt-2">この金額は最終精算ではなく、店舗確認用の調整メモです。</div>
            </template>
          </div>
        </div>
        </section>

        <section id="ca-info-notes" v-show="activeInfoTab === 'notes'" role="tabpanel" aria-labelledby="ca-info-tab-notes" tabindex="0" class="ca-info-panel">
        <!-- ノート/施術マニュアル（Phase 4） -->
        <div class="rk-section-header"><i class="ti ti-notebook"></i> ノート/マニュアル</div>
        <div class="card mb-3">
          <div class="card-body">
            <div v-if="notesLoading" class="text-muted text-center py-2 small">読み込み中...</div>
            <template v-else-if="!notes.pinned.length && !notes.recent.length">
              <div class="text-muted text-center py-2 small">まだノートはありません</div>
            </template>
            <template v-else>
              <template v-if="notes.pinned.length">
                <div class="small fw-bold text-muted mb-1"><i class="ti ti-pin text-warning"></i> ピン留め</div>
                <div
                  v-for="n in notes.pinned"
                  :key="'pinned-' + n.id"
                  class="d-flex justify-content-between align-items-center border-bottom py-2 small"
                  style="cursor: pointer;"
                  @click="openNote(n)"
                >
                  <div>
                    <span v-if="n.category" class="badge bg-light text-dark border me-1">{{ n.category }}</span>
                    <span class="fw-bold">{{ n.title }}</span>
                  </div>
                  <i class="ti ti-chevron-right text-muted"></i>
                </div>
              </template>
              <template v-if="notes.recent.length">
                <div class="small fw-bold text-muted mb-1 mt-2"><i class="ti ti-news"></i> 新着</div>
                <div
                  v-for="n in (showAllNotes ? notes.recent : notes.recent.slice(0, 5))"
                  :key="'recent-' + n.id"
                  class="d-flex justify-content-between align-items-center border-bottom py-2 small"
                  style="cursor: pointer;"
                  @click="openNote(n)"
                >
                  <div>
                    <span v-if="n.category" class="badge bg-light text-dark border me-1">{{ n.category }}</span>
                    <span>{{ n.title }}</span>
                  </div>
                  <i class="ti ti-chevron-right text-muted"></i>
                </div>
                <button
                  v-if="notes.recent.length > 5"
                  class="btn btn-link btn-sm p-0 mt-2"
                  @click="showAllNotes = !showAllNotes"
                >{{ showAllNotes ? '閉じる' : `もっと見る（${notes.recent.length}件）` }}</button>
              </template>
            </template>
          </div>
        </div>
        </section>

        <!-- ノート詳細モーダル -->
        <Teleport to="body">
          <div v-if="selectedNote" class="line-modal-overlay" @click.self="selectedNote = null">
            <div class="line-modal" style="max-width: 520px;">
              <div class="line-modal-header">
                <span class="fw-bold fs-5">{{ selectedNote.title }}</span>
                <button class="btn btn-sm btn-light rounded-circle" @click="selectedNote = null" style="width: 32px; height: 32px; padding: 0;">
                  <i class="ti ti-x"></i>
                </button>
              </div>
              <div class="line-modal-body">
                <div v-if="selectedNote.category" class="mb-2">
                  <span class="badge bg-light text-dark border">{{ selectedNote.category }}</span>
                </div>
                <div class="small text-muted mb-3" v-if="selectedNote.published_at">
                  公開日: {{ formatTime(selectedNote.published_at) === '' ? '' : selectedNote.published_at.slice(0, 10) }}
                </div>
                <div class="note-content" v-html="noteHtml(selectedNote)" @click="openNoteImage"></div>
                <div v-if="selectedNote.video_url" class="mt-3 small">
                  <a :href="selectedNote.video_url" target="_blank" rel="noopener"><i class="ti ti-video"></i> 関連動画リンク</a>
                </div>
              </div>
              <div class="line-modal-footer">
                <button class="btn btn-outline-secondary w-100" @click="selectedNote = null">閉じる</button>
              </div>
            </div>
          </div>
        </Teleport>

        <Teleport to="body">
          <div v-if="selectedNoteImage" class="line-modal-overlay note-image-overlay" @click="selectedNoteImage = ''">
            <button class="note-image-close" type="button" aria-label="閉じる" @click="selectedNoteImage = ''">
              <i class="ti ti-x"></i>
            </button>
            <img :src="selectedNoteImage" alt="ノート添付画像の拡大表示" @click.stop />
          </div>
        </Teleport>

        <!-- LINE連携カード -->
        <div v-if="lineLinked" class="card mb-3 border-success">
          <div class="card-body">
            <div class="d-flex align-items-center gap-3">
              <div class="flex-shrink-0">
                <div class="rounded-circle d-flex align-items-center justify-content-center bg-success" style="width: 40px; height: 40px;">
                  <i class="ti ti-brand-line" style="font-size: 20px; color: #fff;"></i>
                </div>
              </div>
              <div class="flex-grow-1">
                <div class="fw-bold mb-1">LINE連携</div>
                <div class="small text-success"><i class="ti ti-check"></i> 連携済み — リマインド通知が届きます</div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="card mb-3 border-warning border-2" style="cursor: pointer;" @click="showLineModal = true">
          <div class="card-body">
            <div class="d-flex align-items-center gap-3">
              <div class="flex-shrink-0">
                <div class="rounded-circle d-flex align-items-center justify-content-center bg-warning" style="width: 40px; height: 40px;">
                  <i class="ti ti-brand-line" style="font-size: 20px; color: #fff;"></i>
                </div>
              </div>
              <div class="flex-grow-1">
                <div class="fw-bold mb-1">LINE連携が必要です</div>
                <div class="small text-muted">タップして連携手順を確認 <i class="ti ti-chevron-right"></i></div>
              </div>
            </div>
          </div>
        </div>

        <!-- LINE連携モーダル -->
        <Teleport to="body">
          <div v-if="showLineModal && !lineLinked" class="line-modal-overlay" @click.self="showLineModal = false">
            <div class="line-modal">
              <div class="line-modal-header">
                <div class="d-flex align-items-center gap-2">
                  <div class="rounded-circle d-flex align-items-center justify-content-center" style="width: 36px; height: 36px; background: #06C755;">
                    <i class="ti ti-brand-line" style="font-size: 18px; color: #fff;"></i>
                  </div>
                  <span class="fw-bold fs-5">LINE連携</span>
                </div>
                <button class="btn btn-sm btn-light rounded-circle" @click="showLineModal = false" style="width: 32px; height: 32px; padding: 0;">
                  <i class="ti ti-x"></i>
                </button>
              </div>

              <div class="line-modal-body">
                <p class="text-muted small mb-3">出勤リマインドを受け取るためにLINE連携が必要です。</p>

                <!-- ステップ -->
                <div class="line-step">
                  <div class="line-step-num">1</div>
                  <div class="line-step-content">
                    <div class="fw-bold mb-2">連携コードをコピー</div>
                    <div class="line-code-box" @click="copyCode">
                      <span class="line-code">{{ lineLinkCode }}</span>
                      <span class="line-code-copy" :class="{ copied: codeCopied }">
                        <i :class="codeCopied ? 'ti ti-check' : 'ti ti-copy'"></i>
                        {{ codeCopied ? 'コピー済' : 'コピー' }}
                      </span>
                    </div>
                  </div>
                </div>

                <div class="line-step">
                  <div class="line-step-num">2</div>
                  <div class="line-step-content">
                    <div class="fw-bold mb-2">公式LINEを友だち追加してコードを送信</div>
                    <button class="btn w-100 text-white fw-bold" style="background: #06C755;" @click="openLineFriend">
                      <i class="ti ti-brand-line me-1"></i> 友だち追加する
                    </button>
                    <div class="small text-muted mt-2">友だち追加後、トーク画面でコピーしたコードを送信してください</div>
                  </div>
                </div>

                <div class="line-step">
                  <div class="line-step-num">3</div>
                  <div class="line-step-content">
                    <div class="fw-bold">連携完了！</div>
                    <div class="small text-muted mb-2">コード送信後、自動で連携されます。</div>
                    <button class="btn btn-sm btn-outline-success w-100" @click="location.reload()">
                      <i class="ti ti-refresh me-1"></i> ページを再読み込み
                    </button>
                  </div>
                </div>
              </div>

              <div class="line-modal-footer">
                <button class="btn btn-outline-secondary w-100" @click="showLineModal = false">あとで設定する</button>
              </div>
            </div>
          </div>
        </Teleport>

        <!-- 退勤 -->
        <div class="rk-section-header"><i class="ti ti-door-exit"></i> 退勤</div>

        <div v-if="checkoutData?.checkout" class="card mb-3">
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <span class="fw-bold"><i class="ti ti-clipboard-check text-primary"></i> 本日の退勤提出</span>
              <span
                class="badge"
                :class="{
                  SUBMITTED: 'badge-unconfirmed',
                  REVIEWED: 'badge-approved',
                  RETURNED: 'bg-danger',
                }[checkoutData.checkout.status]"
              >{{ checkoutStatusLabel(checkoutData.checkout.status) }}</span>
            </div>
            <div class="small text-muted mb-2">提出日時: {{ formatTime(checkoutData.checkout.submitted_at) }}</div>
            <div v-if="checkoutData.checkout.status === 'RETURNED'" class="alert alert-warning py-2 px-3 small mb-2">
              運営から差戻しされました。内容を確認して再提出してください。
              <div v-if="checkoutData.checkout.manager_memo" class="mt-1">「{{ checkoutData.checkout.manager_memo }}」</div>
            </div>
            <button class="btn btn-sm w-100" :class="checkoutIsReadOnly ? 'btn-outline-primary' : 'btn-warning'" @click="openCheckoutModal">
              <i class="ti ti-eye"></i> {{ checkoutIsReadOnly ? '提出内容を見る' : '内容を確認して再提出する' }}
            </button>
          </div>
        </div>

        <button v-else class="btn btn-primary w-100 mb-3" @click="openCheckoutModal">
          <i class="ti ti-door-exit"></i> 退勤する
        </button>

        <!-- 退勤モーダル -->
        <Teleport to="body">
          <div v-if="showCheckoutModal" class="line-modal-overlay" @click.self="showCheckoutModal = false">
            <div class="line-modal" style="max-width: 520px;">
              <div class="line-modal-header">
                <span class="fw-bold fs-5"><i class="ti ti-door-exit"></i> 退勤{{ checkoutIsReadOnly ? '内容' : '' }}</span>
                <button class="btn btn-sm btn-light rounded-circle" @click="showCheckoutModal = false" style="width: 32px; height: 32px; padding: 0;">
                  <i class="ti ti-x"></i>
                </button>
              </div>

              <div class="line-modal-body">
                <div v-if="checkoutError" class="alert alert-danger py-2 small">{{ checkoutError }}</div>

                <!-- 見込みサマリー -->
                <div class="bg-light rounded p-2 mb-3">
                  <div class="row g-2 text-center">
                    <div class="col-4">
                      <div class="small text-muted mb-1">完了済み</div>
                      <div class="fw-bold">{{ checkoutData?.done_count ?? 0 }}本</div>
                    </div>
                    <div class="col-4">
                      <div class="small text-muted mb-1">売上</div>
                      <div class="fw-bold">{{ formatYen(checkoutData?.total_sales ?? 0) }}</div>
                    </div>
                    <div class="col-4">
                      <div class="small text-muted mb-1">給与見込み</div>
                      <div class="fw-bold text-primary">{{ formatYen(checkoutData?.estimated_pay ?? 0) }}</div>
                    </div>
                  </div>
                  <div class="row g-2 text-center mt-1 pt-2 border-top">
                    <div class="col-6">
                      <div class="small text-muted mb-1">決済手数料見込み<span class="d-block" style="font-size: 0.7rem;">(参考値)</span></div>
                      <div class="small text-danger">-{{ formatYen(feeEstimate.fee) }}</div>
                    </div>
                    <div class="col-6">
                      <div class="small text-muted mb-1">手数料差引後売上<span class="d-block" style="font-size: 0.7rem;">(参考値)</span></div>
                      <div class="small">{{ formatYen(feeEstimate.net) }}</div>
                    </div>
                  </div>
                </div>

                <!-- 固定雑費テンプレ -->
                <div v-if="checkoutData?.expense_templates?.length" class="mb-3">
                  <div class="fw-bold small mb-1"><i class="ti ti-receipt"></i> 固定雑費</div>
                  <div v-for="t in checkoutData.expense_templates" :key="t.id" class="d-flex justify-content-between small border-bottom py-1">
                    <span>{{ t.name }}</span>
                    <span>{{ formatYen(t.amount) }}</span>
                  </div>
                </div>

                <!-- 読み取り専用表示（提出済み・確認済み） -->
                <template v-if="checkoutIsReadOnly">
                  <div class="mb-2">
                    <div class="small text-muted mb-1">実際の持ち帰り金額</div>
                    <div class="fw-bold">{{ formatYen(checkoutData.checkout.actual_take_home_amount) }}</div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted mb-1">チェックリスト</div>
                    <div v-for="item in CHECKLIST_ITEMS" :key="item.key" class="small">
                      <i class="ti" :class="checkoutData.checkout.checklist_json?.[item.key] ? 'ti-square-check text-success' : 'ti-square text-muted'"></i>
                      {{ item.label }}
                    </div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted mb-1">メモ</div>
                    <div class="bg-light p-2 rounded small">{{ checkoutData.checkout.cast_memo || 'なし' }}</div>
                  </div>
                  <div v-if="checkoutData.checkout.manager_memo" class="mb-2">
                    <div class="small text-muted mb-1">運営からのメモ</div>
                    <div class="bg-light p-2 rounded small">{{ checkoutData.checkout.manager_memo }}</div>
                  </div>
                </template>

                <!-- 入力フォーム（未提出 or 差戻し後） -->
                <template v-else>
                  <div class="mb-3">
                    <label class="form-label small fw-bold">実際の持ち帰り金額</label>
                    <input v-model.number="checkoutForm.actual_take_home_amount" type="number" min="0" class="form-control" />
                  </div>
                  <div class="mb-3">
                    <label class="form-label small fw-bold">退勤チェックリスト</label>
                    <div v-for="item in CHECKLIST_ITEMS" :key="item.key" class="form-check">
                      <input
                        v-model="checkoutForm.checklist_json[item.key]"
                        type="checkbox"
                        class="form-check-input"
                        :id="'chk-' + item.key"
                      />
                      <label class="form-check-label small" :for="'chk-' + item.key">{{ item.label }}</label>
                    </div>
                  </div>
                  <div class="mb-2">
                    <label class="form-label small fw-bold">メモ</label>
                    <textarea v-model="checkoutForm.cast_memo" class="form-control" rows="3" placeholder="運営への連絡事項があれば入力してください"></textarea>
                  </div>
                </template>

                <div class="small text-muted mt-2">表示金額は完了済み予約を元にした見込みです。最終精算額とは異なる場合があります。</div>
              </div>

              <div class="line-modal-footer">
                <div v-if="!checkoutIsReadOnly" class="d-flex gap-2">
                  <button class="btn btn-outline-secondary flex-grow-1" @click="showCheckoutModal = false">キャンセル</button>
                  <button class="btn btn-primary flex-grow-1" :disabled="checkoutSaving" @click="submitCheckout">
                    {{ checkoutSaving ? '送信中...' : '退勤提出する' }}
                  </button>
                </div>
                <button v-else class="btn btn-outline-secondary w-100" @click="showCheckoutModal = false">閉じる</button>
              </div>
            </div>
          </div>
        </Teleport>

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

<style scoped>
.ca-home-next { display: grid; gap: 3px; margin-top: 7px; }
.ca-home-next__date { color: #517268; font-size: .76rem; font-weight: 800; }
.ca-home-next__time { color: #20302d; font-size: 1.12rem; font-weight: 800; line-height: 1.35; }
.ca-home-next__time i, .ca-home-next__room i { color: #16836f; }
.ca-home-next__room { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; color: #31453d; font-size: .86rem; font-weight: 700; }
.ca-home-next__address { color: #65736e; font-size: .71rem; line-height: 1.4; }
.ca-home-map { display: inline-flex; align-items: center; gap: 3px; padding: 3px 9px; border: 1px solid #cce3d9; border-radius: 999px; color: #147866; font-size: .73rem; font-weight: 800; text-decoration: none; }
.ca-home-map:hover { background: #e9f5f0; }
.ca-home-map:focus-visible { outline: 2px solid #147866; outline-offset: 2px; }
.ca-bookings-heading { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.ca-bookings-count { display: inline-flex; align-items: center; gap: 8px; color: #3e5950; font-size: .78rem; font-weight: 800; white-space: nowrap; }
.ca-bookings-unconfirmed { color: #b72d32; }
.ca-bookings-alert { padding: 9px 12px; font-size: .83rem; font-weight: 700; }
.ca-booking-card { border-color: #e0eae5; border-radius: 14px; overflow: hidden; }
.ca-booking-card__body { padding: 15px; }
.ca-booking-card__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.ca-booking-card__time { color: #203a32; font-size: 1.16rem; font-weight: 800; line-height: 1.25; }
.ca-booking-card__duration { margin-top: 2px; color: #63756d; font-size: .76rem; }
.ca-booking-card__primary { display: grid; gap: 5px; margin-top: 14px; }
.ca-booking-card__primary > div { display: flex; align-items: center; gap: 7px; min-width: 0; color: #2c433a; font-size: .91rem; overflow-wrap: anywhere; }
.ca-booking-card__primary i, .ca-booking-card__details i { flex: 0 0 auto; color: #238674; }
.ca-booking-card__facts { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 9px; margin-top: 14px; }
.ca-booking-card__fact { min-width: 0; padding: 10px 11px; border-radius: 9px; background: #f1f7f4; overflow-wrap: anywhere; }
.ca-booking-card__fact span, .ca-booking-card__fact small { display: block; color: #5f7269; font-size: .73rem; line-height: 1.35; }
.ca-booking-card__fact strong { display: block; margin-top: 3px; color: #203a32; font-size: .87rem; line-height: 1.35; }
.ca-booking-card__fact small { margin-top: 3px; }
.ca-booking-card__disclosure { display: flex; align-items: center; gap: 5px; width: 100%; min-height: 42px; margin: 4px 0 8px; padding: 6px 0; border: 0; background: transparent; color: #147866; font-size: .79rem; font-weight: 800; text-align: left; }
.ca-booking-card__disclosure i { margin-left: auto; }
.ca-booking-card__disclosure:focus-visible { outline: 2px solid #147866; outline-offset: 2px; }
.ca-booking-card__memo-flag { padding: 2px 6px; border-radius: 4px; background: #fff1c8; color: #8c5c00; font-size: .7rem; white-space: nowrap; }
.ca-booking-card__details { display: grid; gap: 8px; margin-bottom: 12px; padding: 11px; border-radius: 9px; background: #f7faf8; color: #44584e; font-size: .81rem; line-height: 1.5; overflow-wrap: anywhere; }
.ca-info-tabs { display: grid; grid-template-columns: 1.3fr 1fr .8fr; gap: 3px; margin: 18px 0 12px; padding: 4px; border: 1px solid #dbe9e2; border-radius: 12px; background: #f0f6f3; }
.ca-info-tabs button { min-width: 0; padding: 9px 4px; border: 0; border-radius: 9px; background: transparent; color: #62766d; font-size: .8rem; font-weight: 800; white-space: nowrap; }
.ca-info-tabs button.is-active { background: #fff; color: #146f61; box-shadow: 0 1px 4px rgba(25, 73, 58, .1); }
.ca-info-tabs button:focus-visible { outline: 2px solid #147866; outline-offset: -2px; }
.ca-info-panel { min-height: 140px; }
.line-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0;
}
.line-modal {
  background: #fff;
  border-radius: 20px 20px 0 0;
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow-y: auto;
  animation: slideUp 0.25s ease-out;
}
@keyframes slideUp {
  from { transform: translateY(100%); }
  to { transform: translateY(0); }
}
.line-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 20px 12px;
  border-bottom: 1px solid #eee;
}
.line-modal-body {
  padding: 20px;
}
.line-modal-footer {
  padding: 12px 20px 24px;
}
.line-step {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}
.line-step-num {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #06C755;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 14px;
}
.line-step-content {
  flex: 1;
  min-width: 0;
}
.line-code-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f5f5f5;
  border: 2px dashed #ccc;
  border-radius: 10px;
  padding: 12px 16px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.line-code-box:active {
  border-color: #06C755;
}
.line-code {
  font-family: monospace;
  font-size: 1.5rem;
  font-weight: bold;
  letter-spacing: 4px;
}
.line-code-copy {
  font-size: 0.75rem;
  color: #888;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.line-code-copy.copied {
  color: #06C755;
}
.note-content {
  line-height: 1.75;
  overflow-wrap: anywhere;
}
.note-content :deep(> *:first-child) { margin-top: 0; }
.note-content :deep(> *:last-child) { margin-bottom: 0; }
.note-content :deep(h2) { margin: 1.2em 0 .55em; font-size: 1.42rem; }
.note-content :deep(h3) { margin: 1.1em 0 .5em; font-size: 1.16rem; }
.note-content :deep(blockquote) {
  margin: 1em 0;
  padding: .2em 1em;
  border-left: 4px solid #2d9c8f;
  color: #56606d;
}
.note-content :deep(a) { color: #0d6efd; text-decoration: underline; }
.note-content :deep(img) {
  display: block;
  width: auto;
  max-width: 100%;
  max-height: 70vh;
  margin: 14px auto;
  border-radius: 10px;
  object-fit: contain;
  cursor: zoom-in;
}
.note-image-overlay {
  align-items: center;
  padding: 18px;
  background: rgba(0, 0, 0, .9);
}
.note-image-overlay > img {
  max-width: 100%;
  max-height: 88vh;
  object-fit: contain;
}
.note-image-close {
  position: fixed;
  top: 18px;
  right: 18px;
  width: 42px;
  height: 42px;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, .92);
  font-size: 1.3rem;
}
</style>
