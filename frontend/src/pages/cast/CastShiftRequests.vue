<script setup>
import { ref, onMounted } from 'vue'
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
    requests.value = Array.isArray(data) ? data : data.results || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const r = await api.getRooms()
    rooms.value = Array.isArray(r) ? r : r.results || []
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

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const body = {
      date: form.value.date,
      start_time: form.value.start_time,
      end_time: form.value.end_time,
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
</script>

<template>
  <div class="cast-layout">
    <header class="cast-header">
      <div class="cast-nav d-flex align-items-center gap-3">
        <a href="/cast/today"><img src="/icon.svg" alt="" style="width: 24px;"></a>
        <span class="fw-bold">シフト申請</span>
      </div>
    </header>

    <main class="cast-content container">
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
                <div class="small text-muted">{{ r.start_time?.slice(0,5) }} - {{ r.end_time?.slice(0,5) }}</div>
              </div>
              <span class="badge" :class="statusClass[r.status]">{{ statusLabel[r.status] }}</span>
            </div>
            <div v-if="r.desired_room_name" class="small text-muted mb-1">
              <i class="ti ti-door"></i> 希望: {{ r.desired_room_name }}
            </div>
            <div v-if="r.memo" class="small bg-light p-2 rounded mb-2">{{ r.memo }}</div>
            <div v-if="r.admin_memo" class="small bg-info bg-opacity-10 p-2 rounded mb-2">
              <i class="ti ti-message"></i> 運営: {{ r.admin_memo }}
            </div>
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
                  <input v-model="form.start_time" type="time" class="form-control" />
                </div>
                <div class="col-6 mb-3">
                  <label class="form-label">終了時間</label>
                  <input v-model="form.end_time" type="time" class="form-control" />
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
    </main>

    <footer class="footer position-fixed bottom-0 w-100 p-3 bg-white border-top">
      <div class="container d-flex align-items-center justify-content-between">
        <button class="btn border-0 p-0">
          <a href="/cast/today" class="nav-link">
            <i class="ti ti-home"></i>
            <small>マイページ</small>
          </a>
        </button>
        <button class="btn border-0 p-0">
          <a href="/cast/shift-requests" class="nav-link active">
            <i class="ti ti-calendar-plus"></i>
            <small>シフト申請</small>
          </a>
        </button>
      </div>
    </footer>
  </div>
</template>
