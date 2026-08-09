<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { api } from '../api.js'

const props = defineProps({
  mode: { type: String, default: 'create' }, // 'create' | 'edit'
  orderId: { type: [Number, String], default: '' },
  initialOrder: { type: Object, default: null },
  initialDate: { type: String, default: '' },
  initialStartTime: { type: String, default: '15:00' },
  initialCast: { type: [Number, String], default: '' },
  initialCustomerId: { type: [Number, String], default: '' },
  initialPhone: { type: String, default: '' },
  embedded: { type: Boolean, default: false },
  autoConfirm: { type: Boolean, default: true },
  cancelLabel: { type: String, default: '' },
  submitLabel: { type: String, default: '' },
  showFlowHint: { type: Boolean, default: true },
})

const emit = defineEmits(['created', 'updated', 'cancel'])

const isEdit = computed(() => props.mode === 'edit')

const customers = ref([])
const casts = ref([])
const courses = ref([])
const options = ref([])
const extensions = ref([])
const media = ref([])
const discounts = ref([])
const loading = ref(true)
const submitting = ref(false)
const errorMsg = ref('')
const phoneHint = ref(props.initialPhone || '')
const shiftCastIds = ref(null) // null=未取得（絞り込みなし）, Set=取得済み

const form = ref({
  customer: props.initialCustomerId || '',
  cast: props.initialCast || '',
  course: '',
  startDate: props.initialDate || new Date().toISOString().slice(0, 10),
  startTime: props.initialStartTime || '15:00',
  start: '', // edit用 datetime-local
  end: '',   // edit用 datetime-local
  options: [],
  extension: '',
  medium: '',
  discount: '',
  memo: '',
  payment_method: 'UNSET',
})

const paymentMethods = [
  { value: 'UNSET', label: '未設定', icon: 'ti-help' },
  { value: 'CASH', label: '現金', icon: 'ti-cash' },
  { value: 'PAYPAY', label: 'PayPay', icon: 'ti-qrcode' },
  { value: 'CARD', label: 'カード', icon: 'ti-credit-card' },
]

const castSearch = ref('')
const customerSearch = ref('')

const normalizedQuery = computed(() =>
  customerSearch.value.replace(/[-\s()]/g, '').trim()
)

const filteredCustomers = computed(() => {
  const q = normalizedQuery.value
  if (!q) return []
  return customers.value.filter(c => {
    const phone = (c.phone || '').replace(/[-\s()]/g, '')
    const name = c.display_name || ''
    return phone.includes(q) || name.includes(customerSearch.value.trim())
  }).slice(0, 20)
})

const selectedCustomer = computed(() =>
  customers.value.find(c => c.id === form.value.customer)
)

const editCustomerLabel = computed(() => {
  if (!isEdit.value || !props.initialOrder) return ''
  return props.initialOrder.customer_label
    || props.initialOrder.customer_name
    || (selectedCustomer.value ? (selectedCustomer.value.display_name || selectedCustomer.value.phone) : '')
})

const hasExactPhoneMatch = computed(() => {
  const q = normalizedQuery.value
  if (!q) return true
  return customers.value.some(c => (c.phone || '').replace(/[-\s()]/g, '') === q)
})

function selectCustomer(c) {
  form.value.customer = c.id
  customerSearch.value = ''
}

function clearCustomer() {
  form.value.customer = ''
}

const filteredCasts = computed(() => {
  const q = castSearch.value.trim()
  let list = casts.value
  if (!isEdit.value && shiftCastIds.value) {
    list = list.filter(c => shiftCastIds.value.has(c.id))
  }
  if (q) list = list.filter(c => c.name.includes(q))
  return list
})

const selectedCastName = computed(() => {
  const c = casts.value.find(c => c.id === form.value.cast)
  return c ? c.name : ''
})

const selectedCourse = computed(() =>
  courses.value.find(c => c.id === Number(form.value.course))
)

const selectedOptions = computed(() =>
  options.value.filter(o => form.value.options.includes(o.id))
)

const selectedExtension = computed(() =>
  extensions.value.find(e => e.id === Number(form.value.extension))
)

const selectedDiscount = computed(() =>
  discounts.value.find(d => d.id === Number(form.value.discount))
)

