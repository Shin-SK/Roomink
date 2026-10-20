<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

const isManager = computed(() => getAuthRole() === 'manager')

const casts = ref([])
const rooms = ref([])
const areaBreakdownColumns = [
  { key: 'course_sales', label: 'コース' },
  { key: 'options_sales', label: 'オプション' },
  { key: 'extension_sales', label: '延長' },
  { key: 'nomination_fee_sales', label: '指名料' },
  { key: 'discount_amount', label: '割引' },
]

function toLocalDateString(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const today = toLocalDateString(new Date())
const currentBusinessDate = ref(today)
const range = ref('today')
const selectedDate = ref(today)
const dateFrom = ref('')
const dateTo = ref('')
const filterCast = ref('')
const filterRoom = ref('')
const filterPaymentMethod = ref('')

const data = ref(null)
const loading = ref(false)
const error = ref('')
const selectedCastDetail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
let dashboardRequestId = 0
let detailRequestId = 0
let dashboardRefreshTimer
let dashboardInFlight = false
let dashboardRefreshQueued = false
let dashboardDisposed = false

const isToday = computed(() => (
  range.value === 'today'
  || (range.value === 'day' && selectedDate.value === currentBusinessDate.value)
))
const selectedDateLabel = computed(() => {
  if (!selectedDate.value) return ''
  const [year, month, day] = selectedDate.value.split('-').map(Number)
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'short',
  }).format(new Date(year, month - 1, day))
})

function buildDateParams() {
  if (range.value === 'day') {
    return `date_from=${selectedDate.value}&date_to=${selectedDate.value}`
  }
  if (range.value === 'today') return 'range=today'
  if (range.value === 'custom') {
    if (!dateFrom.value || !dateTo.value) return null
    return `date_from=${dateFrom.value}&date_to=${dateTo.value}`
  }
  return `range=${range.value}`
}

function buildParams() {
  let params = buildDateParams()
  if (!params) return null
  if (filterCast.value) params += `&cast=${filterCast.value}`
  if (filterRoom.value) params += `&room=${filterRoom.value}`
  if (filterPaymentMethod.value) params += `&payment_method=${filterPaymentMethod.value}`
  return params
}

function shiftDay(amount) {
  const [year, month, day] = selectedDate.value.split('-').map(Number)
  const next = new Date(year, month - 1, day)
  next.setDate(next.getDate() + amount)
  selectedDate.value = toLocalDateString(next)
  range.value = 'day'
}

function goToday() {
  selectedDate.value = currentBusinessDate.value
  range.value = 'today'
}

async function loadMasters() {
  const [castData, roomData] = await Promise.all([api.getCasts(), api.getRooms()])
  casts.value = Array.isArray(castData) ? castData : []
  rooms.value = Array.isArray(roomData) ? roomData : []
}

async function fetchDashboard() {
  if (dashboardDisposed) return
  // A changed filter replaces the pending refresh; it never starts another
  // server aggregation while the preceding request is still running.
  if (dashboardInFlight) {
    dashboardRefreshQueued = true
    return
  }
  const requestId = ++dashboardRequestId
  detailRequestId += 1
  const params = buildParams()
  if (!params) {
    loading.value = false
    return
  }
  error.value = ''
  selectedCastDetail.value = null
  detailError.value = ''
  loading.value = true
  dashboardInFlight = true
  try {
    const response = await api.getSalesDashboard(params)
    if (requestId !== dashboardRequestId) return
    data.value = response
    if (range.value === 'today' && data.value?.date_from) {
      currentBusinessDate.value = data.value.date_from
      selectedDate.value = data.value.date_from
    }
  } catch (e) {
    if (requestId !== dashboardRequestId) return
    error.value = e.message || '売上集計の取得に失敗しました'
    data.value = null
  } finally {
    dashboardInFlight = false
    if (dashboardRefreshQueued && !dashboardDisposed) {
      dashboardRefreshQueued = false
      clearTimeout(dashboardRefreshTimer)
      dashboardRefreshTimer = setTimeout(fetchDashboard, 350)
    } else if (requestId === dashboardRequestId) {
      loading.value = false
    }
  }
}

