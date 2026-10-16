<script setup>
import { ref, watch } from 'vue'
import { api } from '../api.js'
import { roomCashYen as yen, validCashCount, roomCashDrafts } from '../roomCashDisplay.js'

const props = defineProps({ date: { type: String, required: true } })
const rooms = ref([])
const drafts = ref({})
const loading = ref(false)
const error = ref('')
const saving = ref({})
const rowErrors = ref({})
const conflicts = ref({})
const saved = ref({})
let requestNumber = 0

function datetime(value) {
  return value ? new Intl.DateTimeFormat('ja-JP', { timeZone: 'Asia/Tokyo', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : 'まだ確認されていません'
}

async function reload(preserve = false) {
  const request = ++requestNumber
  const date = props.date
  loading.value = true
  error.value = ''
  try {
    const data = await api.getRoomCashSummary(date)
    if (request !== requestNumber || date !== props.date) return
    rooms.value = data.rooms || []
    drafts.value = roomCashDrafts(rooms.value, drafts.value, preserve)
    conflicts.value = {}
    if (!preserve) { rowErrors.value = {}; saved.value = {} }
  } catch (e) {
    if (request === requestNumber) error.value = e.message || 'ルーム現金を読み込めませんでした。'
  } finally {
    if (request === requestNumber) loading.value = false
  }
}

async function save(row) {
  const draft = drafts.value[row.room]
  if (!row.can_count || error.value || loading.value || !validCashCount(draft?.actual_cash_amount) || Object.values(saving.value).some(Boolean) || conflicts.value[row.room]) return
  const amount = Number(draft.actual_cash_amount)
  if (!window.confirm(`${row.room_name}で今数えた現金 ${yen(amount)} を記録します。よろしいですか？`)) return
  const date = props.date
  const request = ++requestNumber
  saving.value[row.room] = true
  rowErrors.value[row.room] = ''
  saved.value[row.room] = ''
  const signature = JSON.stringify([date, row.room, row.revision, amount, draft.memo])
  if (!draft.request_id || draft.request_signature !== signature) {
    draft.request_id = crypto.randomUUID()
    draft.request_signature = signature
  }
  try {
    const data = await api.saveRoomCashCount({ date, room: row.room, actual_cash_amount: amount, memo: draft.memo,
      expected_revision: row.revision, request_id: draft.request_id })
    if (request !== requestNumber || date !== props.date) return
    rooms.value = data.rooms || []
    drafts.value = roomCashDrafts(rooms.value, drafts.value, true)
    drafts.value[row.room] = { actual_cash_amount: '', memo: '', request_id: null }
    saved.value[row.room] = `${yen(amount)}を記録しました。`
  } catch (e) {
    if (date !== props.date) return
    conflicts.value[row.room] = e.status === 409
    rowErrors.value[row.room] = e.status === 409 ? '現金の情報が更新されました。入力は残しています。最新内容を確認してから、もう一度記録してください。' : e.message || '保存できませんでした。'
    if (e.status === 409) draft.request_id = null
  } finally {
    saving.value[row.room] = false
  }
}

watch(() => props.date, () => { rooms.value = []; drafts.value = {}; reload() }, { immediate: true })
defineExpose({ reload })
</script>

<template>
  <section aria-label="ルーム現金状況">
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <div><h2 class="h6 mb-1">ルーム現金状況</h2><div class="small text-muted">現金売上・受け渡しの記録から残金を自動計算します。実際に数えたときだけ、現金を記録してください。</div></div>
      <button type="button" class="btn btn-outline-secondary btn-sm" :disabled="loading || Object.values(saving).some(Boolean)" @click="reload(true)">最新の内容を確認</button>
    </div>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <div v-if="loading" class="text-muted py-3" role="status">読み込み中…</div>
    <div v-else-if="!rooms.length && !error" class="text-muted">ルームが登録されていません。</div>
    <article v-for="row in rooms" :key="row.room" class="card mb-3">
      <div class="card-body">
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
          <h3 class="h5 mb-0">{{ row.room_name }}</h3>
          <span v-if="!row.balance_known" class="badge bg-secondary">残高未確認</span>
          <span v-else-if="row.requires_confirmation" class="badge bg-warning text-dark">現金の再確認が必要</span>
        </div>
        <div class="row g-3 mb-3">
          <div class="col-12 col-sm-4"><div class="small text-muted">計算上の残金</div><div class="fs-4 fw-bold text-primary">{{ yen(row.expected_cash_amount) }}</div></div>
          <div class="col-6 col-sm-4"><div class="small text-muted">実際に数えた残金（最終確認時）</div><div class="fw-bold">{{ row.actual_cash_amount == null ? '未確認' : yen(row.actual_cash_amount) }}</div></div>
          <div class="col-6 col-sm-4"><div class="small text-muted">差額（最終確認時）</div><div class="fw-bold" :class="row.difference_amount ? 'text-danger' : ''">{{ row.difference_amount == null ? '未確認' : yen(row.difference_amount) }}</div></div>
        </div>
        <p class="small text-muted mb-2">最終実残確認：{{ datetime(row.last_counted_at) }}</p>
        <div v-for="warning in row.warnings || []" :key="warning" class="alert alert-warning small py-2">{{ warning }}</div>
        <details class="mb-3"><summary class="small">当日の現金記録（参考）</summary><p class="small text-muted mt-2 mb-2">当日分の合計です。計算上の残金は、最後に数えた現金を起点に、その後の増減を反映しています。</p><dl class="row small mt-2 mb-0"><dt class="col-7 fw-normal">現金売上</dt><dd class="col-5 text-end">{{ yen(row.cash_sales_amount) }}</dd><dt class="col-7 fw-normal">キャストの受取</dt><dd class="col-5 text-end">{{ yen(row.room_cash_taken_amount) }}</dd><dt class="col-7 fw-normal">ルームへの返金</dt><dd class="col-5 text-end">{{ yen(row.cash_returned_amount) }}</dd></dl></details>
        <div class="bg-light rounded p-3 mb-3">
          <h4 class="h6">受け渡しの見込み</h4>
          <p class="small text-muted">各キャストに単独で渡した場合の試算です。同じ現金を全員へ渡せる意味ではありません。報酬や受取記録は変更されません。</p>
          <div v-if="!row.casts?.length" class="small text-muted">対象のキャストはいません。</div>
          <div v-for="cast in row.casts || []" :key="cast.cast_id" class="border-top pt-2 mt-2">
            <strong>{{ cast.cast_name }}</strong>
            <div class="small mt-1">未受取額 {{ yen(cast.remaining_receivable_amount) }}<span class="text-muted">（受取可能額 {{ yen(cast.receivable_amount) }}）</span></div>
            <div v-if="cast.ambiguous_room" class="small text-warning-emphasis mt-1">複数のルームを利用しています。受け渡し元を確認してください。</div>
            <div v-if="cast.settlement_pending" class="small text-warning-emphasis mt-1">過去の退勤提出が差戻し中です。精算内容の確認後に受け渡しの見込みを確認してください。</div>
            <div v-else-if="row.requires_confirmation" class="small text-warning-emphasis mt-1">現金記録の確認が必要です。実際の残金を確認してから受け渡しを判断してください。</div>
            <div v-else-if="cast.suggested_take_amount == null" class="small text-muted mt-1">残金を確認すると、渡せる金額を確認できます。</div>
            <div v-else class="row g-2 mt-1 small"><div class="col-6 col-md-4">渡せる金額<div class="fw-bold">{{ yen(cast.suggested_take_amount) }}</div></div><div class="col-6 col-md-4">受取後のルーム残金<div class="fw-bold">{{ yen(cast.projected_room_balance) }}</div></div><div class="col-12 col-md-4" :class="cast.shortage_amount > 0 ? 'text-danger' : 'text-success'">不足<div class="fw-bold">{{ yen(cast.shortage_amount) }}</div></div></div>
          </div>
        </div>
        <details class="mb-3"><summary class="small">現金の履歴を見る（{{ row.history?.length || 0 }}件）</summary>
          <div v-if="!row.history?.length" class="small text-muted mt-2">履歴はまだありません。</div>
          <div v-for="entry in row.history || []" :key="entry.id" class="d-flex flex-wrap justify-content-between gap-2 border-bottom py-2 small"><div><span class="badge bg-light text-dark border me-1">{{ entry.kind === 'COUNT' ? '実残確認' : ['CASH_SALE', 'CORRECTION'].includes(entry.kind) ? '売上計算変動' : '受取記録' }}</span>{{ entry.label }}<div class="text-muted">{{ datetime(entry.created_at) }}</div></div><strong>{{ yen(entry.amount) }}</strong></div>
        </details>
        <p v-if="!row.can_count" class="small text-muted border-top pt-3 mb-0">過去の営業日の参考記録です。実残の記録は現在の営業日で行ってください。</p>
        <form v-else-if="drafts[row.room]" class="border-top pt-3" @submit.prevent="save(row)">
          <div class="row g-2 align-items-end"><div class="col-sm-4"><label :for="`room-cash-count-${row.room}`" class="form-label small">今、実際に数えた現金</label><input :id="`room-cash-count-${row.room}`" v-model="drafts[row.room].actual_cash_amount" type="number" min="0" step="1" class="form-control" placeholder="未入力" :disabled="saving[row.room]" /></div><div class="col-sm-5"><label :for="`room-cash-memo-${row.room}`" class="form-label small">メモ（任意）</label><input :id="`room-cash-memo-${row.room}`" v-model="drafts[row.room].memo" class="form-control" placeholder="確認内容・差額の理由など" :disabled="saving[row.room]" /></div><div class="col-sm-3"><button type="submit" class="btn btn-outline-primary w-100" :disabled="!validCashCount(drafts[row.room].actual_cash_amount) || Object.values(saving).some(Boolean) || loading || !!error || conflicts[row.room]">{{ saving[row.room] ? '記録中…' : '実残を記録' }}</button></div></div>
          <p class="form-text mb-0">記録できるのは現在の営業日です。現金がないと確認した場合は「0」を入力してください。</p>
          <div v-if="rowErrors[row.room]" class="alert alert-danger small mt-2 mb-0" role="alert">{{ rowErrors[row.room] }}</div>
          <div v-if="saved[row.room]" class="text-success small mt-2" role="status">{{ saved[row.room] }}</div>
        </form>
      </div>
    </article>
  </section>
</template>
