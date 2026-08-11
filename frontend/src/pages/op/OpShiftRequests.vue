<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

const isManager = computed(() => getAuthRole() === 'manager')

const loading = ref(true)
const error = ref('')
const requests = ref([])
const rooms = ref([])

const filterStatus = ref('REQUESTED')
const viewMode = ref('list')

const filteredRequests = computed(() => requests.value)

const groupedByDate = computed(() => {
  const map = {}
  for (const r of filteredRequests.value) {
    (map[r.date] || (map[r.date] = [])).push(r)
  }
  return Object.keys(map).sort().map((key) => ({ key, items: map[key] }))
})

const groupedByCast = computed(() => {
  const map = {}
  for (const r of filteredRequests.value) {
    const key = r.cast_name || '-'
    ;(map[key] || (map[key] = [])).push(r)
  }
  return Object.keys(map).sort().map((key) => ({ key, items: map[key] }))
})

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
const approveDate = ref('')
const approveStartTime = ref('')
const approveEndTime = ref('')
const approveRoom = ref('')
const approveAdminMemo = ref('')
const approveError = ref('')
const approving = ref(false)

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

function openApprove(r) {
  approveTarget.value = r
  approveDate.value = r.date || ''
  approveStartTime.value = r.start_time?.slice(0, 5) || ''
  approveEndTime.value = r.end_time_extended || r.end_time?.slice(0, 5) || ''
  approveRoom.value = r.desired_room || ''
  approveAdminMemo.value = ''
  approveError.value = ''
  showApprove.value = true
}

async function doApprove() {
  if (!approveDate.value) { approveError.value = '日付を入力してください'; return }
  if (!approveStartTime.value) { approveError.value = '開始時間を入力してください'; return }
  if (!approveEndTime.value) { approveError.value = '終了時間を入力してください'; return }
  let normalizedEnd
  try {
    normalizedEnd = normalizeExtendedEndTime(approveEndTime.value)
  } catch (e) {
    approveError.value = e.message
    return
  }
  approving.value = true
  approveError.value = ''
  try {
    await api.approveShiftRequest(approveTarget.value.id, {
      date: approveDate.value,
      start_time: approveStartTime.value,
      ...normalizedEnd,
      room: approveRoom.value ? Number(approveRoom.value) : null,
      admin_memo: approveAdminMemo.value,
    })
    showApprove.value = false
    window.dispatchEvent(new Event('shift-requests-changed'))
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
    window.dispatchEvent(new Event('shift-requests-changed'))
    await load()
  } catch (e) {
    rejectError.value = e.message
  } finally {
    rejecting.value = false
  }
}

const statusLabel = { REQUESTED: '申請中', APPROVED: '承認済', REJECTED: '却下', CANCELLED: '取消' }
const statusClass = { REQUESTED: 'bg-warning text-dark', APPROVED: 'bg-success', REJECTED: 'bg-danger', CANCELLED: 'bg-secondary' }

function formatDateTime(s) {
  if (!s) return ''
  return s.slice(0, 16).replace('T', ' ')
}

// ── CSV戻し承認の土台（v1: export → preview → 明示確認後にapply） ──
function exportCsv() {
  const params = filterStatus.value ? `status=${filterStatus.value}` : ''
  window.open(api.getOpShiftRequestsExportUrl(params), '_blank')
}

const showImportModal = ref(false)
const importFile = ref(null)
const importError = ref('')
const importLoading = ref(false)
const previewResult = ref(null)
const selectedRows = ref({}) // row_number -> boolean
const applying = ref(false)
const applyResult = ref(null)

function openImportModal() {
  importFile.value = null
  importError.value = ''
  previewResult.value = null
  selectedRows.value = {}
  applyResult.value = null
  showImportModal.value = true
}

function onFileChange(e) {
  importFile.value = e.target.files?.[0] || null
}

async function doPreview() {
  if (!importFile.value) { importError.value = 'CSVファイルを選択してください'; return }
  importLoading.value = true
  importError.value = ''
  previewResult.value = null
  applyResult.value = null
  try {
    const data = await api.importShiftRequestsPreview(importFile.value)
    previewResult.value = data
    const sel = {}
    for (const r of data.rows || []) {
      sel[r.row_number] = !!r.can_apply
    }
    selectedRows.value = sel
  } catch (e) {
    importError.value = e.message
  } finally {
    importLoading.value = false
  }
}

const selectedCount = computed(() => Object.values(selectedRows.value).filter(Boolean).length)

