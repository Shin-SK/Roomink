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
    <div class="d-flex flex-wrap justify-content-between align-items-end gap-3 mb-3">
      <div>
        <h1 class="h4 mb-1">ルーム現金</h1>
        <p class="text-muted small mb-0">ルームに残る現金と、セラピストへの受け渡し見込みを確認できます。</p>
      </div>
      <div><label for="room-cash-date" class="form-label small mb-1">営業日</label><input id="room-cash-date" v-model="date" type="date" class="form-control" /></div>
    </div>
    <div v-if="dateError && !date" class="alert alert-warning">{{ dateError }}</div>
    <RoomCashPanel v-if="date" :date="date" />
  </LayoutOperator>
</template>
