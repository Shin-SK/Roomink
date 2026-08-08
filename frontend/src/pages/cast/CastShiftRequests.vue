<script setup>
import { ref, onMounted } from 'vue'
import LayoutCast from '../../components/LayoutCast.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const requests = ref([])
const rooms = ref([])

const showForm = ref(false)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

function emptyForm() {
  return { date: new Date().toISOString().slice(0, 10), start_time: '', end_time: '', desired_room: '', memo: '' }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getCastShiftRequests()
    requests.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const r = await api.getRooms()
    rooms.value = Array.isArray(r) ? r : []
  } catch (e) {
    error.value = e.message
  }
  await load()
})

function openCreate() {
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function normalizeExtendedEndTime(value) {
  const match = /^(\d{2}):(\d{2})$/.exec(value || '')
  if (!match) throw new Error('終了時間はHH:MM形式で入力してください（例: 23:00 / 29:00）')

  const hour = Number(match[1])
  const minute = Number(match[2])
  if (minute > 59 || hour > 29 || (hour === 29 && minute !== 0)) {
    throw new Error('終了時間は00:00〜29:00で入力してください')
  }

  return {
    end_time: `${String(hour % 24).padStart(2, '0')}:${String(minute).padStart(2, '0')}`,
    end_day_offset: hour >= 24 ? 1 : 0,
  }
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const normalizedEnd = normalizeExtendedEndTime(form.value.end_time)
    const body = {
      date: form.value.date,
      start_time: form.value.start_time,
      ...normalizedEnd,
      memo: form.value.memo,
    }
    if (form.value.desired_room) body.desired_room = Number(form.value.desired_room)
    await api.createCastShiftRequest(body)
    showForm.value = false
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function onCancel(id) {
  if (!confirm('この申請を取消しますか？')) return
  try {
    await api.cancelCastShiftRequest(id)
    await load()
  } catch (e) {
    alert(e.message)
  }
}

const statusLabel = { REQUESTED: '申請中', APPROVED: '承認済', REJECTED: '却下', CANCELLED: '取消' }
const statusClass = { REQUESTED: 'bg-warning text-dark', APPROVED: 'bg-success', REJECTED: 'bg-danger', CANCELLED: 'bg-secondary' }

function formatDateTime(s) {
  if (!s) return ''
  return s.slice(0, 16).replace('T', ' ')
}
</script>

<template>
  <LayoutCast>
      <div v-if="error" class="alert alert-danger">{{ error }}</div>

      <div class="d-flex justify-content-between align-items-center mb-3 mt-3">
        <h5 class="mb-0"><i class="ti ti-calendar-plus"></i> シフト申請一覧</h5>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus"></i> 申請
        </button>
      </div>

      <div v-if="loading" class="text-center py-5">
        <div class="spinner-border text-primary"></div>
      </div>

      <div v-else-if="!requests.length" class="text-muted text-center py-4">
        シフト申請はありません
      </div>

      <div v-else>
        <div v-for="r in requests" :key="r.id" class="card mb-3">
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-start mb-2">
              <div>
                <div class="fw-bold">{{ r.date }}</div>
                <div class="small text-muted">{{ r.start_time?.slice(0,5) }} - {{ r.end_time_extended || r.end_time?.slice(0,5) }}</div>
              </div>
              <span class="badge" :class="statusClass[r.status]">{{ statusLabel[r.status] }}</span>
            </div>
            <div class="small text-muted mb-1">申請日時: {{ formatDateTime(r.created_at) }}</div>
            <div v-if="r.desired_room_name" class="small text-muted mb-1">
              <i class="ti ti-door"></i> 希望: {{ r.desired_room_name }}
            </div>
            <div v-if="r.status === 'APPROVED'" class="small bg-success bg-opacity-10 p-2 rounded mb-2">
              <div class="fw-bold mb-1"><i class="ti ti-check"></i> 承認内容</div>
              <template v-if="r.approved_date">
                <div>{{ r.approved_date }} {{ r.approved_start_time?.slice(0,5) }} - {{ r.approved_end_time_extended || r.approved_end_time?.slice(0,5) }}</div>
                <div>部屋: {{ r.approved_room_name || '-' }}</div>
              </template>
              <div v-else class="text-muted">承認済み（旧データのため詳細未記録）</div>
            </div>
            <div v-if="r.memo" class="small bg-light p-2 rounded mb-2">{{ r.memo }}</div>
            <div v-if="r.admin_memo" class="small bg-info bg-opacity-10 p-2 rounded mb-2">
              <i class="ti ti-message"></i> 運営: {{ r.admin_memo }}
            </div>
            <div v-if="r.decided_at" class="small text-muted mb-2">決定日時: {{ formatDateTime(r.decided_at) }}</div>
            <button
              v-if="r.status === 'REQUESTED'"
              class="btn btn-outline-danger btn-sm w-100"
              @click="onCancel(r.id)"
            >
              <i class="ti ti-x"></i> 取消
            </button>
          </div>
        </div>
      </div>

      <!-- Form modal -->
      <div v-if="showForm" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showForm = false">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">シフト申請</h5>
              <button type="button" class="btn-close" @click="showForm = false"></button>
            </div>
            <div class="modal-body">
              <div v-if="formError" class="alert alert-danger">{{ formError }}</div>
              <div class="mb-3">
                <label class="form-label">日付</label>
                <input v-model="form.date" type="date" class="form-control" />
              </div>
              <div class="row">
                <div class="col-6 mb-3">
                  <label class="form-label">開始時間</label>
                  <input v-model="form.start_time" type="time" step="1800" class="form-control" />
                </div>
                <div class="col-6 mb-3">
                  <label class="form-label">終了時間</label>
                  <input
                    v-model="form.end_time"
                    type="text"
                    inputmode="numeric"
                    maxlength="5"
                    placeholder="例: 23:00 / 29:00"
                    class="form-control"
                  />
                  <div class="form-text">翌朝は24:00〜29:00で入力できます。</div>
                </div>
              </div>
              <div class="mb-3">
                <label class="form-label">希望部屋（任意）</label>
                <select v-model="form.desired_room" class="form-select">
                  <option value="">指定なし</option>
                  <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
                </select>
              </div>
              <div class="mb-3">
                <label class="form-label">メモ（任意）</label>
                <textarea v-model="form.memo" class="form-control" rows="2"></textarea>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" @click="showForm = false">キャンセル</button>
              <button class="btn btn-primary" :disabled="saving" @click="onSave">
                {{ saving ? '送信中...' : '申請する' }}
              </button>
            </div>
          </div>
        </div>
      </div>
  </LayoutCast>
</template>
