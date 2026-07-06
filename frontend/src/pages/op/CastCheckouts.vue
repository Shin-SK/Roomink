<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const router = useRouter()

const PAGE_LIMIT = 50

const loading = ref(true)
const loadingMore = ref(false)
const error = ref('')
const checkouts = ref([])
const totalCount = ref(0)
const casts = ref([])

// Filters
const filterDate = ref(new Date().toISOString().slice(0, 10))
const filterCast = ref('')
const filterStatus = ref('')

// Detail modal
const showDetail = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const managerMemoDraft = ref('')
const actionSaving = ref(false)

const CHECKLIST_ITEMS = [
  { key: 'room_cleaned', label: '部屋の片付け・清掃をした' },
  { key: 'items_returned', label: '備品を返却した' },
  { key: 'cash_confirmed', label: '現金・売上を確認した' },
  { key: 'report_done', label: '特記事項があれば運営へ報告した' },
]

function statusLabel(s) {
  return { SUBMITTED: '提出済み（未確認）', REVIEWED: '確認済み', RETURNED: '差戻し' }[s] || s
}

function statusBadgeClass(s) {
  return { SUBMITTED: 'bg-warning text-dark', REVIEWED: 'bg-success', RETURNED: 'bg-danger' }[s] || 'bg-secondary'
}

function formatYen(n) {
  return `¥${Number(n || 0).toLocaleString()}`
}

