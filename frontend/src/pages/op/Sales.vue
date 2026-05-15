<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

const isManager = computed(() => getAuthRole() === 'manager')

const salesRange = ref('today')
const salesDateFrom = ref('')
const salesDateTo = ref('')
const sales = ref(null)
const salesLoading = ref(false)
const salesError = ref('')

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
  salesError.value = ''
  salesLoading.value = true
  try {
    sales.value = await api.getSalesSummary(params)
  } catch (e) {
    salesError.value = e.message || '売上情報の取得に失敗しました'
    sales.value = null
  } finally {
    salesLoading.value = false
  }
}

function exportCsv() {
  const params = buildSalesParams()
  if (!params) return
  window.open(api.getSalesExportUrl(params), '_blank')
}

function formatYen(n) {
  return `¥${Number(n || 0).toLocaleString()}`
}

watch([salesRange, salesDateFrom, salesDateTo], () => {
  if (isManager.value) fetchSales()
})

onMounted(() => {
  if (isManager.value) fetchSales()
})
</script>

<template>
  <LayoutOperator>
    <template #title>売上確認</template>

    <div v-if="!isManager" class="alert alert-warning mt-3">
      <i class="ti ti-lock me-1"></i>この画面はマネージャー権限が必要です。
    </div>

    <template v-else>
      <div class="card border-0 mb-4">
        <div class="card-header d-flex align-items-center justify-content-between">
          <div><i class="ti ti-chart-bar"></i> 売上確認</div>
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

          <div v-if="salesError" class="alert alert-danger py-2 px-3 mb-3" style="font-size: 0.875rem;">
            {{ salesError }}
          </div>

          <div v-if="salesLoading" class="text-center py-3">
            <div class="spinner-border spinner-border-sm text-primary"></div>
          </div>

          <template v-else-if="sales">
            <!-- 集計期間表示 -->
            <div class="text-muted small mb-2">
              集計期間: {{ sales.date_from }} 〜 {{ sales.date_to }}
            </div>

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
            <div v-if="sales.by_day && sales.by_day.length" class="table-responsive">
              <table class="table table-sm table-bordered mb-0">
                <thead>
                  <tr>
                    <th>日付</th>
                    <th class="text-end">売上</th>
                    <th class="text-end">件数</th>
                  </tr>
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
            <div v-else class="text-muted small">期間内の売上はありません</div>
          </template>
        </div>
      </div>

      <div class="text-muted small">
        ※ セラピスト別 / 支払方法別 / コース別 / オプション別の内訳は、実機確認後に必要粒度を見ながら追加予定です。
      </div>
    </template>
  </LayoutOperator>
</template>
