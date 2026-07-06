<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'

const props = defineProps({
  casts: { type: Array, default: () => [] },
  orders: { type: Array, default: () => [] },
  startHour: { type: Number, default: 12 },
  endHour: { type: Number, default: 20 },
  showRoom: { type: Boolean, default: true },
})

const emit = defineEmits(['block-click', 'create-order'])

const gridRef = ref(null)
const nowMs = ref(Date.now())
let nowTimer = null

const hoveredCastId = ref(null)
const pinnedCastId = ref(null)
const popoverPos = ref({ top: 0, left: 0, placement: 'right' })
let hoverTimeout = null

const visibleCastId = computed(() => pinnedCastId.value || hoveredCastId.value)
const visibleCast = computed(() => props.casts.find(c => c.id === visibleCastId.value) || null)

function positionPopover(element) {
  const rect = element.getBoundingClientRect()
  const popW = 280
  const popH = 200
  const vw = window.innerWidth
  const vh = window.innerHeight
  let left = rect.right + 8
  let placement = 'right'
  if (left + popW > vw - 8) {
    left = rect.left - popW - 8
    placement = 'left'
  }
  let top = rect.top
  if (top + popH > vh - 8) top = Math.max(8, vh - popH - 8)
  popoverPos.value = { top, left, placement }
}

function onCastEnter(castId, event) {
  clearTimeout(hoverTimeout)
  if (pinnedCastId.value) return
  hoveredCastId.value = castId
  positionPopover(event.currentTarget)
}

function onCastLeave() {
  if (pinnedCastId.value) return
  hoverTimeout = setTimeout(() => { hoveredCastId.value = null }, 150)
}

function onCastClick(castId, event) {
  event.stopPropagation()
  if (pinnedCastId.value === castId) {
    pinnedCastId.value = null
    return
  }
  pinnedCastId.value = castId
  hoveredCastId.value = null
  positionPopover(event.currentTarget)
}

function onPopoverEnter() {
  clearTimeout(hoverTimeout)
}

function onPopoverLeave() {
  if (pinnedCastId.value) return
  hoveredCastId.value = null
}

function onDocumentMousedown(e) {
  if (!pinnedCastId.value) return
  if (e.target.closest('.rk-castcell') || e.target.closest('.rk-castpop')) return
  pinnedCastId.value = null
}

function onDocumentKey(e) {
  if (e.key === 'Escape') {
    pinnedCastId.value = null
    hoveredCastId.value = null
  }
}

function onScrollClose() {
  pinnedCastId.value = null
  hoveredCastId.value = null
}

const effectiveStartHour = computed(() => {
  let earliest = props.startHour
  for (const c of props.casts || []) {
    const shifts = Array.isArray(c.shifts) ? c.shifts : []
    for (const s of shifts) {
      const t = (s.start_time || '').slice(0, 5)
      if (!t) continue
      const h = parseInt(t.slice(0, 2), 10)
      if (Number.isFinite(h) && h < earliest) earliest = h
    }
  }
  return Math.max(0, earliest)
})

const effectiveEndHour = computed(() => {
  let latest = props.endHour
  for (const c of props.casts || []) {
    const shifts = Array.isArray(c.shifts) ? c.shifts : []
    for (const s of shifts) {
      const t = (s.end_time || '').slice(0, 5)
      if (!t) continue
      const h = parseInt(t.slice(0, 2), 10)
      const m = parseInt(t.slice(3, 5), 10) || 0
      const eff = m > 0 ? h + 1 : h
      if (Number.isFinite(eff) && eff > latest) latest = eff
    }
  }
  return Math.min(23, latest)
})

const hours = computed(() => {
  const arr = []
  for (let h = effectiveStartHour.value; h <= effectiveEndHour.value; h++) {
    arr.push(`${String(h).padStart(2, '0')}:00`)
  }
  return arr
})

const totalCols = computed(() => effectiveEndHour.value - effectiveStartHour.value + 1)

const castIndexMap = computed(() => {
  const map = {}
  props.casts.forEach((c, i) => { map[c.id] = i })
  return map
})

function parseTimeToMin(t) {
  const [h, m] = String(t).split(':').map(Number)
  return h * 60 + m
}

