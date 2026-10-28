<script setup>
import { computed, nextTick, ref, onMounted } from 'vue'
import { normalizeShiftTime } from '../../shiftTime.js'
import { shiftRequestError } from '../../shiftRequestError.js'
import LayoutCast from '../../components/LayoutCast.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const requests = ref([])
const shiftRequestStartHour = ref(11)

const showForm = ref(false)
const form = ref(emptyForm())
const formError = ref('')
const formErrorAlert = ref(null)
const saving = ref(false)
const shiftEditorScroll = ref(null)

function emptyForm() {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return {
    week_start: formatLocalDate(today),
    days: buildSevenDays(today),
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

function dayNumber(value) {
  return new Date(`${value}T00:00:00`).getDate()
}

function weekdayLabel(value) {
  const date = new Date(`${value}T00:00:00`)
  return ['日', '月', '火', '水', '木', '金', '土'][date.getDay()]
}

function weekdayClass(value) {
  const day = new Date(`${value}T00:00:00`).getDay()
  return { 'weekly-day-button--sunday': day === 0, 'weekly-day-button--saturday': day === 6 }
}

function buildTimeOptions(maxHour, minHour = 0) {
  const options = []
  for (let hour = minHour; hour <= maxHour; hour += 1) {
    for (const minute of [0, 30]) {
      if (hour === maxHour && minute > 0) break
      options.push(`${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`)
    }
  }
  return options
}

const startTimeOptions = computed(() => buildTimeOptions(29, shiftRequestStartHour.value))
const endTimeOptions = buildTimeOptions(29)

function changeWeek(offset) {
  const start = new Date(`${form.value.week_start}T00:00:00`)
  start.setDate(start.getDate() + offset * 7)
  form.value.week_start = formatLocalDate(start)
  form.value.days = buildSevenDays(start)
}

const selectedDayCount = computed(() => form.value.days.filter((day) => day.enabled).length)
const selectedDays = computed(() => form.value.days.filter((day) => day.enabled))

async function toggleDay(day) {
  day.enabled = !day.enabled
  if (!day.enabled) return

  await nextTick()
  const editor = shiftEditorScroll.value?.querySelector(`[data-shift-date="${day.date}"]`)
  editor?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [requestsData, timeSettings] = await Promise.all([
      api.getCastShiftRequests(),
      api.getCastShiftRequestTimeSettings(),
    ])
    requests.value = Array.isArray(requestsData) ? requestsData : []
    const configuredHour = Number(timeSettings?.shift_request_start_hour)
    shiftRequestStartHour.value = Number.isInteger(configuredHour) && configuredHour >= 0 && configuredHour <= 23
      ? configuredHour
      : 11
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)

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

function normalizeExtendedEndTime(value) {
  const normalized = normalizeShiftTime(value, '終了時間')
  return {
    end_time: normalized.time,
    end_day_offset: normalized.dayOffset,
  }
}

async function onSave() {
  if (saving.value) return
  saving.value = true
  formError.value = ''
  try {
    const selectedItems = form.value.days.filter((day) => day.enabled)
    if (!selectedItems.length) throw new Error('出勤する日を1日以上選択してください')

    const items = selectedItems.map((day) => {
      if (!day.start_time || !day.end_time) {
        throw new Error(`${dateLabel(day.date)}の開始・終了時間を入力してください`)
      }
      const normalizedEnd = normalizeExtendedEndTime(day.end_time)
      const normalizedStart = normalizeShiftTime(day.start_time, '開始時間')
      day.end_time = formatExtendedEndTimeInput(day.end_time)
      return {
        date: day.date,
        start_time: normalizedStart.time,
        start_day_offset: normalizedStart.dayOffset,
        ...normalizedEnd,
      }
    })
    const body = {
      items,
      memo: form.value.memo,
    }
    await api.createCastShiftRequestsBulk(body)
    showForm.value = false
    await load()
  } catch (e) {
    formError.value = e.data || e.status || e instanceof TypeError ? shiftRequestError(e) : e.message
    await nextTick()
    formErrorAlert.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
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
                <div class="small text-muted">{{ r.start_time_extended || r.start_time?.slice(0,5) }} - {{ r.end_time_extended || r.end_time?.slice(0,5) }}</div>
              </div>
              <span class="badge" :class="statusClass[r.status]">{{ statusLabel[r.status] }}</span>
            </div>
            <div class="small text-muted mb-1">申請日時: {{ formatDateTime(r.created_at) }}</div>
            <div v-if="r.status === 'APPROVED'" class="small bg-success bg-opacity-10 p-2 rounded mb-2">
              <div class="fw-bold mb-1"><i class="ti ti-check"></i> 承認内容</div>
              <template v-if="r.approved_date">
                <div>{{ r.approved_date }} {{ r.approved_start_time_extended || r.approved_start_time?.slice(0,5) }} - {{ r.approved_end_time_extended || r.approved_end_time?.slice(0,5) }}</div>
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
      <div v-if="showForm" class="modal d-block" role="dialog" aria-modal="true" aria-labelledby="weekly-shift-modal-title" style="background: rgba(0,0,0,0.3);" @click.self="showForm = false">
        <div class="modal-dialog modal-dialog-centered modal-lg weekly-shift-modal-dialog">
          <div class="modal-content weekly-shift-modal-content">
            <div class="modal-header">
              <h5 id="weekly-shift-modal-title" class="modal-title">シフト申請</h5>
              <button type="button" class="btn-close" @click="showForm = false"></button>
            </div>
            <div class="modal-body weekly-shift-modal-body">
              <div v-if="formError" ref="formErrorAlert" class="alert alert-danger" role="alert" style="white-space: pre-line;">{{ formError }}</div>
              <div class="weekly-shift-picker">
                <div class="d-flex justify-content-between align-items-center mb-3">
                  <button type="button" class="btn btn-outline-secondary weekly-week-button" aria-label="前の7日" @click="changeWeek(-1)">
                    <i class="ti ti-chevron-left"></i>
                  </button>
                  <div class="fw-bold text-center">
                    {{ dateLabel(form.days[0].date) }}〜{{ dateLabel(form.days[6].date) }}
                  </div>
                  <button type="button" class="btn btn-outline-secondary weekly-week-button" aria-label="次の7日" @click="changeWeek(1)">
                    <i class="ti ti-chevron-right"></i>
                  </button>
                </div>
                <div class="weekly-day-picker" role="group" aria-label="出勤日を選択">
                  <button
                    v-for="day in form.days"
                    :key="day.date"
                    type="button"
                    class="weekly-day-button"
                    :class="[{ 'weekly-day-button--selected': day.enabled }, weekdayClass(day.date)]"
                    :aria-pressed="day.enabled"
                    :aria-label="`${dateLabel(day.date)}を${day.enabled ? '選択解除' : '選択'}`"
                    @click="toggleDay(day)"
                  >
                    <span class="weekly-day-weekday">{{ weekdayLabel(day.date) }}</span>
                    <span class="weekly-day-number">{{ dayNumber(day.date) }}</span>
                  </button>
                </div>
              </div>

              <div ref="shiftEditorScroll" class="weekly-shift-scroll-body">
                <div v-if="!selectedDays.length" class="weekly-shift-empty">
                  出勤する日を上の日付から選択してください
                </div>
                <div
                  v-for="day in selectedDays"
                  :key="day.date"
                  class="weekly-shift-editor"
                  :data-shift-date="day.date"
                >
                  <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="fw-bold">{{ dateLabel(day.date) }}の時間</div>
                    <button type="button" class="btn btn-sm btn-link text-danger text-decoration-none" @click="toggleDay(day)">
                      選択解除
                    </button>
                  </div>
                  <div class="weekly-shift-time">
                    <div>
                      <label class="form-label small text-muted">開始時間</label>
                      <select v-model="day.start_time" class="form-select" :aria-label="`${dateLabel(day.date)}の開始時間`">
                        <option value="">選択</option>
                        <option v-for="time in startTimeOptions" :key="time" :value="time">{{ time }}</option>
                      </select>
                    </div>
                    <div>
                      <label class="form-label small text-muted">終了時間</label>
                      <select v-model="day.end_time" class="form-select" :aria-label="`${dateLabel(day.date)}の終了時間`">
                        <option value="">選択</option>
                        <option v-for="time in endTimeOptions" :key="time" :value="time">{{ time }}</option>
                      </select>
                    </div>
                  </div>
                </div>
                <div v-if="selectedDays.length" class="form-text mb-3">翌朝の開始・終了時間は24:00〜29:00から選択できます。</div>
                <p class="small text-muted mb-3">
                  出勤場所は、登録済みの希望エリアと空室状況をもとに運営が調整します。部屋の指定はできません。
                </p>
                <div class="mb-3">
                  <label class="form-label">メモ（任意）</label>
                  <textarea v-model="form.memo" class="form-control" rows="2"></textarea>
                </div>
              </div>
            </div>
            <div class="modal-footer weekly-shift-modal-footer">
              <span class="me-auto text-muted">選択中：{{ selectedDayCount }}日</span>
              <button class="btn btn-secondary" @click="showForm = false">キャンセル</button>
              <button class="btn btn-primary" :disabled="saving || selectedDayCount === 0" @click="onSave">
                {{ saving ? '送信中...' : `${selectedDayCount}日分を申請` }}
              </button>
            </div>
          </div>
        </div>
      </div>
  </LayoutCast>
</template>

<style scoped>
.weekly-shift-modal-content {
  height: min(46rem, calc(100dvh - 2rem));
  max-height: calc(100dvh - 2rem);
  overflow: hidden;
}

.weekly-shift-modal-body {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  padding: 0;
}

.weekly-shift-picker {
  flex: 0 0 auto;
  padding: 1rem;
  border-bottom: 1px solid var(--bs-border-color);
  background: var(--bs-body-bg);
}

.weekly-week-button {
  width: 2.75rem;
  height: 2.75rem;
  padding: 0;
}

.weekly-day-picker {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 0.35rem;
}

.weekly-day-button {
  display: flex;
  min-width: 0;
  min-height: 4rem;
  padding: 0.35rem 0.2rem;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--bs-border-color);
  border-radius: 0.65rem;
  background: var(--bs-body-bg);
  color: var(--bs-body-color);
}

.weekly-day-button--selected {
  border-color: var(--bs-primary);
  background: var(--bs-primary);
  color: #fff;
}

.weekly-day-button--saturday:not(.weekly-day-button--selected) {
  color: var(--bs-primary);
}

.weekly-day-button--sunday:not(.weekly-day-button--selected) {
  color: var(--bs-danger);
}

.weekly-day-weekday {
  font-size: 0.75rem;
}

.weekly-day-number {
  font-size: 1.1rem;
  font-weight: 600;
}

.weekly-shift-scroll-body {
  min-height: 0;
  padding: 1rem;
  flex: 1 1 auto;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.weekly-shift-empty {
  padding: 2rem 1rem;
  color: var(--bs-secondary-color);
  text-align: center;
}

.weekly-shift-editor {
  padding: 0.85rem;
  margin-bottom: 0.75rem;
  border-radius: 0.75rem;
  background: var(--bs-tertiary-bg);
}

.weekly-shift-time {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.weekly-shift-modal-footer {
  flex: 0 0 auto;
  background: var(--bs-body-bg);
}

@media (max-width: 575.98px) {
  .weekly-shift-modal-dialog {
    height: 100dvh;
    margin: 0;
  }

  .weekly-shift-modal-content {
    height: 100dvh;
    max-height: 100dvh;
    border: 0;
    border-radius: 0;
  }

  .weekly-shift-picker,
  .weekly-shift-scroll-body {
    padding-right: 0.75rem;
    padding-left: 0.75rem;
  }

  .weekly-shift-modal-footer {
    padding-bottom: max(0.75rem, env(safe-area-inset-bottom));
  }

  .weekly-shift-modal-footer .btn-secondary {
    display: none;
  }

  .weekly-shift-modal-footer .btn-primary {
    min-height: 3rem;
  }
}
</style>
