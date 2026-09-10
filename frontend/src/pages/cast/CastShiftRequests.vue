<script setup>
import { computed, ref, onMounted } from 'vue'
import LayoutCast from '../../components/LayoutCast.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const requests = ref([])
const rooms = ref([])

const showForm = ref(false)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

function emptyForm() {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return {
    week_start: formatLocalDate(today),
    days: buildSevenDays(today),
    desired_room: '',
    memo: '',
  }
}

function formatLocalDate(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function buildSevenDays(startDate) {
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(startDate)
    date.setDate(date.getDate() + index)
    return {
      date: formatLocalDate(date),
      enabled: false,
      start_time: '',
      end_time: '',
    }
  })
}

function dateLabel(value) {
  const date = new Date(`${value}T00:00:00`)
  return `${date.getMonth() + 1}/${date.getDate()}（${['日', '月', '火', '水', '木', '金', '土'][date.getDay()]}）`
}

function changeWeek(offset) {
  const start = new Date(`${form.value.week_start}T00:00:00`)
  start.setDate(start.getDate() + offset * 7)
  form.value.week_start = formatLocalDate(start)
  form.value.days = buildSevenDays(start)
}

const selectedDayCount = computed(() => form.value.days.filter((day) => day.enabled).length)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getCastShiftRequests()
    requests.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const r = await api.getRooms()
    rooms.value = Array.isArray(r) ? r : []
  } catch (e) {
    error.value = e.message
  }
  await load()
})

