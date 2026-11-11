<script setup>
import { onMounted, ref } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const calls = ref([])
const selected = ref(null)
const error = ref('')
const busy = ref(false)
let selectionGeneration = 0

async function load() {
  busy.value = true
  error.value = ''
  try { calls.value = (await api.getWorkDiagnostics()).calls }
  catch (reason) { error.value = reason.message }
  finally { busy.value = false }
}
async function select(id) {
  const generation = ++selectionGeneration
  selected.value = null
  error.value = ''
  try {
    const result = await api.getWorkDiagnostics(id)
    if (generation === selectionGeneration) selected.value = result
  } catch (reason) { if (generation === selectionGeneration) error.value = reason.message }
}
function download() {
  const blob = new Blob([JSON.stringify(selected.value.replay, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'roomink-voice-replay.json'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
onMounted(load)
</script>

<template>
  <LayoutOperator>
    <template #title>着信診断</template>
    <p v-if="error" class="alert alert-danger" role="alert">{{ error }}</p>
    <button class="btn btn-outline-primary mb-3" :disabled="busy" @click="load">一覧を更新</button>
    <div class="row g-4">
      <div class="col-lg-4">
        <p v-if="!calls.length && !busy">着信記録がありません。</p>
        <div class="list-group">
          <button v-for="call in calls" :key="call.id" class="list-group-item list-group-item-action"
            :class="{ active: selected?.call_id === call.id }" @click="select(call.id)">
            {{ call.store__name }} · {{ new Date(call.created_at).toLocaleString('ja-JP') }} · {{ call.status }}
          </button>
        </div>
      </div>
      <div v-if="selected" class="col-lg-8">
        <h2 class="h5">サーバーの記録</h2>
        <ol>
          <li v-for="(event, index) in selected.server" :key="index">
            +{{ event.at_ms }}ms · {{ event.leg }} · {{ event.stage }} {{ event.details }}
          </li>
        </ol>
        <h2 class="h5">端末の記録</h2>
        <p v-for="target in selected.targets" :key="target.device">
          {{ target.device }} · {{ target.observation === 'observed' ? '記録あり' : '未確認' }}
        </p>
        <p v-if="selected.device_observation === 'unobserved'" role="status">
          端末からの記録は未確認です。Push未達・未送信・診断未対応の可能性があります。
        </p>
        <div class="table-responsive">
          <table v-if="selected.devices.length" class="table">
            <thead><tr><th>時差</th><th>端末</th><th>段階</th><th>当時の状態</th></tr></thead>
            <tbody><tr v-for="(event, index) in selected.devices" :key="index">
              <td>{{ event.at_ms }}ms</td><td>{{ event.device }}</td><td>{{ event.stage }}</td>
              <td>{{ event.snapshot }}</td>
            </tr></tbody>
          </table>
        </div>
        <p>端末の時刻とサーバーの受信時刻には差が出る場合があります。</p>
        <button class="btn btn-primary" @click="download">検証データを保存</button>
        <p class="mt-2">検証用Workの「着信の再生」にJSONを貼り付け、対象端末の記録を選びます。</p>
      </div>
    </div>
  </LayoutOperator>
</template>