const subtotalPrice = computed(() => {
  let total = selectedCourse.value ? selectedCourse.value.price : 0
  total += selectedOptions.value.reduce((sum, o) => sum + o.price, 0)
  total += selectedExtension.value ? selectedExtension.value.price : 0
  return total
})

const discountAmount = computed(() => {
  const d = selectedDiscount.value
  if (!d) return 0
  if (d.discount_type === 'percent') return Math.floor(subtotalPrice.value * d.value / 100)
  return d.value
})

const totalPrice = computed(() => Math.max(0, subtotalPrice.value - discountAmount.value))

const isCardPayment = computed(() => form.value.payment_method === 'CARD')
const cardFee = computed(() => isCardPayment.value ? Math.round(totalPrice.value * 0.1) : 0)
const cardTotal = computed(() => totalPrice.value + cardFee.value)

const resolvedSubmitLabel = computed(() => {
  if (props.submitLabel) return props.submitLabel
  return isEdit.value ? '保存' : '予約を確定'
})
const resolvedCancelLabel = computed(() => {
  if (props.cancelLabel) return props.cancelLabel
  return isEdit.value ? '戻る' : 'キャンセル'
})

function toLocalInput(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function applyInitialOrder() {
  const o = props.initialOrder
  if (!o) return
  form.value.customer = o.customer ?? ''
  form.value.cast = o.cast ?? ''
  form.value.course = o.course ?? ''
  form.value.options = Array.isArray(o.option_ids) ? [...o.option_ids] : []
  form.value.medium = o.medium ?? ''
  form.value.discount = o.discount ?? ''
  form.value.memo = o.memo || ''
  form.value.payment_method = o.payment_method || 'UNSET'
  form.value.start = toLocalInput(o.start)
  form.value.end = toLocalInput(o.end)
}

async function loadMasters() {
  loading.value = true
  try {
    const [custData, castData, courseData, optData, extData, mdData, dcData] = await Promise.all([
      api.getCustomers(),
      api.getCasts(),
      api.getCourses(),
      api.getOptions(),
      api.getExtensions(),
      api.getMedia(),
      api.getDiscounts(),
    ])
    customers.value = Array.isArray(custData) ? custData : []
    casts.value = Array.isArray(castData) ? castData : []
    courses.value = Array.isArray(courseData) ? courseData : []
    options.value = Array.isArray(optData) ? optData : []
    extensions.value = (Array.isArray(extData) ? extData : []).filter(e => e.is_active)
    const allMedia = Array.isArray(mdData) ? mdData : []
    media.value = allMedia.filter(m => m.is_active)
    const allDiscounts = Array.isArray(dcData) ? dcData : []
    discounts.value = allDiscounts.filter(d => d.is_active)

    if (isEdit.value) {
      applyInitialOrder()
    } else if (props.initialCustomerId) {
      const match = customers.value.find(c => c.id === Number(props.initialCustomerId))
      if (match) form.value.customer = match.id
    } else if (props.initialPhone) {
      const match = customers.value.find(c => c.phone === props.initialPhone)
      if (match) {
        form.value.customer = match.id
      } else {
        customerSearch.value = props.initialPhone
      }
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function loadShiftCasts(date) {
  if (isEdit.value || !date) return
  try {
    const data = await api.getSchedule(date)
    const list = Array.isArray(data?.casts) ? data.casts : []
    const availableIds = list
      .filter(c => Array.isArray(c.shifts) && c.shifts.some(s => !s.is_absent))
      .map(c => c.id)
    shiftCastIds.value = new Set(availableIds)
    if (form.value.cast && !shiftCastIds.value.has(Number(form.value.cast))) {
      form.value.cast = ''
    }
  } catch (e) {
    shiftCastIds.value = null
  }
}

onMounted(async () => {
  await loadMasters()
  await loadShiftCasts(form.value.startDate)
})

watch(() => form.value.startDate, (val) => {
  if (!isEdit.value) loadShiftCasts(val)
})

watch(() => props.initialPhone, (val) => {
  phoneHint.value = val || ''
  if (!val || form.value.customer) return
  const match = customers.value.find(c => c.phone === val)
  if (match) form.value.customer = match.id
  else customerSearch.value = val
})

watch(() => props.initialOrder, () => {
  if (isEdit.value) applyInitialOrder()
})

function toggleOption(optId) {
  const idx = form.value.options.indexOf(optId)
  if (idx >= 0) {
    form.value.options.splice(idx, 1)
  } else {
    form.value.options.push(optId)
  }
}

async function submit() {
  errorMsg.value = ''
  if (isEdit.value) {
    return submitEdit()
  }
  return submitCreate()
}

async function submitCreate() {
  if (!form.value.customer || !form.value.cast || !form.value.course) {
    errorMsg.value = '顧客・キャスト・コースは必須です'
    return
  }
  if (form.value.payment_method === 'UNSET' && !confirm('支払い方法が未設定です。このまま予約を作成しますか？')) {
    return
  }
  const startDt = `${form.value.startDate}T${form.value.startTime}:00`
  const body = {
    customer: Number(form.value.customer),
    cast: Number(form.value.cast),
    course: Number(form.value.course),
    start: startDt,
    memo: form.value.memo,
  }
  if (form.value.options.length) body.options = form.value.options
  if (form.value.extension) body.extension = Number(form.value.extension)
  if (form.value.medium) body.medium = Number(form.value.medium)
  if (form.value.discount) body.discount = Number(form.value.discount)
  if (form.value.payment_method) body.payment_method = form.value.payment_method

  submitting.value = true
  try {
    const order = await api.createOrder(body)
    if (props.autoConfirm) {
      try {
        await api.confirmOrder(order.id)
      } catch (_) { /* 詳細画面で手動承認できる */ }
    }
    emit('created', { order, startDate: form.value.startDate })
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    submitting.value = false
  }
}

async function submitEdit() {
  if (!form.value.cast || !form.value.course) {
    errorMsg.value = 'キャスト・コースは必須です'
    return
  }
  if (!form.value.start || !form.value.end) {
    errorMsg.value = '開始日時・終了日時は必須です'
    return
  }
  const body = {
    cast: Number(form.value.cast),
    course: Number(form.value.course),
    start: form.value.start,
    end: form.value.end,
    options: form.value.options,
    memo: form.value.memo,
    medium: form.value.medium ? Number(form.value.medium) : null,
    payment_method: form.value.payment_method || 'UNSET',
  }
  submitting.value = true
  try {
    const order = await api.updateOrder(props.orderId, body)
    emit('updated', { order })
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    submitting.value = false
  }
}

function onCancel() {
  emit('cancel')
}

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}
</script>

<template>
  <div class="order-form" :class="{ 'order-form--embedded': embedded, 'order-form--edit': isEdit }">
    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else>
      <div v-if="isEdit" class="d-flex align-items-center mb-3">
        <span class="badge order-form__edit-badge">
          <i class="ti ti-edit me-1"></i>編集中
        </span>
        <span v-if="editCustomerLabel" class="ms-2 text-muted small">
          {{ editCustomerLabel }}
        </span>
      </div>

      <div v-if="!isEdit && showFlowHint" class="alert alert-info">
        <strong>予約フロー</strong><br>
        1. 顧客を選択 → 2. 日時・キャスト・コースを選択 → 3. 予約を作成
      </div>

      <div v-if="!isEdit && phoneHint && !form.customer" class="alert alert-warning d-flex justify-content-between align-items-center">
        <div>
          <i class="ti ti-phone-incoming"></i>
          着信番号 <strong>{{ phoneHint }}</strong> に一致する顧客が見つかりませんでした。
        </div>
        <router-link
          :to="`/op/customers/new?phone=${encodeURIComponent(phoneHint)}&return=${encodeURIComponent('/op/phone?phone=' + phoneHint)}`"
          class="btn btn-sm btn-primary ms-3"
        >
          <i class="ti ti-user-plus"></i> この番号で顧客作成
        </router-link>
      </div>

      <!-- STEP 1: 顧客検索（create時のみ） -->
      <div v-if="!isEdit" class="card">
        <div class="card-header">STEP 1: 顧客検索</div>
        <div class="card-body">
          <div v-if="selectedCustomer" class="selected-customer">
            <div>
              <div class="fw-bold">
                {{ selectedCustomer.display_name || selectedCustomer.phone }}
                <span v-if="selectedCustomer.flag === 'ATTENTION'" class="badge bg-warning text-dark ms-1">要注意</span>
                <span v-if="selectedCustomer.flag === 'BAN'" class="badge bg-danger ms-1">BAN</span>
              </div>
              <div class="text-muted small">{{ selectedCustomer.phone }}</div>
            </div>
            <button type="button" class="btn btn-sm btn-outline-secondary" @click="clearCustomer">
              <i class="ti ti-x"></i> 変更
            </button>
          </div>

          <div v-else>
            <label class="form-label">電話番号 / 名前で検索</label>
            <input
              type="search"
              class="form-control"
              placeholder="例: 09012345678 / 山田"
              v-model="customerSearch"
              autofocus
            >

            <div v-if="customerSearch.trim()" class="customer-results mt-2">
              <button
                v-for="c in filteredCustomers"
                :key="c.id"
                type="button"
                class="customer-result-item"
                @click="selectCustomer(c)"
              >
                <div>
                  <span class="fw-bold">{{ c.display_name || c.phone }}</span>
                  <span v-if="c.flag === 'ATTENTION'" class="badge bg-warning text-dark ms-1">要注意</span>
                  <span v-if="c.flag === 'BAN'" class="badge bg-danger ms-1">BAN</span>
                </div>
                <div class="text-muted small">{{ c.phone }}</div>
              </button>
              <div v-if="filteredCustomers.length === 0" class="text-muted small py-2">
                該当する顧客はいません
              </div>
            </div>

            <div v-if="customerSearch.trim() && !hasExactPhoneMatch" class="mt-3">
              <router-link
                :to="`/op/customers/new?phone=${encodeURIComponent(normalizedQuery)}&return=${encodeURIComponent('/op/phone?phone=' + normalizedQuery)}`"
                class="btn btn-primary w-100"
              >
                <i class="ti ti-user-plus"></i>
                「{{ normalizedQuery || customerSearch }}」で新規顧客を作成
              </router-link>
            </div>

            <div v-if="!customerSearch.trim()" class="mt-3 text-end">
              <router-link to="/op/customers/new?return=/op/phone" class="btn btn-outline-primary btn-sm">
                <i class="ti ti-user-plus"></i> 新規顧客を作成
              </router-link>
            </div>
          </div>
        </div>
      </div>

      <!-- 顧客（edit時の読み取り専用カード） -->
      <div v-else class="card">
        <div class="card-header">顧客</div>
        <div class="card-body">
          <div class="selected-customer">
            <div>
              <div class="fw-bold">{{ editCustomerLabel || '-' }}</div>
              <div v-if="selectedCustomer && selectedCustomer.phone" class="text-muted small">
                {{ selectedCustomer.phone }}
              </div>
            </div>
            <span class="badge bg-secondary">変更不可</span>
          </div>
        </div>
      </div>

      <!-- 予約内容入力 -->
      <div class="card" v-show="isEdit || form.customer">
        <div class="card-header">{{ isEdit ? '予約内容' : 'STEP 2: 予約内容入力' }}</div>
        <div class="card-body">
          <form @submit.prevent="submit">
            <!-- create: 日付＋開始時刻 / edit: 開始日時＋終了日時 -->
            <div v-if="!isEdit" class="row">
              <div class="col-md-6">
                <div class="mb-3">
                  <label class="form-label">予約日</label>
                  <input type="date" class="form-control" v-model="form.startDate">
                </div>
              </div>
              <div class="col-md-3">
                <div class="mb-3">
                  <label class="form-label">開始時刻</label>
                  <input type="time" step="300" class="form-control" v-model="form.startTime">
                </div>
              </div>
            </div>

            <div v-else class="row">
              <div class="col-md-6">
                <div class="mb-3">
                  <label class="form-label">開始日時</label>
                  <input type="datetime-local" step="300" class="form-control" v-model="form.start" required>
                </div>
              </div>
              <div class="col-md-6">
                <div class="mb-3">
                  <label class="form-label">終了日時</label>
                  <input type="datetime-local" step="300" class="form-control" v-model="form.end" required>
                </div>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label">キャスト</label>
              <input
                type="text"
                class="form-control form-control-sm mb-2"
                placeholder="名前で検索..."
                v-model="castSearch"
              />
              <div class="cast-scroll">
                <div
                  v-for="c in filteredCasts"
                  :key="c.id"
                  class="cast-chip"
                  :class="{ active: form.cast === c.id }"
                  @click="form.cast = c.id"
                >
                  <img
                    v-if="c.avatar_url"
                    :src="c.avatar_url"
                    :alt="c.name"
                    class="cast-chip__avatar"
                  >
                  <div v-else class="cast-chip__avatar cast-chip__avatar--placeholder">
                    <i class="ti ti-user"></i>
                  </div>
                  <span class="cast-chip__name">{{ c.name }}</span>
                </div>
                <div v-if="filteredCasts.length === 0" class="text-muted small py-2 px-1">
                  該当なし
                </div>
              </div>
              <div v-if="selectedCastName" class="small text-muted mt-1">
                選択中: <strong>{{ selectedCastName }}</strong>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label">コース</label>
              <div class="select-grid">
                <button
                  v-for="c in courses"
                  :key="c.id"
                  type="button"
                  class="btn btn-sm select-btn"
                  :class="form.course == c.id ? 'active' : ''"
                  @click="form.course = c.id"
                >
                  {{ c.name }}<br><small>{{ formatYen(c.price) }}</small>
                </button>
              </div>
            </div>

            <div class="mb-3" v-if="options.length">
              <label class="form-label">オプション</label>
              <div class="select-grid">
                <button
                  v-for="opt in options"
                  :key="opt.id"
                  type="button"
                  class="btn btn-sm select-btn"
                  :class="form.options.includes(opt.id) ? 'active' : ''"
                  @click="toggleOption(opt.id)"
                >
                  {{ opt.name }}<br><small>+{{ formatYen(opt.price) }}</small>
                </button>
              </div>
            </div>

            <div class="mb-3" v-if="!isEdit && extensions.length">
              <label class="form-label">延長</label>
              <div class="select-grid">
                <button
                  type="button"
                  class="btn btn-sm select-btn"
                  :class="form.extension === '' ? 'active' : ''"
                  @click="form.extension = ''"
                >
                  なし
                </button>
                <button
                  v-for="ext in extensions"
                  :key="ext.id"
                  type="button"
                  class="btn btn-sm select-btn"
                  :class="form.extension == ext.id ? 'active' : ''"
                  @click="form.extension = ext.id"
                >
                  {{ ext.name }}<br>
                  <small>+{{ ext.duration }}分 / +{{ formatYen(ext.price) }}</small>
                </button>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label">支払い方法</label>
              <div class="select-grid select-grid--3">
                <button
                  v-for="pm in paymentMethods"
                  :key="pm.value"
                  type="button"
                  class="btn btn-sm select-btn"
                  :class="form.payment_method === pm.value ? 'active' : ''"
                  @click="form.payment_method = pm.value"
                >
                  <i :class="['ti', pm.icon, 'me-1']"></i>{{ pm.label }}
                </button>
              </div>
            </div>

            <div class="row">
              <div class="col-md-6">
                <div class="mb-3">
                  <label class="form-label">媒体</label>
                  <select class="form-select" v-model="form.medium">
                    <option value="">-- 未設定 --</option>
                    <option v-for="m in media" :key="m.id" :value="m.id">{{ m.name }}</option>
                  </select>
                </div>
              </div>
              <div class="col-md-6">
                <div class="mb-3">
                  <label class="form-label">割引</label>
                  <select class="form-select" v-model="form.discount" :disabled="isEdit">
                    <option value="">-- 割引なし --</option>
                    <option v-for="d in discounts" :key="d.id" :value="d.id">
                      {{ d.name }}（{{ d.discount_type === 'percent' ? d.value + '%' : d.value.toLocaleString() + '円' }}引き）
                    </option>
                  </select>
                  <div v-if="isEdit" class="form-text">編集時の割引変更は予約詳細から行ってください</div>
                </div>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label">備考</label>
              <textarea class="form-control" rows="3" placeholder="備考やメモ..." v-model="form.memo"></textarea>
            </div>

            <hr>

            <div class="text-center mb-3">
              <h5 v-if="selectedCourse" class="mb-0">合計料金: <strong>{{ formatYen(totalPrice) }}</strong></h5>
              <div v-if="selectedCourse && discountAmount > 0" class="small text-muted mt-1">
                小計 {{ formatYen(subtotalPrice) }} − 割引 {{ formatYen(discountAmount) }}
              </div>
              <div v-if="selectedCourse && isCardPayment" class="card-fee-note mt-2">
                <div class="card-fee-note__total">
                  カード決済時のお客様請求額（目安）:
                  <strong>{{ formatYen(cardTotal) }}</strong>
                </div>
                <div class="card-fee-note__breakdown">
                  （{{ formatYen(totalPrice) }} ＋ 手数料10% {{ formatYen(cardFee) }}）
                </div>
                <div class="card-fee-note__hint">※ 売上計上額は手数料を含みません</div>
              </div>
            </div>
            <div v-if="errorMsg" class="alert alert-danger py-2 mb-2">
              <i class="ti ti-alert-circle me-1"></i>{{ errorMsg }}
            </div>
            <div class="d-flex gap-2">
              <button type="button" class="btn btn-outline-secondary flex-fill" @click="onCancel">{{ resolvedCancelLabel }}</button>
              <button type="submit" class="btn btn-success flex-fill" :disabled="submitting">
                <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
                <i v-else class="ti" :class="isEdit ? 'ti-device-floppy' : 'ti-check'"></i> {{ resolvedSubmitLabel }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.form-label {
  font-weight: bold;
}

.order-form--embedded .card {
  border: none;
  box-shadow: none;
}
.order-form--embedded .card-header {
  background: transparent;
  padding-left: 0;
  padding-right: 0;
  border-bottom: 1px solid #eee;
}
.order-form--embedded .card-body {
  padding-left: 0;
  padding-right: 0;
}

.order-form__edit-badge {
  background: #fff3cd;
  color: #7c5e00;
  border: 1px solid #ffd76a;
  font-size: 0.85rem;
  font-weight: bold;
  padding: 0.4rem 0.7rem;
}

.cast-scroll {
  display: flex;
  flex-wrap: nowrap;
  gap: 0.5rem;
  overflow-x: auto;
  padding-bottom: 0.5rem;
  -webkit-overflow-scrolling: touch;
  align-items: center;
  justify-content: flex-start;

  &::-webkit-scrollbar {
    height: 4px;
  }
  &::-webkit-scrollbar-thumb {
    background: #ccc;
    border-radius: 2px;
  }
}

.cast-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  border: 2px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  flex-shrink: 0;
  width: 72px;
  transition: all 0.15s;

  &:hover {
    border-color: var(--bs-primary);
  }

  &.active {
    border-color: var(--bs-primary);
    background: rgba(var(--bs-primary-rgb), 0.08);
  }

  &__avatar {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    object-fit: cover;

    &--placeholder {
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f0f0f0;
      color: #aaa;
      font-size: 20px;
    }
  }

  &__name {
    font-size: 0.7rem;
    text-align: center;
    line-height: 1.2;
    word-break: keep-all;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }
}

.select-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 0.5rem;

  @media (max-width: 575.98px) {
    grid-template-columns: repeat(3, 1fr);
  }

  &--3 {
    grid-template-columns: repeat(3, 1fr);
  }
}

.selected-customer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border: 1px solid var(--bs-primary);
  border-radius: 8px;
  background: rgba(var(--bs-primary-rgb), 0.06);
}

.customer-results {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 0.25rem;
  background: #fff;
}

.customer-result-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.5rem 0.75rem;
  border: 1px solid transparent;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  transition: all 0.1s;

  &:hover {
    border-color: var(--bs-primary);
    background: rgba(var(--bs-primary-rgb), 0.05);
  }
}

.select-btn {
  border: 1px solid #dee2e6;
  background: #fff;
  border-radius: 8px;
  padding: 0.5rem 0.25rem;
  text-align: center;
  line-height: 1.3;
  transition: all 0.15s;
  width: 100%;

  &:hover {
    border-color: var(--bs-primary);
  }

  &.active {
    background: var(--bs-primary);
    border-color: var(--bs-primary);
    color: #fff;
  }
}

.card-fee-note {
  font-size: 0.85rem;
  color: #7c2d12;
  background: #fff7ed;
  border: 1px dashed #fb923c;
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  display: inline-block;

  &__total strong { color: #c2410c; font-size: 1rem; }
  &__breakdown { font-size: 0.8rem; color: #9a3412; margin-top: 2px; }
  &__hint { font-size: 0.7rem; color: #78350f; margin-top: 2px; opacity: 0.8; }
}
</style>
