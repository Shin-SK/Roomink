<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, normalizePhone } from '../../api.js'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const loadingOptions = ref(false)
const slotsLoading = ref(false)
const submitting = ref(false)
const error = ref('')
const step = ref('booking')
const verificationId = ref('')
const maskedPhone = ref('')
const code = ref('')

const stores = ref([])
const casts = ref([])
const courses = ref([])
const options = ref([])
const slots = ref([])
const selectedSlotStartAt = ref('')
const castSearch = ref('')
const courseSearch = ref('')
const selectedArea = ref('all')
const selectedDuration = ref('all')
const castVisibleLimit = ref(12)
const courseVisibleLimit = ref(12)
const publicBookingNotice = ref('')

function dateString(daysFromToday = 0) {
  const value = new Date()
  value.setDate(value.getDate() + daysFromToday)
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const form = ref({
  store: '',
  display_name: '',
  phone: '',
  cast: '',
  course: '',
  date: dateString(1),
  time: '',
  options: [],
  memo: '',
})

const bookingDates = computed(() => Array.from({ length: 14 }, (_, index) => {
  const value = dateString(index)
  const date = new Date(`${value}T00:00:00`)
  return {
    value,
    monthDay: `${date.getMonth() + 1}/${date.getDate()}`,
    weekday: new Intl.DateTimeFormat('ja-JP', { weekday: 'short' }).format(date),
    isWeekend: date.getDay() === 0 || date.getDay() === 6,
  }
}))

const selectedStore = computed(() => stores.value.find(item => item.store_id === Number(form.value.store)))
const selectedCast = computed(() => casts.value.find(item => item.id === Number(form.value.cast)))
const selectedCourse = computed(() => courses.value.find(item => item.id === Number(form.value.course)))
const eligibleCourses = computed(() => courses.value.filter(item => (
  !item.target_cast_ids?.length || item.target_cast_ids.includes(Number(form.value.cast))
)))
const areaOptions = computed(() => [...new Set(casts.value.flatMap(cast => cast.area_names || []))].sort())
const durationOptions = computed(() => [...new Set(eligibleCourses.value.map(course => course.duration))].sort((a, b) => a - b))
const filteredCasts = computed(() => {
  const keyword = castSearch.value.trim().toLowerCase()
  return casts.value.filter(cast => {
    const matchesArea = selectedArea.value === 'all' || cast.area_names?.includes(selectedArea.value)
    const matchesKeyword = !keyword || [
      cast.name,
      ...(cast.area_names || []),
      ...(cast.shift_summaries || []).map(shift => shift.room_name),
    ].join(' ').toLowerCase().includes(keyword)
    return matchesArea && matchesKeyword
  })
})
const visibleCasts = computed(() => filteredCasts.value.slice(0, castVisibleLimit.value))
const filteredCourses = computed(() => {
  const keyword = courseSearch.value.trim().toLowerCase()
  return eligibleCourses.value.filter(course => (
    (selectedDuration.value === 'all' || course.duration === Number(selectedDuration.value))
    && (!keyword || course.name.toLowerCase().includes(keyword))
  ))
})
const visibleCourses = computed(() => filteredCourses.value.slice(0, courseVisibleLimit.value))
const totalPrice = computed(() => {
  let total = selectedCourse.value?.price || 0
  for (const optionId of form.value.options) {
    total += options.value.find(item => item.id === optionId)?.price || 0
  }
  return total
})

function formatYen(value) {
  return `¥${Number(value || 0).toLocaleString()}`
}

function toggleOption(optionId) {
  const index = form.value.options.indexOf(optionId)
  if (index >= 0) form.value.options.splice(index, 1)
  else form.value.options.push(optionId)
}

function selectSlot(slot) {
  form.value.time = slot.start
  selectedSlotStartAt.value = slot.start_at
}

function selectCast(castId) {
  if (Number(form.value.cast) === castId) return
  form.value.cast = castId
  form.value.course = ''
  courseSearch.value = ''
  selectedDuration.value = 'all'
}

function selectCourse(courseId) {
  form.value.course = courseId
}

async function loadOptions() {
  if (!form.value.store || !form.value.date) return
  loadingOptions.value = true
  error.value = ''
  try {
    const data = await api.getPublicBookingOptions(form.value.store, form.value.date)
    if (data.store) {
      stores.value = [{ store_id: data.store.id, store_name: data.store.name }]
      publicBookingNotice.value = data.store.public_booking_notice || ''
    }
    casts.value = data.casts || []
    courses.value = data.courses || []
    options.value = data.options || []
    form.value.cast = ''
    form.value.course = ''
    form.value.options = []
    castSearch.value = ''
    courseSearch.value = ''
    selectedArea.value = 'all'
    selectedDuration.value = 'all'
    castVisibleLimit.value = 12
    courseVisibleLimit.value = 12
  } catch (e) {
    error.value = e.message
  } finally {
    loadingOptions.value = false
  }
}

async function loadSlots() {
  slots.value = []
  form.value.time = ''
  selectedSlotStartAt.value = ''
  if (!form.value.store || !form.value.cast || !form.value.course || !form.value.date) return
  slotsLoading.value = true
  try {
    const data = await api.getPublicBookingSlots(
      form.value.store,
      form.value.cast,
      form.value.course,
      form.value.date,
    )
    slots.value = data.slots || []
  } catch (e) {
    error.value = e.message
  } finally {
    slotsLoading.value = false
  }
}

watch(() => [form.value.store, form.value.date], loadOptions)
watch(
  () => [form.value.cast, form.value.course],
  async () => {
    if (form.value.course && !eligibleCourses.value.some(item => item.id === Number(form.value.course))) {
      form.value.course = ''
    }
    await loadSlots()
  },
)
watch([castSearch, selectedArea], () => { castVisibleLimit.value = 12 })
watch([courseSearch, selectedDuration], () => { courseVisibleLimit.value = 12 })

onMounted(() => {
  const requestedStore = Number(route.query.store)
  if (!Number.isInteger(requestedStore) || requestedStore <= 0) {
    error.value = '店舗専用のWeb予約URLからアクセスしてください。'
  } else {
    form.value.store = requestedStore
  }
  loading.value = false
})

function validateBookingForm() {
  if (!form.value.store || !form.value.display_name.trim() || !normalizePhone(form.value.phone)) {
    return '店舗、お名前、電話番号を入力してください。'
  }
  if (!form.value.cast || !form.value.course || !form.value.date || !selectedSlotStartAt.value) {
    return 'キャスト、コース、予約日時を選択してください。'
  }
  return ''
}

async function requestVerification() {
  const message = validateBookingForm()
  if (message) {
    error.value = message
    window.scrollTo({ top: 0, behavior: 'smooth' })
    return
  }
  error.value = ''
  submitting.value = true
  try {
    const result = await api.requestPublicBookingVerification({
      ...form.value,
      store: Number(form.value.store),
      cast: Number(form.value.cast),
      course: Number(form.value.course),
      phone: normalizePhone(form.value.phone),
      start: selectedSlotStartAt.value,
    })
    verificationId.value = result.verification_id
    maskedPhone.value = result.masked_phone
    step.value = 'verification'
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (e) {
    error.value = e.message
    if (e.status === 409) await loadSlots()
  } finally {
    submitting.value = false
  }
}

async function confirmBooking() {
  if (!/^\d{6}$/.test(code.value)) {
    error.value = 'SMSに届いた6桁の認証コードを入力してください。'
    return
  }
  error.value = ''
  submitting.value = true
  try {
    const result = await api.confirmPublicBooking(verificationId.value, code.value)
    sessionStorage.setItem('roomink-public-booking-result', JSON.stringify(result))
    router.replace({ name: 'public-booking-complete' })
  } catch (e) {
    error.value = e.message
    if (e.status === 409) step.value = 'booking'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="public-booking-page">
    <header class="public-header">
      <img src="/logo.svg" alt="Roomink" class="public-header__logo">
      <router-link to="/cu/login" class="member-link">会員ログイン</router-link>
    </header>

    <main class="public-booking-container">
      <div class="reservation-hero">
        <p class="reservation-kicker">WEB RESERVATION</p>
        <h1>Web予約</h1>
        <p>空き時間を選んで、スマホですぐに予約できます。</p>
      </div>

      <div v-if="publicBookingNotice" class="public-booking-notice" role="note">
        <i class="ti ti-alert-circle"></i>
        <div>{{ publicBookingNotice }}</div>
      </div>

      <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
      <div v-if="loading" class="text-center py-5">
        <span class="spinner-border text-primary"></span>
      </div>

      <form v-else-if="step === 'booking' && form.store" @submit.prevent="requestVerification">
        <section class="booking-card">
          <div class="section-heading">
            <span>1</span>
            <div><h2>予約日を選ぶ</h2><p>ご希望の日付を選択してください</p></div>
          </div>

          <div v-if="selectedStore" class="fixed-store mb-3">
            <small>ご予約店舗</small>
            <strong>{{ selectedStore.store_name }}</strong>
          </div>

          <div class="date-scroller" aria-label="予約日">
            <button
              v-for="day in bookingDates"
              :key="day.value"
              type="button"
              class="date-chip"
              :class="{ active: form.date === day.value, weekend: day.isWeekend }"
              @click="form.date = day.value"
            >
              <strong>{{ day.monthDay }}</strong>
              <small>{{ day.weekday }}</small>
            </button>
          </div>
          <details class="date-other">
            <summary>別の日付を選ぶ</summary>
            <input v-model="form.date" type="date" class="form-control mt-2" :min="dateString()" required>
          </details>
        </section>

        <section class="booking-card">
          <div class="section-heading">
            <span>2</span>
            <div><h2>キャストを選ぶ</h2><p>選んだ日の出勤キャストを表示しています</p></div>
          </div>

          <div v-if="loadingOptions" class="text-center py-4">
            <span class="spinner-border spinner-border-sm text-primary"></span>
          </div>
          <template v-else>
            <div v-if="casts.length" class="filter-panel">
              <label class="search-box">
                <i class="ti ti-search"></i>
                <input v-model="castSearch" type="search" placeholder="名前・エリア・ルームで検索" aria-label="キャストを検索">
              </label>
              <div v-if="areaOptions.length" class="segment-scroller" aria-label="エリアで絞り込み">
                <button type="button" :class="{ active: selectedArea === 'all' }" @click="selectedArea = 'all'">すべて</button>
                <button
                  v-for="area in areaOptions"
                  :key="area"
                  type="button"
                  :class="{ active: selectedArea === area }"
                  @click="selectedArea = area"
                >{{ area }}</button>
              </div>
            </div>

            <p v-if="!casts.length" class="empty-message">この日は出勤予定のキャストがいません。別の日付をお選びください。</p>
            <p v-else-if="!filteredCasts.length" class="empty-message">条件に合うキャストが見つかりません。</p>
            <div v-else class="cast-grid">
              <button
                v-for="cast in visibleCasts"
                :key="cast.id"
                type="button"
                class="cast-card"
                :class="{ active: Number(form.cast) === cast.id }"
                @click="selectCast(cast.id)"
              >
                <img v-if="cast.avatar_url" :src="cast.avatar_url" :alt="cast.name">
                <span v-else class="cast-placeholder"><i class="ti ti-user"></i></span>
                <span class="cast-card__content">
                  <strong>{{ cast.name }}</strong>
                  <small v-if="cast.shift_summaries?.length" class="cast-area">
                    <i class="ti ti-map-pin"></i>{{ cast.shift_summaries[0].area_name }}
                  </small>
                  <small v-if="cast.shift_summaries?.length">
                    {{ cast.shift_summaries[0].room_name }}・{{ cast.shift_summaries[0].start }}〜{{ cast.shift_summaries[0].end }}
                  </small>
                  <small v-if="cast.shift_summaries?.length > 1">ほか{{ cast.shift_summaries.length - 1 }}件</small>
                </span>
                <i v-if="Number(form.cast) === cast.id" class="ti ti-circle-check cast-card__check"></i>
              </button>
            </div>
            <button
              v-if="filteredCasts.length > castVisibleLimit"
              type="button"
              class="show-more"
              @click="castVisibleLimit += 12"
            >さらに{{ Math.min(12, filteredCasts.length - castVisibleLimit) }}名を表示</button>
          </template>
        </section>

        <section class="booking-card" :class="{ muted: !form.cast }">
          <div class="section-heading">
            <span>3</span>
            <div><h2>コース・時間を選ぶ</h2><p>キャスト選択後に予約可能時間を確認できます</p></div>
          </div>

          <p v-if="!form.cast" class="empty-message">先にキャストを選択してください。</p>
          <template v-else>
            <div class="filter-panel">
              <label class="search-box">
                <i class="ti ti-search"></i>
                <input v-model="courseSearch" type="search" placeholder="コース名で検索" aria-label="コースを検索">
              </label>
              <div class="segment-scroller" aria-label="施術時間で絞り込み">
                <button type="button" :class="{ active: selectedDuration === 'all' }" @click="selectedDuration = 'all'">すべて</button>
                <button
                  v-for="duration in durationOptions"
                  :key="duration"
                  type="button"
                  :class="{ active: Number(selectedDuration) === duration }"
                  @click="selectedDuration = duration"
                >{{ duration }}分</button>
              </div>
            </div>

            <p v-if="!filteredCourses.length" class="empty-message">条件に合うコースが見つかりません。</p>
            <div v-else class="course-grid">
              <button
                v-for="course in visibleCourses"
                :key="course.id"
                type="button"
                class="course-card"
                :class="{ active: Number(form.course) === course.id }"
                @click="selectCourse(course.id)"
              >
                <span><strong>{{ course.name }}</strong><small>{{ course.duration }}分</small></span>
                <b>{{ formatYen(course.price) }}</b>
              </button>
            </div>
            <button
              v-if="filteredCourses.length > courseVisibleLimit"
              type="button"
              class="show-more"
              @click="courseVisibleLimit += 12"
            >さらに{{ Math.min(12, filteredCourses.length - courseVisibleLimit) }}件を表示</button>

            <div class="time-selection">
              <label class="form-label">開始時間 <span class="required">必須</span></label>
              <p v-if="!form.course" class="text-muted small mb-0">コースを選択してください。</p>
              <div v-else-if="slotsLoading" class="text-center py-3"><span class="spinner-border spinner-border-sm text-primary"></span></div>
              <p v-else-if="!slots.length" class="empty-message mb-0">このコースで予約できる時間がありません。</p>
              <div v-else class="slot-grid">
                <button
                  v-for="slot in slots"
                  :key="slot.start_at"
                  type="button"
                  class="slot-button"
                  :class="{ active: form.time === slot.start }"
                  @click="selectSlot(slot)"
                >{{ slot.start }}</button>
              </div>
            </div>
          </template>
        </section>

        <section v-if="options.length" class="booking-card">
          <div class="section-heading">
            <span>4</span>
            <div><h2>オプション</h2><p>複数選択できます</p></div>
          </div>
          <div class="option-grid">
            <button
              v-for="option in options"
              :key="option.id"
              type="button"
              class="option-card"
              :class="{ active: form.options.includes(option.id) }"
              @click="toggleOption(option.id)"
            >
              <span><strong>{{ option.name }}</strong><small>+{{ formatYen(option.price) }}</small></span>
              <i :class="form.options.includes(option.id) ? 'ti ti-circle-check-filled' : 'ti ti-circle-plus'"></i>
            </button>
          </div>
        </section>

        <section class="booking-card">
          <div class="section-heading">
            <span>{{ options.length ? 5 : 4 }}</span>
            <div><h2>お客様情報・確認</h2><p>SMS認証後、その場で予約が確定します</p></div>
          </div>

          <div class="row g-3 mb-3">
            <div class="col-md-6">
              <label class="form-label">お名前 <span class="required">必須</span></label>
              <input v-model.trim="form.display_name" class="form-control form-control-lg" maxlength="50" autocomplete="name" required>
            </div>
            <div class="col-md-6">
              <label class="form-label">電話番号 <span class="required">必須</span></label>
              <input
                v-model="form.phone"
                class="form-control form-control-lg"
                type="tel"
                inputmode="tel"
                autocomplete="tel"
                placeholder="09012345678"
                required
              >
            </div>
          </div>
          <label class="form-label">ご要望（任意）</label>
          <textarea v-model="form.memo" class="form-control mb-3" rows="3" maxlength="1000" placeholder="ご要望があれば入力してください"></textarea>

          <div class="summary">
            <div><span>店舗</span><strong>{{ selectedStore?.store_name || '-' }}</strong></div>
            <div><span>担当</span><strong>{{ selectedCast?.name || '-' }}</strong></div>
            <div><span>日時</span><strong>{{ form.date }} {{ form.time || '-' }}</strong></div>
            <div><span>コース</span><strong>{{ selectedCourse?.name || '-' }}</strong></div>
            <div class="summary__total"><span>合計</span><strong>{{ formatYen(totalPrice) }}</strong></div>
          </div>
          <p class="confirmation-note">
            <i class="ti ti-lock"></i>
            認証コード入力後に空き状況を再確認し、予約を確定します。
          </p>
          <button type="submit" class="submit-button" :disabled="submitting">
            <span v-if="submitting" class="spinner-border spinner-border-sm me-2"></span>
            SMS認証へ進む
            <i v-if="!submitting" class="ti ti-arrow-right"></i>
          </button>
        </section>
      </form>

      <section v-else-if="step === 'verification'" class="booking-card verification-card">
        <div class="verification-icon"><i class="ti ti-message-code"></i></div>
        <h2 class="text-center">認証コードを入力</h2>
        <p class="text-center text-muted">
          {{ maskedPhone }} へ6桁の認証コードを送信しました。<br>10分以内に入力してください。
        </p>
        <form @submit.prevent="confirmBooking">
          <input
            v-model="code"
            type="text"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="6"
            class="form-control verification-code"
            placeholder="000000"
          >
          <button type="submit" class="submit-button mt-3" :disabled="submitting">
            <span v-if="submitting" class="spinner-border spinner-border-sm me-2"></span>
            予約を確定する
          </button>
          <button type="button" class="btn btn-link w-100 mt-2" :disabled="submitting" @click="step = 'booking'">
            予約内容を変更する
          </button>
        </form>
      </section>
    </main>
  </div>
</template>

<style scoped>
.public-booking-page {
  --booking-primary: #2a9d8f;
  --booking-primary-dark: #217f74;
  --booking-primary-soft: #e8f6f3;
  min-height: 100vh;
  background: #f6faf9;
  color: #0f172a;
}
.public-header {
  position: sticky;
  top: 0;
  z-index: 20;
  height: 64px;
  padding: 0 max(18px, calc((100vw - 960px) / 2));
  background: rgba(255, 255, 255, .96);
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  backdrop-filter: blur(10px);
}
.public-header__logo { width: 126px; height: auto; display: block; }
.member-link { color: var(--booking-primary-dark); font-size: .86rem; font-weight: 700; text-decoration: none; padding: 9px 12px; border: 1px solid #bcded9; border-radius: 999px; }
.public-booking-container { width: min(760px, calc(100% - 24px)); margin: 0 auto; padding: 32px 0 80px; }
.reservation-hero { text-align: center; margin-bottom: 26px; }
.reservation-kicker { color: var(--booking-primary); font-size: .78rem; font-weight: 900; letter-spacing: .16em; margin: 0 0 6px; }
.reservation-hero h1 { font-size: clamp(1.65rem, 5vw, 2rem); font-weight: 900; margin: 0 0 8px; }
.reservation-hero > p:last-child { color: #64748b; margin: 0; font-size: .95rem; }
.public-booking-notice { display: flex; gap: 10px; margin: 0 0 18px; padding: 16px; border: 1px solid #f1cf91; border-radius: 14px; background: #fff8e8; color: #594515; font-size: .9rem; line-height: 1.7; }
.public-booking-notice > i { flex: 0 0 auto; margin-top: 3px; color: #c48316; font-size: 1.15rem; }
.public-booking-notice > div { white-space: pre-wrap; }
.booking-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; margin-bottom: 18px; box-shadow: 0 8px 28px rgba(15, 23, 42, .055); }
.booking-card.muted { background: #fbfdfd; }
.fixed-store { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-radius: 11px; background: var(--booking-primary-soft); color: var(--booking-primary-dark); }
.fixed-store small { font-weight: 700; }
.fixed-store strong { text-align: right; }
.section-heading { display: flex; align-items: flex-start; gap: 11px; margin-bottom: 18px; }
.section-heading > span { width: 29px; height: 29px; flex: 0 0 29px; display: grid; place-items: center; border-radius: 50%; background: var(--booking-primary); color: #fff; font-size: .85rem; font-weight: 900; }
.section-heading h2 { font-size: 1.05rem; font-weight: 900; margin: 3px 0 3px; }
.section-heading p { color: #64748b; font-size: .78rem; margin: 0; }
.form-label { font-size: .9rem; font-weight: 800; }
.required { color: var(--booking-primary-dark); background: var(--booking-primary-soft); border-radius: 4px; padding: 2px 5px; font-size: .65rem; margin-left: 3px; }
.form-control, .form-select { border-color: #cbd5e1; min-height: 48px; }
.form-control:focus, .form-select:focus { border-color: var(--booking-primary); box-shadow: 0 0 0 .2rem rgba(42, 157, 143, .13); }
.date-scroller, .segment-scroller { display: flex; gap: 8px; overflow-x: auto; padding: 2px 1px 7px; scrollbar-width: none; scroll-snap-type: x proximity; }
.date-scroller::-webkit-scrollbar, .segment-scroller::-webkit-scrollbar { display: none; }
.date-chip { min-width: 68px; min-height: 62px; scroll-snap-align: start; border: 1px solid #d8e2e0; background: #fff; border-radius: 12px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #334155; }
.date-chip strong { font-size: .95rem; }
.date-chip small { font-size: .72rem; color: #64748b; }
.date-chip.weekend:not(.active) small { color: #d05656; }
.date-chip.active { background: var(--booking-primary); border-color: var(--booking-primary); color: #fff; box-shadow: 0 5px 14px rgba(42, 157, 143, .25); }
.date-chip.active small { color: #fff; }
.date-other { margin-top: 8px; color: #64748b; font-size: .82rem; }
.date-other summary { cursor: pointer; width: fit-content; }
.filter-panel { background: #f4f8f7; border-radius: 13px; padding: 10px; margin-bottom: 14px; }
.search-box { min-height: 46px; background: #fff; border: 1px solid #d7e2df; border-radius: 10px; padding: 0 12px; display: flex; align-items: center; gap: 8px; }
.search-box i { color: var(--booking-primary); font-size: 1.1rem; }
.search-box input { width: 100%; border: 0; outline: 0; background: transparent; font-size: .9rem; }
.segment-scroller { margin-top: 9px; padding-bottom: 1px; }
.segment-scroller button { min-height: 38px; flex: 0 0 auto; padding: 7px 14px; border-radius: 999px; border: 1px solid #cbdad7; background: #fff; color: #52616d; font-size: .82rem; font-weight: 700; }
.segment-scroller button.active { color: #fff; background: var(--booking-primary); border-color: var(--booking-primary); }
.cast-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.cast-card { position: relative; min-width: 0; min-height: 118px; padding: 13px 10px; border: 1px solid #dbe4e2; border-radius: 13px; background: #fff; color: inherit; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 7px; }
.cast-card img, .cast-placeholder { width: 58px; height: 58px; flex: 0 0 58px; border-radius: 50%; object-fit: cover; display: grid; place-items: center; background: #edf4f2; color: var(--booking-primary); font-size: 1.45rem; }
.cast-card__content { min-width: 0; display: flex; flex-direction: column; align-items: center; gap: 2px; }
.cast-card__content strong { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: .96rem; }
.cast-card__content small { max-width: 100%; color: #64748b; font-size: .7rem; line-height: 1.35; }
.cast-card__content .cast-area { color: var(--booking-primary-dark); font-weight: 800; }
.cast-card__check { position: absolute; top: 8px; right: 8px; color: var(--booking-primary); font-size: 1.2rem; }
.cast-card.active, .course-card.active, .option-card.active, .slot-button.active { border-color: var(--booking-primary); background: var(--booking-primary-soft); box-shadow: 0 0 0 2px rgba(42, 157, 143, .12); }
.course-grid, .option-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
.course-card, .option-card { min-height: 78px; padding: 12px; border: 1px solid #dbe4e2; border-radius: 12px; background: #fff; color: inherit; text-align: left; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.course-card span, .option-card span { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.course-card strong, .option-card strong { font-size: .87rem; line-height: 1.35; }
.course-card small, .option-card small { color: #64748b; font-size: .74rem; }
.course-card b { flex-shrink: 0; color: var(--booking-primary-dark); font-size: .85rem; }
.option-card i { flex-shrink: 0; color: var(--booking-primary); font-size: 1.3rem; }
.show-more { width: 100%; min-height: 44px; margin-top: 10px; border: 0; background: transparent; color: var(--booking-primary-dark); font-size: .86rem; font-weight: 800; }
.time-selection { border-top: 1px solid #e2e8f0; margin-top: 18px; padding-top: 16px; }
.slot-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.slot-button { min-height: 46px; padding: 8px 4px; border: 1px solid #d7e2df; background: #fff; border-radius: 10px; color: #334155; font-weight: 800; }
.empty-message { color: #64748b; background: #f4f8f7; border-radius: 11px; padding: 14px; margin: 0; font-size: .84rem; text-align: center; }
.summary { background: #f4f8f7; border-radius: 13px; padding: 13px 15px; }
.summary > div { display: flex; justify-content: space-between; gap: 16px; padding: 7px 0; }
.summary span { color: #64748b; }
.summary strong { text-align: right; }
.summary__total { border-top: 1px solid #d8e2e0; margin-top: 5px; padding-top: 12px !important; font-size: 1.15rem; }
.summary__total strong { color: var(--booking-primary-dark); }
.confirmation-note { display: flex; align-items: center; gap: 7px; color: #64748b; font-size: .76rem; line-height: 1.5; margin: 13px 2px; }
.confirmation-note i { color: var(--booking-primary); font-size: 1rem; }
.submit-button { width: 100%; min-height: 54px; border: 0; border-radius: 12px; padding: 12px 18px; background: var(--booking-primary); color: #fff; display: flex; align-items: center; justify-content: center; gap: 8px; font-size: 1rem; font-weight: 900; box-shadow: 0 7px 18px rgba(42, 157, 143, .24); }
.submit-button:hover:not(:disabled) { background: var(--booking-primary-dark); }
.submit-button:disabled { opacity: .65; }
.verification-card { max-width: 520px; margin: 0 auto; padding: 32px; }
.verification-icon { width: 72px; height: 72px; border-radius: 50%; margin: 0 auto 18px; display: grid; place-items: center; background: var(--booking-primary-soft); color: var(--booking-primary); font-size: 2rem; }
.verification-code { max-width: 260px; margin: 24px auto 0; text-align: center; font-size: 2rem; font-weight: 800; letter-spacing: .35em; padding-left: calc(.75rem + .35em); }
@media (min-width: 640px) {
  .cast-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .cast-card { flex-direction: row; text-align: left; align-items: center; }
  .cast-card__content { align-items: flex-start; }
}
@media (max-width: 576px) {
  .public-header { height: 58px; padding: 0 14px; }
  .public-header__logo { width: 112px; }
  .member-link { padding: 7px 10px; font-size: .78rem; }
  .public-booking-container { width: min(100% - 18px, 760px); padding: 22px 0 70px; }
  .reservation-hero { margin-bottom: 18px; }
  .reservation-hero > p:last-child { font-size: .84rem; }
  .booking-card { padding: 16px 14px; border-radius: 15px; margin-bottom: 12px; }
  .section-heading { margin-bottom: 15px; }
  .filter-panel { margin-left: -3px; margin-right: -3px; }
  .cast-grid, .course-grid, .option-grid { gap: 8px; }
  .course-card, .option-card { padding: 10px; }
  .course-card { align-items: flex-start; flex-direction: column; }
  .slot-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .verification-card { padding: 26px 18px; }
}
</style>
