<script setup>
import { ref, onMounted } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const rooms = ref([])

// Form
const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

function emptyForm() {
  return { name: '', sort_order: 0 }
}

async function loadRooms() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getRooms()
    rooms.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(() => loadRooms())

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(r) {
  editingId.value = r.id
  form.value = { name: r.name, sort_order: r.sort_order ?? 0 }
  formError.value = ''
  showForm.value = true
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const payload = { name: form.value.name, sort_order: form.value.sort_order }
    if (editingId.value) {
      await api.updateRoom(editingId.value, payload)
    } else {
      await api.createRoom(payload)
    }
    showForm.value = false
    await loadRooms()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function onDelete(r) {
  if (!confirm(`「${r.name}」を削除しますか？`)) return
  error.value = ''
  try {
    await api.deleteRoom(r.id)
    await loadRooms()
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <LayoutOperator>
    <template #title>ルーム管理</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-door"></i> ルーム一覧</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus"></i> ルーム追加
        </button>
      </div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!rooms.length" class="text-muted text-center py-3">
          ルームが登録されていません
        </div>

        <table v-else class="table table-hover mb-0">
          <thead>
            <tr>
              <th>名前</th>
              <th style="width: 100px;">表示順</th>
              <th style="width: 120px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rooms" :key="r.id">
              <td>{{ r.name }}</td>
              <td>{{ r.sort_order }}</td>
              <td>
                <button class="btn btn-outline-primary btn-sm me-1" @click="openEdit(r)">
                  <i class="ti ti-edit"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" @click="onDelete(r)">
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
            <h5 class="modal-title">{{ editingId ? 'ルーム編集' : 'ルーム追加' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

            <div class="mb-3">
              <label class="form-label">名前 <span class="text-danger">*</span></label>
              <input v-model="form.name" type="text" class="form-control" placeholder="ルーム名" />
            </div>
            <div class="mb-3">
              <label class="form-label">表示順</label>
              <input v-model.number="form.sort_order" type="number" class="form-control" min="0" />
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
