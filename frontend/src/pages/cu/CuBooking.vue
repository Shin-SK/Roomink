<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
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
const drawerOpen = ref(false)
const selectedStoreId = ref(null)

const slots = ref([])
const slotsLoading = ref(false)
const slotsFetched = ref(false)

const currentStoreName = computed(() => {
  const s = stores.value.find(s => s.store_id === selectedStoreId.value)
  return s ? s.store_name : ''
})

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
    } else if (stores.value.length > 1) {
      drawerOpen.value = true
      loading.value = false
      return
    }

    const data = await api.getBookingOptions(selectedStoreId.value)
    casts.value = data.casts
    courses.value = data.courses
    options.value = data.options

    // pre-select cast from query param
    if (route.query.cast) {
      form.value.cast = Number(route.query.cast)
    }

    // default date = tomorrow
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

function switchStore(storeId) {
  drawerOpen.value = false
  window.location.href = '/cu/booking?store=' + storeId
}

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
        cast_name: casts.value.find(c => c.id === Number(form.value.cast))?.name || '',
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
  <div class="customer-layout">
    <!-- Store Drawer -->
    <div v-if="stores.length > 1" class="rk-store-overlay" :class="{ show: drawerOpen }" @click="drawerOpen = false"></div>
    <aside v-if="stores.length > 1" class="rk-store-drawer" :class="{ show: drawerOpen }">
      <div class="rk-store-drawer__header">
        <span>店舗を選択</span>
        <button class="btn-close" @click="drawerOpen = false"></button>
      </div>
      <div class="rk-store-drawer__list">
        <button
          v-for="s in stores" :key="s.store_id"
          class="rk-store-drawer__item" :class="{ active: s.store_id === selectedStoreId }"
          @click="switchStore(s.store_id)"
        >
          <div class="rk-store-drawer__logo">
            <i class="ti ti-building-store" style="font-size:20px; color:var(--rk-primary)"></i>
          </div>
          <span class="rk-store-drawer__name">{{ s.store_name }}</span>
        </button>
      </div>
    </aside>

    <header class="customer-header">
      <div class="customer-nav">
        <a href="/cu/mypage"><img src="/icon.svg" alt="" style="width: 24px;"></a>
        <button v-if="stores.length > 1" class="rk-store-btn" @click="drawerOpen = true">
          <i class="ti ti-building-store"></i>
          {{ currentStoreName }}
          <i class="ti ti-chevron-down" style="font-size:14px;"></i>
        </button>
      </div>
    </header>

    <main class="customer-content container customer-booking">

      <div v-if="loading" class="text-center py-5">
        <div class="spinner-border text-primary"></div>
      </div>

      <template v-else>
        <h1 class="fs-3 mb-3 fw-bold">Web予約</h1>
        <p class="text-muted mb-4">ご希望の内容を入力して予約申請してください。内容を確認後、SMSで結果をお知らせします。</p>

        <div v-if="error" class="alert alert-danger mb-3">{{ error }}</div>

        <form @submit.prevent="submit">
          <div class="card">
            <div class="card-header">予約情報</div>
            <div class="card-body">

              <!-- セラピスト指名 -->
              <div class="mb-3">
                <label class="form-label">セラピスト指名 <span class="text-danger">*</span></label>
                <select class="form-select" v-model="form.cast">
                  <option value="">選択してください</option>
                  <option v-for="c in casts" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
              </div>

              <!-- 予約日 -->
              <div class="mb-3">
                <label class="form-label">予約日 <span class="text-danger">*</span></label>
                <input type="date" class="form-control" v-model="form.date">
              </div>

              <!-- 希望時間（空き枠） -->
              <div class="mb-3">
                <label class="form-label">希望時間 <span class="text-danger">*</span></label>
                <div v-if="!form.cast || !form.date" class="text-muted small">セラピストと予約日を選択すると、空き時間が表示されます</div>
                <div v-else-if="slotsLoading" class="text-center py-2">
                  <span class="spinner-border spinner-border-sm text-primary"></span> 空き枠を取得中...
                </div>
                <div v-else-if="slotsFetched && slots.length === 0" class="text-muted small">この日は予約可能な時間帯がありません</div>
                <div v-else-if="slots.length > 0" class="d-flex flex-wrap gap-2">
                  <button
                    v-for="slot in slots" :key="slot.start"
                    type="button"
                    class="btn btn-sm"
                    :class="form.time === slot.start ? 'btn-primary' : 'btn-outline-primary'"
                    @click="selectSlot(slot)"
                  >
                    {{ slot.start }}
                  </button>
                </div>
                <div v-if="form.time" class="mt-2 small text-muted">選択中: {{ form.time }}</div>
              </div>

              <!-- コース -->
              <div class="mb-3">
                <label class="form-label">コース <span class="text-danger">*</span></label>
                <div class="d-flex flex-column gap-2">
                  <div v-for="c in courses" :key="c.id" class="form-check">
                    <input class="form-check-input" type="radio" :id="'course-' + c.id" :value="c.id" v-model="form.course">
                    <label class="form-check-label" :for="'course-' + c.id">
                      <strong>{{ c.name }}</strong> - {{ formatYen(c.price) }}
                    </label>
                  </div>
                </div>
              </div>

              <!-- オプション -->
              <div class="mb-3">
                <label class="form-label">オプション</label>
                <div class="d-flex flex-column gap-2">
                  <div v-for="o in options" :key="o.id" class="form-check">
                    <input class="form-check-input" type="checkbox" :id="'opt-' + o.id" :value="o.id" v-model="form.options">
                    <label class="form-check-label" :for="'opt-' + o.id">
                      {{ o.name }}（+{{ formatYen(o.price) }}）
                    </label>
                  </div>
                </div>
              </div>

              <!-- 備考 -->
              <div class="mb-3">
                <label class="form-label">備考・ご要望</label>
                <textarea class="form-control" v-model="form.memo" rows="3" placeholder="駐車場利用希望、初回、その他ご要望など"></textarea>
              </div>

            </div>
          </div>

          <!-- 注意事項 -->
          <div class="alert alert-info mb-4">
            <strong>ご予約について</strong>
            <ul class="mb-0">
              <li>予約は「申請」として受け付けられます。内容を確認後、SMSで承認結果をお知らせします。</li>
              <li>承認後、場所や詳細情報をSMSでお送りします。</li>
              <li>キャンセルは予約の24時間前までにお願いします。</li>
            </ul>
          </div>

          <!-- 送信ボタン -->
          <div class="d-flex flex-column align-items-center mb-4">
            <button type="submit" class="btn btn-primary btn-sm w-100 text-center" :disabled="submitting">
              <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
              <i v-else class="ti ti-send"></i> 予約を申請
            </button>
            <a :href="'/cu/mypage' + storeQ" class="btn btn-sm btn-outline">戻る</a>
          </div>
        </form>
      </template>
    </main>
  </div>
</template>
