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
const media = ref([])
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
  medium: '',
  memo: '',
})

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

const selectedCourse = computed(() =>
  courses.value.find(c => c.id === Number(form.value.course))
)

const selectedOptions = computed(() =>
  options.value.filter(o => form.value.options.includes(o.id))
)

const totalPrice = computed(() => {
  let total = selectedCourse.value ? selectedCourse.value.price : 0
  total += selectedOptions.value.reduce((sum, o) => sum + o.price, 0)
  return total
})

onMounted(async () => {
  try {
    const [custData, castData, courseData, optData, mdData] = await Promise.all([
      api.getCustomers(),
      api.getCasts(),
      api.getCourses(),
      api.getOptions(),
      api.getMedia(),
    ])
    customers.value = Array.isArray(custData) ? custData : []
    casts.value = Array.isArray(castData) ? castData : []
    courses.value = Array.isArray(courseData) ? courseData : []
    options.value = Array.isArray(optData) ? optData : []
    const allMedia = Array.isArray(mdData) ? mdData : []
    media.value = allMedia.filter(m => m.is_active)

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
  if (form.value.medium) {
    body.medium = Number(form.value.medium)
  }

  submitting.value = true
  try {
    const order = await api.createOrder(body)
    try {
      await api.confirmOrder(order.id)
    } catch (_) {
      // confirm 失敗しても詳細画面で手動承認できる
    }
    router.push(`/op/schedule?date=${form.value.startDate}&highlight=${order.id}`)
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
    <template #title>予約フロー</template>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else>

      <div class="alert alert-info">
        <strong>予約フロー</strong><br>
        1. 顧客を選択 → 2. 日時・キャスト・コースを選択 → 3. 予約を作成
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
            </div>

            <div class="mb-3">
              <label class="form-label">備考</label>
              <textarea class="form-control" rows="3" placeholder="備考やメモ..." v-model="form.memo"></textarea>
            </div>

            <hr>

            <div class="text-center mb-3">
              <h5 v-if="selectedCourse" class="mb-0">合計料金: <strong>{{ formatYen(totalPrice) }}</strong></h5>
            </div>
            <div class="d-flex gap-2">
              <router-link to="/op/schedule" class="btn btn-outline-secondary flex-fill">キャンセル</router-link>
              <button type="submit" class="btn btn-success flex-fill" :disabled="submitting">
                <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
                <i v-else class="ti ti-check"></i> 予約を確定
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>


<style scoped lang="scss">

.form-label{
  font-weight: bold;
}

.cast-scroll {
  display: grid;
  grid-auto-flow: column;
  grid-template-rows: repeat(3, auto);
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