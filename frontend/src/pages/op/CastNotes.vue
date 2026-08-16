<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'
import { uploadToCloudinary } from '../../cloudinary.js'

const loading = ref(true)
const error = ref('')
const notes = ref([])
const isManager = computed(() => getAuthRole() === 'manager')
const casts = ref([])
const targetCastSearch = ref('')
const imageUploading = ref(false)

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
onMounted(async () => {
  try {
    casts.value = await api.getCasts()
  } catch (e) {
    error.value = e.message
  }
})
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
  return {
    title: '', category: '', body: '', visibility: 'CAST', video_url: '', status: 'DRAFT',
    target_cast_ids: [], image_urls: [],
  }
}

const filteredTargetCasts = computed(() => {
  const keyword = targetCastSearch.value.trim().toLowerCase()
  return casts.value.filter(cast => !keyword || cast.name.toLowerCase().includes(keyword))
})

function toggleTargetCast(id) {
  const index = form.value.target_cast_ids.indexOf(id)
  if (index >= 0) form.value.target_cast_ids.splice(index, 1)
  else form.value.target_cast_ids.push(id)
}

async function onImageFiles(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  if (form.value.image_urls.length + files.length > 10) {
    formError.value = '画像は1つのノートにつき10枚までです'
    return
  }
  imageUploading.value = true
  formError.value = ''
  try {
    for (const file of files) {
      if (!file.type.startsWith('image/')) throw new Error('画像ファイルを選択してください')
      form.value.image_urls.push(await uploadToCloudinary(file))
    }
  } catch (e) {
    formError.value = e.message
  } finally {
    imageUploading.value = false
  }
}

function removeImage(index) {
  form.value.image_urls.splice(index, 1)
}

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  targetCastSearch.value = ''
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
    target_cast_ids: [...(n.target_cast_ids || [])],
    image_urls: [...(n.image_urls || [])],
  }
  formError.value = ''
  targetCastSearch.value = ''
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
              <td class="small">
                <div>{{ visibilityLabel[n.visibility] }}</div>
                <div v-if="n.target_cast_names?.length" class="text-muted mt-1">
                  対象: {{ n.target_cast_names.join('、') }}
                </div>
                <div v-else-if="n.visibility !== 'STAFF'" class="text-muted mt-1">対象: 全キャスト</div>
              </td>
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
            <div v-if="form.visibility !== 'STAFF'" class="mb-3">
              <label class="form-label">閲覧できるキャスト（任意）</label>
              <div class="form-text mb-2">指定しない場合は、所属する全キャストへ表示します。</div>
              <input v-model="targetCastSearch" type="search" class="form-control form-control-sm mb-2" placeholder="キャスト名で検索" />
              <div class="target-cast-list">
                <label v-for="cast in filteredTargetCasts" :key="cast.id" class="target-cast-item">
                  <input
                    type="checkbox"
                    class="form-check-input"
                    :checked="form.target_cast_ids.includes(cast.id)"
                    @change="toggleTargetCast(cast.id)"
                  />
                  <span>{{ cast.name }}</span>
                </label>
              </div>
              <div class="small text-muted mt-1">{{ form.target_cast_ids.length ? `${form.target_cast_ids.length}名を指定中` : '全キャストへ表示' }}</div>
            </div>
            <div class="mb-3">
              <label class="form-label">画像（任意・最大10枚）</label>
              <input
                type="file"
                class="form-control"
                accept="image/*"
                multiple
                :disabled="imageUploading || form.image_urls.length >= 10"
                @change="onImageFiles"
              />
              <div v-if="imageUploading" class="small text-primary mt-1">画像をアップロードしています...</div>
              <div v-if="form.image_urls.length" class="note-image-grid mt-2">
                <div v-for="(url, index) in form.image_urls" :key="url" class="note-image-item">
                  <img :src="url" alt="ノート添付画像" />
                  <button type="button" class="btn btn-danger btn-sm" title="画像を外す" @click="removeImage(index)">
                    <i class="ti ti-x"></i>
                  </button>
                </div>
              </div>
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

<style scoped>
.target-cast-list {
  max-height: 210px;
  overflow-y: auto;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 6px;
}
.target-cast-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
}
.target-cast-item:hover { background: #f6f8f8; }
.note-image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 8px;
}
.note-image-item { position: relative; }
.note-image-item img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #dee2e6;
}
.note-image-item button {
  position: absolute;
  top: 4px;
  right: 4px;
  padding: 2px 5px;
}
</style>
