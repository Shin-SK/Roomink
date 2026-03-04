<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const router = useRouter()
const route = useRoute()

const customers = ref([])
const casts = ref([])
const courses = ref([])
const options = ref([])
const loading = ref(true)
const submitting = ref(false)
const errorMsg = ref('')
const phoneHint = ref('')

const form = ref({
  customer: '',
  cast: '',
  course: '',
  startDate: new Date().toISOString().slice(0, 10),
  startTime: '15:00',
  options: [],
  memo: '',
})

const selectedCourse = computed(() =>
  courses.value.find(c => c.id === Number(form.value.course))
)

onMounted(async () => {
  try {
    const [custData, castData, courseData, optData] = await Promise.all([
      api.getCustomers(),
      api.getCasts(),
      api.getCourses(),
      api.getOptions(),
    ])
    customers.value = Array.isArray(custData) ? custData : custData.results || []
    casts.value = Array.isArray(castData) ? castData : castData.results || []
    courses.value = Array.isArray(courseData) ? courseData : courseData.results || []
    options.value = Array.isArray(optData) ? optData : optData.results || []

    // ?phone= auto-select
    const qPhone = route.query.phone
    if (qPhone) {
      phoneHint.value = qPhone
      const match = customers.value.find(c => c.phone === qPhone)
      if (match) {
        form.value.customer = match.id
      }
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
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
  if (!form.value.customer || !form.value.cast || !form.value.course) {
    errorMsg.value = '顧客・キャスト・コースは必須です'
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
  if (form.value.options.length) {
    body.options = form.value.options
  }

  submitting.value = true
  try {
    await api.createOrder(body)
    router.push('/op/schedule')
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    submitting.value = false
  }
}

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}
</script>

<template>
  <LayoutOperator>
    <template #title>Phone Booking</template>
    <template #actions>
      <span class="text-muted">電話予約クイック作成</span>
    </template>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else class="container">

      <div class="alert alert-info">
        <strong>電話予約フロー</strong><br>
        1. 顧客を選択 → 2. 日時・セラピスト・コースを選択 → 3. 承認済み予約を作成
      </div>

      <div v-if="phoneHint && !form.customer" class="alert alert-warning d-flex justify-content-between align-items-center">
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

      <!-- Error -->
      <div v-if="errorMsg" class="alert alert-danger">
        {{ errorMsg }}
      </div>

      <!-- STEP 1: 顧客検索 -->
      <div class="card">
        <div class="card-header">STEP 1: 顧客検索</div>
        <div class="card-body">
          <div class="row">
            <div class="col-md-6">
              <div class="mb-3">
                <label class="form-label">顧客</label>
                <select class="form-select" v-model="form.customer">
                  <option value="">-- 選択してください --</option>
                  <option v-for="c in customers" :key="c.id" :value="c.id">
                    {{ c.display_name || c.phone }}{{ c.flag === 'ATTENTION' ? ' (要注意)' : '' }}{{ c.flag === 'BAN' ? ' (BAN)' : '' }}
                  </option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- STEP 2: 予約内容入力 -->
      <div class="card" v-show="form.customer">
        <div class="card-header">STEP 2: 予約内容入力</div>
        <div class="card-body">
          <form @submit.prevent="submit">
            <div class="row">
              <div class="col-md-6">
                <div class="mb-3">
                  <label class="form-label">予約日</label>
                  <input type="date" class="form-control" v-model="form.startDate">
                </div>
              </div>
              <div class="col-md-3">
                <div class="mb-3">
                  <label class="form-label">開始時刻</label>
                  <input type="time" class="form-control" v-model="form.startTime">
                </div>
              </div>
            </div>

            <div class="row">
              <div class="col-md-6">
                <div class="mb-3">
                  <label class="form-label">セラピスト</label>
                  <select class="form-select" v-model="form.cast">
                    <option value="">-- 選択 --</option>
                    <option v-for="c in casts" :key="c.id" :value="c.id">{{ c.name }}</option>
                  </select>
                </div>
              </div>
              <div class="col-md-6">
                <div class="mb-3">
                  <label class="form-label">コース</label>
                  <select class="form-select" v-model="form.course">
                    <option value="">-- 選択 --</option>
                    <option v-for="c in courses" :key="c.id" :value="c.id">
                      {{ c.name }}（{{ formatYen(c.price) }}）
                    </option>
                  </select>
                </div>
              </div>
            </div>

            <div class="mb-3" v-if="options.length">
              <label class="form-label">オプション</label>
              <div class="d-flex gap-3">
                <div v-for="opt in options" :key="opt.id" class="form-check">
                  <input
                    class="form-check-input"
                    type="checkbox"
                    :id="'op-' + opt.id"
                    :checked="form.options.includes(opt.id)"
                    @change="toggleOption(opt.id)"
                  >
                  <label class="form-check-label" :for="'op-' + opt.id">
                    {{ opt.name }}（+{{ formatYen(opt.price) }}）
                  </label>
                </div>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label">備考</label>
              <textarea class="form-control" rows="3" placeholder="備考やメモ..." v-model="form.memo"></textarea>
            </div>

            <hr>

            <div class="d-flex justify-content-between align-items-center">
              <div>
                <h5 v-if="selectedCourse" class="mb-0">合計料金: <strong>{{ formatYen(selectedCourse.price) }}</strong></h5>
              </div>
              <div class="btn-group gap-2">
                <router-link to="/op/schedule" class="btn btn-outline-secondary">キャンセル</router-link>
                <button type="submit" class="btn btn-success" :disabled="submitting">
                  <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
                  <i v-else class="ti ti-check"></i> 予約を確定
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>
