<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import TimelineGrid from '../../components/TimelineGrid.vue'
import { api } from '../../api.js'

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

// 予約作成モーダル
const showCreateModal = ref(false)
const createForm = ref({ cast: '', customer: '', course: '', startTime: '', memo: '', options: [], medium: '' })
const createError = ref('')
const creating = ref(false)
const customers = ref([])
const allCourses = ref([])
const allOptions = ref([])
const allMedia = ref([])
const mastersLoaded = ref(false)
const customerSearch = ref('')

const filteredCustomers = computed(() => {
  const q = customerSearch.value.trim().toLowerCase()
  if (!q) return customers.value
  return customers.value.filter(c =>
    (c.phone || '').includes(q) ||
    (c.display_name || '').toLowerCase().includes(q)
  )
})

const selectedCustomerWarning = computed(() => {
  if (!createForm.value.customer) return ''
  const c = customers.value.find(cu => cu.id === Number(createForm.value.customer))
  if (!c) return ''
  const warnings = []
  if (c.flag === 'BAN') warnings.push('この顧客は出禁です')
  else if (c.flag === 'ATTENTION') warnings.push('この顧客は要注意です')
  if (c.duplicate_count) warnings.push(`重複候補が${c.duplicate_count}件あります`)
  return warnings.join(' / ')
})

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

async function onCreateOrder(cast) {
  createError.value = ''
  createForm.value = { cast: cast.id, customer: '', course: '', startTime: '', memo: '', options: [], medium: '' }
  showCreateModal.value = true

  if (!mastersLoaded.value) {
    try {
      const [custs, courses, opts, mds] = await Promise.all([
        api.getCustomers(),
        api.getCourses(),
        api.getOptions(),
        api.getMedia(),
      ])
      customers.value = Array.isArray(custs) ? custs : []
      allCourses.value = Array.isArray(courses) ? courses : []
      allOptions.value = Array.isArray(opts) ? opts : []
      allMedia.value = Array.isArray(mds) ? mds : []
      mastersLoaded.value = true
    } catch (e) {
      createError.value = e.message
    }
  }
}

function toggleCreateOption(optId) {
  const idx = createForm.value.options.indexOf(optId)
  if (idx >= 0) createForm.value.options.splice(idx, 1)
  else createForm.value.options.push(optId)
}

async function submitCreate() {
  createError.value = ''
  if (!createForm.value.customer || !createForm.value.course || !createForm.value.startTime) {
    createError.value = '顧客・コース・開始時間は必須です'
    return
  }
  creating.value = true
  try {
    const startDt = `${selectedDate.value}T${createForm.value.startTime}:00`
    const body = {
      customer: Number(createForm.value.customer),
      cast: Number(createForm.value.cast),
      course: Number(createForm.value.course),
      start: startDt,
      memo: createForm.value.memo,
    }
    if (createForm.value.options.length) body.options = createForm.value.options
    if (createForm.value.medium) body.medium = Number(createForm.value.medium)

    const order = await api.createOrder(body)
    showCreateModal.value = false
    highlightId.value = order.id
    await fetchSchedule()
  } catch (e) {
    createError.value = e.message
  } finally {
    creating.value = false
  }
}

function castNameById(id) {
  const c = casts.value.find(c => c.id === id)
  return c ? c.name : ''
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
  mastersLoaded.value = false
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

    <!-- 予約作成モーダル -->
    <div v-if="showCreateModal" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showCreateModal = false">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="ti ti-plus me-1"></i>予約作成 — {{ castNameById(createForm.cast) }} ({{ selectedDate }})
            </h5>
            <button type="button" class="btn-close" @click="showCreateModal = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="createError" class="alert alert-danger py-2 px-3 mb-3" style="font-size: 0.875rem;">{{ createError }}</div>

            <div class="mb-3">
              <label class="form-label">顧客 <span class="text-danger">*</span></label>
              <input
                v-model="customerSearch"
                type="text"
                class="form-control form-control-sm mb-1"
                placeholder="電話番号 or 名前で検索..."
              />
              <select v-model="createForm.customer" class="form-select">
                <option value="" disabled>選択してください</option>
                <option v-for="c in filteredCustomers" :key="c.id" :value="c.id">
                  {{ c.display_name || c.phone }} ({{ c.phone }}){{ c.flag === 'BAN' ? ' ★出禁' : c.flag === 'ATTENTION' ? ' ★注意' : '' }}{{ c.duplicate_count ? ` [重複${c.duplicate_count}件]` : '' }}
                </option>
              </select>
              <div v-if="selectedCustomerWarning" class="alert alert-warning py-1 px-2 mt-1 mb-0" style="font-size: 0.8rem;">
                <i class="ti ti-alert-triangle"></i> {{ selectedCustomerWarning }}
              </div>
            </div>
            <div class="mb-3">
              <label class="form-label">コース <span class="text-danger">*</span></label>
              <select v-model="createForm.course" class="form-select">
                <option value="" disabled>選択してください</option>
                <option v-for="c in allCourses" :key="c.id" :value="c.id">{{ c.name }} ({{ c.duration }}分 / ¥{{ c.price.toLocaleString() }})</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">開始時間 <span class="text-danger">*</span></label>
              <input v-model="createForm.startTime" type="time" class="form-control" />
            </div>
            <div v-if="allOptions.length" class="mb-3">
              <label class="form-label">オプション</label>
              <div class="d-flex flex-wrap gap-1">
                <button
                  v-for="opt in allOptions" :key="opt.id"
                  type="button"
                  class="btn btn-sm"
                  :class="createForm.options.includes(opt.id) ? 'btn-primary' : 'btn-outline-secondary'"
                  @click="toggleCreateOption(opt.id)"
                >{{ opt.name }} (+¥{{ opt.price.toLocaleString() }})</button>
              </div>
            </div>
            <div v-if="allMedia.length" class="mb-3">
              <label class="form-label">媒体</label>
              <select v-model="createForm.medium" class="form-select">
                <option value="">なし</option>
                <option v-for="m in allMedia" :key="m.id" :value="m.id">{{ m.name }}</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">メモ</label>
              <textarea v-model="createForm.memo" class="form-control" rows="2"></textarea>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCreateModal = false">キャンセル</button>
            <button class="btn btn-primary" :disabled="creating" @click="submitCreate">
              {{ creating ? '作成中...' : '予約作成' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>
