<script setup>
import { computed } from 'vue'
import { calendarDays, compactDayEvents, shiftMinutes } from '../shiftCalendar.js'
const props = defineProps({
  mode: { type: String, required: true }, anchor: { type: String, required: true },
  today: { type: String, required: true }, selected: { type: String, required: true },
  shifts: { type: Array, default: () => [] },
})
const emit = defineEmits(['select-day', 'select-shift'])
const days = computed(() => calendarDays(props.anchor, props.mode))
const byDay = computed(() => {
  const map = new Map(days.value.map(day => [day, []]))
  for (const shift of props.shifts) map.get(shift.date)?.push(shift)
  for (const rows of map.values()) rows.sort((a, b) => shiftMinutes(a).start - shiftMinutes(b).start || a.id - b.id)
  return map
})
const range = computed(() => {
  const intervals = props.shifts.map(shiftMinutes)
  return { start: Math.min(9 * 60, ...intervals.map(v => Math.floor(v.start / 60) * 60)), end: Math.max(24 * 60, ...intervals.map(v => Math.ceil(v.end / 60) * 60)) }
})
const hours = computed(() => Array.from({ length: (range.value.end - range.value.start) / 60 }, (_, i) => range.value.start / 60 + i))
const height = computed(() => hours.value.length * 44)
const weekEvents = computed(() => new Map(days.value.map(day => [day, compactDayEvents(byDay.value.get(day))])))
const weekdays = ['月', '火', '水', '木', '金', '土', '日']
function timeLabel(s) { return `${s.start_time_extended || s.start_time?.slice(0, 5)}〜${s.end_time_extended || s.end_time?.slice(0, 5)}` }
function status(s) { return s.is_absent ? '当欠' : s.clocked_in_at ? '出勤済み' : '未打刻' }
function title(s) { return `${s.cast_name} ${timeLabel(s)} ${s.room_name || 'ルーム未定'} ${status(s)}` }
function eventStyle(item) {
  return { top: `${(item.start - range.value.start) / 60 * 44}px`, height: `${Math.max(28, (item.end - item.start) / 60 * 44 - 2)}px`, left: `calc(${item.lane / item.columns * 100}% + 2px)`, width: `calc(${100 / item.columns}% - 4px)` }
}
</script>

<template>
  <section class="shift-calendar" :aria-label="mode === 'month' ? '月のシフトカレンダー' : '週のシフトカレンダー'">
    <div v-if="mode === 'month'" class="month-grid">
      <div v-for="(weekday, i) in weekdays" :key="weekday" class="month-weekday" :class="{ weekend: i > 4 }">{{ weekday }}</div>
      <div v-for="day in days" :key="day" class="month-day" :class="{ outside: day.slice(0, 7) !== anchor.slice(0, 7), selected: day === selected }">
        <button type="button" class="day-number" :class="{ today: day === today }" :aria-label="`${day}のシフトを見る`" :aria-pressed="day === selected" @click="emit('select-day', day)">{{ Number(day.slice(-2)) }}</button>
        <button v-for="shift in byDay.get(day).slice(0, 3)" :key="shift.id" type="button" class="month-event" :class="{ absent: shift.is_absent, attended: shift.clocked_in_at && !shift.is_absent }" :title="title(shift)" :aria-label="`${title(shift)}を編集`" @click="emit('select-shift', shift)">
          <span class="event-dot"></span><span class="event-name">{{ shift.cast_name }}</span><span class="event-start">{{ (shift.start_time_extended || shift.start_time)?.slice(0, 5) }}</span>
        </button>
        <button v-if="byDay.get(day).length > 3" type="button" class="more-events" :aria-label="`${day}の全${byDay.get(day).length}件を見る`" @click="emit('select-day', day)">他{{ byDay.get(day).length - 3 }}件</button>
      </div>
    </div>
    <div v-else class="week-scroll" tabindex="0" aria-label="週表示。左右にスクロールできます">
      <div class="week-grid">
        <div class="week-header"><span class="time-zone">営業日</span><button v-for="(day, i) in days" :key="day" type="button" :class="{ selected: day === selected }" :aria-label="`${day}の全${byDay.get(day).length}件を見る`" @click="emit('select-day', day)"><span>{{ weekdays[i] }}</span><strong :class="{ today: day === today }">{{ Number(day.slice(-2)) }}</strong><span>{{ byDay.get(day).length }}件</span></button></div>
        <div class="week-body" :style="{ height: `${height}px` }">
          <div class="time-axis"><div v-for="hour in hours" :key="hour" class="time-label">{{ String(hour).padStart(2, '0') }}:00</div></div>
          <div v-for="day in days" :key="day" class="week-day" :class="{ 'selected-column': day === selected }">
            <div v-for="hour in hours" :key="hour" class="hour-line"></div>
            <button v-for="item in weekEvents.get(day).visible" :key="item.shift.id" type="button" class="week-event" :class="{ absent: item.shift.is_absent, attended: item.shift.clocked_in_at && !item.shift.is_absent }" :style="eventStyle(item)" :title="title(item.shift)" :aria-label="`${title(item.shift)}を編集`" @click="emit('select-shift', item.shift)">
              <strong>{{ item.shift.cast_name }}</strong><span>{{ timeLabel(item.shift) }}</span><span>{{ item.shift.room_name || 'ルーム未定' }}</span><span>{{ status(item.shift) }}</span>
            </button>
            <button v-for="item in weekEvents.get(day).overflow" :key="item.key" type="button" class="week-event week-overflow" :style="eventStyle(item)" :aria-label="`${day}の重なるシフト他${item.count}件を一覧で見る`" @click="emit('select-day', day)">他{{ item.count }}件<span>一覧で確認</span></button>
          </div>
        </div>
      </div>
    </div>
    <p class="calendar-hint">日付を選ぶと下に一覧を表示します。シフトを選ぶと編集できます。24時以降も元の営業日に表示します。</p>
  </section>