function formatDateTime(dt) {
  if (!dt) return '—'
  const d = new Date(dt)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function loadMasters() {
  const data = await api.getCasts()
  casts.value = Array.isArray(data) ? data : []
}

function buildListParams(offset) {
  let params = `date=${filterDate.value}&limit=${PAGE_LIMIT}&offset=${offset}`
  if (filterCast.value) params += `&cast=${filterCast.value}`
  if (filterStatus.value) params += `&status=${filterStatus.value}`
  return params
}

function buildExportParams() {
  let params = `date=${filterDate.value}`
  if (filterCast.value) params += `&cast=${filterCast.value}`
  if (filterStatus.value) params += `&status=${filterStatus.value}`
  return params
}

async function loadCheckouts() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getCastCheckoutsPage(buildListParams(0))
    checkouts.value = Array.isArray(data?.results) ? data.results : []
    totalCount.value = data?.count ?? checkouts.value.length
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadMoreCheckouts() {
  loadingMore.value = true
  error.value = ''
  try {
    const data = await api.getCastCheckoutsPage(buildListParams(checkouts.value.length))
    checkouts.value = checkouts.value.concat(Array.isArray(data?.results) ? data.results : [])
    totalCount.value = data?.count ?? checkouts.value.length
  } catch (e) {
    error.value = e.message
  } finally {
    loadingMore.value = false
  }
}

function exportCsv() {
  window.open(api.getCastCheckoutsExportUrl(buildExportParams()), '_blank')
}

onMounted(async () => {
  try {
    await loadMasters()
  } catch (e) {
    error.value = e.message
  }
  await loadCheckouts()
})

watch([filterDate, filterCast, filterStatus], () => loadCheckouts())

async function openDetail(row) {
  showDetail.value = true
  detail.value = null
  detailError.value = ''
  detailLoading.value = true
  try {
    detail.value = await api.getCastCheckoutDetail(row.id)
    managerMemoDraft.value = detail.value.manager_memo || ''
  } catch (e) {
    detailError.value = e.message
  } finally {
    detailLoading.value = false
  }
}

async function saveManagerMemo() {
  if (!detail.value) return
  actionSaving.value = true
  detailError.value = ''
  try {
    detail.value = await api.updateCastCheckoutManagerMemo(detail.value.id, managerMemoDraft.value)
    await loadCheckouts()
  } catch (e) {
    detailError.value = e.message
  } finally {
    actionSaving.value = false
  }
}

async function markReviewed() {
  if (!detail.value) return
  actionSaving.value = true
  detailError.value = ''
  try {
    detail.value = await api.reviewCastCheckout(detail.value.id, managerMemoDraft.value)
    await loadCheckouts()
  } catch (e) {
    detailError.value = e.message
  } finally {
    actionSaving.value = false
  }
}

async function markReturned() {
  if (!detail.value) return
  if (!confirm('差戻しにしますか？キャストが再提出できるようになります。')) return
  actionSaving.value = true
  detailError.value = ''
  try {
    detail.value = await api.returnCastCheckout(detail.value.id, managerMemoDraft.value)
    await loadCheckouts()
  } catch (e) {
    detailError.value = e.message
  } finally {
    actionSaving.value = false
  }
}

async function resetToSubmitted() {
  if (!detail.value) return
  if (!confirm('未確認の状態に戻しますか？')) return
  actionSaving.value = true
  detailError.value = ''
  try {
    detail.value = await api.resetCastCheckout(detail.value.id)
    await loadCheckouts()
  } catch (e) {
    detailError.value = e.message
  } finally {
    actionSaving.value = false
  }
}

function closeDetail() {
  showDetail.value = false
  detail.value = null
}

function createAdjustmentFromCheckout() {
  if (!detail.value) return
  router.push({
    path: '/op/cast-adjustments',
    query: { cast: detail.value.cast, date: detail.value.date, checkout: detail.value.id },
  })
}
</script>

<template>
  <LayoutOperator>
    <template #title>退勤提出一覧</template>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <div><i class="ti ti-door-exit"></i> 退勤提出一覧</div>
        <button class="btn btn-sm btn-outline-dark" @click="exportCsv">
          <i class="ti ti-download"></i> CSV
        </button>
      </div>
      <div class="card-body">
        <!-- Filters -->
        <div class="row mb-3 g-2">
          <div class="col-md-3">
            <input v-model="filterDate" type="date" class="form-control" />
          </div>
          <div class="col-md-3">
            <select v-model="filterCast" class="form-select">
              <option value="">全キャスト</option>
              <option v-for="c in casts" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </div>
          <div class="col-md-3">
            <select v-model="filterStatus" class="form-select">
              <option value="">全ステータス</option>
              <option value="SUBMITTED">提出済み（未確認）</option>
              <option value="REVIEWED">確認済み</option>
              <option value="RETURNED">差戻し</option>
            </select>
          </div>
        </div>

        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!checkouts.length" class="text-muted text-center py-3">
          この条件の退勤提出はありません
        </div>

        <table v-else class="table table-hover mb-0">
          <thead>
            <tr>
              <th>日付</th>
              <th>キャスト</th>
              <th>ステータス</th>
              <th style="width: 100px;">売上</th>
              <th style="width: 100px;">給与見込み</th>
              <th style="width: 110px;">持ち帰り金額</th>
              <th>提出日時</th>
              <th>確認者</th>
              <th>確認日時</th>
              <th style="width: 90px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in checkouts" :key="row.id">
              <td>{{ row.date }}</td>
              <td>{{ row.cast_name }}</td>
              <td><span class="badge" :class="statusBadgeClass(row.status)">{{ statusLabel(row.status) }}</span></td>
              <td>{{ formatYen(row.total_sales) }}</td>
              <td>{{ formatYen(row.estimated_pay) }}</td>
              <td>{{ formatYen(row.actual_take_home_amount) }}</td>
              <td>{{ formatDateTime(row.submitted_at) }}</td>
              <td>{{ row.reviewed_by_name || '—' }}</td>
              <td>{{ formatDateTime(row.reviewed_at) }}</td>
              <td>
                <button class="btn btn-outline-primary btn-sm" @click="openDetail(row)">
                  <i class="ti ti-eye"></i> 詳細
                </button>
              </td>
            </tr>
          </tbody>
        </table>

        <div v-if="!loading && checkouts.length < totalCount" class="text-center mt-3">
          <button class="btn btn-outline-secondary btn-sm" :disabled="loadingMore" @click="loadMoreCheckouts">
            <span v-if="loadingMore" class="spinner-border spinner-border-sm me-1"></span>
            もっと見る（{{ checkouts.length }} / {{ totalCount }}件）
          </button>
        </div>
      </div>
    </div>

    <!-- Detail modal -->
    <div v-if="showDetail" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="closeDetail">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              退勤提出詳細
              <span v-if="detail" class="badge ms-2" :class="statusBadgeClass(detail.status)">{{ statusLabel(detail.status) }}</span>
            </h5>
            <button type="button" class="btn-close" @click="closeDetail"></button>
          </div>
          <div class="modal-body">
            <div v-if="detailError" class="alert alert-danger">{{ detailError }}</div>

            <div v-if="detailLoading" class="text-center py-3">
              <div class="spinner-border text-primary"></div>
            </div>

            <template v-else-if="detail">
              <div class="row g-2 mb-3">
                <div class="col-6 col-md-3">
                  <div class="small text-muted">キャスト</div>
                  <div class="fw-bold">{{ detail.cast_name }}</div>
                </div>
                <div class="col-6 col-md-3">
                  <div class="small text-muted">日付</div>
                  <div class="fw-bold">{{ detail.date }}</div>
                </div>
                <div class="col-6 col-md-3">
                  <div class="small text-muted">完了済み件数</div>
                  <div class="fw-bold">{{ detail.done_count }}本</div>
                </div>
                <div class="col-6 col-md-3">
                  <div class="small text-muted">売上</div>
                  <div class="fw-bold">{{ formatYen(detail.total_sales) }}</div>
                </div>
                <div class="col-6 col-md-3">
                  <div class="small text-muted">給与見込み</div>
                  <div class="fw-bold text-primary">{{ formatYen(detail.estimated_pay) }}</div>
                </div>
                <div class="col-6 col-md-3">
                  <div class="small text-muted">実際の持ち帰り金額</div>
                  <div class="fw-bold">{{ formatYen(detail.actual_take_home_amount) }}</div>
                </div>
                <div class="col-6 col-md-3">
                  <div class="small text-muted">提出日時</div>
                  <div>{{ formatDateTime(detail.submitted_at) }}</div>
                </div>
                <div class="col-6 col-md-3">
                  <div class="small text-muted">確認者 / 確認日時</div>
                  <div>{{ detail.reviewed_by_name || '—' }} / {{ formatDateTime(detail.reviewed_at) }}</div>
                </div>
              </div>

              <div v-if="detail.expense_snapshots?.length" class="mb-3">
                <div class="fw-bold small mb-1"><i class="ti ti-receipt"></i> 固定雑費スナップショット</div>
                <table class="table table-sm mb-0">
                  <tbody>
                    <tr v-for="s in detail.expense_snapshots" :key="s.id">
                      <td>{{ s.name }}</td>
                      <td style="width: 100px;">{{ formatYen(s.amount) }}</td>
                      <td class="text-muted">{{ s.memo || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div class="mb-3">
                <div class="fw-bold small mb-1">退勤チェックリスト</div>
                <div v-for="item in CHECKLIST_ITEMS" :key="item.key" class="small">
                  <i class="ti" :class="detail.checklist_json?.[item.key] ? 'ti-square-check text-success' : 'ti-square text-muted'"></i>
                  {{ item.label }}
                </div>
              </div>

              <div class="mb-3">
                <div class="fw-bold small mb-1">キャストメモ</div>
                <div class="bg-light p-2 rounded small">{{ detail.cast_memo || 'なし' }}</div>
              </div>

              <div class="mb-3">
                <label class="form-label fw-bold small">マネージャーメモ</label>
                <textarea v-model="managerMemoDraft" class="form-control" rows="3"></textarea>
                <button class="btn btn-outline-secondary btn-sm mt-2" :disabled="actionSaving" @click="saveManagerMemo">
                  メモを保存
                </button>
              </div>
            </template>
          </div>
          <div class="modal-footer" v-if="detail">
            <button class="btn btn-secondary" @click="closeDetail">閉じる</button>
            <button class="btn btn-outline-primary" @click="createAdjustmentFromCheckout">
              <i class="ti ti-cash-banknote"></i> 調整金を作成
            </button>
            <button v-if="detail.status !== 'SUBMITTED'" class="btn btn-outline-warning" :disabled="actionSaving" @click="resetToSubmitted">
              未確認に戻す
            </button>
            <button v-if="detail.status !== 'RETURNED'" class="btn btn-outline-danger" :disabled="actionSaving" @click="markReturned">
              差戻し
            </button>
            <button v-if="detail.status !== 'REVIEWED'" class="btn btn-primary" :disabled="actionSaving" @click="markReviewed">
              確認済みにする
            </button>
          </div>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>
