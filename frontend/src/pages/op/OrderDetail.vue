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

// Edit mode
const editing = ref(false)
const editForm = ref({ start: '', end: '', cast: null, memo: '' })
const casts = ref([])
const saving = ref(false)
const editError = ref('')

const statusMap = {
  REQUESTED: { text: '申請中', cls: 'badge-pending' },
  CONFIRMED: { text: '承認済', cls: 'badge-approved' },
  IN_PROGRESS: { text: '施術中', cls: 'badge-approved' },
  DONE: { text: '完了', cls: 'badge-approved' },
  CANCELLED: { text: 'キャンセル', cls: 'badge-banned' },
}

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
    order.value = await api.getOrder(props.id)
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

async function startEdit() {
  editError.value = ''
  editForm.value = {
    start: toLocalInput(order.value.start),
    end: toLocalInput(order.value.end),
    cast: order.value.cast,
    memo: order.value.memo || '',
  }
  if (!casts.value.length) {
    casts.value = await api.getCasts()
  }
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  editError.value = ''
}

async function saveEdit() {
  editError.value = ''
  saving.value = true
  try {
    order.value = await api.updateOrder(props.id, editForm.value)
    editing.value = false
  } catch (e) {
    editError.value = e.message
  } finally {
    saving.value = false
  }
}

async function doConfirm() {
  if (!confirm('この予約を承認しますか？')) return
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

function goBack() {
  router.back()
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
        <div class="row">
          <!-- 左カラム：予約情報 -->
          <div class="col-lg-8">

            <!-- 予約基本情報 -->
            <div class="card mb-4">
              <div class="card-header">
                <i class="ti ti-file-text"></i> 予約情報
              </div>

              <!-- 閲覧モード -->
              <div v-if="!editing" class="card-body">
                <table class="table mb-0">
                  <tbody>
                    <tr>
                      <th style="width: 150px;">予約日時</th>
                      <td>{{ formatDt(order.start) }} – {{ formatTime(order.end) }}</td>
                    </tr>
                    <tr>
                      <th>コース</th>
                      <td>{{ order.course_name }}</td>
                    </tr>
                    <tr>
                      <th>オプション</th>
                      <td>{{ order.options && order.options.length ? order.options.join(', ') : 'なし' }}</td>
                    </tr>
                    <tr>
                      <th>ステータス</th>
                      <td>
                        <span
                          class="badge"
                          :class="statusMap[order.status]?.cls || 'bg-secondary'"
                        >{{ statusMap[order.status]?.text || order.status }}</span>
                      </td>
                    </tr>
                    <tr>
                      <th>顧客</th>
                      <td>{{ order.customer_label }}</td>
                    </tr>
                    <tr>
                      <th>メモ</th>
                      <td>{{ order.memo || '—' }}</td>
                    </tr>
                    <tr>
                      <th>申請日時</th>
                      <td>{{ formatDt(order.created_at) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <!-- 編集モード -->
              <div v-else class="card-body">
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
                    <label class="form-label">メモ</label>
                    <textarea v-model="editForm.memo" class="form-control" rows="3"></textarea>
                  </div>
                  <div class="d-flex gap-2">
                    <button type="submit" class="btn btn-primary" :disabled="saving">
                      {{ saving ? '保存中...' : '保存' }}
                    </button>
                    <button type="button" class="btn btn-outline-secondary" @click="cancelEdit" :disabled="saving">
                      キャンセル
                    </button>
                  </div>
                </form>
              </div>
            </div>

            <!-- 運営メモ -->
            <div class="card mb-4">
              <div class="card-header">
                <i class="ti ti-notes"></i> 運営メモ
              </div>
              <div class="card-body">
                <p class="mb-0" style="white-space: pre-wrap;">{{ order.memo || '—' }}</p>
              </div>
            </div>

          </div>

          <!-- 右カラム：アクション -->
          <div class="col-lg-4">

            <!-- アクションカード -->
            <div class="card mb-4">
              <div class="card-header">
                <i class="ti ti-bolt"></i> アクション
              </div>
              <div class="card-body">
                <div class="d-flex flex-column gap-2">
                  <button
                    class="btn btn-outline-primary w-100"
                    :disabled="!canEdit || acting || editing"
                    @click="startEdit"
                  >
                    <i class="ti ti-edit"></i> 編集
                  </button>
                  <button
                    class="btn btn-success w-100"
                    :disabled="!canConfirm || acting || editing"
                    @click="doConfirm"
                  >
                    <i class="ti ti-check"></i> 承認
                  </button>
                  <button
                    class="btn btn-danger w-100"
                    :disabled="!canCancel || acting || editing"
                    @click="doCancel"
                  >
                    <i class="ti ti-x"></i> キャンセル
                  </button>
                  <button
                    class="btn btn-primary w-100"
                    :disabled="!canDone || acting || editing"
                    @click="doDone"
                  >
                    <i class="ti ti-circle-check"></i> 完了
                  </button>
                  <hr>
                  <router-link to="/op/schedule" class="btn btn-outline-secondary w-100">
                    <i class="ti ti-calendar"></i> スケジュールに戻る
                  </router-link>
                  <router-link to="/op/phone" class="btn btn-outline-secondary w-100">
                    <i class="ti ti-phone"></i> 新規電話予約
                  </router-link>
                </div>
              </div>
            </div>

            <!-- ID情報 -->
            <div class="card mb-4">
              <div class="card-header">
                <i class="ti ti-info-circle"></i> ID情報
              </div>
              <div class="card-body small text-muted">
                <div>Order ID: {{ order.id }}</div>
                <div>Cast ID: {{ order.cast }}</div>
                <div>Room ID: {{ order.room }}</div>
                <div>Customer ID: {{ order.customer }}</div>
                <div>Course ID: {{ order.course }}</div>
              </div>
            </div>

          </div>
        </div>
      </main>
    </template>
  </LayoutOperator>
</template>
