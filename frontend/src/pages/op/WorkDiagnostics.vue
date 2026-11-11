<script setup>
import { onMounted, ref } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const calls = ref([])
const selected = ref(null)
const error = ref('')
const busy = ref(false)
let selectionGeneration = 0
const stageLabels = {
  inbound_received: 'Roominkが着信を受信', work_route_requested: 'Workへの呼出を指示',
  work_target_requested: '受信端末を選択', work_progress: 'Twilioの通話結果',
  inbound_status: '元の着信の状態', sip_route_requested: 'SIP端末への呼出を指示',
  sip_progress: 'SIP端末の呼出結果', dial_result: '呼出の最終結果',
  push_received: 'iPhoneがPushを受信', callkit_requested: 'iOSへ着信表示を依頼',
  callkit_reported: 'iOSが着信表示の依頼を受付', callkit_failed: 'iOSへの着信表示依頼でエラー',
  registering: '着信登録を開始', registered: '着信登録が成功',
  registration_failed: '着信登録が失敗', invite: 'アプリが着信を処理',
  accepted: '応答操作', rejected: '拒否', cancelled: '着信をキャンセル',
  connecting: '通話を接続中', connected: '通話が接続', reconnecting: '通話を再接続中',
  ended: '通話を終了', error: '通話処理でエラー', app_state: 'アプリの状態変更',
}

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
        <p>この着信はRoominkに保存されています。</p>
        <ol>
          <li v-for="(event, index) in selected.server" :key="index">
            +{{ event.at_ms }}ms · {{ event.leg }} · {{ stageLabels[event.stage] || event.stage }} {{ event.details }}
          </li>
        </ol>
        <h2 class="h5">端末の記録</h2>
        <p v-for="target in selected.targets" :key="target.device">
          {{ target.device }} · {{ target.last_stage ? '最後に確認できた段階 — ' + (stageLabels[target.last_stage] || target.last_stage) : '端末からの記録は未確認' }}
        </p>
        <p v-if="selected.device_observation === 'unobserved'" role="status">
          端末からの記録は未確認です。Push未達・未送信・診断未対応の可能性があります。
        </p>
        <div class="table-responsive">
          <table v-if="selected.devices.length" class="table">
            <thead><tr><th>時差</th><th>端末</th><th>段階</th><th>当時の状態</th></tr></thead>
            <tbody><tr v-for="(event, index) in selected.devices" :key="index">
              <td>{{ event.at_ms }}ms</td><td>{{ event.device }}</td>
              <td>{{ stageLabels[event.stage] || event.stage }}
                <small v-if="event.correlation === 'nearby'" class="d-block">着信前後の参考記録</small>
              </td>
              <td>
                <div>{{ event.snapshot.model }} · iOS {{ event.snapshot.os }} · Work {{ event.snapshot.app_version }} ({{ event.snapshot.build }})</div>
                <div>{{ event.snapshot.app_state }} · {{ event.snapshot.network }}</div>
                <div v-if="event.snapshot.error_code !== undefined">エラーコード {{ event.snapshot.error_code }}</div>
                <details><summary>状態の詳細</summary><pre>{{ event.snapshot }}</pre></details>
              </td>
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
