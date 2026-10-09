<script setup>
import { onMounted, ref } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const hour = ref(5)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const notice = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getBusinessDaySettings()
    hour.value = data.business_day_boundary_hour
  } catch (e) {
    error.value = e.message || '設定を読み込めませんでした'
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const data = await api.updateBusinessDaySettings({ business_day_boundary_hour: Number(hour.value) })
    hour.value = data.business_day_boundary_hour
    notice.value = '保存しました。以後、この時刻までは前営業日のタイムラインを開きます。'
  } catch (e) {
    error.value = e.message || '保存できませんでした'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <LayoutOperator>
    <template #title>営業日・タイムライン設定</template>
    <div class="card settings-business-day">
      <div class="card-body">
        <div v-if="loading" class="text-center py-4"><div class="spinner-border text-primary"></div></div>
        <template v-else>
          <p class="text-muted">指定時刻を過ぎるまで、タイムラインの「今日」は前営業日を表示します。</p>
          <label for="business-day-boundary" class="form-label">営業日の切替時刻</label>
          <select id="business-day-boundary" v-model.number="hour" class="form-select" :disabled="saving">
            <option v-for="value in 6" :key="value - 1" :value="value - 1">{{ String(value - 1).padStart(2, '0') }}:00</option>
          </select>
          <div class="form-text">例: 05:00なら、翌朝05:00まで前日のタイムラインを表示します（29:00営業終了に対応）。</div>
          <p v-if="error" class="text-danger small mt-3 mb-0">{{ error }}</p>
          <p v-if="notice" class="text-success small mt-3 mb-0">{{ notice }}</p>
          <button class="btn btn-primary mt-3" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </template>
      </div>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.settings-business-day { max-width: 620px; }
</style>
