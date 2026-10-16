<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import AttendanceCards from '../../components/AttendanceCards.vue'
import { attendanceCards } from '../../attendanceCards.js'
import { localBusinessDate } from '../../businessDate.js'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

const router = useRouter()
const isManager = computed(() => getAuthRole() === 'manager')
const kpi = ref({ estimated_sales: 0, requested: 0, confirmed: 0, total_orders: 0 })
const requestedOrders = ref([])
const unconfirmedOrders = ref([])
const confirmedOrders = ref([])
const pendingFinalizeOrders = ref([])
const allOrders = ref([])
const casts = ref([])
const hasSchedule = ref(false)
const shiftConfirmAlerts = ref([])
const attendance = computed(() => attendanceCards(shiftConfirmAlerts.value, casts.value, notClockedIn.value))
const castForOrder = order => casts.value.find(cast => cast.id === order.cast_id)?.name || order.cast_name
const expandedAttention = ref(null)
const expandedGroup = computed(() => attentionGroups.value.find(group => group.key === expandedAttention.value))
const refreshing = ref(false)
const refreshErrors = ref([])
const updatedAt = ref(null)
let refreshRequest = 0
let refreshTimer = null
let mounted = true
let businessDayBoundaryHour = null
const roomPendingOrders = computed(() => allOrders.value.filter(
  o => o.is_room_pending && o.status !== 'CANCELLED' && o.status !== 'DONE'
))
const loading = ref(true)
// タブ: mikakunin(キャスト未確認) / request(予約リクエスト) / confirmed(本日の確定予約) / finalize(会計待ち)
const activeTab = ref('mikakunin')

// CONFIRMED の中で「現在時刻が施術時間内」なら UI 上「施術中」と表示する
const nowTick = ref(Date.now())
let nowTickTimer = null
function isInSession(order) {
  if (order.status !== 'CONFIRMED') return false
  const now = nowTick.value
  return new Date(order.start).getTime() <= now && now < new Date(order.end).getTime()
}

const requestedTop3 = computed(() => requestedOrders.value.slice(0, 3))
const unconfirmedTop3 = computed(() => unconfirmedOrders.value.slice(0, 3))
const proxyAcking = ref({})   // { [orderId]: true } 代理確認の二重クリック防止
const proxyAckError = ref('')

// LINE Alerts
const lineUnlinked = ref([])
const lineFailed = ref([])
const notClockedIn = ref([])
const shiftEndAlerts = ref([])

function makeAttentionGroup(key, label, tone, icon, to, entries) {
  return { key, label, tone, icon, to, entries }
}

const attentionGroups = computed(() => {
  const current = [
    ...(unconfirmedOrders.value.length ? [makeAttentionGroup('cast-unconfirmed', '予約未確認', 'warning', 'user-question', '/op/schedule', unconfirmedOrders.value.map(order => ({
      id: order.id,
      time: formatTime(order.start),
      title: orderPartyLabel(order),
      detail: castForOrder(order) || 'キャストの確認待ち',
      to: `/op/orders/${order.id}`,
    })))] : []),
    ...(requestedOrders.value.length ? [makeAttentionGroup('reservation-request', '予約リクエスト', 'warning', 'calendar-plus', '/op/schedule', requestedOrders.value.map(order => ({
      id: order.id,
      time: formatTime(order.start),
      title: orderPartyLabel(order),
      detail: castForOrder(order) || '内容を確認',
      to: `/op/orders/${order.id}`,
    })))] : []),
    ...(pendingFinalizeOrders.value.length ? [makeAttentionGroup('pending-finalize', '会計待ち', 'warning', 'cash-register', '/op/schedule', pendingFinalizeOrders.value.map(order => ({
      id: order.id,
      time: formatTime(order.start),
      title: orderPartyLabel(order),
      detail: castForOrder(order) || '会計を確認',
      to: `/op/orders/${order.id}`,
    })))] : []),
    ...(roomPendingOrders.value.length ? [makeAttentionGroup('room-pending', 'ルーム未定', 'warning', 'door-off', '/op/schedule', roomPendingOrders.value.map(order => ({
      id: order.id,
      time: formatTime(order.start),
      title: castForOrder(order) || 'キャスト未定',
      detail: orderPartyLabel(order),
    })))] : []),
    ...(shiftEndAlerts.value.length ? [makeAttentionGroup('shift-end', '受付終了の確認', 'warning', 'clock-exclamation', '/op/schedule', shiftEndAlerts.value.map(alert => ({
      id: alert.id,
      time: alert.shift_end_time_extended ? `終了 ${alert.shift_end_time_extended}` : '',
      title: alert.cast_name,
      detail: `本日 ${alert.valid_order_count}件 / ${formatYen(alert.done_sales)}`,
    })))] : []),
    ...(lineFailed.value.length ? [makeAttentionGroup('line-failed', 'LINE送信失敗', 'danger', 'brand-line', '/op/settings/line', lineFailed.value.map(item => ({
      id: item.id,
      time: item.sent_at ? formatTime(item.sent_at) : '',
      title: item.cast_name || '通知送信',
      detail: item.notification_type || 'LINE通知',
    })))] : []),
    ...(lineUnlinked.value.length ? [makeAttentionGroup('line-unlinked', 'LINE未連携', 'warning', 'brand-line', '/op/settings/line', lineUnlinked.value.map(cast => ({
      id: cast.id,
      time: cast.start_time ? `${cast.start_time}〜` : '',
      title: cast.name,
      detail: '本日出勤予定',
    })))] : []),
  ]
  return current
})

