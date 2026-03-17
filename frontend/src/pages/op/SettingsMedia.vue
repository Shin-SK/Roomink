<script setup>
import { ref, onMounted } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const media = ref([])

const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

function emptyForm() {
  return { name: '', sort_order: 0, is_active: true }
}

async function loadMedia() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getMedia()
    media.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(() => loadMedia())

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(o) {
  editingId.value = o.id
  form.value = { name: o.name, sort_order: o.sort_order, is_active: o.is_active }
  formError.value = ''
  showForm.value = true
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const payload = {
      name: form.value.name,
      sort_order: form.value.sort_order,
      is_active: form.value.is_active,
    }
    if (editingId.value) {
      await api.updateMedium(editingId.value, payload)
    } else {
      await api.createMedium(payload)
    }
    showForm.value = false
    await loadMedia()
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
    await api.deleteMedium(o.id)
    await loadMedia()
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <LayoutOperator>
    <template #title>媒体管理</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-antenna"></i> 媒体一覧</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus"></i> 媒体追加
        </button>
      </div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!media.length" class="text-muted text-center py-3">
          媒体が登録されていません
        </div>

        <table v-else class="table table-hover mb-0">
          <thead>
            <tr>
              <th>名前</th>
              <th style="width: 80px;">順序</th>
              <th style="width: 80px;">有効</th>
              <th style="width: 50px;"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="o in media" :key="o.id">
              <td>{{ o.name }}</td>
              <td>{{ o.sort_order }}</td>
              <td>
                <span v-if="o.is_active" class="badge bg-success">有効</span>
                <span v-else class="badge bg-secondary">無効</span>
              </td>
              <td>
                <button class="btn btn-link p-0" @click="openEdit(o)">
                  <i class="ti ti-edit" style="font-size: 1.25rem;"></i>
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
            <h5 class="modal-title">{{ editingId ? '媒体編集' : '媒体追加' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

            <div class="mb-3">
              <label class="form-label">名前 <span class="text-danger">*</span></label>
              <input v-model="form.name" type="text" class="form-control" placeholder="例: ホットペッパー" />
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
          <div class="modal-footer d-flex">
            <button v-if="editingId" class="btn btn-outline-danger me-auto" @click="onDelete({ id: editingId, name: form.name })">
              <i class="ti ti-trash"></i> 削除
            </button>
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
