<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')
const rowErrors = ref([])

const casts = ref([])
const rooms = ref([])
const selectedCast = ref('')
const weekStart = ref(mondayOf(new Date()))
const days = ref([])

// 一括反映用（全曜日にまとめて入れる）
const bulk = ref({ start_time: '18:00', end_time: '23:00', room: '' })

const WEEKDAYS = ['月', '火', '水', '木', '金', '土', '日']

function mondayOf(d) {
  const date = new Date(d)
  const day = (date.getDay() + 6) % 7 // 月=0
  date.setDate(date.getDate() - day)
  return toISO(date)
}

function toISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function shiftWeek(deltaDays) {
  const d = new Date(weekStart.value)
  d.setDate(d.getDate() + deltaDays)
  weekStart.value = toISO(d)
}

const weekEndLabel = computed(() => {
  if (!weekStart.value) return ''
  const d = new Date(weekStart.value)
  d.setDate(d.getDate() + 6)
  return toISO(d)
})

const enabledCount = computed(() => days.value.filter(d => d.enabled).length)

function emptyDays() {
  const out = []
  const base = new Date(weekStart.value)
  for (let i = 0; i < 7; i++) {
    const d = new Date(base)
    d.setDate(d.getDate() + i)
    out.push({
      date: toISO(d),
      weekday: WEEKDAYS[i],
      enabled: false,
      start_time: '18:00',
      end_time: '23:00',
      room: rooms.value.length ? rooms.value[0].id : '',
      daily_memo: '',
      existing_shifts: [],
    })
  }
  return out
}

async function loadMasters() {
  try {
    const [cs, rs] = await Promise.all([api.getCasts(), api.getRooms()])
    casts.value = Array.isArray(cs) ? cs : []
    rooms.value = Array.isArray(rs) ? rs : []
    if (rooms.value.length) bulk.value.room = rooms.value[0].id
  } catch (e) {
    error.value = e.message
  }
}

async function loadWeek() {
  rowErrors.value = []
  success.value = ''
  if (!selectedCast.value) {
    days.value = emptyDays()
    return
  }
  loading.value = true
  error.value = ''
  try {
    const data = await api.getWeeklyShifts(selectedCast.value, weekStart.value)
    const base = emptyDays()
    data.days.forEach((d, i) => {
      base[i].existing_shifts = d.existing_shifts || []
    })
    days.value = base
  } catch (e) {
    error.value = e.message
    days.value = emptyDays()
  } finally {
    loading.value = false
  }
}

function applyBulk() {
  days.value.forEach(d => {
    if (d.existing_shifts.length) return
    d.enabled = true
    d.start_time = bulk.value.start_time
    d.end_time = bulk.value.end_time
    d.room = bulk.value.room
  })
}

function clearAll() {
  days.value.forEach(d => { d.enabled = false })
}

async function onSubmit() {
  error.value = ''
  success.value = ''
  rowErrors.value = []

  const items = days.value.map(d => (
    d.enabled
      ? {
          date: d.date,
          enabled: true,
          start_time: d.start_time,
          end_time: d.end_time,
          room: d.room,
          daily_memo: d.daily_memo,
        }
      : { date: d.date, enabled: false }
  ))

  if (!items.some(i => i.enabled)) {
    error.value = '出勤する日を1日以上選択してください'
    return
  }

  saving.value = true
  try {
    const res = await api.createWeeklyShifts({
      cast: selectedCast.value,
      week_start: weekStart.value,
      items,
    })
    success.value = `${res.created_count}件のシフトを登録しました`
    await loadWeek()
  } catch (e) {
    // backend が {detail, errors:[{date, detail}]} を返す場合は日別にも表示する
    error.value = e.message
    if (e.data && Array.isArray(e.data.errors)) rowErrors.value = e.data.errors
  } finally {
    saving.value = false
  }
}

function errorFor(date) {
  const hit = rowErrors.value.find(e => e.date === date)
  return hit ? hit.detail : ''
}

watch(weekStart, loadWeek)
watch(selectedCast, loadWeek)

onMounted(async () => {
  await loadMasters()
  days.value = emptyDays()
})
</script>

