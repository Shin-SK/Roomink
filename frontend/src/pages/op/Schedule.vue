<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import TimelineGrid from '../../components/TimelineGrid.vue'
import CustomerInfoCard from '../../components/CustomerInfoCard.vue'
import OrderForm from '../../components/OrderForm.vue'
import { api, normalizePhone } from '../../api.js'

const router = useRouter()
const route = useRoute()
const selectedDate = ref(route.query.date || today())
const highlightId = ref(route.query.highlight ? Number(route.query.highlight) : null)
const casts = ref([])
const orders = ref([])
const kpi = ref({ total_orders: 0, confirmed: 0, requested: 0, estimated_sales: 0 })
const loading = ref(true)
const toolbarOpen = ref(false)
const showLegend = ref(false)
const showPhoneSearch = ref(false)

// 予約作成モーダル
const showCreateModal = ref(false)
const modalCast = ref('')
const modalStartTime = ref('')
const modalCustomerId = ref('')

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
  return new Date().toISOString().slice(0, 10)
}

function tomorrow() {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return d.toISOString().slice(0, 10)
}

async function fetchSchedule() {
  loading.value = true
  try {
    const data = await api.getSchedule(selectedDate.value)
    casts.value = data.casts
    orders.value = data.orders
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

function onBlockClick(order) {
  router.push(`/op/orders/${order.id}`)
}

function openCreateModal({ cast = '', customer = '', startTime = '' } = {}) {
  modalCast.value = cast
  modalCustomerId.value = customer
  modalStartTime.value = startTime || '15:00'
  showCreateModal.value = true
}

function onCreateOrder(payload) {
  // payload: { cast, start_time, room_id, room_name }（タイムライン空セルクリック）
  // または cast 単体（後方互換）
  const cast = payload && payload.cast ? payload.cast : payload
  const startTime = (payload && payload.start_time) || ''
  if (!cast || !cast.id) return
  openCreateModal({ cast: cast.id, startTime })
}

function onOrderCreated({ order }) {
  showCreateModal.value = false
  highlightId.value = order.id
  fetchSchedule()
}

function onOrderCancel() {
  showCreateModal.value = false
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
  fetchSchedule()
})
onMounted(fetchSchedule)
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
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 新規予約 / 番号検索 -->
    <div class="rk-actions mb-2">
      <div class="rk-actions__buttons">
        <router-link to="/op/phone" class="btn btn-sm btn-primary">
          <i class="ti ti-plus me-1"></i>新規予約
        </router-link>
        <button
          type="button"
          class="btn btn-sm"
          :class="showPhoneSearch ? 'btn-secondary' : 'btn-outline-secondary'"
          @click="showPhoneSearch = !showPhoneSearch"
        >
          <i class="ti ti-search me-1"></i>番号検索
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
        :casts="casts"
        :orders="orders"
        @block-click="onBlockClick"
        @create-order="onCreateOrder"
      />
      <div v-if="casts.length === 0" class="position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center" style="pointer-events: none; z-index: 9999;">
        <span class="text-muted bg-white px-3 py-2 rounded shadow-sm text-center" style="max-width: 240px;">この日にシフトが登録されたキャストがいません</span>
      </div>
    </div>

    <!-- 予約作成モーダル（OrderForm 雛形を利用） -->
    <div v-if="showCreateModal" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showCreateModal = false">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="ti ti-plus me-1"></i>予約作成（{{ selectedDate }}）
            </h5>
            <button type="button" class="btn-close" @click="showCreateModal = false"></button>
          </div>
          <div class="modal-body">
            <OrderForm
              :initial-date="selectedDate"
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
</style>
