<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const shifts = ref([])
const casts = ref([])
const rooms = ref([])

// Filter
const filterDate = ref(new Date().toISOString().slice(0, 10))
const searchQuery = ref('')

// Form
const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

// キャスト選択用検索
const castSearch = ref('')
const filteredCasts = computed(() => {
  const q = castSearch.value.trim()
  if (!q) return casts.value
  return casts.value.filter(c => (c.name || '').includes(q))
})

function emptyForm() {
  return { date: filterDate.value, cast: '', room: '', start_time: '', end_time: '' }
}

async function loadMasters() {
  const [c, r] = await Promise.all([api.getCasts(), api.getRooms()])
  casts.value = Array.isArray(c) ? c : []
  rooms.value = Array.isArray(r) ? r : []
}

async function loadShifts() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getShifts(`date=${filterDate.value}`)
    shifts.value = Array.isArray(data) ? data : []
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
  await loadShifts()
})

watch(filterDate, () => loadShifts())

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(s) {
  editingId.value = s.id
  form.value = {
    date: s.date,
    cast: s.cast,
    room: s.room,
    start_time: s.start_time?.slice(0, 5) || '',
    end_time: s.end_time?.slice(0, 5) || '',
  }
  formError.value = ''
  showForm.value = true
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const body = {
      date: form.value.date,
      cast: Number(form.value.cast),
      room: Number(form.value.room),
      start_time: form.value.start_time,
      end_time: form.value.end_time,
    }
    if (editingId.value) {
      await api.updateShift(editingId.value, body)
    } else {
      await api.createShift(body)
    }
    showForm.value = false
    await loadShifts()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function onDelete(id) {
  if (!confirm('このシフトを削除しますか？')) return
  try {
    await api.deleteShift(id)
    await loadShifts()
  } catch (e) {
    error.value = e.message
  }
}

const filteredShifts = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return shifts.value
  return shifts.value.filter(s => {
    const name = (s.cast_name || castName(s.cast)).toLowerCase()
    return name.includes(q)
  })
})

function castName(id) {
  return casts.value.find(c => c.id === id)?.name || id
}
function roomName(id) {
  return rooms.value.find(r => r.id === id)?.name || id
}
</script>

<template>
  <LayoutOperator>
    <template #title>シフト管理</template>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-clock"></i> シフト一覧</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus"></i> シフト追加
        </button>
      </div>
      <div class="card-body">
        <!-- Date filter + Search -->
        <div class="row mb-3">
          <div class="col-md-4">
            <input v-model="filterDate" type="date" class="form-control" />
          </div>
          <div class="col-md-4">
            <input v-model="searchQuery" type="text" class="form-control" placeholder="キャスト名で検索..." />
          </div>
        </div>

        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!filteredShifts.length" class="text-muted text-center py-3">
          {{ searchQuery ? '該当するシフトがありません' : 'この日のシフトはありません' }}
        </div>

        <table v-else class="table table-hover mb-0">
          <thead>
            <tr>
              <th>キャスト</th>
              <th>部屋</th>
              <th>開始</th>
              <th>終了</th>
              <th style="width: 120px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in filteredShifts" :key="s.id">
              <td>{{ s.cast_name || castName(s.cast) }}</td>
              <td>{{ s.room_name || roomName(s.room) }}</td>
              <td>{{ s.start_time?.slice(0, 5) }}</td>
              <td>{{ s.end_time?.slice(0, 5) }}</td>
              <td>
                <button class="btn btn-outline-primary btn-sm me-1" @click="openEdit(s)">
                  <i class="ti ti-edit"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm" @click="onDelete(s.id)">
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
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editingId ? 'シフト編集' : 'シフト追加' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

            <div class="mb-3">
              <label class="form-label">日付</label>
              <input v-model="form.date" type="date" class="form-control" />
            </div>
            <div class="mb-3">
              <label class="form-label">キャスト</label>
              <input
                v-model="castSearch"
                type="text"
                class="form-control form-control-sm mb-2"
                placeholder="名前で検索..."
              />
              <div class="cast-scroll">
                <div
                  v-for="c in filteredCasts"
                  :key="c.id"
                  class="cast-chip"
                  :class="{ active: form.cast === c.id }"
                  @click="form.cast = c.id"
                >
                  <img
                    v-if="c.avatar_url"
                    :src="c.avatar_url"
                    :alt="c.name"
                    class="cast-chip__avatar"
                  />
                  <div v-else class="cast-chip__avatar cast-chip__avatar--placeholder">
                    <i class="ti ti-user"></i>
                  </div>
                  <span class="cast-chip__name">{{ c.name }}</span>
                </div>
              </div>
              <div v-if="filteredCasts.length === 0" class="text-muted small mt-1">
                該当するキャストがいません
              </div>
            </div>
            <div class="mb-3">
              <label class="form-label">部屋</label>
              <select v-model="form.room" class="form-select">
                <option value="" disabled>選択してください</option>
                <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
              </select>
            </div>
            <div class="row">
              <div class="col-6 mb-3">
                <label class="form-label">開始時間</label>
                <input v-model="form.start_time" type="time" class="form-control" />
              </div>
              <div class="col-6 mb-3">
                <label class="form-label">終了時間</label>
                <input v-model="form.end_time" type="time" class="form-control" />
              </div>
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

<style scoped lang="scss">
.cast-scroll {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.5rem;
  border: 1px solid var(--rk-grid-border, #E6EEF0);
  border-radius: 8px;
  max-height: 280px;
  overflow-y: auto;
}

.cast-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  border: 2px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  width: 88px;
  padding: 4px;
  transition: all 0.15s;

  &:hover {
    border-color: var(--rk-primary);
  }

  &.active {
    border-color: var(--rk-primary);
    background: rgba(42, 157, 143, 0.08);
  }

  &__avatar {
    width: 64px;
    height: 64px;
    border-radius: 50%;
    object-fit: cover;

    &--placeholder {
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f0f0f0;
      color: #aaa;
      font-size: 22px;
    }
  }

  &__name {
    font-size: 0.75rem;
    text-align: center;
    line-height: 1.2;
    word-break: keep-all;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }
}
</style>
