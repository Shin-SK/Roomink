<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const router = useRouter()
const kpi = ref({ estimated_sales: 0, requested: 0, confirmed: 0, total_orders: 0 })
const requestedOrders = ref([])
const allOrders = ref([])
const loading = ref(true)
const activeTab = ref('mikakunin')

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
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
})

function goOrder(id) {
  router.push(`/op/orders/${id}`)
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}
</script>

<template>
  <LayoutOperator>
    <template #title>ホーム</template>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <template v-else>
      <!-- 通知エリア -->
      <div class="wrap bg-white overflow-y-auto mb-4" style="max-height: 20vh;">
        <ul class="d-flex flex-column gap-2">
          <li v-if="requestedOrders.length">
            <a href="#" @click.prevent="activeTab = 'kakunin'" class="d-flex align-items-center gap-2 border-bottom w-100 pb-2 text-decoration-none">
              <div class="badge badge-pending">承認待ち</div><small>{{ requestedOrders.length }}件</small>
            </a>
          </li>
        </ul>
      </div>

      <!-- 統計カード -->
      <div class="row g-2 mb-5">
        <div class="col-12 col-sm-6 col-xl-3">
          <div class="card">
            <div class="card-body">
              <div class="wrap d-flex align-items-center gap-3">
                <div class="stat-label m-0">
                  <i class="ti ti-currency-yen"></i> 本日売上（予定）</div>
              </div>
              <div class="d-flex align-items-center justify-content-between">
                <div class="stat-value">{{ formatYen(kpi.estimated_sales) }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="col-6 col-sm-6 col-xl-3">
          <div class="card">
            <div class="card-body">
              <div class="stat-label"><i class="ti ti-calendar-event"></i> 本日本数</div>
              <div class="stat-value">{{ kpi.total_orders }}本</div>
              <div class="stat-change">{{ kpi.confirmed }} 承認済 / {{ kpi.requested }} 申請中</div>
            </div>
          </div>
        </div>
        <div class="col-6 col-sm-6 col-xl-3">
          <div class="card">
            <div class="card-body">
              <div class="stat-label"><i class="ti ti-users"></i> 出勤キャスト</div>
              <div class="stat-value">—</div>
              <div class="stat-change">
                <router-link to="/op/schedule">スケジュールで確認</router-link>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- タブ -->
      <nav class="dashboard-tabs mb-3">
        <div class="wrap">
          <button
            :class="{ active: activeTab === 'mikakunin' }"
            @click="activeTab = 'mikakunin'"
          >未確認</button>
        </div>
        <div class="wrap">
          <button
            :class="{ active: activeTab === 'kakunin' }"
            @click="activeTab = 'kakunin'"
          >承認待ち</button>
        </div>
      </nav>

      <!-- 未確認アラート -->
      <div v-show="activeTab === 'mikakunin'" class="card border-0 mb-4">
        <div class="card-header bg-attention">
          <i class="ti ti-alert-triangle text-dark"></i> 未確認アラート
        </div>
        <div class="card-body p-0">
          <ul class="list-group list-group-flush">
            <li
              v-for="order in requestedOrders.slice(0, 3)"
              :key="'alert-' + order.id"
              class="list-group-item"
            >
              <div class="d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center gap-2">
                  <span class="badge badge-attention">申請中</span>
                  <strong>{{ order.customer_label }}</strong>
                  <span class="text-muted small">{{ formatTime(order.start) }}</span>
                </div>
                <a href="#" class="btn btn-sm btn-attention" @click.prevent="goOrder(order.id)">
                  <i class="ti ti-check"></i> 詳細
                </a>
              </div>
            </li>
            <li v-if="requestedOrders.length === 0" class="list-group-item text-muted text-center py-3">
              未確認の予約はありません
            </li>
          </ul>
        </div>
      </div>

      <!-- 承認待ち -->
      <div v-show="activeTab === 'kakunin'" class="card border-0 mb-4">
        <div class="card-header">
          <i class="ti ti-inbox"></i> 承認待ち予約申請
        </div>
        <div class="card-body p-0">
          <ul class="list-group list-group-flush">
            <li
              v-for="order in requestedOrders"
              :key="'req-' + order.id"
              class="list-group-item"
            >
              <div class="d-flex justify-content-between align-items-start">
                <div class="flex-grow-1">
                  <div class="list-header">
                    <div class="d-flex align-items-center gap-2">
                      <h5 class="mb-0 fw-bold">{{ order.customer_label }}</h5>
                      <span class="badge badge-pending">申請中</span>
                    </div>
                  </div>
                  <div class="list-body">
                    <div class="d-flex align-items-center gap-2">
                      <i class="ti ti-calendar"></i>{{ formatTime(order.start) }}–{{ formatTime(order.end) }}
                    </div>
                    <div class="d-flex align-items-center gap-2">
                      <i class="ti ti-category-2"></i>{{ order.course_name }}
                    </div>
                  </div>
                  <div class="list-footer mt-3">
                    <div class="row g-2">
                      <div class="col-4">
                        <a
                          href="#"
                          class="btn btn-sm btn-outline-dark w-100"
                          @click.prevent="goOrder(order.id)"
                        >詳細</a>
                      </div>
                      <div class="col-4">
                        <router-link
                          to="/op/schedule"
                          class="btn btn-sm btn-primary w-100"
                        >スケジュール</router-link>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </li>
            <li v-if="requestedOrders.length === 0" class="list-group-item text-muted text-center py-3">
              承認待ちの予約はありません
            </li>
          </ul>
        </div>
      </div>
    </template>
  </LayoutOperator>
</template>
