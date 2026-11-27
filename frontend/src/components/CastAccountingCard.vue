<script setup>
import { computed, ref } from 'vue'
import { api } from '../api.js'
const props = defineProps({ row: Object, date: String, entry: Object })
const emit = defineEmits(['saved'])
const editing = ref(false)
const saving = ref(false)
const error = ref('')
const collected = ref('')
const unpaid = ref('')
const memo = ref('')
const version = ref(0)
const requestId = ref('')
const money = n => n == null ? '未確認' : `¥${Number(n).toLocaleString('ja-JP')}`
const lastUnpaid = computed(() => props.entry ? props.entry.latest_unpaid : props.row.confirmed_unpaid)
function open() {
  collected.value = props.entry?.collected_amount ?? ''
  unpaid.value = props.entry?.unpaid_amount ?? ''
  memo.value = props.entry?.memo || ''
  version.value = props.entry?.version || 0
  requestId.value = ''
  error.value = ''
  editing.value = true
}
async function save() {
  if (saving.value) return
  const valid = n => n === '' || (Number.isSafeInteger(n) && n >= 0 && n <= 2147483647)
  if (!valid(collected.value) || !valid(unpaid.value) || !memo.value.trim()) {
    error.value = '金額は0円以上の整数、未確認なら空欄にしてください。確認内容・変更理由も入力してください。'
    return
  }
  saving.value = true
  error.value = ''
  // Reuse only for an unchanged retry; edits get a new request ID.
  const payload = { cast: props.row.cast_id, date: props.date, version: version.value,
    collected_amount: collected.value === '' ? null : collected.value,
    unpaid_amount: unpaid.value === '' ? null : unpaid.value, memo: memo.value.trim() }
  const signature = JSON.stringify(payload)
  if (requestId.value.signature !== signature) requestId.value = { signature, id: crypto.randomUUID() }
  try {
    await api.saveCastAccounting({ ...payload, request_id: requestId.value.id })
    editing.value = false
    emit('saved')
  } catch (e) { error.value = e.message }
  finally { saving.value = false }
}
async function refreshKeepingInput() {
  saving.value = true
  try {
    const data = await api.getCastAccounting(props.date)
    version.value = data.rows.find(row => row.cast_id === props.row.cast_id)?.version || 0
    requestId.value = ''
    error.value = '最新の保存内容を取得しました。表示された金額と入力内容を確認してから保存してください。'
    emit('saved')
  } catch (e) { error.value = e.message }
  finally { saving.value = false }
}
</script>

<template>
  <div class="border rounded p-3 mb-3">
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <strong>{{ row.cast_name }}</strong>
      <span class="badge" :class="entry?.collected_amount == null ? 'bg-warning text-dark' : 'bg-success'">{{ entry?.collected_amount == null ? '回収金額は未確認' : '回収金額を確認済み' }}</span>
    </div>
    <div class="row g-3 mb-3">
      <div class="col-6"><div class="small text-muted">この営業日の回収金額</div><strong>{{ money(entry?.collected_amount) }}</strong></div>
      <div class="col-6"><div class="small text-muted">確認済みの未受取残額</div><strong>{{ money(lastUnpaid?.amount) }}</strong><div v-if="lastUnpaid" class="small text-muted">{{ lastUnpaid.date }} 時点</div></div>
    </div>
    <div v-if="entry?.memo" class="small mb-2" style="white-space: pre-wrap">{{ entry.memo }}</div>
    <div v-if="entry?.reviewed_at" class="small text-muted mb-2">記録者 {{ entry.reviewed_by }}・{{ new Date(entry.reviewed_at).toLocaleString('ja-JP') }}</div>
    <button v-if="!editing" type="button" class="btn btn-outline-primary btn-sm" @click="open">経理の確認内容を記録</button>
    <form v-else @submit.prevent="save">
      <div v-if="error" class="alert alert-danger small" role="alert">{{ error }}</div>
      <div class="row g-3">
        <div class="col-sm-6"><label :for="`collected-${row.cast_id}`" class="form-label small">実際に回収できた金額（円）</label><input :id="`collected-${row.cast_id}`" v-model.number="collected" type="number" min="0" step="1" class="form-control" placeholder="未確認なら空欄" :disabled="saving"></div>
        <div class="col-sm-6"><label :for="`unpaid-${row.cast_id}`" class="form-label small">{{ date }} 時点の未受取残額（円）</label><input :id="`unpaid-${row.cast_id}`" v-model.number="unpaid" type="number" min="0" step="1" class="form-control" placeholder="未確認なら空欄" :disabled="saving"></div>
      </div>
      <p class="small text-muted mt-2">未受取額は今回増えた額ではなく、この時点でまだ渡していない合計額です。0円は「残額なしと確認済み」、空欄は「未確認」です。回収金額から自動計算しません。</p>
      <label :for="`accounting-memo-${row.cast_id}`" class="form-label small">確認内容・変更理由</label>
      <textarea :id="`accounting-memo-${row.cast_id}`" v-model="memo" class="form-control mb-2" rows="3" maxlength="1000" required :disabled="saving" placeholder="LINEで確認した内容など"></textarea>
      <button type="submit" class="btn btn-primary btn-sm me-2" :disabled="saving">{{ saving ? '保存中…' : '確認内容を保存' }}</button>
      <button type="button" class="btn btn-outline-secondary btn-sm" :disabled="saving" @click="editing = false">閉じる</button>
      <button v-if="error" type="button" class="btn btn-link btn-sm" :disabled="saving" @click="refreshKeepingInput">入力を残して最新内容を取得</button>
    </form>
    <details v-if="entry?.history?.length" class="small mt-3"><summary>変更履歴（{{ entry.history.length }}件）</summary>
      <div v-for="(event, i) in entry.history" :key="i" class="border-top py-2">
        <div>回収 {{ money(event.before.collected_amount) }} → {{ money(event.after.collected_amount) }}</div>
        <div>未受取 {{ money(event.before.unpaid_amount) }} → {{ money(event.after.unpaid_amount) }}</div>
        <div style="white-space: pre-wrap">{{ event.after.memo }}</div>
        <div class="text-muted">{{ event.recorded_by }}・{{ new Date(event.recorded_at).toLocaleString('ja-JP') }}</div>
      </div>
    </details>
  </div>
</template>