async function openCastDetail(castRow) {
  const requestId = ++detailRequestId
  if (selectedCastDetail.value?.cast_id === castRow.cast_id) {
    selectedCastDetail.value = null
    return
  }
  let params = buildDateParams()
  if (!params) return
  params += `&cast=${castRow.cast_id}`
  if (filterRoom.value) params += `&room=${filterRoom.value}`
  if (filterPaymentMethod.value) params += `&payment_method=${filterPaymentMethod.value}`
  detailLoading.value = true
  detailError.value = ''
  selectedCastDetail.value = null
  try {
    const response = await api.getSalesDashboardCastDetail(params)
    if (requestId !== detailRequestId) return
    selectedCastDetail.value = response
  } catch (e) {
    if (requestId !== detailRequestId) return
    detailError.value = e.message || 'キャスト明細の取得に失敗しました'
  } finally {
    if (requestId === detailRequestId) detailLoading.value = false
  }
}

function exportCsv() {
  const params = buildParams()
  if (!params) return
  window.open(api.getSalesDashboardExportUrl(params), '_blank')
}

function formatYen(n) {
  return `¥${Number(n || 0).toLocaleString()}`
}

watch([range, selectedDate, dateFrom, dateTo, filterCast, filterRoom, filterPaymentMethod], () => {
  clearTimeout(dashboardRefreshTimer)
  dashboardRequestId += 1
  detailRequestId += 1
  if (isManager.value) {
    loading.value = true
    dashboardRefreshTimer = setTimeout(fetchDashboard, 350)
  }
})

onBeforeUnmount(() => {
  dashboardDisposed = true
  clearTimeout(dashboardRefreshTimer)
  dashboardRequestId += 1
  detailRequestId += 1
})

onMounted(async () => {
  if (!isManager.value) return
  try {
    await loadMasters()
  } catch (e) {
    error.value = e.message
  }
  await fetchDashboard()
})
</script>

