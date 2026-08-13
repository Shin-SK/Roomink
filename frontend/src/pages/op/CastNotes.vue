<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

const loading = ref(true)
const error = ref('')
const notes = ref([])
const isManager = computed(() => getAuthRole() === 'manager')

const filterStatus = ref('')
const filterCategory = ref('')
const searchQuery = ref('')

const statusLabel = { DRAFT: '下書き', PUBLISHED: '公開', ARCHIVED: 'アーカイブ' }
const statusClass = { DRAFT: 'bg-secondary', PUBLISHED: 'bg-success', ARCHIVED: 'bg-dark' }
const visibilityLabel = { CAST: 'キャストのみ', STAFF: 'スタッフのみ', ALL: '全員' }

const categories = computed(() => {
  const set = new Set(notes.value.map(n => n.category).filter(Boolean))
  return Array.from(set).sort()
})

function buildParams() {
  const params = new URLSearchParams()
  if (filterStatus.value) params.set('status', filterStatus.value)
  if (filterCategory.value) params.set('category', filterCategory.value)
  if (searchQuery.value.trim()) params.set('search', searchQuery.value.trim())
  params.set('limit', '500')
  return params.toString()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getCastNotes(buildParams())
    notes.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch([filterStatus, filterCategory], load)

let searchTimer = null
watch(searchQuery, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 350)
})

// Form
const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

function emptyForm() {
  return { title: '', category: '', body: '', visibility: 'CAST', video_url: '', status: 'DRAFT' }
}

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(n) {
  editingId.value = n.id
  form.value = {
    title: n.title,
    category: n.category || '',
    body: n.body || '',
    visibility: n.visibility,
    video_url: n.video_url || '',
    status: n.status,
  }
  formError.value = ''
  showForm.value = true
}

