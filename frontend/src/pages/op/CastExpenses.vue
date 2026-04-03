<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const expenses = ref([])
const casts = ref([])

// Filters
const filterDate = ref(new Date().toISOString().slice(0, 10))
const filterCast = ref('')

// Form
const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

function emptyForm() {
  return { cast: '', date: filterDate.value, name: '雑費', amount: 1000, per_order: false, memo: '' }
}

async function loadMasters() {
  const data = await api.getCasts()
  casts.value = Array.isArray(data) ? data : []
}

async function loadExpenses() {
  loading.value = true
  error.value = ''
  try {
    let params = `date=${filterDate.value}`
    if (filterCast.value) params += `&cast=${filterCast.value}`
    const data = await api.getCastExpenses(params)
    expenses.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    await loadMasters()
  } catch (e) {
    error.value = e.message
  }
  await loadExpenses()
})

watch([filterDate, filterCast], () => loadExpenses())

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(exp) {
  editingId.value = exp.id
  form.value = {
    cast: exp.cast,
    date: exp.date,
    name: exp.name,
    amount: exp.amount,
    per_order: exp.per_order,
    memo: exp.memo || '',
  }
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
      name: form.value.name,
      amount: Number(form.value.amount),
      per_order: form.value.per_order,
      memo: form.value.memo,
    }
    if (editingId.value) {
      await api.updateCastExpense(editingId.value, body)
    } else {
      await api.createCastExpense(body)
    }
    showForm.value = false
    await loadExpenses()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function onDelete(id) {
  if (!confirm('この雑費を削除しますか？')) return
  try {
    await api.deleteCastExpense(id)
    await loadExpenses()
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
    <template #title>雑費管理</template>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-receipt"></i> 雑費一覧</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus"></i> 雑費追加
        </button>
      </div>
      <div class="card-body">
        <!-- Filters -->
        <div class="row mb-3 g-2">
          <div class="col-md-4">
            <input v-model="filterDate" type="date" class="form-control" />
          </div>
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

        <div v-else-if="!expenses.length" class="text-muted text-center py-3">
          この日の雑費はありません
        </div>

        <table v-else class="table table-hover mb-0">
          <thead>
            <tr>
              <th>キャスト</th>
              <th>名目</th>
              <th style="width: 100px;">金額</th>
              <th style="width: 80px;">種別</th>
              <th>メモ</th>
              <th style="width: 100px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="exp in expenses" :key="exp.id">
              <td>{{ exp.cast_name || castName(exp.cast) }}</td>
              <td>{{ exp.name }}</td>
              <td>¥{{ exp.amount.toLocaleString() }}</td>
              <td>
                <span v-if="exp.per_order" class="badge bg-info">×件</span>
                <span v-else class="badge bg-secondary">日額</span>
              </td>
              <td class="text-muted" style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ exp.memo || '—' }}</td>
              <td>
                <button class="btn btn-outline-primary btn-sm me-1" @click="openEdit(exp)">
                  <i class="ti ti-edit"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" @click="onDelete(exp.id)">
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
            <h5 class="modal-title">{{ editingId ? '雑費編集' : '雑費追加' }}</h5>
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
              <label class="form-label">名目 <span class="text-danger">*</span></label>
              <input v-model="form.name" type="text" class="form-control" placeholder="雑費 / 交通費 / 備品代" />
            </div>
            <div class="mb-3">
              <label class="form-label">金額（円） <span class="text-danger">*</span></label>
              <input v-model.number="form.amount" type="number" class="form-control" min="0" />
            </div>
            <div class="mb-3 form-check">
              <input v-model="form.per_order" type="checkbox" class="form-check-input" id="perOrder" />
              <label class="form-check-label" for="perOrder">予約ごとに掛ける（DONE 件数 × 金額）</label>
              <small class="text-muted d-block">OFF = その日1回だけ控除 / ON = その日のDONE予約件数 × 金額</small>
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