<template>
  <LayoutOperator>
    <template #title>売上集計</template>

    <div v-if="!isManager" class="alert alert-warning mt-3">
      <i class="ti ti-lock me-1"></i>この画面はマネージャー権限が必要です。
    </div>

    <template v-else>
      <div class="card border-0 mb-4">
        <div class="card-header d-flex align-items-center justify-content-between">
          <div><i class="ti ti-report-money"></i> 売上集計</div>
          <div class="d-flex gap-2">
          <button class="btn btn-sm btn-outline-dark" :disabled="loading" @click="fetchDashboard">
            <i class="ti ti-refresh"></i> 再集計
          </button>
          <button class="btn btn-sm btn-outline-dark" :disabled="loading || !data" @click="exportCsv">
            <i class="ti ti-download"></i> CSV
          </button>
          </div>
        </div>
        <div class="card-body">
          <!-- 期間切替 -->
          <div class="d-flex flex-wrap gap-2 mb-2 sales-range-buttons">
            <button
              class="btn btn-sm btn-outline-dark"
              @click="shiftDay(-1)"
            ><i class="ti ti-chevron-left"></i> 前日</button>
            <button
              class="btn btn-sm"
              :class="isToday ? 'btn-dark' : 'btn-outline-dark'"
              @click="goToday"
            >今日</button>
            <button
              class="btn btn-sm btn-outline-dark"
              :disabled="isToday"
              @click="shiftDay(1)"
            >翌日 <i class="ti ti-chevron-right"></i></button>
            <button
              v-for="r in [{key:'week',label:'今週'},{key:'month',label:'今月'},{key:'custom',label:'期間指定'}]"
              :key="r.key"
              class="btn btn-sm"
              :class="range === r.key ? 'btn-dark' : 'btn-outline-dark'"
              @click="range = r.key"
            >{{ r.label }}</button>
          </div>
          <div v-if="range === 'day' || range === 'today'" class="selected-sales-date mb-3">
            <i class="ti ti-calendar-event"></i>
            <strong>{{ selectedDateLabel }}</strong>
            <span v-if="!isToday">の売上</span>
          </div>
          <div v-if="range === 'custom'" class="d-flex gap-2 mb-3">
            <input type="date" class="form-control form-control-sm" v-model="dateFrom">
            <span class="align-self-center">〜</span>
            <input type="date" class="form-control form-control-sm" v-model="dateTo">
          </div>

          <!-- 絞り込み -->
          <div class="row g-2 mb-3">
            <div class="col-4 col-md-3">
              <select v-model="filterCast" class="form-select form-select-sm">
                <option value="">全キャスト</option>
                <option v-for="c in casts" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </div>
            <div class="col-4 col-md-3">
              <select v-model="filterRoom" class="form-select form-select-sm">
                <option value="">全ルーム</option>
                <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
              </select>
            </div>
            <div class="col-4 col-md-3">
              <select v-model="filterPaymentMethod" class="form-select form-select-sm">
                <option value="">全決済方法</option>
                <option value="CARD">カード</option>
                <option value="CASH">現金</option>
                <option value="PAYPAY">PayPay</option>
                <option value="UNSET">未設定</option>
              </select>
            </div>
          </div>

          <div v-if="error" class="alert alert-danger py-2 px-3 mb-3" style="font-size: 0.875rem;">
            {{ error }}
          </div>

          <div v-if="loading" class="text-center py-3">
            <div class="spinner-border spinner-border-sm text-primary" aria-hidden="true"></div>
            <span class="ms-2" role="status">集計しています…</span>
          </div>

          <template v-else-if="data">
            <div class="text-muted small mb-2">
              集計期間: {{ data.date_from }} 〜 {{ data.date_to }}（DONE注文のみ）
            </div>

            <!-- サマリーカード -->
            <div class="row g-2 mb-4">
              <div class="col-6 col-md-3">
                <div class="stat-box">
                  <div class="stat-label">総売上</div>
                  <div class="stat-value">{{ formatYen(data.total_sales) }}</div>
                </div>
              </div>
              <div class="col-6 col-md-3">
                <div class="stat-box">
                  <div class="stat-label">DONE注文件数</div>
                  <div class="stat-value">{{ data.total_orders }}</div>
                </div>
              </div>
              <div class="col-6 col-md-3">
                <div class="stat-box">
                  <div class="stat-label">コース売上</div>
                  <div class="stat-value">{{ formatYen(data.course_sales) }}</div>
                </div>
              </div>
              <div class="col-6 col-md-3">
                <div class="stat-box">
                  <div class="stat-label">オプション売上</div>
                  <div class="stat-value">{{ formatYen(data.options_sales) }}</div>
                </div>
              </div>
              <div class="col-6 col-md-3">
                <div class="stat-box">
                  <div class="stat-label">延長料金</div>
                  <div class="stat-value">{{ formatYen(data.extension_sales) }}</div>
                </div>
              </div>
              <div class="col-6 col-md-3">
                <div class="stat-box">
                  <div class="stat-label">指名料</div>
                  <div class="stat-value">{{ formatYen(data.nomination_fee_sales) }}</div>
                </div>
              </div>
              <div class="col-6 col-md-3">
                <div class="stat-box">
                  <div class="stat-label">割引額</div>
                  <div class="stat-value">{{ formatYen(data.discount_amount) }}</div>
                </div>
              </div>
              <div class="col-6 col-md-3">
                <div class="stat-box">
                  <div class="stat-label">カード決済加算<span class="text-muted">(お客様負担)</span></div>
                  <div class="stat-value text-success">+{{ formatYen(data.customer_payment_surcharge) }}</div>
                </div>
              </div>
              <div class="col-6 col-md-3">
                <div class="stat-box">
                  <div class="stat-label">お客様決済額</div>
                  <div class="stat-value">{{ formatYen(data.customer_payment_total) }}</div>
                </div>
              </div>
              <div class="col-6 col-md-3">
                <div class="stat-box">
                  <div class="stat-label">店舗側決済手数料<span class="text-muted">(参考値)</span></div>
                  <div class="stat-value text-danger">-{{ formatYen(data.payment_fee_estimate) }}</div>
                </div>
              </div>
              <div class="col-6 col-md-3">
                <div class="stat-box">
                  <div class="stat-label">手数料差引後売上<span class="text-muted">(参考値)</span></div>
                  <div class="stat-value">{{ formatYen(data.net_sales_after_payment_fee) }}</div>
                </div>
              </div>
            </div>
            <div class="small text-muted mb-3">
              ※ カードの設定率はお客様の決済額への上乗せ率です。現金・PayPayの手数料は店舗側の参考値で、カード上乗せ分は店舗配分に含まれます。
            </div>

            <!-- 日別売上 -->
            <div class="fw-bold small mb-1"><i class="ti ti-calendar"></i> 日別売上</div>
            <div v-if="data.by_day && data.by_day.length" class="table-responsive mb-4">
              <table class="table table-sm table-bordered mb-0">
                <thead>
                  <tr>
                    <th>日付</th>
                    <th class="text-end">売上</th>
                    <th class="text-end">件数</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="d in data.by_day" :key="d.date">
                    <td>{{ d.date }}</td>
                    <td class="text-end">{{ formatYen(d.sales) }}</td>
                    <td class="text-end">{{ d.orders }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-muted small mb-4">期間内の売上はありません</div>

            <!-- キャスト別売上 -->
            <div class="fw-bold small mb-1"><i class="ti ti-user"></i> キャスト別売上・給与見込み</div>
            <div v-if="data.by_cast && data.by_cast.length" class="table-responsive mb-4">
              <table class="table table-sm table-bordered mb-0">
                <thead>
                  <tr>
                    <th>キャスト</th>
                    <th class="text-end">件数</th>
                    <th class="text-end">売上</th>
                    <th class="text-end">コース売上</th>
                    <th class="text-end">オプション売上</th>
                    <th class="text-end">バック率</th>
                    <th class="text-end">給与見込み</th>
                    <th class="text-end">明細</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="c in data.by_cast" :key="c.cast_id">
                    <td class="fw-bold">{{ c.cast_name }}</td>
                    <td class="text-end">{{ c.orders }}</td>
                    <td class="text-end">{{ formatYen(c.sales) }}</td>
                    <td class="text-end">{{ formatYen(c.course_sales) }}</td>
                    <td class="text-end">{{ formatYen(c.options_sales) }}</td>
                    <td class="text-end">コース {{ c.course_back_rate }}%・OP {{ c.option_back_rate ?? (c.option_fullback_enabled ? 100 : 0) }}%</td>
                    <td class="text-end fw-bold text-primary">{{ formatYen(c.estimated_pay) }}</td>
                    <td class="text-end">
                      <button class="btn btn-sm btn-outline-primary text-nowrap" @click="openCastDetail(c)">
                        {{ selectedCastDetail?.cast_id === c.cast_id ? '閉じる' : '明細を見る' }}
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-muted small mb-4">期間内のキャスト別売上はありません</div>

            <div v-if="detailLoading" class="cast-detail-loading mb-4">
              <div class="spinner-border spinner-border-sm text-primary"></div>
              <span>明細を読み込んでいます</span>
            </div>
            <div v-if="detailError" class="alert alert-danger py-2 px-3 mb-4">
              {{ detailError }}
            </div>

            <section v-if="selectedCastDetail" class="cast-detail mb-4">
              <div class="cast-detail__header">
                <div>
                  <span class="cast-detail__eyebrow">キャスト別明細</span>
                  <h3>{{ selectedCastDetail.cast_name }}さんの売上明細</h3>
                  <p>{{ selectedCastDetail.date_from }} 〜 {{ selectedCastDetail.date_to }}</p>
                </div>
                <button class="btn btn-sm btn-light" @click="selectedCastDetail = null">
                  <i class="ti ti-x"></i> 閉じる
                </button>
              </div>

              <div class="cast-detail__summary">
                <div><span>売上</span><strong>{{ formatYen(selectedCastDetail.totals.sales) }}</strong></div>
                <div><span>件数</span><strong>{{ selectedCastDetail.totals.orders }}件</strong></div>
                <div><span>報酬見込み</span><strong class="text-primary">{{ formatYen(selectedCastDetail.totals.estimated_pay) }}</strong></div>
                <div><span>店舗配分見込み</span><strong>{{ formatYen(selectedCastDetail.totals.store_allocation_estimate) }}</strong></div>
              </div>

              <div class="cast-detail__title"><i class="ti ti-receipt"></i> 予約ごとの明細</div>
              <div v-if="selectedCastDetail.orders.length" class="table-responsive cast-detail__orders">
                <table class="table table-sm align-middle mb-0">
                  <thead>
                    <tr>
                      <th>日時</th>
                      <th>お客様</th>
                      <th>ルーム</th>
                      <th>コース・追加内容</th>
                      <th>決済</th>
                      <th class="text-end">売上</th>
                      <th class="text-end">報酬</th>
                      <th class="text-end">店舗配分</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="order in selectedCastDetail.orders" :key="order.order_id">
                      <td class="text-nowrap">
                        <strong>{{ order.date }}</strong>
                        <small>{{ order.start_time }}〜{{ order.end_time }}</small>
                      </td>
                      <td>{{ order.customer_name }}</td>
                      <td>{{ order.room_name }}</td>
                      <td class="cast-detail__items">
                        <strong>{{ order.course_name }}</strong>
                        <span v-if="order.option_names.length">OP：{{ order.option_names.join('・') }}</span>
                        <span v-if="order.extension_name">延長：{{ order.extension_name }}</span>
                        <span v-if="order.nomination_fee_name">指名：{{ order.nomination_fee_name }}</span>
                        <span v-if="order.discount_name" class="text-danger">割引：{{ order.discount_name }} -{{ formatYen(order.discount_amount) }}</span>
                      </td>
                      <td>
                        <span class="payment-chip">{{ order.payment_method_label }}</span>
                        <small v-if="order.customer_payment_surcharge">カード手数料 {{ formatYen(order.customer_payment_surcharge) }}</small>
                      </td>
                      <td class="text-end fw-bold">{{ formatYen(order.sales) }}</td>
                      <td class="text-end text-primary fw-bold">{{ formatYen(order.estimated_pay) }}</td>
                      <td class="text-end fw-bold">{{ formatYen(order.store_allocation_estimate) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else class="cast-detail__empty">この期間の明細はありません</div>

              <div class="cast-detail__title mt-4"><i class="ti ti-chart-pie"></i> 売上の内訳</div>
              <div class="cast-detail__breakdowns">
                <div v-for="group in [
                  {key:'courses', label:'コース'},
                  {key:'options', label:'オプション'},
                  {key:'extensions', label:'延長'},
                  {key:'nominations', label:'指名'},
                  {key:'discounts', label:'割引'},
                ]" :key="group.key" class="breakdown-card">
                  <h4>{{ group.label }}</h4>
                  <div v-if="selectedCastDetail.breakdowns[group.key].length">
                    <div v-for="item in selectedCastDetail.breakdowns[group.key]" :key="item.name" class="breakdown-row">
                      <span>{{ item.name }} <small>{{ item.count }}件</small></span>
                      <strong>{{ formatYen(item.amount) }}</strong>
                    </div>
                  </div>
                  <p v-else>該当なし</p>
                </div>
                <div class="breakdown-card">
                  <h4>媒体</h4>
                  <div v-if="selectedCastDetail.breakdowns.media.length">
                    <div v-for="item in selectedCastDetail.breakdowns.media" :key="item.name" class="breakdown-row">
                      <span>{{ item.name }} <small>{{ item.count }}件</small></span>
                      <strong>{{ formatYen(item.sales) }}</strong>
                    </div>
                  </div>
                  <p v-else>該当なし</p>
                </div>
              </div>
              <p class="cast-detail__note">
                ※ 報酬・店舗配分は現在のバック率による見込みです。調整金・雑費・ポイント・現金の受け渡しは含みません。
              </p>
            </section>

            <!-- 部屋別売上 -->
            <div class="fw-bold small mb-1"><i class="ti ti-door"></i> 部屋別売上</div>
            <div v-if="data.by_room && data.by_room.length" class="table-responsive mb-4">
              <table class="table table-sm table-bordered mb-0">
                <thead>
                  <tr>
                    <th>部屋</th>
                    <th class="text-end">件数</th>
                    <th class="text-end">売上</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in data.by_room" :key="r.room_id">
                    <td>{{ r.room_name }}</td>
                    <td class="text-end">{{ r.orders }}</td>
                    <td class="text-end">{{ formatYen(r.sales) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-muted small mb-4">期間内の部屋別売上はありません</div>

            <!-- エリア別売上 -->
            <section class="area-sales mb-4" aria-labelledby="area-sales-title">
              <header class="area-sales__header">
                <div class="area-sales__heading">
                  <span class="area-sales__icon" aria-hidden="true"><i class="ti ti-map-pin"></i></span>
                  <div>
                    <h3 id="area-sales-title">エリア別売上</h3>
                    <p>エリアごとの売上と内訳</p>
                  </div>
                </div>
                <div class="area-sales__total">
                  <span>合計売上</span>
                  <div><strong>{{ formatYen(data.total_sales) }}</strong><span>{{ data.total_orders }}本</span></div>
                </div>
              </header>
            <template v-if="data.by_area && data.by_area.length">
            <div class="area-sales__desktop table-responsive">
              <table class="table mb-0 area-sales-table">
                <caption class="visually-hidden">エリア別の売上と内訳。金額の単位は円です。</caption>
                <thead>
                  <tr>
                    <th scope="col">エリア</th>
                    <th scope="col" class="text-end">本数</th>
                    <th scope="col" class="text-end area-sales-table__sales">売上</th>
                    <th v-for="column in areaBreakdownColumns" :key="column.key" scope="col" class="text-end">{{ column.label }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="a in data.by_area" :key="a.area_id ?? 'unassigned'">
                    <th scope="row"><span class="area-sales__name" :class="{'area-sales__name--unassigned': a.area_id == null}">{{ a.area_name }}</span></th>
                    <td class="text-end">{{ a.orders }}</td>
                    <td class="text-end area-sales-table__sales">{{ formatYen(a.sales) }}</td>
                    <td v-for="column in areaBreakdownColumns" :key="column.key" class="text-end">{{ formatYen(a[column.key]) }}</td>
                  </tr>
                </tbody>
                <tfoot>
                  <tr class="fw-bold">
                    <th scope="row">合計<span class="area-sales-table__hint">未設定を含む</span></th>
                    <td class="text-end">{{ data.total_orders }}</td>
                    <td class="text-end area-sales-table__sales">{{ formatYen(data.total_sales) }}</td>
                    <td v-for="column in areaBreakdownColumns" :key="column.key" class="text-end">{{ formatYen(data[column.key]) }}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <div class="area-sales__mobile">
              <article v-for="a in data.by_area" :key="a.area_id ?? 'unassigned'" class="area-sales-card">
                <header class="area-sales-card__header">
                  <div>
                    <h4 class="area-sales__name" :class="{'area-sales__name--unassigned': a.area_id == null}">{{ a.area_name }}</h4>
                    <span class="area-sales-card__count">完了 {{ a.orders }}本</span>
                  </div>
                  <strong class="area-sales-card__amount">{{ formatYen(a.sales) }}</strong>
                </header>
                <details class="area-sales-card__details">
                  <summary>内訳を見る<i class="ti ti-chevron-down" aria-hidden="true"></i></summary>
                  <dl>
                    <div v-for="column in areaBreakdownColumns" :key="column.key">
                      <dt>{{ column.label }}</dt><dd>{{ formatYen(a[column.key]) }}</dd>
                    </div>
                  </dl>
                </details>
              </article>
            </div>
            </template>
            <p v-else class="area-sales__empty">期間内のエリア別売上はありません</p>
            <details class="area-sales__note">
              <summary><i class="ti ti-info-circle" aria-hidden="true"></i> 集計について</summary>
              <p>会計完了時のルームのエリアで集計します。ルームの所属変更で過去の集計先は変わりません。記録のない過去分やエリア未指定分は「未設定」に含みます。再集計は登録済みデータを読み直し、過去のエリアを書き換えません。</p>
            </details>
            </section>

            <!-- 決済方法別売上 -->
            <div class="fw-bold small mb-1"><i class="ti ti-credit-card"></i> 決済方法別売上</div>
            <div v-if="data.by_payment_method && data.by_payment_method.length" class="table-responsive">
              <table class="table table-sm table-bordered mb-0 payment-sales-table">
                <thead>
                  <tr>
                    <th>決済方法</th>
                    <th class="text-end">件数</th>
                    <th class="text-end">売上</th>
                    <th class="text-end">カード加算<span class="text-muted">(お客様負担)</span></th>
                    <th class="text-end">お客様決済額</th>
                    <th class="text-end">店舗側手数料率<span class="text-muted">(参考)</span></th>
                    <th class="text-end">店舗側手数料<span class="text-muted">(参考)</span></th>
                    <th class="text-end">手数料差引後<span class="text-muted">(参考)</span></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in data.by_payment_method" :key="p.payment_method">
                    <td>{{ p.payment_method_label }}</td>
                    <td class="text-end">{{ p.orders }}</td>
                    <td class="text-end">{{ formatYen(p.sales) }}</td>
                    <td class="text-end text-success">+{{ formatYen(p.customer_payment_surcharge) }}</td>
                    <td class="text-end">{{ formatYen(p.customer_payment_total) }}</td>
                    <td class="text-end">{{ p.fee_rate }}%</td>
                    <td class="text-end text-danger">-{{ formatYen(p.fee_estimate) }}</td>
                    <td class="text-end">{{ formatYen(p.net_sales_after_fee) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-muted small">期間内の決済方法別売上はありません</div>
          </template>
        </div>
      </div>

      <div class="text-muted small">
        ※ 給与見込みはコース・オプションのバック率で計算し、指名料の全額バックが有効な店舗では指名料も含みます。延長料金のバック、決済手数料、調整金、ポイント、現金預かり分は含みません。確定給与ではありません。
      </div>
    </template>
  </LayoutOperator>
</template>

<style scoped>
.payment-sales-table { white-space: nowrap; }
.area-sales {
  overflow: hidden;
  border: 1px solid #dce9e5;
  border-radius: 16px;
  background: #fff;
}
.area-sales__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  padding: 22px 24px;
  background: #f1f8f6;
  border-bottom: 1px solid #e1ece8;
}
.area-sales__heading { display: flex; align-items: center; gap: 12px; }
.area-sales__icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 13px;
  background: #dcefe9;
  color: #317f70;
  font-size: 22px;
}
.area-sales__heading h3 { margin: 0; color: #284d43; font-size: 1rem; font-weight: 700; }
.area-sales__heading p { margin: 5px 0 0; color: #617c73; font-size: .74rem; }
.area-sales__total { text-align: right; color: #617c73; font-size: .72rem; }
.area-sales__total > div { display: flex; align-items: baseline; justify-content: flex-end; gap: 12px; margin-top: 3px; }
.area-sales__total strong { color: #235e50; font-size: 1.6rem; line-height: 1.2; font-weight: 700; letter-spacing: -.03em; }
.area-sales__total > div > span { color: #486b5f; font-size: .8rem; white-space: nowrap; }
.area-sales-table { min-width: 850px; white-space: nowrap; }
.area-sales-table > :not(caption) > * > * { padding: 15px 16px; border-bottom-color: #edf1ef; color: #41574f; background: transparent; box-shadow: none; font-size: .8rem; }
.area-sales-table thead th { padding-top: 12px; padding-bottom: 12px; background: #fafcfb; color: #5d7468; font-size: .71rem; font-weight: 500; }
.area-sales-table th:first-child { padding-left: 24px; min-width: 150px; }
.area-sales-table td:last-child, .area-sales-table thead th:last-child { padding-right: 24px; }
.area-sales-table tbody tr:nth-child(even) { background: #fcfdfc; }
.area-sales-table tbody tr:hover { background: #f4faf7; }
.area-sales-table tbody .area-sales-table__sales { color: #285f50; font-size: .92rem; font-weight: 700; }
.area-sales__name { color: #36594c; font-weight: 600; }
.area-sales__name--unassigned { color: #63746b; font-weight: 500; }
.area-sales-table tfoot > tr > * { border-top: 1px solid #dce9e2; border-bottom: 0; background: #edf6f1; color: #315a49; font-weight: 700; }
.area-sales-table__hint { display: block; margin-top: 3px; font-size: .65rem; color: #6f8278; font-weight: 400; }
.area-sales__total strong, .area-sales-table td, .area-sales-card__amount, .area-sales-card dd {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}
.area-sales__note { padding: 13px 24px; border-top: 1px solid #e6eeea; color: #6c8176; font-size: .73rem; }
.area-sales__note summary { width: fit-content; cursor: pointer; }
.area-sales__note p { max-width: 76ch; margin: 9px 0 0; line-height: 1.8; }
.area-sales__empty { margin: 0; padding: 28px 24px; color: #75827a; font-size: .85rem; }
.area-sales__mobile { display: none; }
@media (max-width: 767.98px) {
  .area-sales__desktop { display: none; }
  .area-sales__mobile { display: block; padding: 0 16px; }
  .area-sales__header { padding: 20px 18px; gap: 18px; }
  .area-sales__icon { width: 36px; height: 36px; border-radius: 11px; font-size: 20px; }
  .area-sales__heading h3 { font-size: .95rem; }
  .area-sales__total { width: 100%; text-align: left; padding-top: 16px; border-top: 1px solid #dce9e1; }
  .area-sales__total > div { justify-content: flex-start; gap: 14px; }
  .area-sales__total strong { font-size: 1.85rem; }
  .area-sales-card { padding: 20px 2px 0; border-bottom: 1px solid #e5ede7; }
  .area-sales-card:last-child { border-bottom: 0; }
  .area-sales-card__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .area-sales-card h4 { margin: 0 0 5px; max-width: 16ch; overflow-wrap: anywhere; font-size: .9rem; }
  .area-sales-card__count { color: #66786b; font-size: .71rem; }
  .area-sales-card__amount { flex-shrink: 0; color: #285e4f; font-size: 1.22rem; letter-spacing: -.025em; }
  .area-sales-card__details { padding: 14px 0 16px; }
  .area-sales-card__details summary { display: flex; align-items: center; justify-content: space-between; color: #5b7c6a; font-size: .72rem; cursor: pointer; list-style: none; }
  .area-sales-card__details summary::-webkit-details-marker { display: none; }
  .area-sales-card__details[open] summary i { transform: rotate(180deg); }
  .area-sales-card dl { margin: 12px 0 0; padding: 12px 14px; border-radius: 10px; background: #f6f9f7; }
  .area-sales-card dl > div { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; padding: 5px 0; }
  .area-sales-card dt { color: #65786b; font-size: .73rem; font-weight: 400; }
  .area-sales-card dd { margin: 0; color: #3f5a49; font-size: .83rem; font-weight: 500; }
  .area-sales__note { padding: 14px 18px; }
}
.sales-range-buttons .btn {
  min-width: 62px;
}

.selected-sales-date {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 12px;
  border-radius: 9px;
  background: #eef7f4;
  color: #315f55;
  font-size: .85rem;
}

.cast-detail-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: 92px;
  border: 1px solid #e1e9e6;
  border-radius: 12px;
  color: #62736e;
  font-size: .85rem;
}

.cast-detail {
  overflow: hidden;
  border: 1px solid #d9e6e2;
  border-radius: 15px;
  background: #fff;
  box-shadow: 0 8px 26px rgba(29, 65, 56, .07);
}

.cast-detail__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px 17px;
  background: linear-gradient(135deg, #edf8f4 0%, #f7fbfa 100%);
  border-bottom: 1px solid #dce9e5;
}

.cast-detail__eyebrow {
  display: block;
  margin-bottom: 3px;
  color: #21846e;
  font-size: .7rem;
  font-weight: 700;
}

.cast-detail__header h3 {
  margin: 0;
  color: #203b35;
  font-size: 1.15rem;
  font-weight: 700;
}

.cast-detail__header p {
  margin: 4px 0 0;
  color: #71817c;
  font-size: .76rem;
}

.cast-detail__summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  padding: 18px 22px;
}

.cast-detail__summary > div {
  padding: 13px 14px;
  border: 1px solid #e2e9e7;
  border-radius: 11px;
  background: #fff;
}

.cast-detail__summary span,
.cast-detail__summary strong {
  display: block;
}

.cast-detail__summary span {
  margin-bottom: 4px;
  color: #71817c;
  font-size: .72rem;
}

.cast-detail__summary strong {
  color: #253d37;
  font-size: 1.08rem;
}

.cast-detail__title {
  padding: 0 22px 8px;
  color: #365a51;
  font-size: .84rem;
  font-weight: 700;
}

.cast-detail__orders {
  margin: 0 22px;
  border: 1px solid #e0e7e5;
  border-radius: 10px;
}

.cast-detail__orders th {
  padding: 9px 10px;
  background: #f4f7f6;
  color: #63736f;
  font-size: .7rem;
  white-space: nowrap;
}

.cast-detail__orders td {
  padding: 10px;
  font-size: .78rem;
  vertical-align: top;
}

.cast-detail__orders td small,
.cast-detail__items span {
  display: block;
  margin-top: 2px;
  color: #71817c;
  font-size: .68rem;
}

.payment-chip {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eaf5f2;
  color: #267563;
  font-size: .7rem;
  font-weight: 700;
}

.cast-detail__empty {
  margin: 0 22px;
  padding: 30px 15px;
  border: 1px dashed #dce5e2;
  border-radius: 10px;
  color: #7b8985;
  text-align: center;
  font-size: .82rem;
}

.cast-detail__breakdowns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 0 22px;
}

.breakdown-card {
  padding: 13px 14px;
  border: 1px solid #e1e8e6;
  border-radius: 10px;
  background: #fbfcfc;
}

.breakdown-card h4 {
  margin: 0 0 9px;
  color: #385950;
  font-size: .78rem;
  font-weight: 700;
}

.breakdown-card p {
  margin: 0;
  color: #8a9692;
  font-size: .72rem;
}

.breakdown-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 0;
  border-top: 1px solid #edf1f0;
  font-size: .73rem;
}

.breakdown-row:first-child {
  border-top: 0;
  padding-top: 0;
}

.breakdown-row span {
  min-width: 0;
}

.breakdown-row small {
  color: #899591;
}

.breakdown-row strong {
  flex-shrink: 0;
}

.cast-detail__note {
  margin: 15px 22px 20px;
  color: #75847f;
  font-size: .7rem;
}

@media (max-width: 767px) {
  .sales-range-buttons {
    display: grid !important;
    grid-template-columns: repeat(3, 1fr);
  }

  .sales-range-buttons .btn {
    min-width: 0;
  }

  .cast-detail__header {
    padding: 17px 15px 14px;
  }

  .cast-detail__summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: 14px 15px;
  }

  .cast-detail__summary > div {
    padding: 11px;
  }

  .cast-detail__title {
    padding: 0 15px 8px;
  }

  .cast-detail__orders,
  .cast-detail__empty {
    margin: 0 15px;
  }

  .cast-detail__orders table {
    min-width: 940px;
  }

  .cast-detail__breakdowns {
    grid-template-columns: 1fr;
    padding: 0 15px;
  }

  .cast-detail__note {
    margin: 14px 15px 17px;
  }
}
</style>
