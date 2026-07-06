<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const error = ref('')
const adjustments = ref([])
const casts = ref([])

// Filters
const filterDate = ref('')
const filterCast = ref('')
const filterStatus = ref('')

// Form
const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

// Resolve / Void modal
const showResolveModal = ref(false)
const resolveTarget = ref(null)
const resolveMode = ref('resolve') // 'resolve' | 'void'
const resolveMemo = ref('')
const resolveSaving = ref(false)
const resolveError = ref('')

function emptyForm() {
  return {
    cast: '', date: new Date().toISOString().slice(0, 10), amount: 0,
    title: '', memo: '', source_type: 'MANUAL', source_checkout: null,
  }
}

function statusLabel(s) {
  return { OPEN: '未解消', RESOLVED: '解消済', VOID: '無効' }[s] || s
}

function statusBadgeClass(s) {
  return { OPEN: 'bg-warning text-dark', RESOLVED: 'bg-success', VOID: 'bg-secondary' }[s] || 'bg-secondary'
}

function formatYen(n) {
  const v = Number(n || 0)
  return `${v >= 0 ? '+' : ''}¥${v.toLocaleString()}`
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

function buildParams() {
  const params = []
  if (filterDate.value) params.push(`date=${filterDate.value}`)
  if (filterCast.value) params.push(`cast=${filterCast.value}`)
  if (filterStatus.value) params.push(`status=${filterStatus.value}`)
  params.push('limit=500')
  return params.join('&')
}

async function loadAdjustments() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getCastAdjustments(buildParams())
    adjustments.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function exportCsv() {
  window.open(api.getCastAdjustmentsExportUrl(buildParams().replace(/&?limit=\d+/, '')), '_blank')
}

onMounted(async () => {
  try {
    await loadMasters()
  } catch (e) {
    error.value = e.message
  }
  await loadAdjustments()

  // CastCheckouts.vueの詳細モーダルからの遷移（?cast=&date=&checkout=）を検知して作成フォームを事前入力
  const { cast, date, checkout } = route.query
  if (cast || date || checkout) {
    editingId.value = null
    form.value = {
      ...emptyForm(),
      cast: cast ? Number(cast) : '',
      date: date || emptyForm().date,
      source_type: checkout ? 'CHECKOUT' : 'MANUAL',
      source_checkout: checkout ? Number(checkout) : null,
    }
    formError.value = ''
    showForm.value = true
    // クエリはフォームに反映済みなのでURLから消しておく
    router.replace({ path: '/op/cast-adjustments' })
  }
})

watch([filterDate, filterCast, filterStatus], () => loadAdjustments())

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(a) {
  editingId.value = a.id
  form.value = {
    cast: a.cast, date: a.date, amount: a.amount, title: a.title, memo: a.memo || '',
    source_type: a.source_type, source_checkout: a.source_checkout,
  }
  formError.value = ''
  showForm.value = true
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    if (editingId.value) {
      // 編集時は未解消のもののみ全項目編集可（backend側でも保護）
      await api.updateCastAdjustment(editingId.value, {
        cast: Number(form.value.cast),
        date: form.value.date,
        amount: Number(form.value.amount),
        title: form.value.title,
        memo: form.value.memo,
      })
    } else {
      const body = {
        cast: Number(form.value.cast),
        date: form.value.date,
        amount: Number(form.value.amount),
        title: form.value.title,
        memo: form.value.memo,
        source_type: form.value.source_type,
      }
      if (form.value.source_checkout) body.source_checkout = form.value.source_checkout
      await api.createCastAdjustment(body)
    }
    showForm.value = false
    await loadAdjustments()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

function openResolve(a) {
  resolveTarget.value = a
  resolveMode.value = 'resolve'
  resolveMemo.value = ''
  resolveError.value = ''
  showResolveModal.value = true
}

function openVoid(a) {
  resolveTarget.value = a
  resolveMode.value = 'void'
  resolveMemo.value = ''
  resolveError.value = ''
  showResolveModal.value = true
}

async function submitResolve() {
  if (!resolveTarget.value) return
  resolveSaving.value = true
  resolveError.value = ''
  try {
    if (resolveMode.value === 'resolve') {
      await api.resolveCastAdjustment(resolveTarget.value.id, resolveMemo.value)
    } else {
      await api.voidCastAdjustment(resolveTarget.value.id, resolveMemo.value)
    }
    showResolveModal.value = false
    await loadAdjustments()
  } catch (e) {
    resolveError.value = e.message
  } finally {
    resolveSaving.value = false
  }
}

function castName(id) {
  return casts.value.find(c => c.id === id)?.name || id
}
</script>

<template>
  <LayoutOperator>
    <template #title>調整金管理</template>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-cash-banknote"></i> 調整金台帳</span>
        <div class="d-flex gap-2">
          <button class="btn btn-sm btn-outline-dark" @click="exportCsv">
            <i class="ti ti-download"></i> CSV
          </button>
          <button class="btn btn-primary btn-sm" @click="openCreate">
            <i class="ti ti-plus"></i> 新規登録
          </button>
        </div>
      </div>
      <div class="card-body">
        <div class="small text-muted mb-3">
          給与確定・支払い処理とは接続しない、調整金台帳の未解消/解消管理のみです。
        </div>

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
              <option value="OPEN">未解消</option>
              <option value="RESOLVED">解消済</option>
              <option value="VOID">無効</option>
            </select>
          </div>
          <div class="col-md-3">
            <button
              v-if="filterDate || filterCast || filterStatus"
              class="btn btn-outline-secondary w-100"
              @click="filterDate = ''; filterCast = ''; filterStatus = ''"
            >絞り込み解除</button>
          </div>
        </div>

        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!adjustments.length" class="text-muted text-center py-3">
          この条件の調整金はありません
        </div>

        <table v-else class="table table-hover table-sm mb-0">
          <thead>
            <tr>
              <th>日付</th>
              <th>キャスト</th>
              <th>タイトル</th>
              <th class="text-end">金額</th>
              <th>ステータス</th>
              <th>メモ</th>
              <th>作成者</th>
              <th>作成日時</th>
              <th>解消者</th>
              <th>解消日時</th>
              <th style="width: 140px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in adjustments" :key="a.id">
              <td>{{ a.date }}</td>
              <td>{{ a.cast_name || castName(a.cast) }}</td>
              <td>{{ a.title }}</td>
              <td class="text-end fw-bold" :class="a.amount >= 0 ? 'text-success' : 'text-danger'">
                {{ formatYen(a.amount) }}
              </td>
              <td><span class="badge" :class="statusBadgeClass(a.status)">{{ a.status_display || statusLabel(a.status) }}</span></td>
              <td class="text-muted" style="max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ a.memo || '—' }}</td>
              <td>{{ a.created_by_name || '—' }}</td>
              <td>{{ formatDateTime(a.created_at) }}</td>
              <td>{{ a.resolved_by_name || '—' }}</td>
              <td>{{ formatDateTime(a.resolved_at) }}</td>
              <td>
                <button
                  v-if="a.status === 'OPEN'"
                  class="btn btn-outline-primary btn-sm me-1"
                  title="編集"
                  @click="openEdit(a)"
                ><i class="ti ti-edit"></i></button>
                <button
                  v-if="a.status === 'OPEN'"
                  class="btn btn-outline-success btn-sm me-1"
                  title="解消済みにする"
                  @click="openResolve(a)"
                ><i class="ti ti-check"></i></button>
                <button
                  v-if="a.status !== 'VOID'"
                  class="btn btn-outline-danger btn-sm"
                  title="無効化"
                  @click="openVoid(a)"
                ><i class="ti ti-ban"></i></button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Form modal -->
    <div v-if="showForm" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showForm = false">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editingId ? '調整金編集' : '調整金 新規登録' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>
            <div v-if="form.source_checkout" class="alert alert-info py-2 small">
              <i class="ti ti-link"></i> 退勤提出（checkout #{{ form.source_checkout }}）に紐づけて作成します
            </div>

            <div class="mb-3">
              <label class="form-label">日付 <span class="text-danger">*</span></label>
              <input v-model="form.date" type="date" class="form-control" />
            </div>
            <div class="mb-3">
              <label class="form-label">キャスト <span class="text-danger">*</span></label>
              <select v-model="form.cast" class="form-select">
                <option value="" disabled>選択してください</option>
                <option v-for="c in casts" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">タイトル <span class="text-danger">*</span></label>
              <input v-model="form.title" type="text" class="form-control" placeholder="例: 現金過不足調整、備品弁償 など" />
            </div>
            <div class="mb-3">
              <label class="form-label">金額 <span class="text-danger">*</span></label>
              <input v-model.number="form.amount" type="number" class="form-control" />
              <small class="text-muted">正の数=キャストへ追加で渡す金額 / 負の数=キャストから店へ戻す（差し引く）金額</small>
            </div>
            <div class="mb-3">
              <label class="form-label">メモ</label>
              <textarea v-model="form.memo" class="form-control" rows="2" placeholder="キャストにも表示されます"></textarea>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showForm = false">キャンセル</button>
            <button class="btn btn-primary" :disabled="saving" @click="onSave">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Resolve / Void modal -->
    <div v-if="showResolveModal" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showResolveModal = false">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ resolveMode === 'resolve' ? '解消済みにする' : '無効化する' }}</h5>
            <button type="button" class="btn-close" @click="showResolveModal = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="resolveError" class="alert alert-danger">{{ resolveError }}</div>
            <div v-if="resolveTarget" class="mb-3 small">
              <div class="fw-bold">{{ resolveTarget.cast_name || castName(resolveTarget.cast) }} / {{ resolveTarget.date }}</div>
              <div>{{ resolveTarget.title }} ： <span :class="resolveTarget.amount >= 0 ? 'text-success' : 'text-danger'">{{ formatYen(resolveTarget.amount) }}</span></div>
            </div>
            <div class="mb-2">
              <label class="form-label">{{ resolveMode === 'resolve' ? '解消メモ' : '無効化理由' }}</label>
              <textarea v-model="resolveMemo" class="form-control" rows="2"></textarea>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showResolveModal = false">キャンセル</button>
            <button
              class="btn"
              :class="resolveMode === 'resolve' ? 'btn-success' : 'btn-danger'"
              :disabled="resolveSaving"
              @click="submitResolve"
            >
              {{ resolveSaving ? '処理中...' : (resolveMode === 'resolve' ? '解消済みにする' : '無効化する') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>
