<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import LayoutCast from '../../components/LayoutCast.vue'
import { api } from '../../api.js'

const schedule = ref(null)
const loading = ref(true)
const error = ref('')
const showRooms = ref(false)
const selectedDate = ref(null)
const dayStrip = ref(null)
const todayDate = ref('')
const roomCache = ref({})
const roomLoading = ref(false)
const roomError = ref('')
const dragging = ref(false)
let requestNumber = 0
let roomRequestNumber = 0
let dragStart = null
let ignoreDragClick = false

function parseDate(value) {
  return new Date(`${value}T12:00:00`)
}

function dateString(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function moveDate(value, days) {
  const date = parseDate(value)
  date.setDate(date.getDate() + days)
  return dateString(date)
}

function dayLabel(value) {
  const date = parseDate(value)
  const weekDay = ['日', '月', '火', '水', '木', '金', '土'][date.getDay()]
  return `${date.getMonth() + 1}/${date.getDate()}（${weekDay}）`
}

function dayCardLabel(day) {
  const shifts = day.shifts.length
    ? day.shifts.map(shift => `${shift.start}から${shift.end}、${shift.room_name}`).join('、')
    : '出勤予定なし'
  return `${dayLabel(day.date)}、${shifts}、予約${day.order_count}件`
}

function minutes(value) {
  const [hour, minute] = String(value || '00:00').split(':').map(Number)
  return hour * 60 + minute
}

function hourLabel(value) {
  return `${String(value).padStart(2, '0')}:00`
}

function centerSelectedDay() {
  const strip = dayStrip.value
  const card = [...(strip?.children || [])].find(item => item.dataset.date === selectedDate.value)
  if (!card) return
  const cardLeft = card.getBoundingClientRect().left - strip.getBoundingClientRect().left + strip.scrollLeft
  strip.scrollTo({
    left: cardLeft - (strip.clientWidth - card.clientWidth) / 2,
    behavior: 'smooth',
  })
}

async function load(date = '', weekStart = '') {
  const currentRequest = ++requestNumber
  ++roomRequestNumber
  loading.value = true
  error.value = ''
  try {
    const data = await api.getCastSchedule(date, weekStart)
    if (currentRequest === requestNumber) {
      schedule.value = data
      selectedDate.value = data.selected_date
      roomCache.value = { [data.selected_date]: data.rooms }
      roomLoading.value = false
      roomError.value = ''
      showRooms.value = false
      if (!date) todayDate.value = data.selected_date
      await nextTick()
      centerSelectedDay()
    }
  } catch (exception) {
    if (currentRequest === requestNumber) error.value = exception.message
  } finally {
    if (currentRequest === requestNumber) loading.value = false
  }
}

onMounted(() => load())

function selectDay(day) {
  if (loading.value || !schedule.value) return
  if (selectedDate.value === day.date) return
  showRooms.value = false
  roomError.value = ''
  selectedDate.value = day.date
  nextTick(centerSelectedDay)
}

function goToday() {
  const todayInWeek = schedule.value?.days.find(day => day.date === todayDate.value)
  if (todayInWeek) selectDay(todayInWeek)
  else load()
}

function changeWeek(direction) {
  if (schedule.value) {
    load(
      moveDate(selectedDate.value, direction * 7),
      moveDate(schedule.value.week_start, direction * 7),
    )
  }
}

const selectedDay = computed(() =>
  schedule.value?.days.find(day => day.date === selectedDate.value),
)
const selectedOrders = computed(() => selectedDay.value?.orders || [])
const selectedRooms = computed(() => roomCache.value[selectedDate.value] || [])

async function toggleRooms() {
  showRooms.value = !showRooms.value
  if (!showRooms.value || !schedule.value || roomCache.value[selectedDate.value]) return
  await loadRooms()
}

async function loadRooms() {
  if (!schedule.value) return
  const date = selectedDate.value
  const weekStart = schedule.value.week_start
  const currentRequest = ++roomRequestNumber
  roomLoading.value = true
  roomError.value = ''
  try {
    const data = await api.getCastSchedule(date, weekStart)
    if (currentRequest === roomRequestNumber && schedule.value?.week_start === weekStart) {
      roomCache.value = { ...roomCache.value, [date]: data.rooms }
    }
  } catch (exception) {
    if (currentRequest === roomRequestNumber) roomError.value = exception.message || '読み込めませんでした'
  } finally {
    if (currentRequest === roomRequestNumber) roomLoading.value = false
  }
}

function onStripPointerDown(event) {
  if (event.pointerType !== 'mouse' || event.button !== 0) return
  dragStart = { x: event.clientX, scrollLeft: dayStrip.value.scrollLeft }
}

function onStripPointerMove(event) {
  if (!dragStart) return
  const distance = event.clientX - dragStart.x
  if (!dragging.value && Math.abs(distance) < 5) return
  if (!dragging.value) {
    dragging.value = true
    ignoreDragClick = true
    dayStrip.value.setPointerCapture(event.pointerId)
  }
  event.preventDefault()
  dayStrip.value.scrollLeft = dragStart.scrollLeft - distance
}

function onStripPointerEnd() {
  dragStart = null
  dragging.value = false
  setTimeout(() => { ignoreDragClick = false }, 0)
}

function onStripPointerLeave() {
  if (!dragging.value) onStripPointerEnd()
}

function onStripClick(event) {
  if (!ignoreDragClick) return
  event.preventDefault()
  event.stopPropagation()
  ignoreDragClick = false
}

const weekLabel = computed(() => {
  if (!schedule.value) return ''
  return `${dayLabel(schedule.value.week_start)} — ${dayLabel(moveDate(schedule.value.week_start, 6))}`
})

const timelineStart = computed(() => {
  const starts = [11 * 60]
  for (const shift of selectedDay.value?.shifts || []) starts.push(minutes(shift.start))
  for (const order of selectedOrders.value) starts.push(minutes(order.start))
  return Math.floor(Math.min(...starts) / 60)
})

const timelineEnd = computed(() => {
  const ends = [22 * 60]
  for (const shift of selectedDay.value?.shifts || []) ends.push(minutes(shift.end))
  for (const order of selectedOrders.value) ends.push(minutes(order.end))
  return Math.ceil(Math.max(...ends) / 60)
})

const timelineHours = computed(() =>
  Array.from({ length: timelineEnd.value - timelineStart.value + 1 }, (_, index) => timelineStart.value + index),
)

const timelineHeight = computed(() => (timelineEnd.value - timelineStart.value) * 52)

function bookingStyle(order) {
  const start = minutes(order.start)
  const end = minutes(order.end)
  return {
    top: `${((start - timelineStart.value * 60) / 60) * 52}px`,
    height: `${Math.max(((end - start) / 60) * 52, 36)}px`,
  }
}

function bookingState(status) {
  return {
    REQUESTED: '店舗確認待ち',
    CONFIRMED: '予約確定',
    IN_PROGRESS: '接客中',
    PENDING_FINALIZE: '会計待ち',
    DONE: '終了',
  }[status] || status
}

const roomAxisStart = computed(() => {
  const starts = [11 * 60]
  for (const room of selectedRooms.value) {
    for (const period of room.occupied) starts.push(minutes(period.start))
  }
  return Math.floor(Math.min(...starts) / 60)
})

const roomAxisEnd = computed(() => {
  const ends = [29 * 60]
  for (const room of selectedRooms.value) {
    for (const period of room.occupied) ends.push(minutes(period.end))
  }
  return Math.ceil(Math.max(...ends) / 60)
})

function roomPeriodStyle(period) {
  const base = roomAxisStart.value * 60
  const span = (roomAxisEnd.value - roomAxisStart.value) * 60
  return {
    left: `${((minutes(period.start) - base) / span) * 100}%`,
    width: `${((minutes(period.end) - minutes(period.start)) / span) * 100}%`,
  }
}
</script>

<template>
  <LayoutCast>
    <div class="cs-page">
      <header class="cs-heading">
        <div>
          <div class="cs-eyebrow">MY SCHEDULE</div>
          <h2>出勤・予約予定</h2>
          <p>確定した勤務と、あなたに入った予約をまとめて確認できます。</p>
        </div>
        <router-link to="/cast/shift-requests" class="cs-request-link">シフト申請 <i class="ti ti-arrow-right"></i></router-link>
      </header>

      <div v-if="error" class="alert alert-danger" role="alert">
        {{ error }} <button class="btn btn-sm btn-outline-danger ms-2" @click="load(schedule?.selected_date || '', schedule?.week_start || '')">再読み込み</button>
      </div>
      <div v-if="loading && !schedule" class="text-center py-5" role="status">読み込み中...</div>

      <template v-if="schedule">
        <section class="cs-card cs-week">
          <div class="cs-week-head">
            <button class="cs-icon-button" aria-label="前の週" :disabled="loading" @click="changeWeek(-1)"><i class="ti ti-chevron-left"></i></button>
            <strong>{{ weekLabel }}</strong>
            <button class="cs-icon-button" aria-label="次の週" :disabled="loading" @click="changeWeek(1)"><i class="ti ti-chevron-right"></i></button>
          </div>
          <div
            ref="dayStrip"
            class="cs-day-strip"
            :class="{ 'is-dragging': dragging }"
            :aria-busy="loading"
            aria-label="日付を選択"
            @pointerdown="onStripPointerDown"
            @pointermove="onStripPointerMove"
            @pointerup="onStripPointerEnd"
            @pointercancel="onStripPointerEnd"
            @lostpointercapture="onStripPointerEnd"
            @pointerleave="onStripPointerLeave"
            @click.capture="onStripClick"
          >
            <button
              v-for="day in schedule.days"
              :id="`cs-day-${day.date}`"
              :key="day.date"
              :data-date="day.date"
              class="cs-day"
              :class="{ 'is-selected': selectedDate === day.date }"
              :aria-label="dayCardLabel(day)"
              :aria-pressed="selectedDate === day.date"
              aria-controls="cs-day-panel"
              :disabled="loading"
              @click="selectDay(day)"
            >
              <span class="cs-day-top">
                <span class="cs-day-date">{{ dayLabel(day.date) }}</span>
                <span v-if="day.order_count" class="cs-booking-count" :title="`予約${day.order_count}件`" aria-hidden="true">{{ day.order_count > 99 ? '99+' : day.order_count }}</span>
              </span>
              <span class="cs-day-detail">
                <template v-if="day.shifts.length">
                  <span v-for="(shift, index) in day.shifts" :key="index" class="cs-day-shift">
                    {{ shift.start }}–{{ shift.end }}
                    <span>{{ shift.room_name }}</span>
                  </span>
                </template>
                <span v-else>出勤予定なし</span>
              </span>
            </button>
          </div>
          <div
            id="cs-day-panel"
            class="cs-day-panel"
            role="region"
            :aria-labelledby="`cs-day-${selectedDate}`"
            :aria-busy="loading"
          >
            <template v-if="selectedDay">
              <div class="cs-section-top">
                <h4>{{ dayLabel(selectedDate) }} の予定</h4>
                <button v-if="selectedDate !== todayDate" class="cs-today-button" :disabled="loading" @click="goToday">今日へ戻る</button>
              </div>

              <div v-if="selectedDay.shifts.length" class="cs-shift-summary">
                <i class="ti ti-door"></i>
                <div>
                  <strong>確定した出勤</strong>
                  <p v-for="(shift, index) in selectedDay.shifts" :key="index">
                    {{ shift.start }}–{{ shift.end }}　{{ shift.room_name }}
                  </p>
                </div>
              </div>
              <div v-else class="cs-no-shift">この日の確定した出勤はありません。</div>

              <div class="cs-timeline-title">
                <h5>予約タイムライン</h5>
                <span>{{ selectedOrders.length }}件</span>
              </div>
              <div v-if="selectedOrders.length" class="cs-timeline" :style="{ height: `${timelineHeight}px` }">
                <div
                  v-for="hour in timelineHours"
                  :key="hour"
                  class="cs-hour"
                  :style="{ top: `${(hour - timelineStart) * 52}px` }"
                ><span>{{ hourLabel(hour) }}</span></div>
                <div
                  v-for="order in selectedOrders"
                  :key="order.id"
                  class="cs-booking"
                  :class="{ 'is-pending': order.status === 'REQUESTED', 'is-done': order.status === 'DONE' }"
                  :style="bookingStyle(order)"
                >
                  <strong>{{ order.start }}–{{ order.end }}</strong>
                  <span>{{ order.room_name }} <span class="cs-booking-status">{{ bookingState(order.status) }}</span></span>
                </div>
              </div>
              <div v-else class="cs-empty-bookings">この日の予約はありません</div>

              <section class="cs-rooms">
                <button class="cs-rooms-toggle" :aria-expanded="showRooms" @click="toggleRooms">
                  <span><i class="ti ti-door"></i> この日のルーム使用状況</span>
                  <i class="ti" :class="showRooms ? 'ti-chevron-up' : 'ti-chevron-down'"></i>
                </button>
                <div v-if="showRooms" class="cs-rooms-body">
                  <p>色のついた時間は、確定シフトや予約で使用予定です。</p>
                  <div v-if="roomLoading" class="text-muted small" role="status">読み込み中...</div>
                  <div v-else-if="roomError" class="text-danger small">{{ roomError }} <button class="btn btn-sm btn-link" @click="loadRooms">再読み込み</button></div>
                  <div v-else-if="!selectedRooms.length" class="text-muted small">登録済みのルームはありません。</div>
                  <div v-for="room in roomLoading || roomError ? [] : selectedRooms" :key="room.name" class="cs-room">
                    <div class="cs-room-head"><strong>{{ room.name }}</strong><span>{{ room.occupied.length ? '使用予定あり' : '使用予定なし' }}</span></div>
                    <div class="cs-room-bar">
                      <div v-for="(period, index) in room.occupied" :key="index" class="cs-room-occupied" :style="roomPeriodStyle(period)"></div>
                    </div>
                    <div class="cs-room-scale"><span>{{ hourLabel(roomAxisStart) }}</span><span>{{ hourLabel(roomAxisEnd) }}</span></div>
                    <div v-if="room.occupied.length" class="cs-room-periods">使用予定: {{ room.occupied.map(period => `${period.start}–${period.end}`).join('、') }}</div>
                  </div>
                  <p class="cs-room-note">「使用予定なし」はシフト・予約の割当がない状態です。清掃などを含む予約可能時間の保証ではありません。</p>
                </div>
              </section>
            </template>
          </div>
        </section>
      </template>
    </div>
  </LayoutCast>
</template>

<style scoped>
.cs-page { max-width: 720px; margin: 0 auto; padding: 14px 0 34px; color: #20302d; }
.cs-heading { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; margin: 8px 0 20px; }
.cs-heading h2 { margin: 3px 0 5px; font-size: 1.6rem; font-weight: 800; }
.cs-heading p { margin: 0; color: #697874; font-size: .82rem; line-height: 1.5; }
.cs-eyebrow { color: #15816f; font-size: .68rem; font-weight: 800; letter-spacing: .12em; }
.cs-request-link { flex-shrink: 0; color: #177f70; font-size: .82rem; font-weight: 700; text-decoration: none; }
.cs-card { margin-bottom: 16px; border: 1px solid #e0e9e6; border-radius: 16px; background: #fff; box-shadow: 0 5px 20px rgba(27, 56, 47, .04); overflow: hidden; }
.cs-week-head { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: #f2f8f5; }
.cs-week-head strong { font-size: .9rem; }
.cs-icon-button { width: 38px; height: 38px; border: 1px solid #d6e5df; border-radius: 10px; background: #fff; color: #146f62; }
.cs-day-strip { --cs-day-width: 128px; display: flex; gap: 9px; overflow-x: auto; padding: 12px max(12px, calc((100% - var(--cs-day-width)) / 2)) 15px; scroll-snap-type: x mandatory; overscroll-behavior-x: contain; scrollbar-width: none; cursor: grab; }
.cs-day-strip.is-dragging { cursor: grabbing; scroll-snap-type: none; user-select: none; }
.cs-day-strip::-webkit-scrollbar { display: none; }
.cs-day { display: flex; flex: 0 0 var(--cs-day-width); flex-direction: column; gap: 7px; min-height: 112px; padding: 10px 11px; border: 1px solid #dfe9e3; border-radius: 12px; background: #fff; color: inherit; text-align: left; scroll-snap-align: center; }
.cs-day.is-selected { border-color: #1b987e; background: #e9f5f0; box-shadow: 0 0 0 1px #1b987e; }
.cs-day:focus-visible { outline: 2px solid #137d69; outline-offset: 2px; }
.cs-day-top { display: flex; justify-content: space-between; align-items: center; gap: 3px; min-height: 25px; }
.cs-day-date { font-size: .78rem; font-weight: 800; white-space: nowrap; }
.cs-booking-count { display: grid; flex: 0 0 auto; place-items: center; min-width: 24px; height: 24px; padding: 0 4px; border-radius: 999px; background: var(--bs-danger, #dc3545); color: #fff; font-size: .74rem; font-weight: 800; line-height: 1; }
.cs-day-detail { display: grid; gap: 5px; min-width: 0; color: #63736e; font-size: .74rem; line-height: 1.3; }
.cs-day-shift { display: grid; gap: 2px; overflow-wrap: anywhere; color: #213e36; font-weight: 700; }
.cs-day-panel { padding: 18px; border-top: 1px solid #d9ebe3; background: #fff; }
.cs-section-top { display: flex; justify-content: space-between; align-items: center; gap: 12px; min-height: 36px; margin-bottom: 16px; }
.cs-section-top h4 { margin: 0; font-size: 1.08rem; font-weight: 800; line-height: 1.3; }
.cs-today-button { flex-shrink: 0; padding: 7px 11px; border: 1px solid #cce1d8; border-radius: 9px; background: #fff; color: #177f70; font-size: .8rem; font-weight: 800; white-space: nowrap; }
.cs-shift-summary { display: flex; gap: 12px; margin-bottom: 24px; padding: 15px; border-radius: 12px; background: #e9f6f1; }
.cs-shift-summary > i { color: #178b75; font-size: 1.2rem; }
.cs-shift-summary strong { font-size: .82rem; }
.cs-shift-summary p { margin: 2px 0 0; font-size: .92rem; font-weight: 700; }
.cs-no-shift { margin-bottom: 24px; padding: 13px; border-radius: 10px; background: #f6f8f7; color: #66736f; font-size: .84rem; }
.cs-timeline-title { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 13px; }
.cs-timeline-title h5 { margin: 0; font-size: .98rem; font-weight: 800; }
.cs-timeline-title span { color: #64736e; font-size: .8rem; }
.cs-timeline { position: relative; margin: 0 0 14px 7px; border-left: 1px solid #dbe6e1; }
.cs-hour { position: absolute; left: 0; right: 0; height: 1px; border-top: 1px solid #e6edeb; }
.cs-hour span { position: relative; top: -10px; left: 9px; padding-right: 6px; background: #fff; color: #73827c; font-size: .68rem; }
.cs-booking { position: absolute; right: 3px; left: 65px; z-index: 1; display: flex; flex-direction: column; justify-content: center; gap: 2px; min-height: 36px; padding: 4px 10px; border: 1px solid #cde6da; border-radius: 8px; background: #e6f4ed; overflow: hidden; line-height: 1.2; }
.cs-booking strong { font-size: .81rem; }
.cs-booking > span { font-size: .72rem; }
.cs-booking-status { color: #526f63; }
.cs-booking.is-pending { border-color: #e9ddc5; background: #fff5e4; }
.cs-booking.is-done { border-color: #dce5df; background: #edf1ef; }
.cs-empty-bookings { margin-bottom: 8px; padding: 20px 12px; border-radius: 10px; background: #f7f9f8; color: #71817a; font-size: .82rem; text-align: center; }
.cs-rooms { margin-top: 22px; border: 1px solid #e0e9e6; border-radius: 12px; overflow: hidden; }
.cs-rooms-toggle { display: flex; justify-content: space-between; align-items: center; width: 100%; padding: 15px; border: 0; background: #f8fbf9; color: #213c32; font-weight: 800; text-align: left; }
.cs-rooms-toggle span { display: flex; align-items: center; gap: 8px; }
.cs-rooms-toggle span i { color: #16836f; }
.cs-rooms-body { padding: 0 18px 18px; }
.cs-rooms-body > p { color: #677a72; font-size: .8rem; line-height: 1.6; }
.cs-room { margin-top: 14px; padding: 14px; border: 1px solid #e6ece8; border-radius: 12px; }
.cs-room-head, .cs-room-scale { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.cs-room-head strong { font-size: .86rem; }
.cs-room-head span, .cs-room-periods { color: #63756d; font-size: .73rem; }
.cs-room-bar { position: relative; height: 18px; margin-top: 13px; border-radius: 9px; background: #eaf2ed; overflow: hidden; }
.cs-room-occupied { position: absolute; top: 0; bottom: 0; background: #e38884; }
.cs-room-scale { margin-top: 3px; color: #83908a; font-size: .65rem; }
.cs-room-periods { margin-top: 6px; line-height: 1.5; }
.cs-room-note { margin: 18px 0 0; padding: 10px; border-radius: 9px; background: #f6f8f7; }
@media (max-width: 400px) {
  .cs-heading { align-items: flex-start; flex-direction: column; }
  .cs-day-strip { --cs-day-width: 118px; }
  .cs-day-panel { padding: 16px 12px; }
}
</style>