async function doApply() {
  if (!previewResult.value) return
  const rows = (previewResult.value.rows || []).filter(r => r.can_apply && selectedRows.value[r.row_number])
  if (!rows.length) { importError.value = '反映する行を選択してください'; return }
  if (!confirm(`${rows.length}件のシフト申請を承認として反映します。よろしいですか？`)) return
  applying.value = true
  importError.value = ''
  try {
    const payload = rows.map(r => ({
      row_number: r.row_number,
      shift_request_id: r.shift_request_id,
      cast_id: r.original?.cast_id,
      approved_date: r.csv.approved_date,
      approved_start_time: r.csv.approved_start_time,
      approved_end_time: r.csv.approved_end_time,
      approved_room_id: r.csv.approved_room_id,
      admin_memo: r.csv.admin_memo,
    }))
    applyResult.value = await api.applyShiftRequestsImport(payload)
    window.dispatchEvent(new Event('shift-requests-changed'))
    await load()
  } catch (e) {
    importError.value = e.message
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <LayoutOperator>
    <template #title>シフト申請管理</template>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between flex-wrap gap-2">
        <span><i class="ti ti-calendar-check"></i> シフト申請一覧</span>
        <div class="d-flex gap-2 flex-wrap">
          <select v-model="viewMode" class="form-select form-select-sm" style="width: auto;">
            <option value="list">申請順</option>
            <option value="by_date">日付別</option>
            <option value="by_cast">キャスト別</option>
          </select>
          <select v-model="filterStatus" class="form-select form-select-sm" style="width: auto;">
            <option value="">すべて</option>
            <option value="REQUESTED">申請中</option>
            <option value="APPROVED">承認済</option>
            <option value="REJECTED">却下</option>
            <option value="CANCELLED">取消</option>
          </select>
          <template v-if="isManager">
            <button class="btn btn-outline-dark btn-sm" @click="exportCsv">
              <i class="ti ti-download"></i> CSVエクスポート
            </button>
            <button class="btn btn-outline-primary btn-sm" @click="openImportModal">
              <i class="ti ti-upload"></i> CSVインポート
            </button>
          </template>
        </div>
      </div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!requests.length" class="text-muted text-center py-3">
          該当する申請はありません
        </div>

        <!-- 申請順 -->
        <table v-else-if="viewMode === 'list'" class="table table-hover mb-0">
          <thead>
            <tr>
              <th>キャスト</th>
              <th>申請内容</th>
              <th>承認内容</th>
              <th>ステータス</th>
              <th>決定情報</th>
              <th>メモ</th>
              <th style="width: 140px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in requests" :key="r.id">
              <td>{{ r.cast_name }}</td>
              <td>
                <div>{{ r.date }}</div>
                <div class="small text-muted">{{ r.start_time?.slice(0,5) }}-{{ r.end_time_extended || r.end_time?.slice(0,5) }}</div>
                <div class="small text-muted">{{ r.desired_room_name || '-' }}</div>
              </td>
              <td>
                <template v-if="r.status === 'APPROVED'">
                  <template v-if="r.approved_date">
                    <div>{{ r.approved_date }}</div>
                    <div class="small text-muted">{{ r.approved_start_time?.slice(0,5) }}-{{ r.approved_end_time_extended || r.approved_end_time?.slice(0,5) }}</div>
                    <div class="small text-muted">{{ r.approved_room_name || '-' }}</div>
                  </template>
                  <span v-else class="text-muted small">履歴未記録（旧データ）</span>
                </template>
                <span v-else class="text-muted small">-</span>
              </td>
              <td><span class="badge" :class="statusClass[r.status]">{{ statusLabel[r.status] }}</span></td>
              <td>
                <template v-if="r.decided_at">
                  <div class="small">{{ r.decided_by_name || '-' }}</div>
                  <div class="small text-muted">{{ formatDateTime(r.decided_at) }}</div>
                </template>
                <span v-else class="text-muted small">-</span>
              </td>
              <td>
                <div v-if="r.memo" class="small">{{ r.memo }}</div>
                <div v-if="r.admin_memo" class="small text-info">{{ r.admin_memo }}</div>
                <span v-if="!r.memo && !r.admin_memo" class="text-muted small">-</span>
              </td>
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

        <!-- 日付別 -->
        <div v-else-if="viewMode === 'by_date'">
          <div v-for="g in groupedByDate" :key="g.key" class="mb-3">
            <h6 class="text-muted mb-2"><i class="ti ti-calendar"></i> {{ g.key }}</h6>
            <table class="table table-hover mb-0">
              <thead>
                <tr>
                  <th>キャスト</th>
                  <th>申請内容</th>
                  <th>承認内容</th>
                  <th>ステータス</th>
                  <th>決定情報</th>
                  <th>メモ</th>
                  <th style="width: 140px;">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in g.items" :key="r.id">
                  <td>{{ r.cast_name }}</td>
                  <td>
                    <div class="small text-muted">{{ r.start_time?.slice(0,5) }}-{{ r.end_time_extended || r.end_time?.slice(0,5) }}</div>
                    <div class="small text-muted">{{ r.desired_room_name || '-' }}</div>
                  </td>
                  <td>
                    <template v-if="r.status === 'APPROVED'">
                      <template v-if="r.approved_date">
                        <div>{{ r.approved_date }}</div>
                        <div class="small text-muted">{{ r.approved_start_time?.slice(0,5) }}-{{ r.approved_end_time_extended || r.approved_end_time?.slice(0,5) }}</div>
                        <div class="small text-muted">{{ r.approved_room_name || '-' }}</div>
                      </template>
                      <span v-else class="text-muted small">履歴未記録（旧データ）</span>
                    </template>
                    <span v-else class="text-muted small">-</span>
                  </td>
                  <td><span class="badge" :class="statusClass[r.status]">{{ statusLabel[r.status] }}</span></td>
                  <td>
                    <template v-if="r.decided_at">
                      <div class="small">{{ r.decided_by_name || '-' }}</div>
                      <div class="small text-muted">{{ formatDateTime(r.decided_at) }}</div>
                    </template>
                    <span v-else class="text-muted small">-</span>
                  </td>
                  <td>
                    <div v-if="r.memo" class="small">{{ r.memo }}</div>
                    <div v-if="r.admin_memo" class="small text-info">{{ r.admin_memo }}</div>
                    <span v-if="!r.memo && !r.admin_memo" class="text-muted small">-</span>
                  </td>
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

        <!-- キャスト別 -->
        <div v-else>
          <div v-for="g in groupedByCast" :key="g.key" class="mb-3">
            <h6 class="text-muted mb-2"><i class="ti ti-user"></i> {{ g.key }}</h6>
            <table class="table table-hover mb-0">
              <thead>
                <tr>
                  <th>申請内容</th>
                  <th>承認内容</th>
                  <th>ステータス</th>
                  <th>決定情報</th>
                  <th>メモ</th>
                  <th style="width: 140px;">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in g.items" :key="r.id">
                  <td>
                    <div>{{ r.date }}</div>
                    <div class="small text-muted">{{ r.start_time?.slice(0,5) }}-{{ r.end_time_extended || r.end_time?.slice(0,5) }}</div>
                    <div class="small text-muted">{{ r.desired_room_name || '-' }}</div>
                  </td>
                  <td>
                    <template v-if="r.status === 'APPROVED'">
                      <template v-if="r.approved_date">
                        <div>{{ r.approved_date }}</div>
                        <div class="small text-muted">{{ r.approved_start_time?.slice(0,5) }}-{{ r.approved_end_time_extended || r.approved_end_time?.slice(0,5) }}</div>
                        <div class="small text-muted">{{ r.approved_room_name || '-' }}</div>
                      </template>
                      <span v-else class="text-muted small">履歴未記録（旧データ）</span>
                    </template>
                    <span v-else class="text-muted small">-</span>
                  </td>
                  <td><span class="badge" :class="statusClass[r.status]">{{ statusLabel[r.status] }}</span></td>
                  <td>
                    <template v-if="r.decided_at">
                      <div class="small">{{ r.decided_by_name || '-' }}</div>
                      <div class="small text-muted">{{ formatDateTime(r.decided_at) }}</div>
                    </template>
                    <span v-else class="text-muted small">-</span>
                  </td>
                  <td>
                    <div v-if="r.memo" class="small">{{ r.memo }}</div>
                    <div v-if="r.admin_memo" class="small text-info">{{ r.admin_memo }}</div>
                    <span v-if="!r.memo && !r.admin_memo" class="text-muted small">-</span>
                  </td>
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
              <strong>{{ approveTarget?.cast_name }}</strong>
              <span class="text-muted small">（申請: {{ approveTarget?.date }}
              {{ approveTarget?.start_time?.slice(0,5) }}-{{ approveTarget?.end_time_extended || approveTarget?.end_time?.slice(0,5) }}）</span>
            </p>
            <div class="mb-3">
              <label class="form-label">日付（必須）</label>
              <input v-model="approveDate" type="date" class="form-control">
            </div>
            <div class="row">
              <div class="col mb-3">
                <label class="form-label">開始（必須）</label>
                <input v-model="approveStartTime" type="time" class="form-control">
              </div>
              <div class="col mb-3">
                <label class="form-label">終了（必須）</label>
                <input
                  v-model="approveEndTime"
                  type="text"
                  inputmode="numeric"
                  maxlength="5"
                  placeholder="例: 23:00 / 29:00"
                  class="form-control"
                >
                <div class="form-text">翌朝は24:00〜29:00で入力できます。</div>
              </div>
            </div>
            <div class="mb-3">
              <label class="form-label">部屋</label>
              <select v-model="approveRoom" class="form-select">
                <option value="">自動選択（希望エリア・空室優先）</option>
                <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}{{ r.area_name ? `（${r.area_name}）` : '' }}</option>
              </select>
              <div class="form-text">申請で希望ルームが選ばれている場合は初期表示へ反映されます。</div>
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
              {{ rejectTarget?.start_time?.slice(0,5) }}-{{ rejectTarget?.end_time_extended || rejectTarget?.end_time?.slice(0,5) }}
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

    <!-- CSVインポート(戻し承認)モーダル -->
    <div v-if="showImportModal" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showImportModal = false">
      <div class="modal-dialog modal-xl">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="ti ti-upload"></i> シフト申請 CSVインポート（戻し承認・プレビュー確認式）</h5>
            <button type="button" class="btn-close" @click="showImportModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="alert alert-info small">
              CSVエクスポートしたファイルをExcel等で編集し（approved_date / approved_start_time / approved_end_time / approved_room_id / admin_memo）、
              ここでアップロードしてください。まず検証結果（プレビュー）を確認し、問題のない行だけを選択して「反映する」を押すと承認されます。
              自動一括承認ではなく、必ず内容を確認してから反映してください。
            </div>
            <div v-if="importError" class="alert alert-danger">{{ importError }}</div>

            <div class="d-flex align-items-center gap-2 mb-3">
              <input type="file" accept=".csv" class="form-control form-control-sm" style="max-width: 360px;" @change="onFileChange">
              <button class="btn btn-primary btn-sm" :disabled="importLoading" @click="doPreview">
                {{ importLoading ? '検証中...' : '検証する（プレビュー）' }}
              </button>
            </div>

            <template v-if="previewResult">
              <div class="mb-2 small">
                総行数: {{ previewResult.total_rows }} / 反映可能: {{ previewResult.applicable_rows }} / 選択中: {{ selectedCount }}
              </div>
              <div class="table-responsive mb-3" style="max-height: 420px; overflow-y: auto;">
                <table class="table table-sm table-bordered mb-0">
                  <thead>
                    <tr>
                      <th style="width: 32px;"></th>
                      <th>行</th>
                      <th>申請内容（元）</th>
                      <th>CSV上の承認予定</th>
                      <th>エラー/警告</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="r in previewResult.rows" :key="r.row_number" :class="!r.can_apply ? 'table-danger' : (r.warnings.length ? 'table-warning' : '')">
                      <td>
                        <input
                          type="checkbox"
                          :disabled="!r.can_apply"
                          v-model="selectedRows[r.row_number]"
                        >
                      </td>
                      <td class="small">{{ r.row_number }}<br><span class="text-muted">#{{ r.shift_request_id }}</span></td>
                      <td class="small">
                        <template v-if="r.original">
                          {{ r.original.cast_name }}<br>
                          {{ r.original.date }} {{ r.original.start_time }}-{{ r.original.end_time }}<br>
                          <span class="text-muted">希望: {{ r.original.desired_room_name || '-' }}</span><br>
                          <span class="badge" :class="statusClass[r.original.status]">{{ r.original.status_display }}</span>
                        </template>
                        <span v-else class="text-muted">-</span>
                      </td>
                      <td class="small">
                        {{ r.csv.approved_date }} {{ r.csv.approved_start_time }}-{{ r.csv.approved_end_time }}<br>
                        部屋: {{ r.csv.approved_room_name || r.csv.approved_room_id || '-' }}<br>
                        <span v-if="r.csv.admin_memo" class="text-info">{{ r.csv.admin_memo }}</span>
                      </td>
                      <td class="small">
                        <div v-for="(e, i) in r.errors" :key="'e'+i" class="text-danger"><i class="ti ti-alert-circle"></i> {{ e }}</div>
                        <div v-for="(w, i) in r.warnings" :key="'w'+i" class="text-warning"><i class="ti ti-alert-triangle"></i> {{ w }}</div>
                        <span v-if="!r.errors.length && !r.warnings.length" class="text-success"><i class="ti ti-check"></i> 反映可能</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <template v-if="applyResult">
                <div class="alert alert-success small">
                  反映完了: {{ applyResult.applied_count }} / {{ applyResult.total }} 件
                </div>
              </template>
            </template>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showImportModal = false">閉じる</button>
            <button
              v-if="previewResult"
              class="btn btn-success"
              :disabled="applying || selectedCount === 0"
              @click="doApply"
            >{{ applying ? '反映中...' : `選択した${selectedCount}件を反映する` }}</button>
          </div>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>