watch(attentionGroups, groups => {
  if (!groups.some(group => group.key === expandedAttention.value)) expandedAttention.value = null
})

function today() {
  return localBusinessDate(new Date(), businessDayBoundaryHour)
}

async function refreshDashboard() {
  if (refreshing.value) return
  const request = ++refreshRequest
  refreshing.value = true
  if (businessDayBoundaryHour === null) {
    try {
      const settings = await api.getBusinessDaySettings()
      if (!mounted || request !== refreshRequest) return
      if (!Number.isInteger(settings.business_day_boundary_hour)) throw new Error('Invalid boundary')
      businessDayBoundaryHour = settings.business_day_boundary_hour
    } catch (_) {
      if (!mounted || request !== refreshRequest) return
      refreshErrors.value = ['営業日の設定']
      refreshing.value = false
      loading.value = false
      return
    }
  }
  const date = today()
  const results = await Promise.allSettled([
    api.getSchedule(date), api.getLineAlerts(), api.getShiftEndAlerts(), api.getShiftConfirmAlerts(date),
  ])
  if (!mounted || request !== refreshRequest) return
  refreshErrors.value = results.flatMap((result, index) => result.status === 'rejected'
    ? [['予約・シフト', '出勤・LINE', '受付終了', '出勤確認'][index]] : [])
  if (results[0].status === 'fulfilled') {
    const data = results[0].value
    hasSchedule.value = true
    kpi.value = data.kpi
    casts.value = data.casts || []
    allOrders.value = data.orders
    requestedOrders.value = data.orders.filter(o => o.status === 'REQUESTED')
    unconfirmedOrders.value = data.orders.filter(o => o.is_unconfirmed && !['REQUESTED', 'CANCELLED', 'DONE'].includes(o.status))
    confirmedOrders.value = data.orders.filter(o => ['CONFIRMED', 'IN_PROGRESS'].includes(o.status))
    pendingFinalizeOrders.value = data.orders.filter(o => o.status === 'PENDING_FINALIZE')
  }
  if (results[1].status === 'fulfilled') {
    const data = results[1].value
    lineUnlinked.value = data.unlinked_casts || []
    lineFailed.value = data.failed_notifications || []
    notClockedIn.value = data.not_clocked_in_casts || []
  }
  if (results[2].status === 'fulfilled') shiftEndAlerts.value = results[2].value.open_alerts || []
  if (results[3].status === 'fulfilled') shiftConfirmAlerts.value = results[3].value.alerts || []
  if (!refreshErrors.value.length) updatedAt.value = new Date().toISOString()
  refreshing.value = false
  loading.value = false
}

function refreshWhenVisible() {
  if (!document.hidden) refreshDashboard()
}

