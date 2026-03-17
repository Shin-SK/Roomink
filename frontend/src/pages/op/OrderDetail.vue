<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const props = defineProps({
  id: { type: [String, Number], required: true },
})

const router = useRouter()
const order = ref(null)
const loading = ref(true)
const error = ref('')
const acting = ref(false)
const mode = ref('confirm') // 'confirm' | 'edit'

// Edit mode
const editForm = ref({ start: '', end: '', cast: null, course: null, options: [], memo: '' })
const casts = ref([])
const courses = ref([])
const options = ref([])
const saving = ref(false)
const editError = ref('')

// Addon
const addonError = ref('')
const addonActing = ref(false)
const extensions = ref([])
const nominationFees = ref([])
const discounts = ref([])
const media = ref([])
const selectedExtension = ref(null)
const selectedNominationFee = ref(null)
const selectedDiscount = ref(null)
const selectedMedium = ref(null)

const statusMap = {
  REQUESTED: { text: '確定待ち', cls: 'badge-pending' },
  CONFIRMED: { text: '確定済', cls: 'badge-approved' },
  IN_PROGRESS: { text: '施術中', cls: 'badge-approved' },
  DONE: { text: '完了', cls: 'badge-approved' },
  CANCELLED: { text: 'キャンセル', cls: 'badge-banned' },
}

const displayStatus = computed(() => {
  if (!order.value) return statusMap.REQUESTED
  if (order.value.status === 'CONFIRMED' && order.value.is_unconfirmed) {
    return { text: 'キャスト確認待ち', cls: 'badge-attention' }
  }
  return statusMap[order.value.status] || { text: order.value.status, cls: 'bg-secondary' }
})

const canConfirm = computed(() => order.value?.status === 'REQUESTED')
const canCancel = computed(() =>
  order.value && !['DONE', 'CANCELLED'].includes(order.value.status)
)
const canDone = computed(() =>
  order.value && ['CONFIRMED', 'IN_PROGRESS'].includes(order.value.status)
)
const canEdit = computed(() =>
  order.value && !['DONE', 'CANCELLED'].includes(order.value.status)
)