async function onSave() {
  if (!form.value.title.trim()) { formError.value = 'タイトルを入力してください'; return }
  saving.value = true
  formError.value = ''
  try {
    const payload = { ...form.value }
    if (editingId.value) {
      await api.updateCastNote(editingId.value, payload)
    } else {
      await api.createCastNote(payload)
    }
    showForm.value = false
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function onDelete(n) {
  if (!confirm(`「${n.title}」を削除しますか？`)) return
  error.value = ''
  try {
    await api.deleteCastNote(n.id)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

async function doAction(fn, n) {
  error.value = ''
  try {
    await fn(n.id)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

function formatDateTime(s) {
  if (!s) return '-'
  return s.slice(0, 16).replace('T', ' ')
}
</script>

<template>
  <LayoutOperator>
    <template #title>ノート</template>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between flex-wrap gap-2">
        <span><i class="ti ti-notebook"></i> ノート一覧（施術マニュアル・接客メモ・お知らせ）</span>
        <button v-if="isManager" class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus text-white"></i> 新規作成
        </button>
      </div>
      <div class="card-body">
        <div class="row g-2 mb-3">
          <div class="col-6 col-md-3">
            <select v-model="filterStatus" class="form-select form-select-sm">
              <option value="">すべてのステータス</option>
              <option value="DRAFT">下書き</option>
              <option value="PUBLISHED">公開</option>
              <option value="ARCHIVED">アーカイブ</option>
            </select>
          </div>
          <div class="col-6 col-md-3">
            <select v-model="filterCategory" class="form-select form-select-sm">
              <option value="">すべてのカテゴリ</option>
              <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
            </select>
          </div>
          <div class="col-12 col-md-4">
            <input v-model="searchQuery" type="text" class="form-control form-control-sm" placeholder="タイトル・本文で検索" />
          </div>
        </div>

        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>
        <div v-else-if="!notes.length" class="text-muted text-center py-3">
          該当するノートはありません
        </div>
        <table v-else class="table table-hover mb-0">
          <thead>
            <tr>
              <th style="width: 40px;"></th>
              <th>タイトル</th>
              <th>カテゴリ</th>
              <th>公開範囲</th>
              <th>ステータス</th>
              <th>更新日時</th>
              <th v-if="isManager" style="width: 220px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="n in notes" :key="n.id">
              <td><i v-if="n.is_pinned" class="ti ti-pin text-warning" title="ピン留め"></i></td>
              <td>{{ n.title }}</td>
              <td><span v-if="n.category" class="badge bg-light text-dark border">{{ n.category }}</span><span v-else class="text-muted small">-</span></td>
              <td class="small">{{ visibilityLabel[n.visibility] }}</td>
              <td><span class="badge" :class="statusClass[n.status]">{{ statusLabel[n.status] }}</span></td>
              <td class="small text-muted">{{ formatDateTime(n.updated_at) }}</td>
              <td v-if="isManager">
                <div class="d-flex flex-wrap gap-1">
                  <button class="btn btn-outline-secondary btn-sm" @click="openEdit(n)"><i class="ti ti-edit"></i></button>
                  <button
                    v-if="n.status !== 'PUBLISHED'"
                    class="btn btn-outline-success btn-sm"
                    title="公開する"
                    @click="doAction(api.publishCastNote, n)"
                  ><i class="ti ti-eye"></i></button>
                  <button
                    v-if="n.status === 'PUBLISHED'"
                    class="btn btn-outline-secondary btn-sm"
                    title="下書きに戻す"
                    @click="doAction(api.unpublishCastNote, n)"
                  ><i class="ti ti-eye-off"></i></button>
                  <button
                    v-if="n.status !== 'ARCHIVED'"
                    class="btn btn-outline-dark btn-sm"
                    title="アーカイブ"
                    @click="doAction(api.archiveCastNote, n)"
                  ><i class="ti ti-archive"></i></button>
                  <button
                    v-if="!n.is_pinned"
                    class="btn btn-outline-warning btn-sm"
                    title="ピン留め"
                    @click="doAction(api.pinCastNote, n)"
                  ><i class="ti ti-pin"></i></button>
                  <button
                    v-else
                    class="btn btn-warning btn-sm"
                    title="ピン留め解除"
                    @click="doAction(api.unpinCastNote, n)"
                  ><i class="ti ti-pin-filled"></i></button>
                  <button class="btn btn-outline-danger btn-sm" title="削除" @click="onDelete(n)"><i class="ti ti-trash"></i></button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Form modal -->
    <div v-if="showForm" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showForm = false">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editingId ? 'ノート編集' : 'ノート新規作成' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

            <div class="mb-3">
              <label class="form-label">タイトル <span class="text-danger">*</span></label>
              <input v-model="form.title" type="text" class="form-control" />
            </div>
            <div class="row">
              <div class="col-6 mb-3">
                <label class="form-label">カテゴリ（任意）</label>
                <input v-model="form.category" type="text" class="form-control" placeholder="例: 施術マニュアル・接客メモ・店舗ルール" />
              </div>
              <div class="col-6 mb-3">
                <label class="form-label">公開範囲</label>
                <select v-model="form.visibility" class="form-select">
                  <option value="CAST">キャストのみ</option>
                  <option value="STAFF">スタッフのみ</option>
                  <option value="ALL">全員</option>
                </select>
              </div>
            </div>
            <div class="mb-3">
              <label class="form-label">本文（プレーンテキスト/簡易Markdown）</label>
              <textarea v-model="form.body" class="form-control" rows="8"></textarea>
            </div>
            <div class="mb-3">
              <label class="form-label">動画URL（任意・将来用。今回はアップロード機能なし）</label>
              <input v-model="form.video_url" type="url" class="form-control" placeholder="https://..." />
            </div>
            <div class="mb-3">
              <label class="form-label">ステータス</label>
              <select v-model="form.status" class="form-select">
                <option value="DRAFT">下書き</option>
                <option value="PUBLISHED">公開</option>
                <option value="ARCHIVED">アーカイブ</option>
              </select>
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
