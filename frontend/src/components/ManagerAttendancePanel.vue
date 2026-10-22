<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { api } from '../api.js'
import { attendanceState as state, attendanceTime as time, attendanceDate as dateLabel, scheduledTime, filterAttendance } from '../attendanceDisplay.js'
const props = defineProps({ date: { type: String, required: true }, castId: { type: String, default: '' } })
const shifts = ref([])
const error = ref('')
const loading = ref(false)
const saving = ref(false)
const editing = ref(null)
const draft = ref({})
const query = ref('')
const status = ref('all')
const page = ref(1)
const pageSize = 20
const castRows = computed(() => filterAttendance(shifts.value, { castId: props.castId }))
const filters = computed(() => [
  { key: 'all', label: 'すべて', count: castRows.value.length },
  { key: 'review', label: '要確認', count: castRows.value.filter(s => s.alerts?.length).length },
  { key: 'working', label: '勤務中', count: castRows.value.filter(s => state(s).key === 'working').length },
  { key: 'done', label: '退勤済み', count: castRows.value.filter(s => state(s).key === 'done').length },
  { key: 'waiting', label: '未出勤', count: castRows.value.filter(s => state(s).key === 'waiting').length },
])
const filtered = computed(() => filterAttendance(shifts.value, { query: query.value, status: status.value, castId: props.castId }))
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)))
const rows = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))
let requestNumber = 0
const drawerPanel = ref(null)
let returnFocus = null
watch(editing, async value => {
  if (value) { returnFocus = document.activeElement; await nextTick(); drawerPanel.value?.focus() }
  else { await nextTick(); returnFocus?.focus?.() }
})
function trapFocus(event) {
  if (event.key !== 'Tab') return
  const nodes = Array.from(drawerPanel.value?.querySelectorAll('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), summary') || [])
  const first = nodes[0], last = nodes.at(-1)
  if (event.shiftKey && (document.activeElement === first || document.activeElement === drawerPanel.value)) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
function datetime(value) { return value ? new Date(value).toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' }) : '未打刻' }
function inputDate(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(value)).replace(' ', 'T')
}
async function load() {
  const request = ++requestNumber
  loading.value = true
  error.value = ''
  try { const data = await api.getManagerAttendance(props.date); if (request === requestNumber) { shifts.value = data.shifts || []; page.value = Math.min(page.value, pages.value) } }
  catch (e) { if (request === requestNumber) error.value = e.message }
  finally { if (request === requestNumber) loading.value = false }
}
function edit(shift) {
  editing.value = shift
  error.value = ''
  draft.value = { clocked_in_at: inputDate(shift.clocked_in_at), clocked_out_at: inputDate(shift.clocked_out_at), reason: '' }
}
async function save() {
  if (saving.value || !editing.value || !draft.value.reason.trim()) return
  saving.value = true
  error.value = ''
  const shift = editing.value
  try {
    await api.correctAttendance({ shift_id: shift.id,
      clocked_in_at: draft.value.clocked_in_at ? `${draft.value.clocked_in_at}+09:00` : null,
      clocked_out_at: draft.value.clocked_out_at ? `${draft.value.clocked_out_at}+09:00` : null,
      expected: { clocked_in_at: shift.clocked_in_at, clocked_out_at: shift.clocked_out_at }, reason: draft.value.reason })
    editing.value = null
    await load()
  } catch (e) { error.value = e.message } finally { saving.value = false }
}
watch([query, status, () => props.castId], () => { page.value = 1 })
watch(() => props.date, () => { editing.value = null; shifts.value = []; page.value = 1; load() }, { immediate: true })
</script>
<template>
  <section class="attendance" aria-label="勤務の打刻確認">
    <header class="attendance__heading"><div><h2>勤怠一覧 <span>{{ castRows.length }}件</span></h2><p>要確認の勤務を上に表示</p></div><button type="button" class="btn btn-outline-secondary btn-sm" :disabled="loading || saving" @click="editing = null; load()"><i class="ti ti-refresh" aria-hidden="true"></i> 更新</button></header>
    <div class="attendance__toolbar">
      <div class="attendance__filters" aria-label="勤怠の状態で絞り込み"><button v-for="filter in filters" :key="filter.key" type="button" :class="{ active: status === filter.key, attention: filter.key === 'review' && filter.count }" :aria-pressed="status === filter.key" @click="status = filter.key">{{ filter.label }}<span>{{ filter.count }}</span></button></div>
      <label class="attendance__search"><i class="ti ti-search" aria-hidden="true"></i><input v-model="query" type="search" placeholder="名前で検索" aria-label="勤怠を名前で検索"></label>
    </div>
    <div v-if="error && !editing" class="alert alert-danger" role="alert">{{ error }}</div>
    <div v-if="loading" class="attendance__empty" role="status">読み込み中…</div>
    <div v-else-if="!filtered.length" class="attendance__empty">該当する勤務はありません</div>
    <div v-else class="attendance__scroll"><table class="attendance__table">
      <thead><tr><th>セラピスト</th><th>勤務予定</th><th>出勤</th><th>退勤</th><th>状態</th><th><span class="visually-hidden">詳細・訂正</span></th></tr></thead>
      <tbody><tr v-for="shift in rows" :key="shift.id" :class="{ 'needs-review': shift.alerts?.length }">
        <td><div class="attendance__person"><span class="attendance__avatar" aria-hidden="true">{{ shift.cast_name.slice(0, 1) }}</span><div><strong>{{ shift.cast_name }}</strong><small v-if="shift.date !== date">{{ dateLabel(shift.date) }}分</small></div></div></td>
        <td class="attendance__planned">{{ scheduledTime(shift.scheduled_start, shift.date) }}<span>–</span>{{ scheduledTime(shift.scheduled_end, shift.date) }}</td>
        <td class="attendance__time">{{ time(shift.clocked_in_at) }}</td><td class="attendance__time">{{ time(shift.clocked_out_at) }}</td>
        <td><span class="attendance__status" :class="state(shift).tone"><i v-if="state(shift).key === 'working'" class="attendance__dot" aria-hidden="true"></i>{{ state(shift).label }}</span><span v-if="shift.alerts?.length" class="attendance__flag" :title="shift.alerts.join(' / ')"><i class="ti ti-alert-circle" aria-hidden="true"></i> 要確認</span></td>
        <td><button type="button" class="attendance__detail" :aria-label="`${shift.cast_name}の打刻詳細・訂正`" @click="edit(shift)"><i class="ti ti-chevron-right" aria-hidden="true"></i></button></td>
      </tr></tbody>
    </table></div>
    <footer class="attendance__footer"><span>{{ filtered.length ? (page - 1) * pageSize + 1 : 0 }}–{{ Math.min(page * pageSize, filtered.length) }} / {{ filtered.length }}件</span><div><button type="button" :disabled="page <= 1" aria-label="勤怠の前のページ" @click="page--"><i class="ti ti-chevron-left" aria-hidden="true"></i></button><span>{{ page }} / {{ pages }}</span><button type="button" :disabled="page >= pages" aria-label="勤怠の次のページ" @click="page++"><i class="ti ti-chevron-right" aria-hidden="true"></i></button></div></footer>
    <Teleport to="body"><div v-if="editing" class="attendance-drawer" @click.self="!saving && (editing = null)" @keydown.esc="!saving && (editing = null)">
      <section ref="drawerPanel" class="attendance-drawer__panel" role="dialog" aria-modal="true" aria-labelledby="attendance-detail-title" tabindex="-1" @keydown="trapFocus">
        <header><div><small>{{ dateLabel(editing.date) }}の勤務</small><h2 id="attendance-detail-title">{{ editing.cast_name }}</h2></div><button type="button" class="btn-close" aria-label="打刻詳細を閉じる" :disabled="saving" @click="editing = null"></button></header>
        <div class="attendance-drawer__body">
          <div class="attendance-drawer__scheduled"><i class="ti ti-clock" aria-hidden="true"></i> 勤務予定 <strong>{{ scheduledTime(editing.scheduled_start, editing.date) }}–{{ scheduledTime(editing.scheduled_end, editing.date) }}</strong></div>
          <div v-if="editing.alerts?.length" class="attendance-drawer__alerts"><i class="ti ti-alert-circle" aria-hidden="true"></i><span>{{ editing.alerts.join(' / ') }}</span></div>
          <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
          <form id="attendance-correction" @submit.prevent="save"><h3>打刻の訂正</h3>
            <label>出勤日時<input v-model="draft.clocked_in_at" type="datetime-local" step="1" class="form-control" :disabled="saving"></label>
            <label>退勤日時<input v-model="draft.clocked_out_at" type="datetime-local" step="1" class="form-control" :disabled="saving"></label>
            <label>訂正理由<textarea v-model="draft.reason" required maxlength="500" rows="2" placeholder="例：退勤の打刻忘れ。本人に確認済み。" class="form-control" :disabled="saving"></textarea></label>
            <p class="attendance-drawer__hint">日本時間で入力。元の打刻と訂正理由は履歴に残ります。</p>
          </form>
          <details class="attendance-drawer__history"><summary>打刻・訂正履歴 <span>{{ editing.history?.length || 0 }}</span></summary><p v-if="!editing.history?.length" class="attendance-drawer__hint">履歴はありません</p><article v-for="event in editing.history" :key="event.id"><small>{{ datetime(event.recorded_at) }}</small><strong>{{ event.reason || (event.action === 'clock_in' ? '出勤打刻' : '退勤打刻') }}</strong><div>出勤 {{ time(event.before.clocked_in_at) }} → {{ time(event.after.clocked_in_at) }}<br>退勤 {{ time(event.before.clocked_out_at) }} → {{ time(event.after.clocked_out_at) }}</div></article></details>
        </div>
        <footer><button type="button" class="btn btn-outline-secondary" :disabled="saving" @click="editing = null">閉じる</button><button form="attendance-correction" class="btn btn-primary" :disabled="saving || !draft.reason.trim()">{{ saving ? '保存中…' : '訂正を保存' }}</button></footer>
      </section>
    </div></Teleport>
  </section>
</template>

<style scoped>
.attendance { color:var(--rk-text); }
.attendance__heading { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:20px; }
.attendance__heading h2 { margin:0; font-size:1.05rem; font-weight:750; }
.attendance__heading h2 span { font-size:.8rem; color:var(--rk-muted); font-weight:500; margin-left:8px; }
.attendance__heading p { margin:5px 0 0; font-size:.75rem; color:var(--rk-muted); }
.attendance__toolbar { display:flex; flex-wrap:wrap; gap:12px; justify-content:space-between; align-items:center; margin-bottom:16px; }
.attendance__filters { display:flex; gap:4px; flex-wrap:wrap; }
.attendance__filters button { display:flex; gap:8px; align-items:center; padding:7px 10px; border:0; border-radius:7px; background:transparent; color:var(--rk-muted); font-size:.78rem; white-space:nowrap; }
.attendance__filters button span { font-size:.7rem; opacity:.8; }
.attendance__filters button.active { color:var(--rk-primary); background:#eaf5f2; font-weight:700; }
.attendance__filters button.attention { color:#a66b1c; }
.attendance__search { display:flex; align-items:center; gap:8px; border:1px solid var(--rk-border); border-radius:8px; padding:8px 11px; color:var(--rk-muted); }
.attendance__search input { border:0; outline:none; background:transparent; width:145px; font-size:.8rem; }
.attendance__scroll { overflow:auto; max-height:590px; border:1px solid var(--rk-border); border-radius:10px; }
.attendance__table { border-collapse:collapse; width:100%; min-width:620px; font-size:.82rem; }
.attendance__table th { text-align:left; position:sticky; top:0; z-index:1; background:#f6faf9; color:var(--rk-muted); font-size:.73rem; font-weight:600; padding:11px 14px; border-bottom:1px solid var(--rk-border); }
.attendance__table td { padding:7px 14px; border-bottom:1px solid #edf1f0; vertical-align:middle; }
.attendance__table tr:last-child td { border-bottom:0; }
.attendance__table tr.needs-review { background:#fffcf5; }
.attendance__person { display:flex; gap:10px; align-items:center; }
.attendance__person strong { display:block; font-weight:650; white-space:nowrap; }
.attendance__person small { display:block; color:#a66b1c; font-size:.68rem; }
.attendance__avatar { display:grid; place-items:center; width:30px; height:30px; border-radius:50%; background:#e6f2ee; color:#3e7e70; flex-shrink:0; font-size:.75rem; font-weight:700; }
.attendance__planned { white-space:nowrap; color:var(--rk-muted); font-variant-numeric:tabular-nums; }
.attendance__planned span { padding:0 5px; color:#a4b2ae; }
.attendance__time { font-variant-numeric:tabular-nums; font-weight:650; white-space:nowrap; }
.attendance__status { display:inline-flex; align-items:center; gap:5px; font-size:.72rem; white-space:nowrap; color:var(--rk-muted); background:#f0f3f2; padding:4px 7px; border-radius:5px; }
.attendance__status.green { color:#237c65; background:#e7f5ef; }
.attendance__dot { width:5px; height:5px; border-radius:50%; background:currentColor; }
.attendance__flag { display:inline-flex; gap:3px; align-items:center; color:#aa741d; font-size:.69rem; margin-left:7px; white-space:nowrap; }
.attendance__detail { border:0; background:transparent; color:#7d938c; padding:4px; border-radius:6px; }
.attendance__detail:hover { background:#e6f2ee; color:var(--rk-primary); }
.attendance__empty { text-align:center; color:var(--rk-muted); padding:45px 10px; font-size:.85rem; }
.attendance__footer { display:flex; justify-content:space-between; align-items:center; padding-top:14px; color:var(--rk-muted); font-size:.73rem; }
.attendance__footer div { display:flex; align-items:center; gap:15px; margin-right:70px; }
.attendance__footer button { background:white; border:1px solid var(--rk-border); border-radius:6px; width:28px; height:28px; color:var(--rk-text); }
.attendance__footer button:disabled { opacity:.3; }
.attendance-drawer { position:fixed; inset:0; z-index:1060; background:#132c2440; display:flex; justify-content:flex-end; }
.attendance-drawer__panel { width:440px; max-width:100%; background:var(--rk-card-bg); display:flex; flex-direction:column; box-shadow:-8px 0 40px #153d2414; }
.attendance-drawer__panel > header { display:flex; justify-content:space-between; align-items:center; padding:24px; border-bottom:1px solid var(--rk-border); }
.attendance-drawer__panel > header small { color:var(--rk-muted); font-size:.75rem; }
.attendance-drawer__panel h2 { font-size:1.15rem; font-weight:750; margin:4px 0 0; }
.attendance-drawer__body { padding:24px; overflow:auto; flex:1; }
.attendance-drawer__scheduled { padding:12px; background:var(--rk-bg); border-radius:8px; font-size:.78rem; color:var(--rk-muted); display:flex; align-items:center; gap:8px; }
.attendance-drawer__scheduled strong { color:var(--rk-text); margin-left:auto; }
.attendance-drawer__alerts { display:flex; gap:8px; color:#a66b1c; background:#fff8e9; padding:11px; margin-top:12px; border-radius:8px; font-size:.78rem; }
.attendance-drawer__panel h3 { font-size:.9rem; font-weight:700; margin:26px 0 16px; }
.attendance-drawer__panel label { display:block; margin-bottom:16px; font-size:.78rem; font-weight:600; }
.attendance-drawer__panel input,.attendance-drawer__panel textarea { margin-top:7px; font-size:.85rem; }
.attendance-drawer__hint { font-size:.72rem; color:var(--rk-muted); line-height:1.6; }
.attendance-drawer__history { margin-top:24px; border-top:1px solid var(--rk-border); padding-top:18px; font-size:.8rem; }
.attendance-drawer__history summary { color:var(--rk-muted); }
.attendance-drawer__history summary span { margin-left:8px; }
.attendance-drawer__history article { border-left:2px solid #d8e8e2; padding-left:13px; margin:18px 0; font-size:.75rem; }
.attendance-drawer__history article small,.attendance-drawer__history article strong { display:block; margin-bottom:5px; }
.attendance-drawer__history article small { color:var(--rk-muted); }
.attendance-drawer__panel > footer { padding:16px 24px max(16px,env(safe-area-inset-bottom)); display:flex; justify-content:flex-end; gap:10px; border-top:1px solid var(--rk-border); }
.attendance-drawer__panel .btn-primary { background:var(--rk-primary); border-color:var(--rk-primary); }
@media(max-width:600px) { .attendance__search { width:100%; } .attendance__search input { width:100%; } .attendance__table td,.attendance__table th { padding:10px; } .attendance__filters button { padding:6px 8px; } .attendance__table td:first-child { position:sticky; left:0; background:white; } .attendance__table tr.needs-review td:first-child { background:#fffcf5; } .attendance__table th:first-child { left:0; z-index:2; } }
</style>
