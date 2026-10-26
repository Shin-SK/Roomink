<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import ShiftCalendar from '../../components/ShiftCalendar.vue'
import { calendarDays, movePeriod, parseDay } from '../../shiftCalendar.js'
import { api } from '../../api.js'
import { normalizeShiftTime as normalizeExtendedTime } from '../../shiftTime.js'

const loading = ref(true)
const error = ref('')
const shifts = ref([])
const casts = ref([])
const rooms = ref([])

function localToday() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const today = ref(localToday())

// 現在時刻（1分ごとに更新して未出勤判定をリアクティブに）
const now = ref(new Date())
let nowTimer = null

// 出勤確認アラート（Phase 3-F土台。外部通知は行わず、画面表示のみ）
const shiftAlerts = ref([])
const shiftAlertsLoading = ref(true)

// Filter: 'all' | 'upcoming' | 'today' | 'date'
const viewMode = ref('month')
const calendarAnchor = ref(today.value)
const selectedDay = ref(today.value)
const filterRoom = ref('')
const isCalendar = computed(() => ['month', 'week'].includes(viewMode.value))
const periodLabel = computed(() => {
  const d = parseDay(calendarAnchor.value)
  if (viewMode.value === 'month') return `${d.getFullYear()}年${d.getMonth() + 1}月`
  const days = calendarDays(calendarAnchor.value, 'week')
  return `${days[0].replaceAll('-', '/')} 〜 ${days[6].replaceAll('-', '/')}`
})
function changePeriod(direction) {
  calendarAnchor.value = movePeriod(calendarAnchor.value, viewMode.value, direction)
  selectedDay.value = calendarAnchor.value
}
function goToday() {
  calendarAnchor.value = today.value; selectedDay.value = today.value
  if (!isCalendar.value) { filterDate.value = today.value; viewMode.value = 'today' }
}
async function selectCalendarDay(day) {
  selectedDay.value = day
  await nextTick()
  document.getElementById('selected-shift-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
const filterDate = ref(today.value)
const searchQuery = ref('')

// Form
const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saveNotice = ref('')
const saving = ref(false)

// キャスト選択用検索
const castSearch = ref('')
const filteredCasts = computed(() => {
  const q = castSearch.value.trim()
  if (!q) return casts.value
  return casts.value.filter(c => (c.name || '').includes(q))
})

function emptyForm() {
  return { date: today.value, cast: '', room: '', start_time: '', end_time: '', daily_memo: '', is_absent: false }
}

async function loadMasters() {
  const [c, r] = await Promise.all([api.getCasts(), api.getRooms()])
  casts.value = Array.isArray(c) ? c : []
  rooms.value = Array.isArray(r) ? r : []
}

function buildParams() {
  if (isCalendar.value) {
    const days = calendarDays(calendarAnchor.value, viewMode.value)
    return `date__gte=${days[0]}&date__lte=${days.at(-1)}&limit=500`
  }
  if (viewMode.value === 'today') return `date=${today.value}&limit=500`
  if (viewMode.value === 'upcoming') return `date__gte=${today.value}&limit=500`
  if (viewMode.value === 'date') return `date=${filterDate.value}&limit=500`
  return 'limit=500' // all
}

let shiftLoadSequence = 0
let disposed = false
async function loadShifts() {
  if (disposed) return
  const sequence = ++shiftLoadSequence
  loading.value = true
  error.value = ''
  try {
    const data = await api.getShifts(buildParams())
    if (sequence !== shiftLoadSequence) return
    shifts.value = Array.isArray(data) ? data : []
  } catch (e) {
    if (sequence !== shiftLoadSequence) return
    shifts.value = []
    error.value = e.message
  } finally {
    if (sequence === shiftLoadSequence) loading.value = false
  }
  await nextTick()
  if (sequence === shiftLoadSequence && !isCalendar.value) scrollToToday()
}

function scrollToToday() {
  const el = document.getElementById(`shift-date-${today.value}`)
  if (el && typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

async function loadShiftAlerts() {
  shiftAlertsLoading.value = true
  try {
    const data = await api.getShiftConfirmAlerts()
    shiftAlerts.value = Array.isArray(data?.alerts) ? data.alerts : []
  } catch (_) {
    // アラート取得失敗は画面全体のerrorには出さない（致命的ではないため）
  } finally {
    shiftAlertsLoading.value = false
  }
}

// 通知テストログ作成（Phase 4土台。実送信は行わない）
const notifyTestingId = ref(null)
async function createNotificationTestLog(a) {
  if (notifyTestingId.value) return
  notifyTestingId.value = a.shift_id
  try {
    await api.markShiftConfirmNotificationTest(a.shift_id, { alert_level: a.alert_level, target_type: 'CAST' })
    await loadShiftAlerts()
  } catch (e) {
    alert(e.message)
  } finally {
    notifyTestingId.value = null
  }
}

const notificationStatusLabel = { PENDING: '送信予定', SENT: '送信済', SKIPPED: 'スキップ(テスト)', FAILED: '失敗' }

async function jumpToShiftAlert(a) {
  if (viewMode.value !== 'upcoming' && viewMode.value !== 'all') {
    viewMode.value = 'upcoming'
  }
  await loadShifts()
  await nextTick()
  const el = document.getElementById(`shift-date-${a.date}`)
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
  if (disposed) return
  await loadShifts()
  if (disposed) return
  await loadShiftAlerts()
  nowTimer = setInterval(() => {
    now.value = new Date()
    if (today.value !== localToday()) {
      today.value = localToday()
      loadShifts()
    }
    loadShiftAlerts()
  }, 60 * 1000)
})

onBeforeUnmount(() => {
  disposed = true
  shiftLoadSequence++
  if (nowTimer) clearInterval(nowTimer)
})

watch(viewMode, () => {
  if (isCalendar.value && !calendarDays(calendarAnchor.value, viewMode.value).includes(selectedDay.value)) selectedDay.value = calendarAnchor.value
  loadShifts()
})
watch(calendarAnchor, () => { if (isCalendar.value) loadShifts() })
watch(filterDate, () => {
  if (viewMode.value === 'date') loadShifts()
})

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  castSearch.value = ''
  formError.value = ''
  showForm.value = true
}

function openEdit(s) {
  editingId.value = s.id
  form.value = {
    date: s.date,
    cast: s.cast,
    room: s.room || '',
    start_time: s.start_time_extended || s.start_time?.slice(0, 5) || '',
    end_time: s.end_time_extended || s.end_time?.slice(0, 5) || '',
    daily_memo: s.daily_memo || '',
    is_absent: !!s.is_absent,
  }
  formError.value = ''
  showForm.value = true
}

async function onSave() {
  if (saving.value) return
  if (!Number.isInteger(Number(form.value.cast)) || Number(form.value.cast) <= 0) {
    formError.value = 'キャストを選択してください'
    return
  }
  saving.value = true
  formError.value = ''
  saveNotice.value = ''
  try {
    const start = normalizeExtendedTime(form.value.start_time, '開始時間')
    const end = normalizeExtendedTime(form.value.end_time, '終了時間')
    const body = {
      date: form.value.date,
      cast: Number(form.value.cast),
      room: form.value.room ? Number(form.value.room) : null,
      requested_area: null,
      start_time: start.time,
      start_day_offset: start.dayOffset,
      end_time: end.time,
      end_day_offset: end.dayOffset,
      daily_memo: form.value.daily_memo || '',
      is_absent: !!form.value.is_absent,
    }
    let saved
    if (editingId.value) {
      saved = await api.updateShift(editingId.value, body)
    } else {
      saved = await api.createShift(body)
    }
    if (saved?.assigned_order_count) {
      saveNotice.value = `ルーム未定だった予約 ${saved.assigned_order_count}件へ「${roomName(saved.room)}」を割り当てました。`
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
  return shifts.value.filter(s => {
    if (filterRoom.value && String(s.room || '') !== filterRoom.value) return false
    const name = (s.cast_name || castName(s.cast)).toLowerCase()
    return !q || name.includes(q)
  })
})

// 日付ごとにグループ化（日付昇順）
const groupedShifts = computed(() => {
  const map = new Map()
  for (const s of filteredShifts.value) {
    if (isCalendar.value && s.date !== selectedDay.value) continue
    if (!map.has(s.date)) map.set(s.date, [])
    map.get(s.date).push(s)
  }
  const keys = Array.from(map.keys()).sort((a, b) => a.localeCompare(b))
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
  if (dateStr === today.value) label += ' ・ 今日'
  return label
}

function isPast(dateStr) {
  return dateStr < today.value
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
  if (s.date !== today.value) return false
  if (s.clocked_in_at) return false
  if (!s.start_time) return false
  const [h, m] = s.start_time.split(':').map(Number)
  const start = new Date(now.value)
  start.setDate(start.getDate() + Number(s.start_day_offset || 0))
  start.setHours(h, m, 0, 0)
  return now.value >= start
}

// 今日のサマリ
const todaySummary = computed(() => {
  const items = shifts.value.filter(s => s.date === today.value)
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

    <div v-if="saveNotice" class="alert alert-success py-2 px-3 mb-3">
      {{ saveNotice }}
    </div>

    <div class="mb-3">
      <router-link to="/op/shifts/weekly" class="btn btn-primary btn-sm">
        <i class="ti ti-calendar-week"></i> 週次シフト入力（1週間分まとめて登録）
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <!-- 出勤確認アラート（Phase 3-F土台） -->
    <div class="card mb-3">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-alert-triangle"></i> 出勤確認アラート</span>
      </div>
      <div class="card-body">
        <div v-if="shiftAlertsLoading" class="text-muted text-center py-2 small">読み込み中...</div>
        <div v-else-if="!shiftAlerts.length" class="text-muted text-center py-2 small">
          現在、出勤確認アラートはありません
        </div>
        <div v-else>
          <div
            v-for="a in shiftAlerts"
            :key="a.shift_id"
            class="border-bottom py-2 small alert-row"
            :class="a.alert_level === 'ONE_HOUR' ? 'alert-row--danger' : 'alert-row--warning'"
          >
            <div class="d-flex justify-content-between align-items-center" style="cursor: pointer;" @click="jumpToShiftAlert(a)">
              <div>
                <span class="badge me-2" :class="a.alert_level === 'ONE_HOUR' ? 'bg-danger' : 'bg-warning text-dark'">
                  {{ a.alert_level === 'ONE_HOUR' ? '1時間前未確認' : '2時間前未確認' }}
                </span>
                <span class="fw-bold">{{ a.cast_name }}</span>
                <span class="text-muted"> {{ a.date }} {{ a.start_time_extended || a.start_time }}〜<template v-if="a.room_name"> {{ a.room_name }}</template></span>
              </div>
              <div class="text-muted flex-shrink-0 ms-2">
                {{ a.minutes_until_start >= 0 ? `残り${a.minutes_until_start}分` : `${-a.minutes_until_start}分超過` }}
              </div>
            </div>
            <div class="d-flex justify-content-between align-items-center mt-1">
              <div class="text-muted" style="font-size: 0.75rem;">
                通知対象: キャスト ・
                <template v-if="a.has_notification_log">
                  ログあり（{{ notificationStatusLabel[a.last_notification_status] || a.last_notification_status }}）
                </template>
                <template v-else>ログなし</template>
                ・実送信は未対応です
              </div>
              <button
                class="btn btn-outline-secondary btn-sm"
                style="font-size: 0.7rem; padding: 2px 8px;"
                :disabled="notifyTestingId === a.shift_id"
                @click.stop="createNotificationTestLog(a)"
              >{{ notifyTestingId === a.shift_id ? '作成中...' : 'テストログ作成' }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-clock"></i> シフト一覧</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus"></i> シフト追加
        </button>
      </div>
      <div class="card-body">
        <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
          <button type="button" class="btn btn-sm btn-outline-secondary" @click="goToday">今日</button>
          <template v-if="isCalendar">
            <button type="button" class="btn btn-sm btn-outline-secondary" :aria-label="viewMode === 'month' ? '前の月' : '前の週'" @click="changePeriod(-1)">‹</button>
            <button type="button" class="btn btn-sm btn-outline-secondary" :aria-label="viewMode === 'month' ? '次の月' : '次の週'" @click="changePeriod(1)">›</button>
            <strong class="me-auto" style="font-size: clamp(.85rem, 2vw, 1.2rem)">{{ periodLabel }}</strong>
          </template>
          <div class="btn-group ms-auto" role="group" aria-label="シフトの表示方法">
            <button type="button" class="btn btn-sm" :class="viewMode === 'month' ? 'btn-primary' : 'btn-outline-secondary'" :aria-pressed="viewMode === 'month'" @click="viewMode = 'month'">月</button>
            <button type="button" class="btn btn-sm" :class="viewMode === 'week' ? 'btn-primary' : 'btn-outline-secondary'" :aria-pressed="viewMode === 'week'" @click="viewMode = 'week'">週</button>
            <button type="button" class="btn btn-sm" :class="!isCalendar ? 'btn-primary' : 'btn-outline-secondary'" :aria-pressed="!isCalendar" @click="viewMode = 'upcoming'">一覧</button>
          </div>
        </div>
        <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
          <div v-if="!isCalendar" class="btn-group" role="group">
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
            aria-label="キャスト名で検索"
          />
          <select v-model="filterRoom" class="form-select form-select-sm" style="max-width: 200px" aria-label="ルームで絞り込み">
            <option value="">すべてのルーム</option>
            <option v-for="room in rooms" :key="room.id" :value="String(room.id)">{{ room.name }}</option>
          </select>
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

        <ShiftCalendar v-if="isCalendar && !loading" :mode="viewMode" :anchor="calendarAnchor" :today="today" :selected="selectedDay" :shifts="filteredShifts" @select-day="selectCalendarDay" @select-shift="openEdit" />
        <div v-if="isCalendar && !loading" id="selected-shift-list" class="d-flex align-items-center justify-content-between mb-2 flex-wrap gap-2" style="scroll-margin-top: 40px">
          <h3 class="h6 m-0">{{ formatDateLabel(selectedDay) }}のシフト</h3>
          <button type="button" class="btn btn-sm btn-outline-primary" @click="openCreate(); form.date = selectedDay">この日にシフトを追加</button>
        </div>

        <div v-if="!loading && !groupedShifts.length" class="text-muted text-center py-4">
          {{ searchQuery ? '該当するシフトがありません' : 'シフトがありません' }}
        </div>

        <div v-else-if="!loading" class="shift-groups">
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
                  <th style="width: 110px;">出勤確認</th>
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
                    <span v-if="s.is_absent" class="badge bg-danger">当欠</span>
                    <span v-else-if="s.clocked_in_at" class="badge bg-success">
                      <i class="ti ti-check"></i> 出勤 {{ formatClockedAt(s.clocked_in_at) }}
                    </span>
                    <span v-else-if="isLate(s)" class="badge bg-danger">未出勤</span>
                    <span v-else-if="s.date === today" class="badge bg-light text-muted">未</span>
                    <span v-else-if="s.date < today" class="badge bg-light text-muted">未記録</span>
                    <span v-else class="text-muted small">—</span>
                  </td>
                  <td>
                    <span v-if="s.confirmed_at" class="badge bg-info-subtle text-info-emphasis">
                      <i class="ti ti-check"></i> 確認済 {{ formatClockedAt(s.confirmed_at) }}
                    </span>
                    <span v-else class="badge bg-light text-muted">未確認</span>
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
                  <td>{{ s.room_name || roomName(s.room) || '未定' }}</td>
                  <td>{{ s.start_time_extended || s.start_time?.slice(0, 5) }}</td>
                  <td>{{ s.end_time_extended || s.end_time?.slice(0, 5) }}</td>
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
              <label class="form-label">ルーム（任意）</label>
              <select v-model="form.room" class="form-select">
                <option value="">未定（後から割り当て）</option>
                <option v-for="room in rooms" :key="room.id" :value="room.id">{{ room.name }}{{ room.area_name ? `（${room.area_name}）` : '' }}</option>
              </select>
              <div class="form-text">予約に使うルームを直接選択します。未定のまま保存して後から割り当てることもできます。</div>
            </div>
            <div class="row">
              <div class="col-6 mb-3">
                <label class="form-label">開始時間</label>
                <input
                  v-model.trim="form.start_time"
                  type="text"
                  inputmode="numeric"
                  maxlength="5"
                  placeholder="例: 18:00 / 24:00"
                  class="form-control"
                />
                <div class="form-text">HH:MM形式。24:00以降は翌日の時刻として保存されます（最大29:00）。</div>
              </div>
              <div class="col-6 mb-3">
                <label class="form-label">終了時間</label>
                <input
                  v-model.trim="form.end_time"
                  type="text"
                  inputmode="numeric"
                  maxlength="5"
                  placeholder="例: 23:00 / 29:00"
                  class="form-control"
                />
                <div class="form-text">HH:MM形式。24:00以降は翌日の時刻として保存されます（最大29:00）。</div>
              </div>
            </div>
            <div class="mb-3">
              <label class="form-label">当日メモ</label>
              <textarea v-model="form.daily_memo" class="form-control" rows="2"
                placeholder="その日だけのメモ（例: 入れ替え連絡必須、当欠理由、本日だけ早上がり注意）"></textarea>
            </div>
            <div class="mb-3 form-check">
              <input v-model="form.is_absent" id="shift-is-absent" type="checkbox" class="form-check-input" />
              <label for="shift-is-absent" class="form-check-label">当欠（このシフトを欠勤扱いにする）</label>
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

.alert-row {
  &:last-child {
    border-bottom: none !important;
  }
  &--warning {
    background: rgba(255, 193, 7, 0.08);
  }
  &--danger {
    background: rgba(220, 53, 69, 0.08);
  }
}

.cast-cell {
  display: flex;
  align-items: center;
  gap: 0.35rem;

  &__avatar {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;

    &--placeholder {
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f0f0f0;
      color: #aaa;
      font-size: 12px;
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

// シフト一覧は一度に多くの行を確認できる密度を保つ。
// スマホでは横スクロールを維持しつつ、文字・余白・列幅を過剰にしない。
.shift-table {
  min-width: 640px;
  font-size: 0.875rem;

  :deep(td),
  :deep(th) {
    white-space: nowrap;
    vertical-align: middle;
    padding: 0.35rem 0.5rem;
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
