<script setup>
import { ref, onMounted, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const logs = ref([])
const casts = ref([])

const filterCast = ref('')

const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

function emptyForm() {
  return { cast: '', date: new Date().toISOString().slice(0, 10), points: 0, reason: '', memo: '' }
}

async function loadMasters() {
  const data = await api.getCasts()
  casts.value = Array.isArray(data) ? data : []
}

async function loadLogs() {
  loading.value = true
  error.value = ''
  try {
    let params = 'limit=200'
    if (filterCast.value) params += `&cast=${filterCast.value}`
    const data = await api.getPointLogs(params)
    logs.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try { await loadMasters() } catch (e) { error.value = e.message }
  await loadLogs()
})

watch(filterCast, () => loadLogs())

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(log) {
  editingId.value = log.id
  form.value = { cast: log.cast, date: log.date, points: log.points, reason: log.reason || '', memo: log.memo || '' }
  formError.value = ''
  showForm.value = true
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const body = {
      cast: Number(form.value.cast),
      date: form.value.date,
      points: Number(form.value.points),
      reason: form.value.reason,
      memo: form.value.memo,
    }
    if (editingId.value) {
      await api.updatePointLog(editingId.value, body)
    } else {
      await api.createPointLog(body)
    }
    showForm.value = false
    await loadLogs()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function onDelete(id) {
  if (!confirm('このポイント記録を削除しますか？')) return
  try {
    await api.deletePointLog(id)
    await loadLogs()
  } catch (e) {
    error.value = e.message
  }
}

function castName(id) {
  return casts.value.find(c => c.id === id)?.name || id
}
</script>

<template>
  <LayoutOperator>
    <template #title>ポイント管理</template>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-star"></i> ポイント履歴</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus"></i> ポイント追加
        </button>
      </div>
      <div class="card-body">
        <div class="row mb-3 g-2">
          <div class="col-md-4">
            <select v-model="filterCast" class="form-select">
              <option value="">全キャスト</option>
              <option v-for="c in casts" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </div>
        </div>

        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!logs.length" class="text-muted text-center py-3">
          ポイント記録がありません
        </div>

        <table v-else class="table table-hover table-sm mb-0">
          <thead>
            <tr>
              <th>日付</th>
              <th>キャスト</th>
              <th class="text-end">ポイント</th>
              <th>理由</th>
              <th>メモ</th>
              <th style="width: 100px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td>{{ log.date }}</td>
              <td>{{ log.cast_name || castName(log.cast) }}</td>
              <td class="text-end fw-bold" :class="log.points >= 0 ? 'text-success' : 'text-danger'">
                {{ log.points >= 0 ? '+' : '' }}{{ log.points }}
              </td>
              <td>{{ log.reason || '—' }}</td>
              <td class="text-muted" style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ log.memo || '—' }}</td>
              <td>
                <button class="btn btn-outline-primary btn-sm me-1" @click="openEdit(log)">
                  <i class="ti ti-edit"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" @click="onDelete(log.id)">
                  <i class="ti ti-trash"></i>
                </button>
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
            <h5 class="modal-title">{{ editingId ? 'ポイント編集' : 'ポイント追加' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

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
              <label class="form-label">ポイント <span class="text-danger">*</span></label>
              <input v-model.number="form.points" type="number" class="form-control" />
              <small class="text-muted">正の数=加点 / 負の数=減点</small>
            </div>
            <div class="mb-3">
              <label class="form-label">理由</label>
              <input v-model="form.reason" type="text" class="form-control" placeholder="指名ボーナス / 遅刻 など" />
            </div>
            <div class="mb-3">
              <label class="form-label">メモ</label>
              <textarea v-model="form.memo" class="form-control" rows="2"></textarea>
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
  </LayoutOperator>
</template>
