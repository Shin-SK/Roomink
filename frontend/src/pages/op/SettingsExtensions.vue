<script setup>
import { ref, onMounted } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const extensions = ref([])

const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

function emptyForm() {
  return { name: '', duration: 30, price: 0, sort_order: 0, is_active: true }
}

async function loadExtensions() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getExtensions()
    extensions.value = Array.isArray(data) ? data : data.results || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(() => loadExtensions())

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(o) {
  editingId.value = o.id
  form.value = { name: o.name, duration: o.duration, price: o.price, sort_order: o.sort_order, is_active: o.is_active }
  formError.value = ''
  showForm.value = true
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const payload = {
      name: form.value.name,
      duration: form.value.duration,
      price: form.value.price,
      sort_order: form.value.sort_order,
      is_active: form.value.is_active,
    }
    if (editingId.value) {
      await api.updateExtension(editingId.value, payload)
    } else {
      await api.createExtension(payload)
    }
    showForm.value = false
    await loadExtensions()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function onDelete(o) {
  if (!confirm(`「${o.name}」を削除しますか？`)) return
  error.value = ''
  try {
    await api.deleteExtension(o.id)
    await loadExtensions()
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <LayoutOperator>
    <template #title>延長管理</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-clock-plus"></i> 延長一覧</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus"></i> 延長追加
        </button>
      </div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!extensions.length" class="text-muted text-center py-3">
          延長が登録されていません
        </div>

        <table v-else class="table table-hover mb-0">
          <thead>
            <tr>
              <th>名前</th>
              <th style="width: 100px;">時間（分）</th>
              <th style="width: 100px;">料金</th>
              <th style="width: 80px;">順序</th>
              <th style="width: 80px;">有効</th>
              <th style="width: 120px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="o in extensions" :key="o.id">
              <td>{{ o.name }}</td>
              <td>{{ o.duration }}分</td>
              <td>{{ o.price.toLocaleString() }}円</td>
              <td>{{ o.sort_order }}</td>
              <td>
                <span v-if="o.is_active" class="badge bg-success">有効</span>
                <span v-else class="badge bg-secondary">無効</span>
              </td>
              <td>
                <button class="btn btn-outline-primary btn-sm me-1" @click="openEdit(o)">
                  <i class="ti ti-edit"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" @click="onDelete(o)">
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
            <h5 class="modal-title">{{ editingId ? '延長編集' : '延長追加' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

            <div class="mb-3">
              <label class="form-label">名前 <span class="text-danger">*</span></label>
              <input v-model="form.name" type="text" class="form-control" placeholder="例: 30分延長" />
            </div>
            <div class="mb-3">
              <label class="form-label">時間（分） <span class="text-danger">*</span></label>
              <input v-model.number="form.duration" type="number" class="form-control" min="1" />
            </div>
            <div class="mb-3">
              <label class="form-label">料金 <span class="text-danger">*</span></label>
              <input v-model.number="form.price" type="number" class="form-control" min="0" />
            </div>
            <div class="mb-3">
              <label class="form-label">表示順</label>
              <input v-model.number="form.sort_order" type="number" class="form-control" min="0" />
            </div>
            <div class="mb-3 form-check">
              <input v-model="form.is_active" type="checkbox" class="form-check-input" id="isActive" />
              <label class="form-check-label" for="isActive">有効</label>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showForm = false">キャンセル</button>
            <button class="btn btn-primary" :disabled="saving || !form.name.trim()" @click="onSave">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>
