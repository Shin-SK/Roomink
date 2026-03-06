<script setup>
import { ref, onMounted } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const courses = ref([])

// Form
const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

function emptyForm() {
  return { name: '', duration: 60, price: 0 }
}

async function loadCourses() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getCourses()
    courses.value = Array.isArray(data) ? data : data.results || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(() => loadCourses())

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(c) {
  editingId.value = c.id
  form.value = { name: c.name, duration: c.duration, price: c.price }
  formError.value = ''
  showForm.value = true
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const payload = { name: form.value.name, duration: form.value.duration, price: form.value.price }
    if (editingId.value) {
      await api.updateCourse(editingId.value, payload)
    } else {
      await api.createCourse(payload)
    }
    showForm.value = false
    await loadCourses()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function onDelete(c) {
  if (!confirm(`「${c.name}」を削除しますか？`)) return
  error.value = ''
  try {
    await api.deleteCourse(c.id)
    await loadCourses()
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <LayoutOperator>
    <template #title>コース管理</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-list"></i> コース一覧</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus"></i> コース追加
        </button>
      </div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!courses.length" class="text-muted text-center py-3">
          コースが登録されていません
        </div>

        <table v-else class="table table-hover mb-0">
          <thead>
            <tr>
              <th>名前</th>
              <th style="width: 100px;">時間(分)</th>
              <th style="width: 120px;">料金</th>
              <th style="width: 120px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in courses" :key="c.id">
              <td>{{ c.name }}</td>
              <td>{{ c.duration }}</td>
              <td>{{ c.price.toLocaleString() }}円</td>
              <td>
                <button class="btn btn-outline-primary btn-sm me-1" @click="openEdit(c)">
                  <i class="ti ti-edit"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" @click="onDelete(c)">
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
            <h5 class="modal-title">{{ editingId ? 'コース編集' : 'コース追加' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

            <div class="mb-3">
              <label class="form-label">名前 <span class="text-danger">*</span></label>
              <input v-model="form.name" type="text" class="form-control" placeholder="コース名" />
            </div>
            <div class="mb-3">
              <label class="form-label">時間(分) <span class="text-danger">*</span></label>
              <input v-model.number="form.duration" type="number" class="form-control" min="1" />
            </div>
            <div class="mb-3">
              <label class="form-label">料金 <span class="text-danger">*</span></label>
              <input v-model.number="form.price" type="number" class="form-control" min="0" />
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
