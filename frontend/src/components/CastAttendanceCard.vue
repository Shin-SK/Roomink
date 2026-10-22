<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api.js'
import { attendanceState as state, attendanceTime as time, attendanceDate as dateLabel, scheduledTime } from '../attendanceDisplay.js'

const shifts = ref([])
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const businessDate = ref('')
const todayShifts = computed(() => shifts.value.filter(shift => shift.date === businessDate.value))
const previousOpen = computed(() => shifts.value.filter(shift => shift.date < businessDate.value && shift.clocked_in_at && !shift.clocked_out_at))
let timer
async function load() {
  try {
    const data = await api.getCastAttendance()
    shifts.value = data.shifts || []
    businessDate.value = data.current_business_date || shifts.value.at(-1)?.date || ''
    error.value = ''
  } catch (e) { error.value = e.message } finally { loading.value = false }
}
async function punch(shift, action) {
  if (saving.value) return
  saving.value = true
  error.value = ''
  try {
    await api.punchCastAttendance(shift.id, action)
    await load()
  } catch (e) { error.value = e.message } finally { saving.value = false }
}
onMounted(() => { load(); timer = window.setInterval(() => { if (!saving.value) load() }, 30000) })
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <section class="timecard mb-3" aria-label="出勤・退勤の打刻">
    <div class="timecard__heading"><h2><i class="ti ti-clock" aria-hidden="true"></i> 今日の勤怠</h2><span>{{ dateLabel(businessDate) }}</span></div>
      <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
      <div v-if="loading" role="status">読み込み中…</div>
      <p v-else-if="!todayShifts.length" class="timecard__empty">今日は勤務予定がありません</p>
      <article v-for="shift in todayShifts" :key="shift.id" class="timecard__shift">
        <div class="timecard__meta"><span>予定 {{ scheduledTime(shift.scheduled_start, shift.date) }}–{{ scheduledTime(shift.scheduled_end, shift.date) }}</span><span class="timecard__status" :class="state(shift).tone">{{ state(shift).label }}</span></div>
        <div class="timecard__main"><div class="timecard__stamp"><small>出勤</small><strong>{{ time(shift.clocked_in_at) }}</strong></div><div class="timecard__stamp"><small>退勤</small><strong>{{ time(shift.clocked_out_at) }}</strong></div>
          <button v-if="shift.clocked_in_at && !shift.clocked_out_at" class="btn btn-primary timecard__action" :disabled="saving" @click="punch(shift, 'clock_out')"><i class="ti ti-door-exit" aria-hidden="true"></i> 退勤する</button>
          <button v-else-if="shift.can_clock_in" class="btn btn-primary timecard__action" :disabled="saving" @click="punch(shift, 'clock_in')"><i class="ti ti-check" aria-hidden="true"></i> 出勤する</button>
          <span v-else class="timecard__complete">{{ shift.clocked_out_at ? 'お疲れさまでした' : shift.is_absent ? '欠勤' : '打刻の修正は店舗へ' }}</span>
        </div>
        <details v-if="shift.alerts?.length" class="timecard__notice"><summary><i class="ti ti-alert-circle" aria-hidden="true"></i> 打刻時刻の確認</summary><p>{{ shift.alerts.join(' / ') }}。修正が必要な場合は店舗へご連絡ください。</p></details>
      </article>
      <div v-for="shift in previousOpen" :key="shift.id" class="timecard__previous"><div><i class="ti ti-alert-circle" aria-hidden="true"></i><span>{{ dateLabel(shift.date) }}分が未退勤です</span></div><button type="button" :disabled="saving" @click="punch(shift, 'clock_out')">退勤を記録 <i class="ti ti-chevron-right" aria-hidden="true"></i></button></div>
  </section>
</template>

<style scoped>
.timecard { border:1px solid #dceae4; border-radius:12px; background:white; padding:18px 20px; color:var(--rk-text); }
.timecard__heading { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.timecard__heading h2 { display:flex; align-items:center; gap:7px; margin:0; font-size:.9rem; font-weight:750; }
.timecard__heading h2 i { color:var(--rk-primary); }
.timecard__heading > span { color:var(--rk-muted); font-size:.75rem; }
.timecard__meta { display:flex; justify-content:space-between; align-items:center; font-size:.75rem; color:var(--rk-muted); margin-bottom:14px; }
.timecard__status { padding:3px 8px; border-radius:5px; background:#f1f4f2; font-size:.7rem; }
.timecard__status.green { background:#e8f5ef; color:#2c7a60; }
.timecard__main { display:grid; grid-template-columns:1fr 1fr minmax(150px,1fr); gap:16px; align-items:center; }
.timecard__stamp small { display:block; color:var(--rk-muted); font-size:.7rem; margin-bottom:2px; }
.timecard__stamp strong { font-size:1.7rem; font-weight:750; font-variant-numeric:tabular-nums; letter-spacing:.02em; }
.timecard__action { min-height:43px; font-size:.85rem; }
.timecard__complete { font-size:.78rem; color:var(--rk-muted); }
.timecard__notice { color:#aa7a27; font-size:.7rem; margin-top:14px; }
.timecard__notice summary { list-style:none; cursor:pointer; }
.timecard__notice summary::-webkit-details-marker { display:none; }
.timecard__notice p { color:var(--rk-muted); margin:7px 0 0; line-height:1.6; }
.timecard__previous { display:flex; gap:10px; justify-content:space-between; align-items:center; background:#fffaef; border:1px solid #f4e8c8; border-radius:8px; padding:10px 12px; margin-top:16px; font-size:.75rem; color:#a17425; }
.timecard__previous > div { display:flex; gap:6px; align-items:center; }
.timecard__previous button { border:0; background:transparent; color:#92702b; white-space:nowrap; font-size:.72rem; padding:5px 0; font-weight:650; }
.timecard__shift + .timecard__shift { border-top:1px solid var(--rk-border); margin-top:16px; padding-top:16px; }
.timecard__empty { margin:0; font-size:.8rem; color:var(--rk-muted); }
@media(max-width:575px) { .timecard { padding:16px; } .timecard__main { grid-template-columns:1fr 1fr; gap:12px; } .timecard__action,.timecard__complete { grid-column:1/-1; } .timecard__stamp strong { font-size:1.75rem; } }
</style>
