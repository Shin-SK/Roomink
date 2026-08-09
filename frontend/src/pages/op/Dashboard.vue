<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
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
let lineAlertTimer = null

function today() {
  const d = new Date()
  return d.toISOString().slice(0, 10)
}

onMounted(async () => {
  try {
    const data = await api.getSchedule(today())
    kpi.value = data.kpi
    allOrders.value = data.orders
    requestedOrders.value = data.orders.filter(o => o.status === 'REQUESTED')
    unconfirmedOrders.value = data.orders.filter(o => o.is_unconfirmed && o.status !== 'REQUESTED' && o.status !== 'CANCELLED' && o.status !== 'DONE')
    // 「本日の確定予約」= CONFIRMED と IN_PROGRESS（後方互換、現状運用では出さない想定）
    confirmedOrders.value = data.orders.filter(o => o.status === 'CONFIRMED' || o.status === 'IN_PROGRESS')
    pendingFinalizeOrders.value = data.orders.filter(o => o.status === 'PENDING_FINALIZE')
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }

  // Sales (manager only)
  if (isManager.value) fetchSales()

  // LINE alerts (30 sec)
  await fetchLineAlerts()
  lineAlertTimer = setInterval(fetchLineAlerts, 30000)

  // 「施術中」表示判定用に1分ごとに現在時刻を更新
  nowTickTimer = setInterval(() => { nowTick.value = Date.now() }, 60000)
})

onUnmounted(() => {
  if (lineAlertTimer) clearInterval(lineAlertTimer)
  if (nowTickTimer) clearInterval(nowTickTimer)
})

async function fetchLineAlerts() {
  try {
    const data = await api.getLineAlerts()
    lineUnlinked.value = data.unlinked_casts || []
    lineFailed.value = data.failed_notifications || []
    notClockedIn.value = data.not_clocked_in_casts || []
  } catch (e) {
    // non-fatal
  }
}

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
      <div v-if="roomPendingOrders.length" class="alert alert-warning mb-3 py-2 px-3">
        <div class="d-flex align-items-center justify-content-between gap-2 mb-1">
          <div class="d-flex align-items-center gap-2">
            <i class="ti ti-door-off"></i>
            <strong>本日、ルーム未定の予約が {{ roomPendingOrders.length }}件あります</strong>
          </div>
          <router-link to="/op/schedule" class="btn btn-sm btn-outline-warning py-0">
            予約タイムラインへ
          </router-link>
        </div>
        <div v-for="order in roomPendingOrders" :key="'room-pending-'+order.id" class="small">
          {{ formatTime(order.start) }} {{ order.cast_name }} / {{ order.customer_label }}
        </div>
      </div>

      <!-- 未出勤アラート -->
      <div v-if="notClockedIn.length" class="alert alert-danger mb-3 py-2 px-3">
        <div class="d-flex align-items-center justify-content-between gap-2 mb-1">
          <div class="d-flex align-items-center gap-2">
            <i class="ti ti-alert-triangle"></i>
            <strong>未出勤のキャストがいます</strong>
          </div>
          <router-link to="/op/shifts" class="btn btn-sm btn-outline-danger py-0">
            シフト管理へ
          </router-link>
        </div>
        <div v-for="c in notClockedIn" :key="'nc-'+c.id" class="small">
          {{ c.name }}（{{ c.start_time }}〜）
        </div>
      </div>

      <!-- LINE アラート -->
      <div v-if="lineUnlinked.length" class="alert alert-warning mb-3 py-2 px-3">
        <div class="d-flex align-items-center gap-2 mb-1">
          <i class="ti ti-brand-line"></i>
          <strong>LINE未連携キャストが本日出勤予定</strong>
        </div>
        <div v-for="c in lineUnlinked" :key="'lu-'+c.id" class="small">
          {{ c.name }}（{{ c.start_time }}〜）
        </div>
      </div>
      <div v-if="lineFailed.length" class="alert alert-danger mb-3 py-2 px-3">
        <div class="d-flex align-items-center gap-2 mb-1">
          <i class="ti ti-brand-line"></i>
          <strong>LINE通知の送信失敗</strong>
        </div>
        <div v-for="f in lineFailed" :key="'lf-'+f.id" class="small">
          {{ f.cast_name }} — {{ f.notification_type }}（{{ f.error_message }}）
        </div>
      </div>

      <!-- 通知エリア -->
      <div class="wrap bg-white overflow-y-auto mb-4" style="max-height: 20vh;">
        <ul class="d-flex flex-column gap-2">
          <li v-if="unconfirmedOrders.length">
            <a href="#" @click.prevent="activeTab = 'mikakunin'" class="d-flex align-items-center gap-2 border-bottom w-100 pb-2 text-decoration-none">
              <div class="badge badge-attention">キャスト未確認</div><small>{{ unconfirmedOrders.length }}件</small>
            </a>
          </li>
          <li v-if="requestedOrders.length">
            <a href="#" @click.prevent="activeTab = 'request'" class="d-flex align-items-center gap-2 border-bottom w-100 pb-2 text-decoration-none">
              <div class="badge badge-pending">予約リクエスト</div><small>{{ requestedOrders.length }}件</small>
            </a>
          </li>
          <li v-if="pendingFinalizeOrders.length">
            <a href="#" @click.prevent="activeTab = 'finalize'" class="d-flex align-items-center gap-2 border-bottom w-100 pb-2 text-decoration-none">
              <div class="badge badge-attention">会計待ち</div><small>{{ pendingFinalizeOrders.length }}件</small>
            </a>
          </li>
        </ul>
      </div>

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
                  <strong>{{ order.customer_label }}</strong>
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
                  <strong>{{ order.customer_label }}</strong>
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
                  <strong>{{ order.customer_label }}</strong>
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
                  <strong>{{ order.customer_label }}</strong>
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
  </LayoutOperator>
</template>