function statusClass(order) {
  // 完了は他のフラグ（要注意・未確認 等）より優先して完了感を出す
  if (order.status === 'DONE') return ['is-done']
  const cls = []
  switch (order.status) {
    case 'CONFIRMED': cls.push('is-approved'); break
    case 'REQUESTED': cls.push('is-requested'); break
    case 'IN_PROGRESS': cls.push('is-approved'); break
    case 'PENDING_FINALIZE': cls.push('is-attention'); break
  }
  if (order.customer_label && order.customer_label.includes('★注意')) {
    cls.push('is-attention')
  }
  if (order.is_unconfirmed) {
    cls.push('is-unconfirmed')
  }
  return cls
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function blockMeta(order) {
  const t = `${formatTime(order.start)}–${formatTime(order.end)}`
  if (order.status === 'REQUESTED') return `申請中 / ${t}`
  return t
}

function castRoomLabel(cast) {
  if (!props.showRoom) return ''
  const shifts = Array.isArray(cast.shifts) ? cast.shifts : []
  if (shifts.length === 0) return ''
  const names = []
  for (const s of shifts) {
    const n = s.room_name || ''
    if (n && !names.includes(n)) names.push(n)
  }
  return names.length ? names.join(' / ') : '未設定'
}

function castShiftRange(cast) {
  const shifts = Array.isArray(cast.shifts) ? cast.shifts : []
  if (shifts.length === 0) return ''
  let minStart = null
  let maxEnd = null
  for (const s of shifts) {
    const st = (s.start_time || '').slice(0, 5)
    const ed = (s.end_time || '').slice(0, 5)
    if (st && (minStart === null || st < minStart)) minStart = st
    if (ed && (maxEnd === null || ed > maxEnd)) maxEnd = ed
  }
  if (!minStart || !maxEnd) return ''
  return `${minStart}〜${maxEnd}`
}

function castStaffMemo(cast) {
  const m = (cast.staff_memo || '').trim()
  return m
}

function castDailyMemo(cast) {
  const shifts = Array.isArray(cast.shifts) ? cast.shifts : []
  for (const s of shifts) {
    const m = (s.daily_memo || '').trim()
    if (m) return m
  }
  return ''
}

const ROOM_COLOR_CLASSES = ['rk-room--c1', 'rk-room--c2', 'rk-room--c3', 'rk-room--c4', 'rk-room--c5', 'rk-room--c6']
const BAND_COLOR_CLASSES = ['rk-shift-band--c1', 'rk-shift-band--c2', 'rk-shift-band--c3', 'rk-shift-band--c4', 'rk-shift-band--c5', 'rk-shift-band--c6']

function roomColorMeta(cast) {
  const shifts = Array.isArray(cast.shifts) ? cast.shifts : []
  for (const s of shifts) {
    if (s.room_color) return { class: '', style: { background: s.room_color } }
    if (s.room_id != null) {
      const idx = Math.abs(Number(s.room_id)) % ROOM_COLOR_CLASSES.length
      return { class: ROOM_COLOR_CLASSES[idx], style: null }
    }
  }
  return { class: 'rk-room--unset', style: null }
}

function bandColorMeta(shift) {
  if (shift && shift.room_color) {
    return { class: '', style: { background: shift.room_color } }
  }
  if (shift && shift.room_id != null) {
    const idx = Math.abs(Number(shift.room_id)) % BAND_COLOR_CLASSES.length
    return { class: BAND_COLOR_CLASSES[idx], style: null }
  }
  return { class: 'rk-shift-band--unset', style: null }
}

function castConfirmFlag(cast) {
  // Phase 3-B-1 残課題: ShiftAssignment.confirmed_at（キャストによる事前出勤確認）の表示。
  // clocked_in_at（実打刻／castStatus()）とは別概念。
  const shifts = Array.isArray(cast.shifts) ? cast.shifts : []
  if (shifts.length === 0) return null
  const anyConfirmed = shifts.some(s => s.confirmed_at)
  return { confirmed: anyConfirmed, label: anyConfirmed ? '出勤確認済み' : '出勤未確認' }
}

function castStatus(cast) {
  const shifts = Array.isArray(cast.shifts) ? cast.shifts : []
  if (shifts.length === 0) return null
  const anyAbsent = shifts.some(s => s.is_absent)
  if (anyAbsent) return { key: 'dayoff', label: '当欠', short: '欠' }
  const anyClockedIn = shifts.some(s => s.clocked_in_at)
  if (anyClockedIn) return { key: 'in', label: '出勤済み', short: '済' }
  let minStart = null
  for (const s of shifts) {
    const st = (s.start_time || '').slice(0, 5)
    if (st && (minStart === null || st < minStart)) minStart = st
  }
  if (!minStart) return { key: 'scheduled', label: '出勤予定', short: '予' }
  const d = new Date(nowMs.value)
  const cur = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (cur < minStart) return { key: 'scheduled', label: '出勤予定', short: '予' }
  return { key: 'absent', label: '未出勤', short: '未' }
}

function fmtMin(min) {
  const hh = String(Math.floor(min / 60)).padStart(2, '0')
  const mm = String(min % 60).padStart(2, '0')
  return `${hh}:${mm}`
}

const shiftBands = computed(() => {
  const visibleStart = effectiveStartHour.value * 60
  const visibleEnd = (effectiveEndHour.value + 1) * 60
  const bands = []
  props.casts.forEach((cast, row) => {
    const shifts = Array.isArray(cast.shifts) ? cast.shifts : []
    for (const s of shifts) {
      const st = (s.start_time || '').slice(0, 5)
      const ed = (s.end_time || '').slice(0, 5)
      if (!st || !ed) continue
      const stMin = parseTimeToMin(st)
      const edMin = parseTimeToMin(ed)
      const clipStart = Math.max(stMin, visibleStart)
      const clipEnd = Math.min(edMin, visibleEnd)
      if (clipEnd <= clipStart) continue
      const meta = bandColorMeta(s)
      bands.push({
        id: `band-${cast.id}-${s.id ?? `${stMin}-${edMin}`}`,
        row,
        start: fmtMin(clipStart),
        end: fmtMin(clipEnd),
        colorClass: meta.class,
        colorStyle: meta.style,
      })
    }
  })
  return bands
})

const intervalBlocks = computed(() => {
  const blocks = []
  for (const cast of props.casts) {
    const interval = cast.interval_minutes || 0
    if (!interval) continue
    const castOrders = props.orders
      .filter(o => o.cast_id === cast.id && o.status !== 'CANCELLED')
      .sort((a, b) => new Date(a.end) - new Date(b.end))
    for (const order of castOrders) {
      const endTime = formatTime(order.end)
      const endMin = parseTimeToMin(endTime)
      const intervalEndMin = endMin + interval
      const intervalEnd = `${String(Math.floor(intervalEndMin / 60)).padStart(2, '0')}:${String(intervalEndMin % 60).padStart(2, '0')}`
      blocks.push({
        id: `iv-${order.id}`,
        cast_id: cast.id,
        start: endTime,
        end: intervalEnd,
        label: `${interval}`,
      })
    }
  }
  return blocks
})

function readVar(name, fallback) {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name))
  return isFinite(v) && v > 0 ? v : fallback
}