</template>

<style scoped>
.shift-calendar { --calendar-line: #e3e7ed; --calendar-blue: #1a73e8; color: #3c4043; }
.month-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); border: 1px solid var(--calendar-line); border-radius: 12px; overflow: hidden; }
.month-weekday { text-align: center; padding: 10px 0; font-size: 12px; border-bottom: 1px solid var(--calendar-line); color: #6b7280; }
.month-day { min-height: 144px; border-right: 1px solid var(--calendar-line); border-bottom: 1px solid var(--calendar-line); padding: 5px; min-width: 0; }
.month-day:nth-child(7n) { border-right: 0; }.month-day:nth-last-child(-n+7) { border-bottom: 0; }
.outside { background: #f8f9fa; color: #90959e; }.selected { background: #eaf2ff; }
.day-number { display: block; width: 28px; height: 28px; line-height: 28px; padding: 0; white-space: nowrap; border: 0; background: transparent; color: inherit; border-radius: 50%; margin: 0 auto 4px; font-size: 13px; }
.today { background: var(--calendar-blue) !important; color: white !important; border-radius: 50%; }
.month-event { display: flex; align-items: center; width: 100%; gap: 4px; border: 0; border-radius: 4px; padding: 3px 4px; background: #e8f0fe; color: #174ea6; margin-bottom: 3px; font-size: 12px; text-align: left; }
.event-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }.event-start { font-size: 10px; white-space: nowrap; }
.event-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.attended { background: #e6f4ea !important; color: #137333 !important; }.absent { background: #fce8e6 !important; color: #b3261e !important; text-decoration: line-through; }
.more-events { background: transparent; border: 0; padding: 1px 4px; border-radius: 4px; color: #5f6368; font-size: 11px; width: 100%; text-align: left; }
.week-scroll { overflow: auto; max-height: 720px; border: 1px solid var(--calendar-line); border-radius: 12px; }
.week-grid { min-width: 860px; }.week-header { position: sticky; top: 0; z-index: 3; background: white; display: grid; grid-template-columns: 60px repeat(7, minmax(0, 1fr)); border-bottom: 1px solid var(--calendar-line); }
.week-header button { border: 0; border-left: 1px solid var(--calendar-line); background: white; padding: 8px; display: flex; flex-direction: column; align-items: center; gap: 2px; }
.week-header button span { font-size: 11px; color: #6b7280; }.week-header strong { font-size: 22px; font-weight: 500; width: 36px; line-height: 36px; }
.time-zone { align-self: end; padding: 5px; font-size: 10px; color: #6b7280; }.week-body { display: grid; grid-template-columns: 60px repeat(7, minmax(0, 1fr)); }
.week-day { position: relative; border-left: 1px solid var(--calendar-line); }.selected-column { background: #f7faff; }.time-label { height: 44px; font-size: 10px; text-align: right; padding: 0 6px; color: #6b7280; }
.hour-line { height: 44px; border-bottom: 1px solid var(--calendar-line); }.week-event { position: absolute; border: 0; border-left: 3px solid var(--calendar-blue); border-radius: 5px; background: #e8f0fe; color: #174ea6; padding: 5px; text-align: left; overflow: auto; font-size: 11px; display: flex; flex-direction: column; gap: 2px; overflow-wrap: anywhere; }
.calendar-hint { font-size: 12px; color: #6b7280; margin: 10px 0 18px; }button:focus-visible { outline: 2px solid var(--calendar-blue); outline-offset: -2px; }button:hover { filter: brightness(.97); }
.week-overflow { background: #f1f3f4; color: #5f6368; border-left-color: #9aa0a6; }.week-header button.selected { background: #eaf2ff; }
@media(max-width: 600px) { .month-day { min-height: 110px; padding: 2px; }.month-event { padding: 2px; gap: 2px; font-size: 10px; }.event-start, .event-dot { display: none; }.day-number { width: 25px; height: 25px; }.more-events { font-size: 10px; padding: 1px; }.week-scroll { max-height: 560px; } }
</style>
