<script setup>
import { ref, onMounted, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const requests = ref([])
const rooms = ref([])

const filterStatus = ref('REQUESTED')

async function loadRooms() {
  const r = await api.getRooms()
  rooms.value = Array.isArray(r) ? r : []
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = filterStatus.value ? `status=${filterStatus.value}` : ''
    const data = await api.getOpShiftRequests(params)
    requests.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try { await loadRooms() } catch (e) { error.value = e.message }
  await load()
})

watch(filterStatus, () => load())

// Approve modal
const showApprove = ref(false)
const approveTarget = ref(null)
const approveRoom = ref('')
const approveAdminMemo = ref('')
const approveError = ref('')
const approving = ref(false)

function openApprove(r) {
  approveTarget.value = r
  approveRoom.value = r.desired_room || ''
  approveAdminMemo.value = ''
  approveError.value = ''
  showApprove.value = true
}

async function doApprove() {
  if (!approveRoom.value) { approveError.value = '部屋を選択してください'; return }
  approving.value = true
  approveError.value = ''
  try {
    await api.approveShiftRequest(approveTarget.value.id, {
      room: Number(approveRoom.value),
      admin_memo: approveAdminMemo.value,
    })
    showApprove.value = false
    await load()
  } catch (e) {
    approveError.value = e.message
  } finally {
    approving.value = false
  }
}

// Reject modal
const showReject = ref(false)
const rejectTarget = ref(null)
const rejectAdminMemo = ref('')
const rejectError = ref('')
const rejecting = ref(false)

function openReject(r) {
  rejectTarget.value = r
  rejectAdminMemo.value = ''
  rejectError.value = ''
  showReject.value = true
}

async function doReject() {
  rejecting.value = true
  rejectError.value = ''
  try {
    await api.rejectShiftRequest(rejectTarget.value.id, {
      admin_memo: rejectAdminMemo.value,
    })
    showReject.value = false
    await load()
  } catch (e) {
    rejectError.value = e.message
  } finally {
    rejecting.value = false
  }
}

const statusLabel = { REQUESTED: '申請中', APPROVED: '承認済', REJECTED: '却下', CANCELLED: '取消' }
const statusClass = { REQUESTED: 'bg-warning text-dark', APPROVED: 'bg-success', REJECTED: 'bg-danger', CANCELLED: 'bg-secondary' }
</script>

<template>
  <LayoutOperator>
    <template #title>シフト申請管理</template>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-calendar-check"></i> シフト申請一覧</span>
        <select v-model="filterStatus" class="form-select form-select-sm" style="width: auto;">
          <option value="">すべて</option>
          <option value="REQUESTED">申請中</option>
          <option value="APPROVED">承認済</option>
          <option value="REJECTED">却下</option>
          <option value="CANCELLED">取消</option>
        </select>
      </div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!requests.length" class="text-muted text-center py-3">
          該当する申請はありません
        </div>

        <table v-else class="table table-hover mb-0">
          <thead>
            <tr>
              <th>キャスト</th>
              <th>日付</th>
              <th>時間</th>
              <th>希望部屋</th>
              <th>ステータス</th>
              <th>メモ</th>
              <th style="width: 140px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in requests" :key="r.id">
              <td>{{ r.cast_name }}</td>
              <td>{{ r.date }}</td>
              <td>{{ r.start_time?.slice(0,5) }}-{{ r.end_time?.slice(0,5) }}</td>
              <td>{{ r.desired_room_name || '-' }}</td>
              <td><span class="badge" :class="statusClass[r.status]">{{ statusLabel[r.status] }}</span></td>
              <td>{{ r.memo || '-' }}</td>
              <td>
                <template v-if="r.status === 'REQUESTED'">
                  <button class="btn btn-success btn-sm me-1" @click="openApprove(r)">
                    <i class="ti ti-check"></i>
                  </button>
                  <button class="btn btn-danger btn-sm" @click="openReject(r)">
                    <i class="ti ti-x"></i>
                  </button>
                </template>
                <span v-else class="text-muted small">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Approve modal -->
    <div v-if="showApprove" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showApprove = false">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">シフト承認</h5>
            <button type="button" class="btn-close" @click="showApprove = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="approveError" class="alert alert-danger">{{ approveError }}</div>
            <p>
              <strong>{{ approveTarget?.cast_name }}</strong> /
              {{ approveTarget?.date }}
              {{ approveTarget?.start_time?.slice(0,5) }}-{{ approveTarget?.end_time?.slice(0,5) }}
            </p>
            <div class="mb-3">
              <label class="form-label">部屋（必須）</label>
              <select v-model="approveRoom" class="form-select">
                <option value="" disabled>選択してください</option>
                <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">管理者メモ（任意）</label>
              <textarea v-model="approveAdminMemo" class="form-control" rows="2"></textarea>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showApprove = false">キャンセル</button>
            <button class="btn btn-success" :disabled="approving" @click="doApprove">
              {{ approving ? '処理中...' : '承認する' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Reject modal -->
    <div v-if="showReject" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showReject = false">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">シフト却下</h5>
            <button type="button" class="btn-close" @click="showReject = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="rejectError" class="alert alert-danger">{{ rejectError }}</div>
            <p>
              <strong>{{ rejectTarget?.cast_name }}</strong> /
              {{ rejectTarget?.date }}
              {{ rejectTarget?.start_time?.slice(0,5) }}-{{ rejectTarget?.end_time?.slice(0,5) }}
            </p>
            <div class="mb-3">
              <label class="form-label">管理者メモ（任意）</label>
              <textarea v-model="rejectAdminMemo" class="form-control" rows="2"></textarea>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showReject = false">キャンセル</button>
            <button class="btn btn-danger" :disabled="rejecting" @click="doReject">
              {{ rejecting ? '処理中...' : '却下する' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>