function openCreate() {
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function formatExtendedEndTimeInput(value) {
  const normalized = String(value || '')
    .trim()
    .replace(/[０-９]/g, (digit) => String.fromCharCode(digit.charCodeAt(0) - 0xfee0))
    .replace('：', ':')

  if (/^\d{4}$/.test(normalized)) {
    return `${normalized.slice(0, 2)}:${normalized.slice(2)}`
  }
  return normalized
}

function formatEndTimeField(day) {
  day.end_time = formatExtendedEndTimeInput(day.end_time)
}

function normalizeExtendedEndTime(value) {
  const formatted = formatExtendedEndTimeInput(value)
  const match = /^(\d{2}):(\d{2})$/.exec(formatted)
  if (!match) throw new Error('終了時間は「23:00」または「2300」の形式で入力してください')

  const hour = Number(match[1])
  const minute = Number(match[2])
  if (minute > 59 || hour > 29 || (hour === 29 && minute !== 0)) {
    throw new Error('終了時間は00:00〜29:00で入力してください')
  }

  return {
    end_time: `${String(hour % 24).padStart(2, '0')}:${String(minute).padStart(2, '0')}`,
    end_day_offset: hour >= 24 ? 1 : 0,
  }
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const selectedDays = form.value.days.filter((day) => day.enabled)
    if (!selectedDays.length) throw new Error('出勤する日を1日以上選択してください')

    const items = selectedDays.map((day) => {
      if (!day.start_time || !day.end_time) {
        throw new Error(`${dateLabel(day.date)}の開始・終了時間を入力してください`)
      }
      const normalizedEnd = normalizeExtendedEndTime(day.end_time)
      day.end_time = formatExtendedEndTimeInput(day.end_time)
      return {
        date: day.date,
        start_time: day.start_time,
        ...normalizedEnd,
      }
    })
    const body = {
      items,
      memo: form.value.memo,
    }
    if (form.value.desired_room) body.desired_room = Number(form.value.desired_room)
    await api.createCastShiftRequestsBulk(body)
    showForm.value = false
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function onCancel(id) {
  if (!confirm('この申請を取消しますか？')) return
  try {
    await api.cancelCastShiftRequest(id)
    await load()
  } catch (e) {
    alert(e.message)
  }
}

const statusLabel = { REQUESTED: '申請中', APPROVED: '承認済', REJECTED: '却下', CANCELLED: '取消' }
const statusClass = { REQUESTED: 'bg-warning text-dark', APPROVED: 'bg-success', REJECTED: 'bg-danger', CANCELLED: 'bg-secondary' }

function formatDateTime(s) {
  if (!s) return ''
  return s.slice(0, 16).replace('T', ' ')
}
</script>

<template>
  <LayoutCast>
      <div v-if="error" class="alert alert-danger">{{ error }}</div>

      <div class="d-flex justify-content-between align-items-center mb-3 mt-3">
        <h5 class="mb-0"><i class="ti ti-calendar-plus"></i> シフト申請一覧</h5>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus"></i> 申請
        </button>
      </div>

      <div v-if="loading" class="text-center py-5">
        <div class="spinner-border text-primary"></div>
      </div>

      <div v-else-if="!requests.length" class="text-muted text-center py-4">
        シフト申請はありません
      </div>

      <div v-else>
        <div v-for="r in requests" :key="r.id" class="card mb-3">
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-start mb-2">
              <div>
                <div class="fw-bold">{{ r.date }}</div>
                <div class="small text-muted">{{ r.start_time?.slice(0,5) }} - {{ r.end_time_extended || r.end_time?.slice(0,5) }}</div>
              </div>
              <span class="badge" :class="statusClass[r.status]">{{ statusLabel[r.status] }}</span>
            </div>
            <div class="small text-muted mb-1">申請日時: {{ formatDateTime(r.created_at) }}</div>
            <div v-if="r.desired_room_name" class="small text-muted mb-1">
              <i class="ti ti-door"></i> 希望: {{ r.desired_room_name }}
            </div>
            <div v-if="r.status === 'APPROVED'" class="small bg-success bg-opacity-10 p-2 rounded mb-2">
              <div class="fw-bold mb-1"><i class="ti ti-check"></i> 承認内容</div>
              <template v-if="r.approved_date">
                <div>{{ r.approved_date }} {{ r.approved_start_time?.slice(0,5) }} - {{ r.approved_end_time_extended || r.approved_end_time?.slice(0,5) }}</div>
                <div>部屋: {{ r.approved_room_name || '-' }}</div>
              </template>
              <div v-else class="text-muted">承認済み（旧データのため詳細未記録）</div>
            </div>
            <div v-if="r.memo" class="small bg-light p-2 rounded mb-2">{{ r.memo }}</div>
            <div v-if="r.admin_memo" class="small bg-info bg-opacity-10 p-2 rounded mb-2">
              <i class="ti ti-message"></i> 運営: {{ r.admin_memo }}
            </div>
            <div v-if="r.decided_at" class="small text-muted mb-2">決定日時: {{ formatDateTime(r.decided_at) }}</div>
            <button
              v-if="r.status === 'REQUESTED'"
              class="btn btn-outline-danger btn-sm w-100"
              @click="onCancel(r.id)"
            >
              <i class="ti ti-x"></i> 取消
            </button>
          </div>
        </div>
      </div>

      <!-- Form modal -->
      <div v-if="showForm" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showForm = false">
        <div class="modal-dialog modal-lg">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">シフト申請</h5>
              <button type="button" class="btn-close" @click="showForm = false"></button>
            </div>
            <div class="modal-body">
              <div v-if="formError" class="alert alert-danger">{{ formError }}</div>
              <div class="d-flex justify-content-between align-items-center mb-3">
                <button type="button" class="btn btn-outline-secondary btn-sm" @click="changeWeek(-1)">
                  <i class="ti ti-chevron-left"></i> 前の7日
                </button>
                <div class="fw-bold text-center">
                  {{ dateLabel(form.days[0].date) }}〜{{ dateLabel(form.days[6].date) }}
                </div>
                <button type="button" class="btn btn-outline-secondary btn-sm" @click="changeWeek(1)">
                  次の7日 <i class="ti ti-chevron-right"></i>
                </button>
              </div>

              <div class="weekly-shift-list mb-3">
                <div
                  v-for="day in form.days"
                  :key="day.date"
                  class="weekly-shift-row"
                  :class="{ 'weekly-shift-row--enabled': day.enabled }"
                >
                  <label class="weekly-shift-date">
                    <input v-model="day.enabled" type="checkbox" class="form-check-input" />
                    <span>{{ dateLabel(day.date) }}</span>
                  </label>
                  <div class="weekly-shift-time">
                    <input
                      v-model="day.start_time"
                      type="time"
                      step="1800"
                      class="form-control"
                      aria-label="開始時間"
                      :disabled="!day.enabled"
                    />
                    <span>〜</span>
                    <input
                      v-model="day.end_time"
                      type="text"
                      inputmode="numeric"
                      maxlength="5"
                      placeholder="終了"
                      class="form-control"
                      aria-label="終了時間"
                      :disabled="!day.enabled"
                      @blur="formatEndTimeField(day)"
                    />
                  </div>
                </div>
              </div>
              <div class="form-text mb-3">出勤する日にチェックを入れ、日ごとに時間を入力してください。翌朝は24:00〜29:00で入力できます。</div>
              <div class="mb-3">
                <label class="form-label">希望部屋（任意）</label>
                <select v-model="form.desired_room" class="form-select">
                  <option value="">指定なし</option>
                  <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
                </select>
              </div>
              <div class="mb-3">
                <label class="form-label">メモ（任意）</label>
                <textarea v-model="form.memo" class="form-control" rows="2"></textarea>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" @click="showForm = false">キャンセル</button>
              <button class="btn btn-primary" :disabled="saving" @click="onSave">
                {{ saving ? '送信中...' : `${selectedDayCount}日分をまとめて申請` }}
              </button>
            </div>
          </div>
        </div>
      </div>
  </LayoutCast>
</template>

<style scoped>
.weekly-shift-list {
  border: 1px solid var(--bs-border-color);
  border-radius: 0.75rem;
  overflow: hidden;
}

.weekly-shift-row {
  display: grid;
  grid-template-columns: 8.5rem minmax(0, 1fr);
  gap: 1rem;
  align-items: center;
  padding: 0.65rem 0.75rem;
  background: var(--bs-tertiary-bg);
  border-bottom: 1px solid var(--bs-border-color);
}

.weekly-shift-row:last-child {
  border-bottom: 0;
}

.weekly-shift-row--enabled {
  background: var(--bs-body-bg);
}

.weekly-shift-date {
  display: flex;
  gap: 0.6rem;
  align-items: center;
  font-weight: 600;
  white-space: nowrap;
}

.weekly-shift-time {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 0.5rem;
  align-items: center;
}

@media (max-width: 575.98px) {
  .weekly-shift-row {
    grid-template-columns: 1fr;
    gap: 0.5rem;
  }
}
</style>