function layoutBlocks() {
  if (!gridRef.value) return
  const grid = gridRef.value
  const hourW = readVar('--rk-col-w', 120)
  const rowH = readVar('--rk-row-hour-h', 80)

  const startMin = effectiveStartHour.value * 60

  grid.style.width = `${hourW * totalCols.value}px`
  grid.style.height = `${rowH * props.casts.length}px`

  grid.querySelectorAll('.rk-block, .rk-interval, .rk-shift-band').forEach(el => {
    const isBand = el.classList.contains('rk-shift-band')
    const row = Number(el.dataset.row || 0)
    const s = parseTimeToMin(el.dataset.start)
    const e = parseTimeToMin(el.dataset.end)

    const padY = isBand ? 0 : 6
    const left = ((s - startMin) / 60) * hourW
    const width = Math.max(12, ((e - s) / 60) * hourW)
    const top = row * rowH + padY
    const height = isBand ? rowH : Math.max(12, rowH - padY * 2)

    el.style.left = `${left}px`
    el.style.top = `${top}px`
    el.style.width = `${width}px`
    el.style.height = `${height}px`
  })
}

function onResize() { layoutBlocks() }

function onGridClick(ev) {
  const target = ev.target
  if (target.closest && (target.closest('.rk-block') || target.closest('.rk-interval'))) return
  if (!gridRef.value) return

  const hourW = readVar('--rk-col-w', 120)
  const rowH = readVar('--rk-row-hour-h', 80)

  const rect = gridRef.value.getBoundingClientRect()
  const x = ev.clientX - rect.left
  const y = ev.clientY - rect.top

  const rowIdx = Math.floor(y / rowH)
  if (rowIdx < 0 || rowIdx >= props.casts.length) return
  const cast = props.casts[rowIdx]
  if (!cast) return

  const minutesFromStart = Math.max(0, Math.floor((x / hourW) * 60))
  const totalMin = effectiveStartHour.value * 60 + minutesFromStart
  const snapped = Math.floor(totalMin / 5) * 5
  const hh = String(Math.floor(snapped / 60)).padStart(2, '0')
  const mm = String(snapped % 60).padStart(2, '0')

  const shifts = Array.isArray(cast.shifts) ? cast.shifts : []
  const first = shifts[0] || null

  emit('create-order', {
    cast,
    start_time: `${hh}:${mm}`,
    room_id: first ? first.room_id : null,
    room_name: first ? first.room_name : '',
  })
}

