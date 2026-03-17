<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import TimelineGrid from '../../components/TimelineGrid.vue'
import { api } from '../../api.js'

const router = useRouter()
const selectedDate = ref(today())
const rooms = ref([])
const orders = ref([])
const kpi = ref({ total_orders: 0, confirmed: 0, requested: 0, estimated_sales: 0 })
const loading = ref(true)
const toolbarOpen = ref(false)

function today() {
  return new Date().toISOString().slice(0, 10)
}

function tomorrow() {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return d.toISOString().slice(0, 10)
}

// rooms → casts 形式に変換（TimelineGrid 流用）
const castsAdapter = computed(() =>
  rooms.value.map(r => ({
    id: r.id,
    name: r.name,
    avatar_url: '',
    shifts: [],
  }))
)

// orders の room_id → cast_id にリネーム（TimelineGrid が cast_id で列を決めるため）
const ordersAdapter = computed(() =>
  orders.value.map(o => ({
    id: o.id,
    cast_id: o.room_id,
    customer_label: `${o.cast_name}`,
    course_name: o.course_name,
    start: o.start,
    end: o.end,
    status: o.status,
    options: o.options,
    is_unconfirmed: o.is_unconfirmed,
  }))
)

async function fetchSchedule() {
  loading.value = true
  try {
    const data = await api.getRoomSchedule(selectedDate.value)
    rooms.value = data.rooms
    orders.value = data.orders
    kpi.value = data.kpi
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function onBlockClick(order) {
  router.push(`/op/orders/${order.id}`)
}

function setToday() {
  selectedDate.value = today()
}

function setTomorrow() {
  selectedDate.value = tomorrow()
}

function toggleToolbar(e) {
  e.stopPropagation()
  toolbarOpen.value = !toolbarOpen.value
}

watch(selectedDate, fetchSchedule)
onMounted(fetchSchedule)
</script>

<template>
  <LayoutOperator>
    <template #title>ルーム タイムライン</template>

    <div class="setting-area position-absolute">
      <button class="toolbar-toggle btn btn-sm border-0 shadow-sm bg-white" @click="toggleToolbar">
        <i class="ti ti-adjustments-horizontal" style="font-size: 24px;"></i>
      </button>
      <div v-show="toolbarOpen" class="rk-schedule__toolbar">
        <div class="rk-toolbar shadow-sm p-3 bg-white rounded">
          <div class="row g-2">
            <div class="col-6">
              <button
                class="btn btn-sm w-100"
                :class="selectedDate === today() ? 'btn-primary' : 'btn-outline-secondary'"
                @click="setToday"
              >今日</button>
            </div>
            <div class="col-6">
              <button
                class="btn btn-sm w-100"
                :class="selectedDate === tomorrow() ? 'btn-primary' : 'btn-outline-secondary'"
                @click="setTomorrow"
              >明日</button>
            </div>
            <div class="col-12">
              <input
                type="date"
                class="form-control form-control-sm"
                v-model="selectedDate"
              >
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else class="position-relative">
      <TimelineGrid
        :casts="castsAdapter"
        :orders="ordersAdapter"
        @block-click="onBlockClick"
      />
      <div v-if="rooms.length === 0" class="position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center" style="pointer-events: none;">
        <span class="text-muted bg-white px-3 py-2 rounded shadow-sm">ルームが登録されていません</span>
      </div>
    </div>
  </LayoutOperator>
</template>
