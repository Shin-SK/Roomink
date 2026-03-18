<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import LayoutCustomer from '../../components/LayoutCustomer.vue'
import { api } from '../../api.js'

const router = useRouter()
const route = useRoute()

const loading = ref(true)
const submitting = ref(false)
const error = ref('')

const casts = ref([])
const courses = ref([])
const options = ref([])

const stores = ref([])
const selectedStoreId = ref(null)

const slots = ref([])
const slotsLoading = ref(false)
const slotsFetched = ref(false)

const storeQ = computed(() => selectedStoreId.value ? '?store=' + selectedStoreId.value : '')

const form = ref({
  cast: '',
  course: '',
  date: '',
  time: '',
  options: [],
  memo: '',
})

onMounted(async () => {
  try {
    const storeData = await api.getCustomerStores()
    stores.value = storeData.stores

    if (route.query.store) {
      selectedStoreId.value = Number(route.query.store)
    } else if (stores.value.length === 1) {
      selectedStoreId.value = stores.value[0].store_id
    }

    const data = await api.getBookingOptions(selectedStoreId.value)
    casts.value = data.casts
    courses.value = data.courses
    options.value = data.options

    if (route.query.cast) {
      form.value.cast = Number(route.query.cast)
    }

    const tomorrow = new Date()
    tomorrow.setDate(tomorrow.getDate() + 1)
    form.value.date = tomorrow.toISOString().slice(0, 10)
    form.value.time = ''
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

watch(
  () => [form.value.cast, form.value.date],
  async ([cast, date]) => {
    slots.value = []
    slotsFetched.value = false
    form.value.time = ''
    if (!cast || !date) return
    slotsLoading.value = true
    try {
      const data = await api.getAvailableSlots(cast, date, selectedStoreId.value)
      slots.value = data.slots
      slotsFetched.value = true
    } catch (e) {
      slots.value = []
      slotsFetched.value = true
    } finally {
      slotsLoading.value = false
    }
  },
)

function selectSlot(slot) {
  form.value.time = slot.start
}

function toggleOption(optId) {
  const idx = form.value.options.indexOf(optId)
  if (idx >= 0) {
    form.value.options.splice(idx, 1)
  } else {
    form.value.options.push(optId)
  }
}

const castSearch = ref('')

const filteredCasts = computed(() => {
  const q = castSearch.value.trim()
  if (!q) return casts.value
  return casts.value.filter(c => c.name.includes(q))
})

const selectedCastName = computed(() => {
  const c = casts.value.find(c => c.id === form.value.cast)
  return c ? c.name : ''
})

const selectedCourse = computed(() => courses.value.find(c => c.id === Number(form.value.course)))

const totalPrice = computed(() => {
  let total = selectedCourse.value ? selectedCourse.value.price : 0
  for (const optId of form.value.options) {
    const opt = options.value.find(o => o.id === optId)
    if (opt) total += opt.price
  }
  return total
})

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}

async function submit() {
  if (!form.value.cast || !form.value.course || !form.value.date || !form.value.time) {
    error.value = 'セラピスト、コース、日時は必須です'
    return
  }

  error.value = ''
  submitting.value = true

  try {
    const start = `${form.value.date}T${form.value.time}:00+09:00`
    const body = {
      cast: Number(form.value.cast),
      course: Number(form.value.course),
      start,
      options: form.value.options,
      memo: form.value.memo,
    }
    const order = await api.createCustomerBooking(body, selectedStoreId.value)
    router.push({
      name: 'cu-submitted',
      query: {
        store: selectedStoreId.value || undefined,
        id: order.id,
        cast_name: selectedCastName.value,
        course_name: selectedCourse.value?.name || '',
        date: form.value.date,
        time: form.value.time,
        total: totalPrice.value,
      },
    })
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <LayoutCustomer>
    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div class="customer-booking" v-else>
      <div v-if="error" class="alert alert-danger mb-3">{{ error }}</div>

      <form @submit.prevent="submit">
        <!-- セラピスト選択 -->
        <div class="card">
          <div class="card-header"><i class="ti ti-user-heart"></i> セラピスト指名</div>
          <div class="card-body">
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
              <div v-if="filteredCasts.length === 0" class="text-muted small py-2">
                該当なし
              </div>
            </div>
            <div v-if="selectedCastName" class="small text-muted mt-1">
              選択中: <strong>{{ selectedCastName }}</strong>
            </div>
          </div>
        </div>

        <!-- 日時選択 -->
        <div class="card">
          <div class="card-header"><i class="ti ti-calendar-event"></i> 日時</div>
          <div class="card-body">
            <div class="mb-3">
              <label class="form-label">予約日 <span class="text-danger">*</span></label>
              <input type="date" class="form-control" v-model="form.date">
            </div>

            <div class="mb-0">
              <label class="form-label">希望時間 <span class="text-danger">*</span></label>
              <div v-if="!form.cast || !form.date" class="text-muted small">セラピストと予約日を選択すると、空き時間が表示されます</div>
              <div v-else-if="slotsLoading" class="text-center py-2">
                <span class="spinner-border spinner-border-sm text-primary"></span> 空き枠を取得中...
              </div>
              <div v-else-if="slotsFetched && slots.length === 0" class="text-muted small">この日は予約可能な時間帯がありません</div>
              <div v-else-if="slots.length > 0" class="select-grid">
                <button
                  v-for="slot in slots" :key="slot.start"
                  type="button"
                  class="btn btn-sm select-btn"
                  :class="{ active: form.time === slot.start }"
                  @click="selectSlot(slot)"
                >
                  {{ slot.start }}
                </button>
              </div>
              <div v-if="form.time" class="mt-2 small text-muted">選択中: {{ form.time }}</div>
            </div>
          </div>
        </div>

        <!-- コース選択 -->
        <div class="card">
          <div class="card-header"><i class="ti ti-clock-hour-4"></i> コース <span class="text-danger">*</span></div>
          <div class="card-body">
            <div class="select-grid">
              <button
                v-for="c in courses"
                :key="c.id"
                type="button"
                class="btn btn-sm select-btn"
                :class="{ active: form.course == c.id }"
                @click="form.course = c.id"
              >
                {{ c.name }}<br><small>{{ formatYen(c.price) }}</small>
              </button>
            </div>
          </div>
        </div>

        <!-- オプション選択 -->
        <div class="card" v-if="options.length">
          <div class="card-header"><i class="ti ti-sparkles"></i> オプション</div>
          <div class="card-body">
            <div class="select-grid">
              <button
                v-for="opt in options"
                :key="opt.id"
                type="button"
                class="btn btn-sm select-btn"
                :class="{ active: form.options.includes(opt.id) }"
                @click="toggleOption(opt.id)"
              >
                {{ opt.name }}<br><small>+{{ formatYen(opt.price) }}</small>
              </button>
            </div>
          </div>
        </div>

        <!-- 備考 -->
        <div class="card">
          <div class="card-header"><i class="ti ti-message-dots"></i> 備考・ご要望</div>
          <div class="card-body">
            <textarea class="form-control" v-model="form.memo" rows="3" placeholder="駐車場利用希望、初回、その他ご要望など"></textarea>
          </div>
        </div>

        <!-- 合計金額 + 送信 -->
        <div class="card">
          <div class="card-body">
            <div class="text-center mb-3">
              <h5 v-if="selectedCourse" class="mb-0">合計料金: <strong>{{ formatYen(totalPrice) }}</strong></h5>
            </div>

            <div class="alert alert-info mb-3 small">
              <ul class="mb-0 ps-3">
                <li>予約は「申請」として受け付けられます</li>
                <li>内容確認後、SMSで承認結果をお知らせします</li>
                <li>キャンセルは24時間前までにお願いします</li>
              </ul>
            </div>

            <div class="d-flex gap-2">
              <router-link :to="'/cu/mypage' + storeQ" class="btn btn-outline-secondary flex-fill">戻る</router-link>
              <button type="submit" class="btn btn-primary flex-fill" :disabled="submitting">
                <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
                <i v-else class="ti ti-send"></i> 予約を申請
              </button>
            </div>
          </div>
        </div>
      </form>
    </div>
  </LayoutCustomer>
</template>

<style scoped lang="scss">
.form-label {
  font-weight: bold;
}

.cast-scroll {
  display: grid;
  grid-auto-flow: column;
  grid-template-rows: repeat(2, auto);
  gap: 0.5rem;
  overflow-x: auto;
  padding-bottom: 0.5rem;
  -webkit-overflow-scrolling: touch;
  align-items: center;
  justify-content: start;

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
    width: 52px;
    height: 52px;
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
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 0.5rem;

  @media (max-width: 575.98px) {
    grid-template-columns: repeat(3, 1fr);
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
</style>