<template>
  <LayoutOperator>
    <template #title>週次シフト入力</template>

    <div class="mb-3">
      <router-link to="/op/shifts" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> シフト管理に戻る
      </router-link>
    </div>

    <div class="alert alert-info small">
      <i class="ti ti-info-circle"></i>
      キャストと週を選び、月〜日の出勤をまとめて登録できます。
      既にシフトがある日は<strong>上書きしません</strong>（新規追加のみ）。
      1日でもエラーがある場合は、1件も登録されません。
    </div>

    <div v-if="error" class="alert alert-danger" style="white-space: pre-wrap;">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <!-- 条件 -->
    <div class="card mb-3">
      <div class="card-body">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-4">
            <label class="form-label small fw-bold">キャスト</label>
            <select v-model="selectedCast" class="form-select form-select-sm">
              <option value="">選択してください</option>
              <option v-for="c in casts" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label small fw-bold">週の開始日（月曜）</label>
            <input v-model="weekStart" type="date" class="form-control form-control-sm" />
          </div>
          <div class="col-12 col-md-4">
            <div class="btn-group w-100">
              <button class="btn btn-sm btn-outline-secondary" @click="shiftWeek(-7)">前の週</button>
              <button class="btn btn-sm btn-outline-secondary" @click="weekStart = mondayOf(new Date())">今週</button>
              <button class="btn btn-sm btn-outline-secondary" @click="shiftWeek(7)">次の週</button>
            </div>
          </div>
        </div>
        <div class="text-muted small mt-2">
          対象期間: {{ weekStart }} 〜 {{ weekEndLabel }}
        </div>
      </div>
    </div>

    <template v-if="selectedCast">
      <!-- 一括反映 -->
      <div class="card mb-3">
        <div class="card-header"><i class="ti ti-wand"></i> 全曜日にまとめて入力</div>
        <div class="card-body">
          <div class="row g-2 align-items-end">
            <div class="col-6 col-md-3">
              <label class="form-label small">開始</label>
              <input v-model="bulk.start_time" type="time" step="300" class="form-control form-control-sm" />
            </div>
            <div class="col-6 col-md-3">
              <label class="form-label small">終了</label>
              <input v-model="bulk.end_time" type="time" step="300" class="form-control form-control-sm" />
            </div>
            <div class="col-8 col-md-4">
              <label class="form-label small">部屋</label>
              <select v-model="bulk.room" class="form-select form-select-sm">
                <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
              </select>
            </div>
            <div class="col-4 col-md-2">
              <button class="btn btn-sm btn-outline-primary w-100" @click="applyBulk">反映</button>
            </div>
          </div>
          <div class="mt-2">
            <button class="btn btn-sm btn-link text-muted p-0" @click="clearAll">すべて「出勤しない」に戻す</button>
          </div>
        </div>
      </div>

      <div v-if="loading" class="text-center py-4">
        <div class="spinner-border text-primary"></div>
      </div>

      <!-- 7日分 -->
      <div v-else class="card mb-3">
        <div class="card-header"><i class="ti ti-calendar-week"></i> 月〜日のシフト</div>
        <div class="card-body p-0">
          <div
            v-for="d in days"
            :key="d.date"
            class="day-row"
            :class="{ 'day-row--on': d.enabled, 'day-row--locked': d.existing_shifts.length }"
          >
            <div class="day-row__head">
              <div class="form-check mb-0">
                <input
                  :id="`day-${d.date}`"
                  v-model="d.enabled"
                  class="form-check-input"
                  type="checkbox"
                  :disabled="d.existing_shifts.length > 0"
                />
                <label class="form-check-label fw-bold" :for="`day-${d.date}`">
                  {{ d.weekday }} <span class="text-muted small">{{ d.date.slice(5) }}</span>
                </label>
              </div>
              <span v-if="d.existing_shifts.length" class="badge bg-secondary">登録済</span>
            </div>

            <div v-if="d.existing_shifts.length" class="day-row__existing small text-muted">
              <div v-for="s in d.existing_shifts" :key="s.id">
                既存: {{ s.start_time?.slice(0, 5) }}〜{{ s.end_time?.slice(0, 5) }} / {{ s.room_name }}
              </div>
              <div class="text-muted" style="font-size: 0.72rem;">
                ※ 既存シフトの変更はシフト管理画面から行ってください
              </div>
            </div>

            <div v-else-if="d.enabled" class="day-row__inputs">
              <div class="row g-2">
                <div class="col-6 col-md-2">
                  <label class="form-label small mb-1">開始</label>
                  <input v-model="d.start_time" type="time" step="300" class="form-control form-control-sm" />
                </div>
                <div class="col-6 col-md-2">
                  <label class="form-label small mb-1">終了</label>
                  <input v-model="d.end_time" type="time" step="300" class="form-control form-control-sm" />
                </div>
                <div class="col-12 col-md-3">
                  <label class="form-label small mb-1">部屋</label>
                  <select v-model="d.room" class="form-select form-select-sm">
                    <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.name }}</option>
                  </select>
                </div>
                <div class="col-12 col-md-5">
                  <label class="form-label small mb-1">メモ</label>
                  <input v-model="d.daily_memo" type="text" class="form-control form-control-sm" placeholder="任意" />
                </div>
              </div>
            </div>

            <div v-if="errorFor(d.date)" class="alert alert-danger py-1 px-2 mt-2 mb-0" style="font-size: 0.8rem;">
              {{ errorFor(d.date) }}
            </div>
          </div>
        </div>
      </div>

      <button
        class="btn btn-primary w-100 mb-4"
        :disabled="saving || !enabledCount"
        @click="onSubmit"
      >
        <i class="ti ti-device-floppy"></i>
        {{ saving ? '登録中...' : `一括登録（${enabledCount}日分）` }}
      </button>
    </template>

    <div v-else class="text-muted text-center py-4 small">
      キャストを選択してください
    </div>
  </LayoutOperator>
</template>

<style scoped>
.day-row {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #f0f0f0;
}
.day-row:last-child {
  border-bottom: none;
}
.day-row--on {
  background: #f6fbfa;
}
.day-row--locked {
  background: #fafafa;
}
.day-row__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.day-row__existing,
.day-row__inputs {
  margin-top: 0.5rem;
}
</style>