onMounted(async () => {
  try {
    const [o, castData, courseData, optData, exts, nfs, dcs, mds] = await Promise.all([
      api.getOrder(props.id),
      api.getCasts(),
      api.getCourses(),
      api.getOptions(),
      api.getExtensions(),
      api.getNominationFees(),
      api.getDiscounts(),
      api.getMedia(),
    ])
    casts.value = Array.isArray(castData) ? castData : []
    courses.value = Array.isArray(courseData) ? courseData : []
    options.value = Array.isArray(optData) ? optData : []
    order.value = o
    extensions.value = Array.isArray(exts) ? exts : []
    nominationFees.value = Array.isArray(nfs) ? nfs : []
    discounts.value = Array.isArray(dcs) ? dcs : []
    const allMedia = Array.isArray(mds) ? mds : []
    media.value = allMedia.filter(m => m.is_active)
    selectedExtension.value = o.extension ?? null
    selectedNominationFee.value = o.nomination_fee ?? null
    selectedDiscount.value = o.discount ?? null
    selectedMedium.value = o.medium ?? null
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function toLocalInput(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function openEdit() {
  editError.value = ''
  editForm.value = {
    start: toLocalInput(order.value.start),
    end: toLocalInput(order.value.end),
    cast: order.value.cast,
    course: order.value.course,
    options: order.value.option_ids || [],
    memo: order.value.memo || '',
  }
  mode.value = 'edit'
}

function toggleEditOption(optId) {
  const idx = editForm.value.options.indexOf(optId)
  if (idx >= 0) editForm.value.options.splice(idx, 1)
  else editForm.value.options.push(optId)
}

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}

function closeEdit() {
  mode.value = 'confirm'
  editError.value = ''
}

async function saveEdit() {
  editError.value = ''
  saving.value = true
  try {
    order.value = await api.updateOrder(props.id, editForm.value)
    mode.value = 'confirm'
  } catch (e) {
    editError.value = e.message
  } finally {
    saving.value = false
  }
}

async function doConfirm() {
  if (!confirm('この予約を確定しますか？')) return
  acting.value = true
  try {
    order.value = await api.confirmOrder(props.id)
  } catch (e) {
    alert(e.message)
  } finally {
    acting.value = false
  }
}

async function doCancel() {
  if (!confirm('この予約をキャンセルしますか？')) return
  acting.value = true
  try {
    order.value = await api.cancelOrder(props.id)
  } catch (e) {
    alert(e.message)
  } finally {
    acting.value = false
  }
}

async function doDone() {
  if (!confirm('この予約を完了にしますか？')) return
  acting.value = true
  try {
    order.value = await api.doneOrder(props.id)
  } catch (e) {
    alert(e.message)
  } finally {
    acting.value = false
  }
}

function formatDt(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

async function doApplyExtension() {
  addonError.value = ''
  addonActing.value = true
  try {
    order.value = await api.applyExtension(props.id, selectedExtension.value)
  } catch (e) {
    addonError.value = e.message
  } finally {
    addonActing.value = false
  }
}

async function doApplyNominationFee() {
  addonError.value = ''
  addonActing.value = true
  try {
    order.value = await api.applyNominationFee(props.id, selectedNominationFee.value)
  } catch (e) {
    addonError.value = e.message
  } finally {
    addonActing.value = false
  }
}

async function doApplyDiscount() {
  addonError.value = ''
  addonActing.value = true
  try {
    order.value = await api.applyDiscount(props.id, selectedDiscount.value)
  } catch (e) {
    addonError.value = e.message
  } finally {
    addonActing.value = false
  }
}

async function doApplyMedium() {
  addonError.value = ''
  addonActing.value = true
  try {
    order.value = await api.applyMedium(props.id, selectedMedium.value)
  } catch (e) {
    addonError.value = e.message
  } finally {
    addonActing.value = false
  }
}
</script>

<template>
  <LayoutOperator>
    <template #title>予約詳細</template>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

    <template v-else-if="order">
      <main class="order">

        <!-- ========== 確認モード ========== -->
        <template v-if="mode === 'confirm'">

          <!-- ステータスバッジ -->
          <div class="text-center mb-3">
            <span
              class="badge fs-6 px-3 py-2"
              :class="displayStatus.cls"
            >{{ displayStatus.text }}</span>
          </div>

          <!-- サマリー -->
          <div class="card mb-3">
            <div class="card-body p-0">
              <table class="table mb-0">
                <tbody>
                  <tr>
                    <th>予約日時</th>
                    <td>{{ formatDt(order.start) }} – {{ formatTime(order.end) }}</td>
                  </tr>
                  <tr>
                    <th>顧客</th>
                    <td>{{ order.customer_label }}</td>
                  </tr>
                  <tr>
                    <th>キャスト</th>
                    <td>{{ order.cast_name }}</td>
                  </tr>
                  <tr>
                    <th>ルーム</th>
                    <td>{{ order.room_name }}</td>
                  </tr>
                  <tr>
                    <th>コース</th>
                    <td>{{ order.course_name }}</td>
                  </tr>
                  <tr v-if="order.options && order.options.length">
                    <th>オプション</th>
                    <td>{{ order.options.join(', ') }}</td>
                  </tr>
                  <tr v-if="order.extension_name">
                    <th>延長</th>
                    <td>{{ order.extension_name }}</td>
                  </tr>
                  <tr v-if="order.nomination_fee_name">
                    <th>指名料</th>
                    <td>{{ order.nomination_fee_name }}</td>
                  </tr>
                  <tr v-if="order.discount_name">
                    <th>割引</th>
                    <td>{{ order.discount_name }}</td>
                  </tr>
                  <tr v-if="order.medium_name">
                    <th>媒体</th>
                    <td>{{ order.medium_name }}</td>
                  </tr>
                  <tr v-if="order.memo">
                    <th>メモ</th>
                    <td style="white-space: pre-wrap;">{{ order.memo }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 料金 -->
          <div class="card mb-4">
            <div class="card-body p-0">
              <table class="table table-sm mb-0">
                <tbody>
                  <tr>
                    <td>コース（{{ order.course_name }}）</td>
                    <td class="text-end">{{ order.course_price.toLocaleString() }}円</td>
                  </tr>
                  <tr v-if="order.options_price > 0">
                    <td>オプション</td>
                    <td class="text-end">{{ order.options_price.toLocaleString() }}円</td>
                  </tr>
                  <tr v-if="order.extension_name">
                    <td>延長（{{ order.extension_name }}）</td>
                    <td class="text-end">{{ order.extension_price.toLocaleString() }}円</td>
                  </tr>
                  <tr v-if="order.nomination_fee_name">
                    <td>指名料（{{ order.nomination_fee_name }}）</td>
                    <td class="text-end">{{ order.nomination_fee_price.toLocaleString() }}円</td>
                  </tr>
                  <tr v-if="order.discount_name">
                    <td>割引（{{ order.discount_name }}）</td>
                    <td class="text-end text-danger">−{{ order.discount_amount.toLocaleString() }}円</td>
                  </tr>
                  <tr class="fw-bold">
                    <td>合計</td>
                    <td class="text-end">{{ order.total_price.toLocaleString() }}円</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- アクション -->
          <div class="d-flex flex-column gap-2 mb-3">
            <button
              v-if="canConfirm"
              class="btn btn-success btn-lg w-100"
              :disabled="acting"
              @click="doConfirm"
            >
              <i class="ti ti-check"></i> 予約確定
            </button>
            <button
              v-if="canDone"
              class="btn btn-primary btn-lg w-100"
              :disabled="acting"
              @click="doDone"
            >
              <i class="ti ti-circle-check"></i> 施術終了
            </button>
          </div>

          <div class="d-flex gap-2 mb-4">
            <button
              v-if="canEdit"
              class="btn btn-outline-secondary flex-fill"
              @click="openEdit"
            >
              <i class="ti ti-edit"></i> 修正する
            </button>
            <button
              v-if="canCancel"
              class="btn btn-outline-danger flex-fill"
              :disabled="acting"
              @click="doCancel"
            >
              <i class="ti ti-x"></i> キャンセル
            </button>
          </div>

          <router-link to="/op/schedule" class="btn btn-outline-secondary w-100 mb-2">
            <i class="ti ti-calendar"></i> スケジュールに戻る
          </router-link>

          <div class="text-muted small text-center mt-3">
            Order #{{ order.id }} / 申請: {{ formatDt(order.created_at) }}
          </div>
        </template>

        <!-- ========== 修正モード ========== -->
        <template v-if="mode === 'edit'">

          <div class="d-flex align-items-center justify-content-between mb-3">
            <h5 class="mb-0"><i class="ti ti-edit"></i> 予約修正</h5>
            <button class="btn btn-outline-secondary btn-sm" @click="closeEdit">
              <i class="ti ti-arrow-left"></i> 戻る
            </button>
          </div>

          <!-- 基本情報編集 -->
          <div class="card mb-4">
            <div class="card-header">
              <i class="ti ti-file-text"></i> 基本情報
            </div>
            <div class="card-body">
              <div v-if="editError" class="alert alert-danger py-2 px-3 mb-3" style="font-size: 0.875rem;">
                {{ editError }}
              </div>
              <form @submit.prevent="saveEdit">
                <div class="mb-3">
                  <label class="form-label">開始日時</label>
                  <input v-model="editForm.start" type="datetime-local" class="form-control" required>
                </div>
                <div class="mb-3">
                  <label class="form-label">終了日時</label>
                  <input v-model="editForm.end" type="datetime-local" class="form-control" required>
                </div>
                <div class="mb-3">
                  <label class="form-label">担当キャスト</label>
                  <select v-model="editForm.cast" class="form-select" required>
                    <option v-for="c in casts" :key="c.id" :value="c.id">{{ c.name }}</option>
                  </select>
                </div>
                <div class="mb-3">
                  <label class="form-label">コース</label>
                  <select v-model="editForm.course" class="form-select" required>
                    <option v-for="c in courses" :key="c.id" :value="c.id">
                      {{ c.name }}（{{ formatYen(c.price) }}）
                    </option>
                  </select>
                </div>
                <div class="mb-3" v-if="options.length">
                  <label class="form-label">オプション</label>
                  <div class="d-flex gap-2 flex-wrap">
                    <button
                      v-for="opt in options"
                      :key="opt.id"
                      type="button"
                      class="btn btn-sm"
                      :class="editForm.options.includes(opt.id) ? 'btn-primary' : 'btn-outline-secondary'"
                      @click="toggleEditOption(opt.id)"
                    >
                      {{ opt.name }}（+{{ formatYen(opt.price) }}）
                    </button>
                  </div>
                </div>
                <div class="mb-3">
                  <label class="form-label">メモ</label>
                  <textarea v-model="editForm.memo" class="form-control" rows="3"></textarea>
                </div>
                <button type="submit" class="btn btn-primary w-100" :disabled="saving">
                  {{ saving ? '保存中...' : '保存' }}
                </button>
              </form>
            </div>
          </div>

          <!-- addon 適用 -->
          <div class="card mb-4">
            <div class="card-header">
              <i class="ti ti-adjustments"></i> addon 適用
            </div>
            <div class="card-body">
              <div v-if="addonError" class="alert alert-danger py-2 px-3 mb-3" style="font-size:0.875rem;">{{ addonError }}</div>

              <div class="mb-3">
                <label class="form-label small fw-bold">延長</label>
                <div class="d-flex gap-2">
                  <select v-model="selectedExtension" class="form-select form-select-sm">
                    <option :value="null">なし</option>
                    <option v-for="e in extensions" :key="e.id" :value="e.id">
                      {{ e.name }}（{{ e.duration }}分 / {{ e.price.toLocaleString() }}円）
                    </option>
                  </select>
                  <button class="btn btn-outline-primary btn-sm" :disabled="addonActing" @click="doApplyExtension">適用</button>
                </div>
              </div>

              <div class="mb-3">
                <label class="form-label small fw-bold">指名料</label>
                <div class="d-flex gap-2">
                  <select v-model="selectedNominationFee" class="form-select form-select-sm">
                    <option :value="null">なし</option>
                    <option v-for="n in nominationFees" :key="n.id" :value="n.id">
                      {{ n.name }}（{{ n.price.toLocaleString() }}円）
                    </option>
                  </select>
                  <button class="btn btn-outline-primary btn-sm" :disabled="addonActing" @click="doApplyNominationFee">適用</button>
                </div>
              </div>

              <div class="mb-3">
                <label class="form-label small fw-bold">割引</label>
                <div class="d-flex gap-2">
                  <select v-model="selectedDiscount" class="form-select form-select-sm">
                    <option :value="null">なし</option>
                    <option v-for="d in discounts" :key="d.id" :value="d.id">
                      {{ d.name }}（{{ d.discount_type === 'percent' ? d.value + '%' : d.value.toLocaleString() + '円' }}引き）
                    </option>
                  </select>
                  <button class="btn btn-outline-primary btn-sm" :disabled="addonActing" @click="doApplyDiscount">適用</button>
                </div>
              </div>

              <div class="mb-0">
                <label class="form-label small fw-bold">媒体</label>
                <div class="d-flex gap-2">
                  <select v-model="selectedMedium" class="form-select form-select-sm">
                    <option :value="null">なし</option>
                    <option v-for="m in media" :key="m.id" :value="m.id">
                      {{ m.name }}
                    </option>
                  </select>
                  <button class="btn btn-outline-primary btn-sm" :disabled="addonActing" @click="doApplyMedium">適用</button>
                </div>
              </div>
            </div>
          </div>

        </template>

      </main>
    </template>
  </LayoutOperator>
</template>
