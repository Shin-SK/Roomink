<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import RoomCashPanel from '../../components/RoomCashPanel.vue'
import { api } from '../../api.js'
import { localBusinessDate } from '../../businessDate.js'

const route = useRoute()
const date = ref(route.query.date || '')
const dateError = ref('')
onMounted(async () => {
  if (date.value) return
  try {
    const settings = await api.getBusinessDaySettings()
    if (!date.value) date.value = localBusinessDate(new Date(), settings.business_day_boundary_hour)
  } catch {
    dateError.value = '営業日を取得できませんでした。確認する営業日を選択してください。'
  }
})
</script>

<template>
  <LayoutOperator>
    <template #title>ルーム現金</template>
    <div class="card mb-4">
      <div class="card-header"><i class="ti ti-cash-banknote"></i> ルーム現金</div>
      <div class="card-body">
        <div class="row g-2 mb-3"><div class="col-sm-6 col-md-3"><label for="room-cash-date" class="form-label small">営業日</label><input id="room-cash-date" v-model="date" type="date" class="form-control" /></div></div>
        <div v-if="dateError && !date" class="alert alert-warning">{{ dateError }}</div>
        <RoomCashPanel v-if="date" :date="date" />
      </div>
    </div>
  </LayoutOperator>
</template>