onMounted(() => {
  refreshDashboard()
  if (isManager.value) fetchSales()
  refreshTimer = setInterval(refreshWhenVisible, 30000)
  document.addEventListener('visibilitychange', refreshWhenVisible)
  nowTickTimer = setInterval(() => { nowTick.value = Date.now() }, 60000)
})
onUnmounted(() => {
  mounted = false
  ++refreshRequest
  clearInterval(refreshTimer)
  clearInterval(nowTickTimer)
  document.removeEventListener('visibilitychange', refreshWhenVisible)
})

function goOrder(id) {
  router.push(`/op/orders/${id}`)
}

async function proxyAck(order) {
  if (proxyAcking.value[order.id]) return
  proxyAcking.value[order.id] = true
  proxyAckError.value = ''
  try {
    await api.opOrderCastAck(order.id)
    unconfirmedOrders.value = unconfirmedOrders.value.filter(o => o.id !== order.id)
  } catch (e) {
    proxyAckError.value = e.message || '代理確認に失敗しました'
  } finally {
    proxyAcking.value[order.id] = false
  }
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function orderPartyLabel(order) {
  if (!order.service_recipient_name) return order.customer_label
  return `${order.service_recipient_name}（連絡: ${order.customer_label}）`
}

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}

const STATUS_LABELS = {
  REQUESTED: '予約リクエスト',
  CONFIRMED: '確定',
  IN_PROGRESS: '施術中',
  PENDING_FINALIZE: '会計待ち',
  DONE: '完了',
  CANCELLED: 'キャンセル',
}
const STATUS_BADGES = {
  REQUESTED: 'badge-pending',
  CONFIRMED: 'badge-approved',
  IN_PROGRESS: 'badge-approved',
  PENDING_FINALIZE: 'badge-attention',
  DONE: 'bg-secondary',
  CANCELLED: 'bg-secondary',
}
function statusLabel(s) { return STATUS_LABELS[s] || s }
function statusBadgeClass(s) { return STATUS_BADGES[s] || 'bg-secondary' }

// ── Sales ──
const salesRange = ref('today')
const salesDateFrom = ref('')
const salesDateTo = ref('')
const sales = ref(null)
const salesLoading = ref(false)

function buildSalesParams() {
  if (salesRange.value === 'custom') {
    if (!salesDateFrom.value || !salesDateTo.value) return null
    return `date_from=${salesDateFrom.value}&date_to=${salesDateTo.value}`
  }
  return `range=${salesRange.value}`
}

async function fetchSales() {
  const params = buildSalesParams()
  if (!params) return
  salesLoading.value = true
  try {
    sales.value = await api.getSalesSummary(params)
  } catch (e) {
    console.error(e)
  } finally {
    salesLoading.value = false
  }
}

function exportCsv() {
  const params = buildSalesParams()
  if (!params) return
  window.open(api.getSalesExportUrl(params), '_blank')
}

watch([salesRange, salesDateFrom, salesDateTo], () => {
  if (isManager.value) fetchSales()
})
</script>

