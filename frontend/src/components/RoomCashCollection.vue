<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api.js'
import { roomCashYen as yen } from '../roomCashDisplay.js'

const props = defineProps({ row: Object, date: String, disabled: Boolean })
const emit = defineEmits(['changed', 'busy'])
const amount = ref('')
const memo = ref('')
const saving = ref(false)
const error = ref('')
const success = ref('')
const conflict = ref(false)
let requestId = null
let signature = ''
const available = computed(() => props.row.can_count && props.row.balance_known && !props.row.requires_confirmation && props.row.expected_cash_amount > 0)
const valid = computed(() => /^\d+$/.test(String(amount.value)) && Number.isSafeInteger(Number(amount.value)) && Number(amount.value) > 0 && Number(amount.value) <= props.row.expected_cash_amount)
const after = computed(() => valid.value ? props.row.expected_cash_amount - Number(amount.value) : null)
watch(() => props.row.revision, () => { conflict.value = false })
function fillAll() {
  if (!available.value || saving.value || props.disabled) return
  amount.value = String(props.row.expected_cash_amount)
  success.value = ''
}
function datetime(value) {
  return new Intl.DateTimeFormat('ja-JP', { timeZone: 'Asia/Tokyo', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}
async function submit(entry = null) {
  if (saving.value || props.disabled || conflict.value || !props.row.can_count || (!entry && (!available.value || !valid.value))) return
  const value = entry ? entry.amount : Number(amount.value)
  if (!window.confirm(entry ? `${yen(value)}の回収を取り消し、金庫の想定残高に戻します。実際の現金も戻しましたか？` : `${props.row.room_name}から${yen(value)}を回収します。登録後の想定残高は${yen(after.value)}です。よろしいですか？`)) return
  const nextSignature = JSON.stringify([props.date, props.row.room, props.row.revision, value, memo.value, entry?.id])
  if (signature !== nextSignature || !requestId) { requestId = crypto.randomUUID(); signature = nextSignature }
  saving.value = true; emit('busy', true); error.value = ''; success.value = ''
  try {
    await api.saveRoomCashCount({ date: props.date, room: props.row.room, expected_revision: props.row.revision,
      operation: entry ? 'cancel_collection' : 'collect', collection_id: entry?.id,
      amount: value, memo: memo.value, request_id: requestId })
    if (!entry) { amount.value = ''; memo.value = '' }
    requestId = null
    success.value = entry ? '回収を取り消しました。' : `${yen(value)}の回収を登録しました。`
    emit('changed')
  } catch (e) {
    conflict.value = e.status === 409
    error.value = conflict.value ? '残高が更新されました。「更新」で最新の残高を確認してください。入力内容は残しています。' : e.message || '登録できませんでした。'
  } finally { saving.value = false; emit('busy', false) }
}
</script>

<template>
  <section class="cash-collection mt-3 p-3 border rounded-3" aria-label="金庫からの回収">
    <div class="d-flex align-items-center gap-2 mb-1"><i class="ti ti-cash-banknote"></i><h3 class="h6 mb-0">金庫から回収する</h3></div>
    <p class="small text-muted mb-3">回収した金額を登録すると、金庫の想定残高から差し引かれます。</p>
    <div class="collection-grid">
    <div>
    <form v-if="row.can_count" @submit.prevent="submit()">
      <div class="collection-fields">
      <div>
      <label :for="`collection-amount-${row.room}`" class="form-label small">回収する金額</label>
      <div class="d-flex gap-2 align-items-center">
        <div class="input-group"><input :id="`collection-amount-${row.room}`" v-model="amount" type="number" min="1" step="1" :max="row.expected_cash_amount ?? 0" class="form-control" placeholder="金額を入力" :disabled="!available || saving || disabled" /><span class="input-group-text">円</span></div>
        <button type="button" class="btn btn-outline-primary text-nowrap" :disabled="!available || saving || disabled || conflict" @click="fillAll">全額回収</button>
      </div>
      <p class="form-text mt-1 mb-0">「全額回収」は金額の入力のみです。</p>
      <p v-if="amount !== '' && !valid" class="small text-danger" role="alert">回収額は1円以上、想定残高以下の整数で入力してください。</p>
      </div>
      <div>
      <label :for="`collection-memo-${row.room}`" class="form-label small">備考（任意）</label>
      <input :id="`collection-memo-${row.room}`" v-model="memo" maxlength="1000" class="form-control" placeholder="回収内容など" :disabled="saving || disabled" />
      </div>
      </div>
      <div class="collection-submit mt-3">
      <div class="small"><div class="text-muted">回収後の想定残高</div><strong class="fs-5">{{ after === null ? '—' : yen(after) }}</strong></div>
      <button class="btn btn-primary" type="submit" :disabled="!available || !valid || saving || disabled || conflict">{{ saving ? '登録中…' : '回収を登録' }}</button>
      </div>
      <p v-if="!available" class="small text-muted mt-2 mb-0">{{ !row.balance_known || row.requires_confirmation ? '実際の現金を確認・記録してから回収できます。' : '回収できる残高はありません。' }}</p>
    </form>
    <p v-else class="small text-muted mb-0">回収の登録・取消は現在の営業日で行ってください。</p>
    <div v-if="error" class="alert alert-danger small mt-2 mb-0" role="alert">{{ error }}</div>
    <p v-if="success" class="text-success small mt-2 mb-0" role="status">{{ success }}</p>
    </div>
    <details class="collection-history small" :open="!!row.collections?.length">
      <summary>回収履歴（{{ row.collections?.length || 0 }}件）</summary>
      <p v-if="!row.collections?.length" class="text-muted mt-2 mb-0">回収の記録はまだありません。</p>
      <div v-for="entry in row.collections || []" :key="entry.id" class="border-bottom py-2">
        <div class="d-flex align-items-center justify-content-between gap-2"><strong :class="entry.cancelled_at ? 'text-muted text-decoration-line-through' : ''">{{ yen(entry.amount) }}</strong><span v-if="entry.cancelled_at" class="badge bg-secondary">取消済み</span><button v-else-if="row.can_count" class="btn btn-sm btn-outline-secondary" :disabled="saving || disabled || conflict" @click="submit(entry)">回収を取消</button></div>
        <div class="text-muted mt-1">{{ datetime(entry.created_at) }} · {{ entry.recorded_by }}</div>
        <div v-if="entry.memo" class="mt-1 text-break">{{ entry.memo }}</div>
        <div v-if="entry.cancelled_at" class="text-muted mt-1">{{ datetime(entry.cancelled_at) }} · {{ entry.cancelled_by }}が取消</div>
      </div>
    </details>
    </div>
  </section>
</template>

<style scoped>
.cash-collection { background: var(--bs-tertiary-bg, #f8f9fa); }
.collection-grid { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 1.5rem; align-items: start; }
.collection-fields { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr); gap: 1rem; }
.collection-fields .input-group { min-width: 0; }
.collection-submit { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding-top: .75rem; border-top: 1px solid var(--bs-border-color); }
.collection-submit .btn { min-width: 9rem; }
.collection-history { border-left: 1px solid var(--bs-border-color); padding-left: 1.5rem; }
@media (max-width: 1199.98px) {
  .collection-fields { grid-template-columns: minmax(0, 1fr); gap: .75rem; }
}
@media (max-width: 767.98px) {
  .collection-grid { grid-template-columns: minmax(0, 1fr); gap: 1rem; }
  .collection-history { border-left: 0; border-top: 1px solid var(--bs-border-color); padding: .75rem 0 0; }
}
</style>