onMounted(() => {
  nextTick(layoutBlocks)
  window.addEventListener('resize', onResize)
  window.addEventListener('scroll', onScrollClose, true)
  document.addEventListener('mousedown', onDocumentMousedown)
  document.addEventListener('keydown', onDocumentKey)
  nowTimer = setInterval(() => { nowMs.value = Date.now() }, 60 * 1000)
})
watch(() => [props.casts, props.orders], () => nextTick(layoutBlocks))
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('scroll', onScrollClose, true)
  document.removeEventListener('mousedown', onDocumentMousedown)
  document.removeEventListener('keydown', onDocumentKey)
  if (nowTimer) clearInterval(nowTimer)
  clearTimeout(hoverTimeout)
})
</script>

<template>
  <section class="rk-schedule">
    <div class="rk-sheet-scroll">
      <div
        class="rk-sheet"
        :data-rows="casts.length"
        :data-start="`${String(effectiveStartHour).padStart(2,'0')}:00`"
        :data-end="`${String(effectiveEndHour).padStart(2,'0')}:00`"
      >
        <!-- 左上の角（固定） -->
        <div class="rk-corner"></div>

        <!-- 上：時間ヘッダー（横） -->
        <div class="rk-timecol">
          <div v-for="hour in hours" :key="hour" class="rk-time">{{ hour }}</div>
        </div>

        <!-- 左：キャスト/ルーム列（縦） -->
        <div class="rk-casthead">
          <div
            v-for="cast in casts"
            :key="cast.id"
            class="rk-castcell"
            :class="{ 'is-active': visibleCastId === cast.id }"
            @mouseenter="onCastEnter(cast.id, $event)"
            @mouseleave="onCastLeave"
            @click="onCastClick(cast.id, $event)"
          >
            <img
              v-if="cast.avatar_url"
              :src="cast.avatar_url"
              :alt="cast.name"
              class="rk-avatar-img"
            >
            <div
              v-else
              class="rk-avatar-img rk-avatar-img--placeholder"
            >
              <i class="ti ti-user"></i>
            </div>
            <div class="rk-castcell__text">
              <div class="rk-name-row">
                <span class="rk-name">{{ cast.name }}</span>
                <span
                  v-if="castStatus(cast)"
                  class="rk-status"
                  :class="`rk-status--${castStatus(cast).key}`"
                  :title="castStatus(cast).label"
                >{{ castStatus(cast).short }}</span>
                <i
                  v-if="castConfirmFlag(cast)"
                  class="ti"
                  :class="castConfirmFlag(cast).confirmed ? 'ti-square-check text-success' : 'ti-square text-muted'"
                  :title="castConfirmFlag(cast).label"
                  style="font-size: 12px;"
                ></i>
              </div>
              <div class="rk-meta-row">
                <span v-if="castShiftRange(cast)" class="rk-shift-time">{{ castShiftRange(cast) }}</span>
                <span
                  v-if="castRoomLabel(cast)"
                  class="rk-room"
                  :class="roomColorMeta(cast).class"
                  :style="roomColorMeta(cast).style"
                  :title="castRoomLabel(cast)"
                >{{ castRoomLabel(cast) }}</span>
              </div>
              <div
                v-if="castStaffMemo(cast)"
                class="rk-staff-memo"
                :title="castStaffMemo(cast)"
              >{{ castStaffMemo(cast) }}</div>
              <div
                v-if="castDailyMemo(cast)"
                class="rk-daily-memo"
                :title="castDailyMemo(cast)"
              ><span class="rk-daily-memo__label">当日メモ</span>{{ castDailyMemo(cast) }}</div>
            </div>
          </div>
        </div>

        <!-- 本体グリッド -->
        <div ref="gridRef" class="rk-grid" :data-rows="casts.length" @click="onGridClick">
          <div
            v-for="band in shiftBands"
            :key="band.id"
            class="rk-shift-band"
            :class="band.colorClass"
            :style="band.colorStyle"
            :data-row="band.row"
            :data-start="band.start"
            :data-end="band.end"
          >
            <span class="rk-shift-band__label">出勤中</span>
          </div>
          <a
            v-for="order in orders"
            :key="order.id"
            class="rk-block"
            :class="statusClass(order)"
            href="#"
            :data-order-id="order.id"
            :data-row="castIndexMap[order.cast_id] ?? 0"
            :data-start="formatTime(order.start)"
            :data-end="formatTime(order.end)"
            @click.prevent.stop="emit('block-click', order)"
          >
            <div class="rk-block__title">{{ order.customer_label }} ({{ order.course_name }})</div>
            <div class="rk-block__meta">{{ blockMeta(order) }}</div>
          </a>

          <div
            v-for="iv in intervalBlocks"
            :key="iv.id"
            class="rk-interval"
            :data-row="castIndexMap[iv.cast_id] ?? 0"
            :data-start="iv.start"
            :data-end="iv.end"
            title="インターバル中（予約不可）"
            @click.stop.prevent
          >
            <span class="rk-interval__label">IV{{ iv.label }}</span>
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="visibleCast"
        class="rk-castpop"
        :class="`rk-castpop--${popoverPos.placement}`"
        :style="{ top: popoverPos.top + 'px', left: popoverPos.left + 'px' }"
        @mouseenter="onPopoverEnter"
        @mouseleave="onPopoverLeave"
        @click.stop
      >
        <div class="rk-castpop__header">
          <img
            v-if="visibleCast.avatar_url"
            :src="visibleCast.avatar_url"
            :alt="visibleCast.name"
            class="rk-castpop__avatar"
          >
          <div v-else class="rk-castpop__avatar rk-castpop__avatar--placeholder">
            <i class="ti ti-user"></i>
          </div>
          <div class="rk-castpop__main">
            <div class="rk-castpop__name">{{ visibleCast.name }}</div>
            <span
              v-if="castStatus(visibleCast)"
              class="rk-castpop__status"
              :class="`rk-status--${castStatus(visibleCast).key}`"
            >{{ castStatus(visibleCast).label }}</span>
          </div>
        </div>

        <div class="rk-castpop__rows">
          <div v-if="castShiftRange(visibleCast)" class="rk-castpop__row">
            <i class="ti ti-clock"></i>
            <span>{{ castShiftRange(visibleCast) }}</span>
          </div>
          <div v-if="castRoomLabel(visibleCast)" class="rk-castpop__row">
            <i class="ti ti-door"></i>
            <span>{{ castRoomLabel(visibleCast) }}</span>
          </div>
          <div v-if="castConfirmFlag(visibleCast)" class="rk-castpop__row">
            <i
              class="ti"
              :class="castConfirmFlag(visibleCast).confirmed ? 'ti-square-check text-success' : 'ti-square text-muted'"
            ></i>
            <span>{{ castConfirmFlag(visibleCast).label }}</span>
          </div>
        </div>

        <div v-if="castStaffMemo(visibleCast)" class="rk-castpop__memo">
          <div class="rk-castpop__memo-label">常時メモ</div>
          <div class="rk-castpop__memo-body">{{ castStaffMemo(visibleCast) }}</div>
        </div>
        <div v-if="castDailyMemo(visibleCast)" class="rk-castpop__memo">
          <div class="rk-castpop__memo-label">当日メモ</div>
          <div class="rk-castpop__memo-body">{{ castDailyMemo(visibleCast) }}</div>
        </div>
      </div>
    </Teleport>
  </section>
</template>
