<script setup>
import { ref, watch } from 'vue'
import { api } from '../api.js'

const props = defineProps({ entry: Object })
const emit = defineEmits(['saved'])
const actual = ref('')
const memo = ref('')
const error = ref('')
const busy = ref(false)
const conflict = ref(false)
let pending = null
const yen = n => n == null ? '—' : `${Number(n).toLocaleString()}円`
const dt = value => value ? new Date(value).toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' }) : ''
function toggle(event) {
  const checked = event.target.checked
  event.target.checked = props.entry.received && !props.entry.needs_reconfirmation
  save(checked ? 'receive' : 'clear', true)
}
watch(() => props.entry?.checkout, () => {
  actual.value = props.entry?.actual_amount == null ? '' : String(props.entry.actual_amount)
  memo.value = props.entry?.memo || ''
  error.value = ''; pending = null
}, { immediate: true })
watch(() => [props.entry?.source_revision, props.entry?.version], () => { conflict.value = false })

async function save(action, matching = false) {
  if (busy.value || conflict.value || !props.entry) return
  const entry = props.entry
  let amount = matching ? (entry.received ? entry.actual_amount : entry.expected_amount) : actual.value
  if (action === 'receive' && (amount === '' || !/^\d+$/.test(String(amount)) || !Number.isSafeInteger(Number(amount)))) {
    error.value = '実際の受領額を0以上の整数で入力してください。'; return
  }
  const content = { checkout: entry.checkout, action, actual_amount: action === 'receive' ? Number(amount) : null,
    memo: memo.value, version: entry.version, source_revision: entry.source_revision }
  const signature = JSON.stringify(content)
  if (!pending || pending.signature !== signature) pending = { signature, id: crypto.randomUUID() }
  busy.value = true; error.value = ''
  try {
    const saved = await api.saveEnvelopeReceipt({ ...content, request_id: pending.id })
    actual.value = saved.actual_amount == null ? '' : String(saved.actual_amount)
    pending = null
    emit('saved')
  } catch (e) {
    conflict.value = e.status === 409
    error.value = e.message || '保存できませんでした。'
  } finally { busy.value = false }
}
</script>

<template>
  <div class="envelope-receipt">
    <div v-if="!entry" class="text-muted small">精算未提出</div>
    <template v-else>
      <div class="fw-bold">{{ entry.expected_amount == null ? '提出時記録なし' : `投函予定 ${yen(entry.expected_amount)}` }}</div>
      <div v-if="entry.expected_amount == null" class="small text-muted">旧提出のため、当時の投函額は確認できません。</div>
      <div v-else-if="entry.expected_amount === 0" class="small text-muted">投函不要{{ entry.withdrawal_amount ? `（不足分受取 ${yen(entry.withdrawal_amount)}）` : '' }}</div>
      <div v-if="entry.returned" class="small text-warning-emphasis">差戻し中・再提出待ち</div>
      <div v-if="entry.changed_since_submission" class="small text-warning-emphasis">提出後の訂正あり・現在の計算 {{ yen(entry.current_amount) }}<br>提出時の金額は保持しています。</div>
      <div v-if="entry.needs_reconfirmation" class="badge bg-warning text-dark">要再確認</div>
      <div v-if="entry.received" class="small mt-1">
        受領 {{ yen(entry.actual_amount) }}
        <span :class="entry.difference_amount ? 'text-danger fw-bold' : 'text-muted'">（{{ entry.difference_amount == null ? '予定額不明・差額未判定' : `差額 ${yen(entry.difference_amount)}` }}）</span>
        <div>{{ entry.reviewed_by }} / {{ dt(entry.reviewed_at) }}</div>
      </div>
      <template v-if="entry.can_receive || entry.received">
        <label class="d-flex gap-2 align-items-center my-2">
          <input type="checkbox" class="form-check-input mt-0" :checked="entry.received && !entry.needs_reconfirmation" :disabled="busy || conflict || entry.expected_amount == null || (!entry.can_receive && !entry.received)" @change="toggle">
          <span>受領済み{{ entry.needs_reconfirmation ? '（再確認）' : '' }}</span>
        </label>
        <label class="small d-block">備考・解除理由
          <textarea v-model="memo" class="form-control form-control-sm" rows="2" maxlength="1000" :disabled="busy" placeholder="差額・訂正の確認内容など"></textarea>
        </label>
        <details class="mt-2">
          <summary class="small">金額に相違がある場合・備考を更新</summary>
          <label class="small d-block mt-2">実際の受領額
            <input v-model="actual" type="number" min="0" step="1" class="form-control form-control-sm" :disabled="busy">
          </label>
          <button type="button" class="btn btn-outline-primary btn-sm mt-2" :disabled="busy || conflict || !entry.can_receive" @click="save('receive')">{{ busy ? '保存中…' : '受領内容を保存' }}</button>
        </details>
        <button v-if="entry.received" type="button" class="btn btn-outline-secondary btn-sm mt-2" :disabled="busy || conflict" @click="save('clear')">理由を記入して確認解除</button>
      </template>
      <div v-if="error" class="alert alert-danger small mt-2 mb-0" role="alert">{{ error }}</div>
      <button v-if="conflict" type="button" class="btn btn-outline-secondary btn-sm mt-1" @click="emit('saved')">最新内容を確認（入力は保持）</button>
      <details v-if="entry.history.length" class="small mt-2">
        <summary>確認履歴（最新{{ entry.history.length }}件）</summary>
        <div v-for="item in entry.history" :key="item.id" class="border-top py-2">
          {{ item.after.received ? '受領確認' : '確認解除' }} / {{ item.recorded_by }}<br>{{ dt(item.created_at) }}<br>
          {{ yen(item.after.actual_amount) }} / {{ item.after.memo || '備考なし' }}
        </div>
      </details>
    </template>
  </div>
</template>

<style scoped>
.envelope-receipt { min-width: 260px; max-width: 330px; white-space: normal; }
.envelope-receipt textarea { min-width: 230px; }
</style>
