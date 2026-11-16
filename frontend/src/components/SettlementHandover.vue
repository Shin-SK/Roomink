<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'

const props = defineProps({ row: Object, date: String, locked: Boolean })
const emit = defineEmits(['saved'])
const route = useRoute()
const opened = ref(false)
const amount = ref('')
const reason = ref('')
const busy = ref(false)
const error = ref('')
const needsRefresh = ref(false)
let pending = null
const yen = n => n == null ? '未確認' : `${Number(n).toLocaleString('ja-JP')}円`
const valid = computed(() => /^\d+$/.test(String(amount.value)) && Number.isSafeInteger(Number(amount.value))
  && Number(amount.value) <= Math.max(0, props.row.receivable_amount - props.row.office_cash_paid_amount)
  && !!reason.value.trim() && reason.value.trim().length <= 500)
watch(() => `${props.date}:${props.row.cast_id}`, () => {
  opened.value = false; amount.value = ''; reason.value = ''; error.value = ''; needsRefresh.value = false; pending = null
})
watch(() => props.row.settlement_source_revision, () => { needsRefresh.value = false })

async function save() {
  if (busy.value || !valid.value || needsRefresh.value || props.locked || !props.row.can_register_by_store) return
  const body = { cast: props.row.cast_id, date: props.date, room_cash_taken_amount: Number(amount.value),
    reason: reason.value.trim(), source_revision: props.row.settlement_source_revision }
  const signature = JSON.stringify(body)
  if (!pending || pending.signature !== signature) pending = { signature, id: crypto.randomUUID() }
  busy.value = true; error.value = ''
  try {
    await api.registerCheckoutByStore({ ...body, request_id: pending.id })
    pending = null; opened.value = false
    emit('saved')
  } catch (e) {
    error.value = e.message || '登録できませんでした。'
    needsRefresh.value = e.status === 409
  } finally { busy.value = false }
}
</script>

<template>
  <section class="border rounded p-3 mb-3" :aria-label="`${row.cast_name}さんの受け取り状況`">
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <strong>{{ row.cast_name }}</strong>
      <span class="badge" :class="row.cash_handover_recorded ? 'bg-success' : 'bg-warning text-dark'">
        {{ row.cash_handover_recorded ? (row.registration_source === 'STORE' ? '店舗で登録済み' : '本人が提出済み') : '受取額が未確認' }}
      </span>
    </div>
    <div v-if="row.unrecorded_prior_dates?.length" class="alert alert-warning small py-2">
      過去に精算が未登録の日があります。その日の分は下の金額に入っていません。
      <details class="mt-1">
        <summary>未登録の日を確認（{{ row.unrecorded_prior_dates.length }}日）</summary>
        <div class="d-flex flex-wrap gap-2 mt-1">
          <RouterLink v-for="day in row.unrecorded_prior_dates" :key="day"
            :to="{ path: '/op/daily-settlement', query: { ...route.query, date: day } }">{{ day }}を確認</RouterLink>
        </div>
      </details>
    </div>
    <dl class="row g-2 small mb-2">
      <div class="col-6 col-md-3"><dt class="fw-normal text-muted">前回までの未受取</dt><dd class="fw-bold mb-0">{{ yen(row.carryover_opening_amount) }}</dd></div>
      <div class="col-6 col-md-3"><dt class="fw-normal text-muted">この日の報酬</dt><dd class="fw-bold mb-0">{{ yen(row.settlement_compensation_amount) }}</dd></div>
      <div class="col-6 col-md-3"><dt class="fw-normal text-muted">ルームで受取済み</dt><dd class="fw-bold mb-0">{{ yen(row.room_cash_taken_amount) }}</dd></div>
      <div class="col-6 col-md-3"><dt class="fw-normal text-muted">事務所で受取済み</dt><dd class="fw-bold mb-0">{{ yen(row.office_cash_paid_amount) }}</dd></div>
    </dl>
    <div class="bg-light rounded p-2 d-flex flex-wrap justify-content-between align-items-center gap-2">
      <span>{{ row.cash_handover_recorded ? 'あと受け取れる金額' : '受取額を確認する前の見込み' }}{{ row.unrecorded_prior_dates?.length ? '（未登録の日を除く）' : '' }}</span>
      <strong :class="row.remaining_receivable_amount < 0 ? 'text-danger' : 'text-primary'">{{ yen(row.remaining_receivable_amount) }}</strong>
    </div>
    <p class="small text-muted mt-2 mb-0">前回までの未受取＋この日の報酬−ルーム・事務所で受取済みの額。マイナスは受け取り超過です。ポイントはこの報酬・繰越には含みません。</p>
    <template v-if="!locked && row.can_register_by_store">
      <button type="button" class="btn btn-outline-primary btn-sm mt-3" :disabled="busy" @click="opened = !opened">{{ opened ? '入力を閉じる' : '店舗で受取額を登録' }}</button>
      <form v-if="opened" class="border-top pt-3 mt-3" @submit.prevent="save">
        <p class="small">{{ date }}分として、セラピストさんが実際にルームで受け取った額を登録します。0円の場合も確認して入力してください。本人の代わりにチェックリストへ回答する操作ではありません。</p>
        <label :for="`store-taken-${row.cast_id}`" class="form-label">実際にルームで受け取った金額</label>
        <input :id="`store-taken-${row.cast_id}`" v-model="amount" type="number" min="0" step="1" required
          class="form-control mb-3" placeholder="確認した金額を入力" :disabled="busy" />
        <p class="small text-muted">受取可能額：{{ yen(Math.max(0, row.receivable_amount - row.office_cash_paid_amount)) }}。0円以上の整数を入力してください。</p>
        <label :for="`store-reason-${row.cast_id}`" class="form-label">金額を確認した内容</label>
        <textarea :id="`store-reason-${row.cast_id}`" v-model="reason" required maxlength="500" rows="2"
          class="form-control mb-3" placeholder="本人に確認した内容など" :disabled="busy"></textarea>
        <p class="small">登録すると、この金額を差し引いた残りが次回へ引き継がれ、封筒の受領確認もできるようになります。</p>
        <div v-if="error" class="alert alert-danger small" role="alert">{{ error }}</div>
        <button v-if="needsRefresh" type="button" class="btn btn-outline-secondary btn-sm me-2" @click="emit('saved')">最新内容を確認</button>
        <button type="submit" class="btn btn-primary" :disabled="busy || !valid || needsRefresh">{{ busy ? '登録中…' : '確認した受取額で登録する' }}</button>
      </form>
    </template>
  </section>
</template>