<template>
  <LayoutOperator>
    <template #title>ホーム</template>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <template v-else>
      <section class="dashboard-attention" aria-label="お知らせ・要対応">
        <header class="dashboard-attention__header">
          <div><span class="dashboard-attention__eyebrow">TODAY</span><h1>お知らせ・要対応</h1></div>
          <div class="dashboard-attention__update"><span v-if="updatedAt">{{ formatTime(updatedAt) }} 更新</span><button type="button" :disabled="refreshing" @click="refreshDashboard"><i class="ti ti-refresh" aria-hidden="true"></i>{{ refreshing ? '更新中…' : '更新' }}</button></div>
        </header>
        <p v-if="refreshErrors.length" class="dashboard-attention__error" role="alert">{{ refreshErrors.join('・') }}の最新情報を取得できませんでした。<template v-if="hasSchedule">表示中の情報は前回取得時のものです。</template>更新して再確認してください。</p>
        <AttendanceCards :cards="attendance" />
        <div v-if="attentionGroups.length" class="dashboard-attention__other" :class="{ 'has-attendance': attendance.length }">
          <h2>その他の要対応</h2>
          <div class="dashboard-attention__categories">
            <button v-for="group in attentionGroups" :key="group.key" type="button"
              class="dashboard-attention__category" :class="[{ 'is-active': expandedAttention === group.key }, `is-${group.tone}`]"
              :aria-expanded="expandedAttention === group.key" aria-controls="dashboard-attention-detail"
              @click="expandedAttention = expandedAttention === group.key ? null : group.key">
              <i class="ti" :class="`ti-${group.icon}`" aria-hidden="true"></i><span>{{ group.label }}</span>
              <strong>{{ group.entries.length }}<small>{{ ['shift-end', 'line-unlinked'].includes(group.key) ? '名' : '件' }}</small></strong>
              <i class="ti" :class="expandedAttention === group.key ? 'ti-chevron-up' : 'ti-chevron-down'" aria-hidden="true"></i>
            </button>
          </div>
          <section v-if="expandedGroup" id="dashboard-attention-detail" class="dashboard-attention__detail" :aria-label="expandedGroup.label">
            <header><h3>{{ expandedGroup.label }} <span>{{ expandedGroup.entries.length }}{{ ['shift-end', 'line-unlinked'].includes(expandedGroup.key) ? '名' : '件' }}</span></h3><button type="button" @click="expandedAttention = null">閉じる</button></header>
            <div class="dashboard-attention__rows">
              <router-link v-for="entry in expandedGroup.entries" :key="entry.id" :to="entry.to || expandedGroup.to" class="dashboard-attention__row">
                <time>{{ entry.time }}</time><span><strong>{{ entry.title }}</strong><small>{{ entry.detail }}</small></span><i class="ti ti-chevron-right" aria-hidden="true"></i>
              </router-link>
            </div>
          </section>
        </div>
        <p v-if="!attendance.length && !attentionGroups.length && !refreshErrors.length" class="dashboard-attention__empty"><i class="ti ti-circle-check" aria-hidden="true"></i>いま対応が必要なお知らせはありません。</p>
      </section>

      <template v-if="hasSchedule">
      <!-- 統計カード -->
      <div class="row g-2 mb-5">
        <div class="col-12 col-sm-6 col-xl-3">
          <div class="stat-box">
            <div class="stat-label">
              <i class="ti ti-currency-yen"></i> 本日売上（確定）
            </div>
            <div class="stat-value">{{ formatYen(kpi.estimated_sales) }}</div>
          </div>
        </div>
        <div class="col-6 col-sm-6 col-xl-3">
          <div class="stat-box">
            <div class="stat-label"><i class="ti ti-calendar-event"></i> 本日本数</div>
            <div class="stat-value">{{ kpi.total_orders }}</div>
            <div class="stat-change">{{ kpi.confirmed }} 確定 / {{ kpi.requested }} リクエスト</div>
          </div>
        </div>
        <div class="col-6 col-sm-6 col-xl-3">
          <div class="stat-box">
            <div class="stat-label"><i class="ti ti-users"></i> 出勤キャスト</div>
            <div class="stat-value">—</div>
            <div class="stat-change">
              <router-link to="/op/schedule">スケジュールで確認</router-link>
            </div>
          </div>
        </div>
      </div>

      <!-- 売上管理 (manager only) -->
      <div v-if="isManager" class="card border-0 mb-4">
        <div class="card-header d-flex align-items-center justify-content-between">
          <div><i class="ti ti-chart-bar"></i> 売上管理</div>
          <button class="btn btn-sm btn-outline-dark" @click="exportCsv">
            <i class="ti ti-download"></i> CSV
          </button>
        </div>
        <div class="card-body">
          <!-- 期間切替 -->
          <div class="d-flex flex-wrap gap-2 mb-3">
            <button
              v-for="r in [{key:'today',label:'今日'},{key:'week',label:'今週'},{key:'month',label:'今月'},{key:'custom',label:'期間指定'}]"
              :key="r.key"
              class="btn btn-sm"
              :class="salesRange === r.key ? 'btn-dark' : 'btn-outline-dark'"
              @click="salesRange = r.key"
            >{{ r.label }}</button>
          </div>
          <div v-if="salesRange === 'custom'" class="d-flex gap-2 mb-3">
            <input type="date" class="form-control form-control-sm" v-model="salesDateFrom">
            <span class="align-self-center">〜</span>
            <input type="date" class="form-control form-control-sm" v-model="salesDateTo">
          </div>

          <div v-if="salesLoading" class="text-center py-3">
            <div class="spinner-border spinner-border-sm text-primary"></div>
          </div>
          <template v-else-if="sales">
            <!-- KPI -->
            <div class="row g-2 mb-3">
              <div class="col-4">
                <div class="stat-box">
                  <div class="stat-label">売上合計</div>
                  <div class="stat-value">{{ formatYen(sales.total_sales) }}</div>
                </div>
              </div>
              <div class="col-4">
                <div class="stat-box">
                  <div class="stat-label">注文数</div>
                  <div class="stat-value">{{ sales.total_orders }}</div>
                </div>
              </div>
              <div class="col-4">
                <div class="stat-box">
                  <div class="stat-label">平均単価</div>
                  <div class="stat-value">{{ formatYen(sales.avg_order_value) }}</div>
                </div>
              </div>
            </div>
            <!-- 日別一覧 -->
            <div v-if="sales.by_day.length > 1" class="table-responsive">
              <table class="table table-sm table-bordered mb-0">
                <thead>
                  <tr><th>日付</th><th class="text-end">売上</th><th class="text-end">件数</th></tr>
                </thead>
                <tbody>
                  <tr v-for="d in sales.by_day" :key="d.date">
                    <td>{{ d.date }}</td>
                    <td class="text-end">{{ formatYen(d.sales) }}</td>
                    <td class="text-end">{{ d.orders }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>
      </div>

      <!-- タブ -->
      <nav class="dashboard-tabs mb-3">
        <div class="wrap">
          <button
            :class="{ active: activeTab === 'mikakunin' }"
            class="tab-mikakunin"
            @click="activeTab = 'mikakunin'"
          >キャスト未確認<span v-if="unconfirmedOrders.length" class="ms-1">({{ unconfirmedOrders.length }})</span></button>
        </div>
        <div class="wrap">
          <button
            :class="{ active: activeTab === 'request' }"
            @click="activeTab = 'request'"
          >予約リクエスト<span v-if="requestedOrders.length" class="ms-1">({{ requestedOrders.length }})</span></button>
        </div>
        <div class="wrap">
          <button
            :class="{ active: activeTab === 'confirmed' }"
            @click="activeTab = 'confirmed'"
          >本日の確定予約<span v-if="confirmedOrders.length" class="ms-1">({{ confirmedOrders.length }})</span></button>
        </div>
        <div class="wrap">
          <button
            :class="{ active: activeTab === 'finalize' }"
            @click="activeTab = 'finalize'"
          >会計待ち<span v-if="pendingFinalizeOrders.length" class="ms-1">({{ pendingFinalizeOrders.length }})</span></button>
        </div>
      </nav>

      <!-- 未確認アラート -->
      <div v-show="activeTab === 'mikakunin'" class="card border-0 mb-4">
        <div class="card-header bg-attention">
          <i class="ti ti-alert-triangle text-dark"></i> キャスト未確認
        </div>
        <div v-if="proxyAckError" class="alert alert-danger py-2 px-3 m-2 mb-0" style="font-size: 0.875rem;">{{ proxyAckError }}</div>
        <div class="card-body p-0">
          <ul class="list-group list-group-flush">
            <li
              v-for="order in unconfirmedTop3"
              :key="'alert-' + order.id"
              class="list-group-item"
            >
              <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
                <div class="d-flex align-items-center gap-2 flex-wrap">
                  <span class="badge badge-attention">キャスト未確認</span>
                  <strong>{{ orderPartyLabel(order) }}</strong>
                  <span class="text-muted small">{{ formatTime(order.start) }}</span>
                </div>
                <div class="d-flex align-items-center gap-2">
                  <button
                    class="btn btn-sm btn-primary"
                    :disabled="proxyAcking[order.id]"
                    @click="proxyAck(order)"
                  >
                    <i class="ti ti-check me-1"></i>{{ proxyAcking[order.id] ? '処理中...' : '代理で確認済みにする' }}
                  </button>
                  <a href="#" class="btn btn-sm btn-attention" @click.prevent="goOrder(order.id)">
                    <i class="ti ti-eye"></i> 詳細
                  </a>
                </div>
              </div>
            </li>
            <li v-if="unconfirmedOrders.length === 0" class="list-group-item text-muted text-center py-3">
              キャスト未確認の予約はありません
            </li>
          </ul>
        </div>
      </div>

      <!-- 予約リクエスト（REQUESTED） -->
      <div v-show="activeTab === 'request'" class="card border-0 mb-4">
        <div class="card-header">
          <i class="ti ti-inbox"></i> 予約リクエスト
        </div>
        <div class="card-body p-0">
          <ul class="list-group list-group-flush">
            <li
              v-for="order in requestedOrders"
              :key="'req-' + order.id"
              class="list-group-item"
            >
              <div class="d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center gap-2 flex-wrap">
                  <span class="badge badge-pending">リクエスト</span>
                  <strong>{{ orderPartyLabel(order) }}</strong>
                  <span class="text-muted small">{{ formatTime(order.start) }}–{{ formatTime(order.end) }}</span>
                  <span class="text-muted small">{{ order.course_name }}</span>
                </div>
                <a href="#" class="btn btn-sm btn-primary" @click.prevent="goOrder(order.id)">
                  <i class="ti ti-check me-1"></i>確認する
                </a>
              </div>
            </li>
            <li v-if="requestedOrders.length === 0" class="list-group-item text-muted text-center py-3">
              予約リクエストはありません
            </li>
          </ul>
        </div>
      </div>

      <!-- 本日の確定予約（CONFIRMED、施術中なら動的に「施術中」バッジ） -->
      <div v-show="activeTab === 'confirmed'" class="card border-0 mb-4">
        <div class="card-header">
          <i class="ti ti-calendar-check"></i> 本日の確定予約
        </div>
        <div class="card-body p-0">
          <ul class="list-group list-group-flush">
            <li
              v-for="order in confirmedOrders"
              :key="'cf-' + order.id"
              class="list-group-item"
            >
              <div class="d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center gap-2 flex-wrap">
                  <span v-if="isInSession(order)" class="badge badge-approved">施術中</span>
                  <span v-else class="badge badge-approved">確定</span>
                  <strong>{{ orderPartyLabel(order) }}</strong>
                  <span class="text-muted small">{{ formatTime(order.start) }}–{{ formatTime(order.end) }}</span>
                  <span class="text-muted small">{{ order.course_name }}</span>
                </div>
                <a href="#" class="btn btn-sm btn-primary" @click.prevent="goOrder(order.id)">
                  <i class="ti ti-circle-check me-1"></i>施術終了
                </a>
              </div>
            </li>
            <li v-if="confirmedOrders.length === 0" class="list-group-item text-muted text-center py-3">
              本日の確定予約はありません
            </li>
          </ul>
        </div>
      </div>

      <!-- 会計待ち（PENDING_FINALIZE） -->
      <div v-show="activeTab === 'finalize'" class="card border-0 mb-4">
        <div class="card-header">
          <i class="ti ti-cash"></i> 会計待ち
        </div>
        <div class="card-body p-0">
          <ul class="list-group list-group-flush">
            <li
              v-for="order in pendingFinalizeOrders"
              :key="'fin-' + order.id"
              class="list-group-item"
            >
              <div class="d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center gap-2 flex-wrap">
                  <span class="badge badge-attention">会計待ち</span>
                  <strong>{{ orderPartyLabel(order) }}</strong>
                  <span class="text-muted small">{{ formatTime(order.start) }}–{{ formatTime(order.end) }}</span>
                </div>
                <a href="#" class="btn btn-sm btn-primary" @click.prevent="goOrder(order.id)">
                  <i class="ti ti-cash me-1"></i>会計確定
                </a>
              </div>
            </li>
            <li v-if="pendingFinalizeOrders.length === 0" class="list-group-item text-muted text-center py-3">
              会計待ちの予約はありません
            </li>
          </ul>
        </div>
      </div>
      </template>
    </template>
  </LayoutOperator>
</template>

<style scoped>
.dashboard-attention {
  margin-bottom: 24px;
  padding: 19px 20px 20px;
  border: 1px solid #e2eae6;
  border-radius: 12px;
  background: #fff;
}

.dashboard-attention__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
.dashboard-attention__eyebrow { display: block; color: #78928b; font-size: .61rem; letter-spacing: .12em; margin-bottom: 3px; }
.dashboard-attention__header h1 { margin: 0; font-size: 1.05rem; font-weight: 700; color: #2b4540; }
.dashboard-attention__update { display: flex; align-items: center; gap: 10px; font-size: .68rem; color: #778b84; }
.dashboard-attention__update button { display: flex; gap: 5px; align-items: center; border: 1px solid #dde7e2; border-radius: 6px; padding: 5px 9px; background: #fff; color: #506b62; font-size: .71rem; }
.dashboard-attention__other.has-attendance { border-top: 1px solid #e8eeeb; margin-top: 16px; padding-top: 13px; }
.dashboard-attention__other > h2 { font-size: .7rem; color: #7c8c86; margin: 0 0 9px; font-weight: 500; }
.dashboard-attention__categories { display: flex; flex-wrap: wrap; gap: 7px; }
.dashboard-attention__category { display: flex; gap: 7px; align-items: center; border: 1px solid #e4ebe7; border-radius: 7px; background: #f8faf9; padding: 8px 10px; font-size: .74rem; color: #50625c; }
.dashboard-attention__category > .ti:first-child { color: #9b7b39; font-size: 15px; }
.dashboard-attention__category > .ti:last-child { font-size: 10px; color: #8d9b95; }
.dashboard-attention__category strong { color: #314c42; font-size: .84rem; margin-left: 3px; }
.dashboard-attention__category small { font-size: .6rem; font-weight: 400; margin-left: 2px; }
.dashboard-attention__category.is-danger > .ti:first-child { color: #b23f50; }
.dashboard-attention__category.is-active { border-color: #75b9a8; background: #ebf6f1; color: #246653; }
.dashboard-attention__category:hover { background: #eef5f1; }
.dashboard-attention__detail { border: 1px solid #dfe9e3; border-radius: 8px; margin-top: 10px; padding: 0 12px; background: #fff; }
.dashboard-attention__detail > header { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 10px 0; }
.dashboard-attention__detail h3 { margin: 0; font-size: .8rem; }
.dashboard-attention__detail h3 span { margin-left: 5px; color: #7c8a83; font-size: .7rem; font-weight: 400; }
.dashboard-attention__detail button { border: 0; background: transparent; padding: 3px 7px; color: #6c8076; font-size: .7rem; }
.dashboard-attention__rows { max-height: 240px; overflow-y: auto; overscroll-behavior: contain; }
.dashboard-attention__error { color: #a63842; font-size: .78rem; padding: 10px 12px; border-radius: 6px; background: #fff1f0; }
.dashboard-attention__empty { margin: 0; display: flex; align-items: center; gap: 7px; font-size: .82rem; color: #6b8176; }

.dashboard-attention__row {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) 12px;
  align-items: center;
  column-gap: 0.45rem;
  min-height: 45px;
  border-top: 1px solid #edf2f1;
  color: #334155;
  font-size: 0.78rem;
  text-decoration: none;
}

.dashboard-attention__row time { color: #64748b; font-variant-numeric: tabular-nums; }
.dashboard-attention__row span { min-width: 0; display: flex; align-items: baseline; flex-wrap: wrap; gap: 0 .6rem; padding: 6px 0; }
.dashboard-attention__row strong { overflow-wrap: anywhere; }
.dashboard-attention__row small { color: #64748b; font-size: .72rem; overflow-wrap: anywhere; }
.dashboard-attention__row .ti-chevron-right { color: #94a3b8; font-size: 0.72rem; }

@media (max-width: 575.98px) {
  .dashboard-tabs {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0;
    margin-inline: -0.25rem;
  }

  .dashboard-tabs .wrap { min-width: 0; }

  .dashboard-tabs button {
    width: 100%;
    min-height: 52px;
    padding: .45rem .15rem;
    font-size: clamp(.73rem, 3.1vw, .88rem);
    line-height: 1.35;
    white-space: nowrap;
  }

  .dashboard-attention { padding: 14px 12px; margin-bottom: 16px; }
  .dashboard-attention__header { margin-bottom: 14px; }
  .dashboard-attention__header h1 { font-size: .92rem; }
  .dashboard-attention__update > span { display: none; }
  .dashboard-attention__categories { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dashboard-attention__category { gap: 5px; padding: 8px; font-size: .69rem; min-width: 0; }
  .dashboard-attention__category > span { flex: 1; }
  .dashboard-attention__category > .ti:last-child { display: none; }
}
@media (pointer: coarse) { .dashboard-attention button { min-height: 44px; } }
</style>
