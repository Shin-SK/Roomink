<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const shifts = ref([])
const casts = ref([])
const rooms = ref([])

const today = new Date().toISOString().slice(0, 10)

// 現在時刻（1分ごとに更新して未出勤判定をリアクティブに）
const now = ref(new Date())
let nowTimer = null

// Filter: 'all' | 'upcoming' | 'today' | 'date'
const viewMode = ref('all')
const filterDate = ref(today)
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
  return { date: today, cast: '', room: '', start_time: '', end_time: '' }
}

async function loadMasters() {
  const [c, r] = await Promise.all([api.getCasts(), api.getRooms()])
  casts.value = Array.isArray(c) ? c : []
  rooms.value = Array.isArray(r) ? r : []
}

function buildParams() {
  if (viewMode.value === 'today') return `date=${today}&limit=500`
  if (viewMode.value === 'upcoming') return `date__gte=${today}&limit=500`
  if (viewMode.value === 'date') return `date=${filterDate.value}&limit=500`
  return 'limit=500' // all
}

async function loadShifts() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getShifts(buildParams())
    shifts.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
  await nextTick()
  scrollToToday()
}

function scrollToToday() {
  const el = document.getElementById(`shift-date-${today}`)
  if (el && typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

onMounted(async () => {
  try {
    await loadMasters()
  } catch (e) {
    error.value = e.message
  }
  await loadShifts()
  nowTimer = setInterval(() => { now.value = new Date() }, 60 * 1000)
})

onBeforeUnmount(() => {
  if (nowTimer) clearInterval(nowTimer)
})

watch(viewMode, () => loadShifts())
watch(filterDate, () => {
  if (viewMode.value === 'date') loadShifts()
})

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

// 日付ごとにグループ化（日付昇順）
const groupedShifts = computed(() => {
  const map = new Map()
  for (const s of filteredShifts.value) {
    if (!map.has(s.date)) map.set(s.date, [])
    map.get(s.date).push(s)
  }
  const keys = Array.from(map.keys()).sort((a, b) => b.localeCompare(a))
  return keys.map(date => ({ date, items: map.get(date) }))
})

const totalCount = computed(() => filteredShifts.value.length)

function castName(id) {
  return casts.value.find(c => c.id === id)?.name || id
}
function castAvatar(s) {
  return s.cast_avatar_url || casts.value.find(c => c.id === s.cast)?.avatar_url || ''
}
function roomName(id) {
  return rooms.value.find(r => r.id === id)?.name || id
}

const WEEK = ['日', '月', '火', '水', '木', '金', '土']
function formatDateLabel(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  const w = WEEK[dt.getDay()]
  let label = `${m}月${d}日 (${w})`
  if (dateStr === today) label += ' ・ 今日'
  return label
}

function isPast(dateStr) {
  return dateStr < today
}

function formatClockedAt(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

// 今日のシフトで「開始時刻を過ぎているのに未出勤」 = 来てない
function isLate(s) {
  if (s.date !== today) return false
  if (s.clocked_in_at) return false
  if (!s.start_time) return false
  const [h, m] = s.start_time.split(':').map(Number)
  const start = new Date(now.value)
  start.setHours(h, m, 0, 0)
  return now.value >= start
}

// 今日のサマリ
const todaySummary = computed(() => {
  const items = shifts.value.filter(s => s.date === today)
  const total = items.length
  const done = items.filter(s => s.clocked_in_at).length
  const late = items.filter(s => isLate(s)).length
  return { total, done, late, notYet: total - done }
})

async function onClockIn(s) {
  try {
    const updated = await api.clockInShift(s.id)
    Object.assign(s, updated)
  } catch (e) {
    error.value = e.message
  }
}

async function onClearClockIn(s) {
  if (!confirm('出勤を取り消しますか？')) return
  try {
    const updated = await api.clearClockInShift(s.id)
    s.clocked_in_at = updated.clocked_in_at
  } catch (e) {
    error.value = e.message
  }
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
        <!-- View mode + Search -->
        <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
          <div class="btn-group" role="group">
            <button
              type="button"
              class="btn btn-sm"
              :class="viewMode === 'all' ? 'btn-primary' : 'btn-outline-secondary'"
              @click="viewMode = 'all'"
            >全期間</button>
            <button
              type="button"
              class="btn btn-sm"
              :class="viewMode === 'upcoming' ? 'btn-primary' : 'btn-outline-secondary'"
              @click="viewMode = 'upcoming'"
            >今後</button>
            <button
              type="button"
              class="btn btn-sm"
              :class="viewMode === 'today' ? 'btn-primary' : 'btn-outline-secondary'"
              @click="viewMode = 'today'"
            >今日</button>
            <button
              type="button"
              class="btn btn-sm"
              :class="viewMode === 'date' ? 'btn-primary' : 'btn-outline-secondary'"
              @click="viewMode = 'date'"
            >日付指定</button>
          </div>
          <input
            v-if="viewMode === 'date'"
            v-model="filterDate"
            type="date"
            class="form-control form-control-sm"
            style="width: 160px;"
          />
          <input
            v-model="searchQuery"
            type="text"
            class="form-control form-control-sm flex-grow-1"
            style="max-width: 280px;"
            placeholder="キャスト名で検索..."
          />
          <button
            v-if="viewMode === 'all' || viewMode === 'upcoming'"
            type="button"
            class="btn btn-sm btn-outline-primary ms-auto"
            @click="scrollToToday"
          >
            <i class="ti ti-calendar-event"></i> 今日へ
          </button>
        </div>

        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!totalCount" class="text-muted text-center py-4">
          {{ searchQuery ? '該当するシフトがありません' : 'シフトがありません' }}
        </div>

        <div v-else class="shift-groups">
          <div
            v-for="g in groupedShifts"
            :key="g.date"
            :id="`shift-date-${g.date}`"
            class="shift-group"
            :class="{ 'shift-group--today': g.date === today, 'shift-group--past': isPast(g.date) }"
          >
            <div class="shift-group__header">
              <span class="shift-group__date">{{ formatDateLabel(g.date) }}</span>
              <span class="shift-group__meta">
                <span
                  v-if="g.date === today && todaySummary.late > 0"
                  class="badge bg-danger me-2"
                >未出勤 {{ todaySummary.late }}</span>
                <span
                  v-if="g.date === today"
                  class="text-muted me-2 small"
                >出勤 {{ todaySummary.done }} / {{ todaySummary.total }}</span>
                <span class="shift-group__count">{{ g.items.length }}件</span>
              </span>
            </div>
            <div class="table-responsive">
            <table class="table table-hover table-sm mb-0 shift-table">
              <thead>
                <tr>
                  <th style="width: 110px;">状態</th>
                  <th>キャスト</th>
                  <th>部屋</th>
                  <th style="width: 80px;">開始</th>
                  <th style="width: 80px;">終了</th>
                  <th style="width: 200px;">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="s in g.items"
                  :key="s.id"
                  :class="{ 'row-late': isLate(s), 'row-done': s.clocked_in_at }"
                >
                  <td>
                    <span v-if="s.clocked_in_at" class="badge bg-success">
                      <i class="ti ti-check"></i> 出勤 {{ formatClockedAt(s.clocked_in_at) }}
                    </span>
                    <span v-else-if="isLate(s)" class="badge bg-danger">未出勤</span>
                    <span v-else-if="s.date === today" class="badge bg-light text-muted">未</span>
                    <span v-else-if="s.date < today" class="badge bg-light text-muted">未記録</span>
                    <span v-else class="text-muted small">—</span>
                  </td>
                  <td>
                    <div class="cast-cell">
                      <img
                        v-if="castAvatar(s)"
                        :src="castAvatar(s)"
                        :alt="s.cast_name || castName(s.cast)"
                        class="cast-cell__avatar"
                      />
                      <div v-else class="cast-cell__avatar cast-cell__avatar--placeholder">
                        <i class="ti ti-user"></i>
                      </div>
                      <span>{{ s.cast_name || castName(s.cast) }}</span>
                    </div>
                  </td>
                  <td>{{ s.room_name || roomName(s.room) }}</td>
                  <td>{{ s.start_time?.slice(0, 5) }}</td>
                  <td>{{ s.end_time?.slice(0, 5) }}</td>
                  <td>
                    <button
                      v-if="s.date === today && !s.clocked_in_at"
                      class="btn btn-success btn-sm me-1"
                      @click="onClockIn(s)"
                    >
                      <i class="ti ti-login"></i> 出勤OK
                    </button>
                    <button
                      v-if="s.date < today && !s.clocked_in_at"
                      class="btn btn-outline-secondary btn-sm me-1"
                      @click="onClockIn(s)"
                      title="この日の出勤として後追い記録"
                    >
                      <i class="ti ti-history"></i> 後追い記録
                    </button>
                    <button
                      v-if="s.clocked_in_at"
                      class="btn btn-outline-secondary btn-sm me-1"
                      @click="onClearClockIn(s)"
                      title="出勤取消"
                    >
                      <i class="ti ti-rotate"></i>
                    </button>
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
        </div>
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
                <input v-model="form.start_time" type="time" step="1800" class="form-control" />
              </div>
              <div class="col-6 mb-3">
                <label class="form-label">終了時間</label>
                <input v-model="form.end_time" type="time" step="1800" class="form-control" />
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
.shift-groups {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.shift-group {
  border: 1px solid var(--rk-grid-border, #E6EEF0);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.85rem;
    background: #f6f9fa;
    border-bottom: 1px solid var(--rk-grid-border, #E6EEF0);
    font-weight: 600;
    font-size: 0.92rem;
  }

  &__count {
    color: #6c757d;
    font-weight: 400;
    font-size: 0.82rem;
  }

  &--today {
    border-color: var(--rk-primary, #2A9D8F);
    box-shadow: 0 0 0 2px rgba(42, 157, 143, 0.15);
  }

  &--today .shift-group__header {
    background: rgba(42, 157, 143, 0.1);
    color: var(--rk-primary, #2A9D8F);
  }

  &--past {
    opacity: 0.65;
  }
}

.cast-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;

  &__avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;

    &--placeholder {
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f0f0f0;
      color: #aaa;
      font-size: 14px;
    }
  }
}

// 行: 未出勤（赤帯）/ 出勤済（緑寄り）
:deep(tr.row-late) > td {
  background: rgba(220, 53, 69, 0.08);
}

:deep(tr.row-done) > td {
  background: rgba(42, 157, 143, 0.05);
}

// スマホでは横スクロール。表は最小幅を確保して詰めない
.shift-table {
  min-width: 720px;

  :deep(td),
  :deep(th) {
    white-space: nowrap;
    vertical-align: middle;
  }
}

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
