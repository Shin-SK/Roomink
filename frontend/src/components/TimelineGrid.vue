<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'

const props = defineProps({
  casts: { type: Array, default: () => [] },
  orders: { type: Array, default: () => [] },
  startHour: { type: Number, default: 12 },
  endHour: { type: Number, default: 20 },
})

const emit = defineEmits(['block-click'])

const gridRef = ref(null)

const hours = computed(() => {
  const arr = []
  for (let h = props.startHour; h <= props.endHour; h++) {
    arr.push(`${String(h).padStart(2, '0')}:00`)
  }
  return arr
})

const totalRows = computed(() => props.endHour - props.startHour + 1)

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
  const t = `${formatTime(order.start)}\u2013${formatTime(order.end)}`
  if (order.status === 'REQUESTED') return `申請中 / ${t}`
  return t
}

function layoutBlocks() {
  if (!gridRef.value) return
  const grid = gridRef.value
  const style = getComputedStyle(document.documentElement)
  const colW = parseFloat(style.getPropertyValue('--rk-col-w')) || 120
  const hourH = parseFloat(style.getPropertyValue('--rk-row-hour-h')) || 80

  const startMin = props.startHour * 60

  grid.style.minWidth = `${colW * props.casts.length}px`
  grid.style.height = `${hourH * totalRows.value}px`

  grid.querySelectorAll('.rk-block').forEach(el => {
    const col = Number(el.dataset.col || 0)
    const s = parseTimeToMin(el.dataset.start)
    const e = parseTimeToMin(el.dataset.end)

    const top = ((s - startMin) / 60) * hourH
    const height = Math.max(24, ((e - s) / 60) * hourH)
    const paddingX = 8
    const left = col * colW + paddingX
    const width = colW - paddingX * 2

    el.style.top = `${top + 6}px`
    el.style.left = `${left}px`
    el.style.width = `${width}px`
    el.style.height = `${height - 12}px`
  })
}

function onResize() { layoutBlocks() }

onMounted(() => {
  nextTick(layoutBlocks)
  window.addEventListener('resize', onResize)
})
// props変更時のみ再計算（onUpdated は毎レンダーで走り重い）
watch(() => [props.casts, props.orders], () => nextTick(layoutBlocks))
onBeforeUnmount(() => window.removeEventListener('resize', onResize))
</script>

<template>
  <section class="rk-schedule">
    <div class="rk-sheet-scroll">
      <div
        class="rk-sheet"
        :data-cols="casts.length"
        :data-start="`${String(startHour).padStart(2,'0')}:00`"
        :data-end="`${String(endHour).padStart(2,'0')}:00`"
      >
        <!-- 左上の角（固定） -->
        <div class="rk-corner"></div>

        <!-- 上：キャストヘッダー（固定） -->
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
              class="rk-avatar-img d-flex align-items-center justify-content-center bg-light"
              style="font-size:18px;color:var(--rk-primary)"
            >
              <i class="ti ti-user"></i>
            </div>
            <div class="rk-name">{{ cast.name }}</div>
          </div>
        </div>

        <!-- 左：時間列（固定） -->
        <div class="rk-timecol">
          <div v-for="hour in hours" :key="hour" class="rk-time">{{ hour }}</div>
        </div>

        <!-- 本体グリッド（縦横スクロール） -->
        <div ref="gridRef" class="rk-grid" :data-cols="casts.length">
          <a
            v-for="order in orders"
            :key="order.id"
            class="rk-block"
            :class="statusClass(order)"
            href="#"
            :data-col="castIndexMap[order.cast_id] ?? 0"
            :data-start="formatTime(order.start)"
            :data-end="formatTime(order.end)"
            @click.prevent="emit('block-click', order)"
          >
            <div class="rk-block__title">{{ order.customer_label }} ({{ order.course_name }})</div>
            <div class="rk-block__meta">{{ blockMeta(order) }}</div>
          </a>
        </div>
      </div>
    </div>
  </section>
</template>
