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

const hours = computed(() => {
  const arr = []
  for (let h = props.startHour; h <= props.endHour; h++) {
    arr.push(`${String(h).padStart(2, '0')}:00`)
  }
  return arr
})

const totalCols = computed(() => props.endHour - props.startHour + 1)

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

  const startMin = props.startHour * 60

  grid.style.width = `${hourW * totalCols.value}px`
  grid.style.height = `${rowH * props.casts.length}px`

  grid.querySelectorAll('.rk-block, .rk-interval').forEach(el => {
    const row = Number(el.dataset.row || 0)
    const s = parseTimeToMin(el.dataset.start)
    const e = parseTimeToMin(el.dataset.end)

    const padY = 6
    const left = ((s - startMin) / 60) * hourW
    const width = Math.max(12, ((e - s) / 60) * hourW)
    const top = row * rowH + padY
    const height = Math.max(12, rowH - padY * 2)

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
  const totalMin = props.startHour * 60 + minutesFromStart
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
})
watch(() => [props.casts, props.orders], () => nextTick(layoutBlocks))
onBeforeUnmount(() => window.removeEventListener('resize', onResize))
</script>

<template>
  <section class="rk-schedule">
    <div class="rk-sheet-scroll">
      <div
        class="rk-sheet"
        :data-rows="casts.length"
        :data-start="`${String(startHour).padStart(2,'0')}:00`"
        :data-end="`${String(endHour).padStart(2,'0')}:00`"
      >
        <!-- 左上の角（固定） -->
        <div class="rk-corner"></div>

        <!-- 上：時間ヘッダー（横） -->
        <div class="rk-timecol">
          <div v-for="hour in hours" :key="hour" class="rk-time">{{ hour }}</div>
        </div>

        <!-- 左：キャスト/ルーム列（縦） -->
        <div class="rk-casthead">
          <div v-for="cast in casts" :key="cast.id" class="rk-castcell">
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
              <div class="rk-name">{{ cast.name }}</div>
              <div v-if="castRoomLabel(cast)" class="rk-room">{{ castRoomLabel(cast) }}</div>
            </div>
          </div>
        </div>

        <!-- 本体グリッド -->
        <div ref="gridRef" class="rk-grid" :data-rows="casts.length" @click="onGridClick">
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
  </section>
</template>
