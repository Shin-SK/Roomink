<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

const isManager = computed(() => getAuthRole() === 'manager')

const casts = ref([])
const rooms = ref([])

const range = ref('today')
const dateFrom = ref('')
const dateTo = ref('')
const filterCast = ref('')
const filterRoom = ref('')
const filterPaymentMethod = ref('')

const data = ref(null)
const loading = ref(false)
const error = ref('')

function buildParams() {
  let params
  if (range.value === 'custom') {
    if (!dateFrom.value || !dateTo.value) return null
    params = `date_from=${dateFrom.value}&date_to=${dateTo.value}`
  } else {
    params = `range=${range.value}`
  }
  if (filterCast.value) params += `&cast=${filterCast.value}`
  if (filterRoom.value) params += `&room=${filterRoom.value}`
  if (filterPaymentMethod.value) params += `&payment_method=${filterPaymentMethod.value}`
  return params
}

async function loadMasters() {
  const [castData, roomData] = await Promise.all([api.getCasts(), api.getRooms()])
  casts.value = Array.isArray(castData) ? castData : []
  rooms.value = Array.isArray(roomData) ? roomData : []
}

async function fetchDashboard() {
  const params = buildParams()
  if (!params) return
  error.value = ''
  loading.value = true
  try {
    data.value = await api.getSalesDashboard(params)
  } catch (e) {
    error.value = e.message || '売上集計の取得に失敗しました'
    data.value = null
  } finally {
    loading.value = false
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

watch([range, dateFrom, dateTo, filterCast, filterRoom, filterPaymentMethod], () => {
  if (isManager.value) fetchDashboard()
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
          <button class="btn btn-sm btn-outline-dark" @click="exportCsv">
            <i class="ti ti-download"></i> CSV
          </button>
        </div>
        <div class="card-body">
          <!-- 期間切替 -->
          <div class="d-flex flex-wrap gap-2 mb-2">
            <button
              v-for="r in [{key:'today',label:'今日'},{key:'week',label:'今週'},{key:'month',label:'今月'},{key:'custom',label:'期間指定'}]"
              :key="r.key"
              class="btn btn-sm"
              :class="range === r.key ? 'btn-dark' : 'btn-outline-dark'"
              @click="range = r.key"
            >{{ r.label }}</button>
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
            <div class="spinner-border spinner-border-sm text-primary"></div>
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
                  <div class="stat-label">決済手数料見込み<span class="text-muted">(参考値)</span></div>
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
              ※ 決済手数料は参考値です（現金/PayPay/カードの設定手数料率から算出）。確定精算・給与確定・日給一覧には反映されません。
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
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="c in data.by_cast" :key="c.cast_id">
                    <td>{{ c.cast_name }}</td>
                    <td class="text-end">{{ c.orders }}</td>
                    <td class="text-end">{{ formatYen(c.sales) }}</td>
                    <td class="text-end">{{ formatYen(c.course_sales) }}</td>
                    <td class="text-end">{{ formatYen(c.options_sales) }}</td>
                    <td class="text-end">{{ c.course_back_rate }}%<span v-if="c.option_fullback_enabled">・OP全額</span></td>
                    <td class="text-end fw-bold text-primary">{{ formatYen(c.estimated_pay) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-muted small mb-4">期間内のキャスト別売上はありません</div>

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
            <div class="fw-bold small mb-1"><i class="ti ti-map-pin"></i> エリア別売上</div>
            <div v-if="data.by_area && data.by_area.length" class="table-responsive mb-4">
              <table class="table table-sm table-bordered mb-0">
                <thead>
                  <tr>
                    <th>エリア</th>
                    <th class="text-end">DONE件数</th>
                    <th class="text-end">売上</th>
                    <th class="text-end">コース売上</th>
                    <th class="text-end">オプション売上</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="a in data.by_area" :key="a.area_name">
                    <td>{{ a.area_name }}</td>
                    <td class="text-end">{{ a.orders }}</td>
                    <td class="text-end">{{ formatYen(a.sales) }}</td>
                    <td class="text-end">{{ formatYen(a.course_sales) }}</td>
                    <td class="text-end">{{ formatYen(a.options_sales) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-muted small mb-4">期間内のエリア別売上はありません</div>

            <!-- 決済方法別売上 -->
            <div class="fw-bold small mb-1"><i class="ti ti-credit-card"></i> 決済方法別売上</div>
            <div v-if="data.by_payment_method && data.by_payment_method.length" class="table-responsive">
              <table class="table table-sm table-bordered mb-0">
                <thead>
                  <tr>
                    <th>決済方法</th>
                    <th class="text-end">件数</th>
                    <th class="text-end">売上</th>
                    <th class="text-end">手数料率<span class="text-muted">(参考)</span></th>
                    <th class="text-end">手数料見込み<span class="text-muted">(参考)</span></th>
                    <th class="text-end">手数料差引後<span class="text-muted">(参考)</span></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in data.by_payment_method" :key="p.payment_method">
                    <td>{{ p.payment_method_label }}</td>
                    <td class="text-end">{{ p.orders }}</td>
                    <td class="text-end">{{ formatYen(p.sales) }}</td>
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
        ※ 給与見込みはPhase 2-C / 3-Aと同じ計算方針（コースバック + オプション全額バック）です。延長料金・指名料のバック、決済手数料、調整金、ポイント、現金預かり分は含みません。確定給与ではありません。
      </div>
    </template>
  </LayoutOperator>
</template>
