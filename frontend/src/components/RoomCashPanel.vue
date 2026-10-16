<script setup>
import { ref, watch } from 'vue'
import { api } from '../api.js'
import { roomCashYen as yen, validCashCount, roomCashDrafts } from '../roomCashDisplay.js'

const props = defineProps({ date: { type: String, required: true }, castMode: Boolean })
const rooms = ref([])
const drafts = ref({})
const loading = ref(false)
const error = ref('')
const saving = ref({})
const rowErrors = ref({})
const conflicts = ref({})
const saved = ref({})
const selectedRoom = ref('')
const roomChoices = ref([])
const needsRoomSelection = ref(false)
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
    const data = props.castMode ? await api.getCastRoomCash(date, selectedRoom.value) : await api.getRoomCashSummary(date)
    if (request !== requestNumber || date !== props.date) return
    rooms.value = data.rooms || []
    if (props.castMode) {
      needsRoomSelection.value = !!data.requires_room_selection
      if (!selectedRoom.value) roomChoices.value = data.rooms || []
    }
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
  if (!row.can_count || (props.castMode && needsRoomSelection.value) || error.value || loading.value || !validCashCount(draft?.actual_cash_amount) || Object.values(saving.value).some(Boolean) || conflicts.value[row.room]) return
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
    const body = { date, room: row.room, actual_cash_amount: amount, memo: draft.memo,
      expected_revision: row.revision, request_id: draft.request_id }
    const data = props.castMode ? await api.saveCastRoomCashCount(body) : await api.saveRoomCashCount(body)
    if (request !== requestNumber || date !== props.date) return
    rooms.value = data.rooms || []
    drafts.value = roomCashDrafts(rooms.value, drafts.value, true)
    drafts.value[row.room] = { actual_cash_amount: '', memo: '', request_id: null }
    saved.value[row.room] = `${yen(amount)}を記録しました。`
  } catch (e) {
    if (request !== requestNumber || date !== props.date) return
    conflicts.value[row.room] = e.status === 409
    rowErrors.value[row.room] = e.status === 409 ? '現金の情報が更新されました。入力は残しています。最新内容を確認してから、もう一度記録してください。' : e.message || '保存できませんでした。'
    if (e.status === 409) draft.request_id = null
  } finally {
    saving.value[row.room] = false
  }
}

function selectRoom() {
  rooms.value = []
  drafts.value = {}
  reload()
}

function settlements(row) {
  return props.castMode ? (row.settlement ? [row.settlement] : []) : row.casts || []
}

watch(() => props.date, () => { rooms.value = []; drafts.value = {}; selectedRoom.value = ''; roomChoices.value = []; reload() }, { immediate: true })
defineExpose({ reload })
</script>

<template>
  <section aria-label="ルーム現金状況">
    <div class="d-flex justify-content-between align-items-center gap-2 mb-2 small">
      <span class="text-muted">{{ castMode ? 'ルームの現金・受け取り見込み' : 'ルームごとの残金・受け渡し見込み' }}</span>
      <button type="button" class="btn btn-outline-secondary btn-sm flex-shrink-0" :disabled="loading || Object.values(saving).some(Boolean)" @click="reload(true)"><i class="ti ti-refresh"></i> 更新</button>
    </div>
    <div v-if="castMode && roomChoices.length > 1" class="mb-3">
      <label for="cast-cash-room" class="form-label small">現金を確認するルーム</label>
      <select id="cast-cash-room" v-model="selectedRoom" class="form-select" :disabled="loading || Object.values(saving).some(Boolean)" @change="selectRoom"><option value="">ルームを選択してください</option><option v-for="room in roomChoices" :key="room.room" :value="room.room">{{ room.room_name }}</option></select>
    </div>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <div v-if="loading" class="text-muted py-3" role="status">読み込み中…</div>
    <div v-else-if="!rooms.length && !error" class="text-muted small">{{ castMode ? '本日の担当ルームはありません。' : 'ルームが登録されていません。' }}</div>
    <template v-if="!castMode || !needsRoomSelection">
    <article v-for="row in rooms" :key="row.room" class="card mb-3">
      <div class="card-header d-flex flex-wrap justify-content-between align-items-center gap-2">
        <span><i class="ti ti-door"></i> {{ row.room_name }}</span>
        <span v-if="!row.balance_known" class="badge bg-secondary">残高未確認</span>
        <span v-else-if="row.requires_confirmation" class="badge bg-warning text-dark">実残の確認が必要</span>
      </div>
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center small mb-2"><span class="text-muted">ルームの計算上の残金</span><strong class="text-primary">{{ yen(row.expected_cash_amount) }}</strong></div>
        <div v-if="!castMode" class="row g-2 small border-top pt-2 mb-2"><div class="col-7 text-muted">実残・差額（最終確認時）</div><div class="col-5 text-end">{{ row.actual_cash_amount == null ? '未確認' : yen(row.actual_cash_amount) }}<span v-if="row.difference_amount != null" :class="row.difference_amount ? 'text-danger' : 'text-muted'"> / {{ yen(row.difference_amount) }}</span></div></div>
        <div v-for="warning in row.warnings || []" :key="warning" class="alert alert-warning small py-2 mb-2">{{ warning }}</div>
        <div v-if="!settlements(row).length" class="small text-muted">対象のキャストはいません。</div>
        <div v-for="cast in settlements(row)" :key="cast.cast_id || 'self'" class="small border-top pt-2 mt-2">
            <strong v-if="!castMode">{{ cast.cast_name }}</strong>
            <div class="d-flex justify-content-between mt-1"><span>{{ castMode ? 'あなたの未受取額' : '未受取額' }}</span><strong>{{ yen(cast.remaining_receivable_amount) }}</strong></div>
            <div v-if="cast.ambiguous_room" class="small text-warning-emphasis mt-1">複数のルームを利用しています。受け渡し元を確認してください。</div>
            <div v-if="cast.settlement_pending" class="small text-warning-emphasis mt-1">過去の退勤提出が差戻し中です。精算内容の確認後に受け渡しの見込みを確認してください。</div>
            <div v-else-if="row.requires_confirmation" class="small text-warning-emphasis mt-1">現金記録の確認が必要です。実際の残金を確認してから受け渡しを判断してください。</div>
            <div v-else-if="cast.suggested_take_amount == null" class="small text-muted mt-1">残金を確認すると、渡せる金額を確認できます。</div>
            <template v-else>
              <div class="d-flex justify-content-between mt-2"><span>{{ castMode ? 'ルームで受け取れる金額' : '渡せる金額' }}</span><strong class="text-primary">{{ yen(cast.suggested_take_amount) }}</strong></div>
              <div class="d-flex justify-content-between mt-1" :class="cast.shortage_amount > 0 ? 'text-danger' : 'text-success'"><span>不足</span><strong>{{ yen(cast.shortage_amount) }}</strong></div>
              <div class="d-flex justify-content-between mt-1 text-muted"><span>受取後のルーム残金（見込み）</span><span>{{ yen(cast.projected_room_balance) }}</span></div>
            </template>
        </div>
        <p v-if="castMode" class="small text-muted mt-2 mb-0">受け取りの記録は「退勤処理」で提出してください。</p>
        <details class="small border-top mt-3 pt-2"><summary>確認内容・計算の詳細</summary>
          <div class="text-muted mt-2">最終実残確認：{{ datetime(row.last_counted_at) }}</div>
          <div v-if="castMode" class="d-flex justify-content-between mt-1"><span>数えた残金 / 差額（最終確認時）</span><span>{{ row.actual_cash_amount == null ? '未確認' : yen(row.actual_cash_amount) }} / {{ row.difference_amount == null ? '未確認' : yen(row.difference_amount) }}</span></div>
          <template v-else>
            <p class="text-muted mt-2 mb-2">各キャストに単独で渡す場合の試算です。同じ現金を全員に渡せる金額ではありません。</p>
            <div class="fw-bold mt-2">当日の現金記録（参考）</div>
            <p class="text-muted mb-2">計算残金は最後の実残確認後の増減を反映しています。以下は当日の合計です。</p>
            <dl class="row mb-0"><dt class="col-7 fw-normal">現金売上</dt><dd class="col-5 text-end">{{ yen(row.cash_sales_amount) }}</dd><dt class="col-7 fw-normal">キャストの受取</dt><dd class="col-5 text-end">{{ yen(row.room_cash_taken_amount) }}</dd><dt class="col-7 fw-normal">ルームへの返金</dt><dd class="col-5 text-end">{{ yen(row.cash_returned_amount) }}</dd></dl>
          </template>
        </details>
        <details v-if="!castMode" class="small border-top mt-2 pt-2"><summary>現金の履歴（{{ row.history?.length || 0 }}件）</summary>
          <div v-if="!row.history?.length" class="small text-muted mt-2">履歴はまだありません。</div>
          <div v-for="entry in row.history || []" :key="entry.id" class="d-flex flex-wrap justify-content-between gap-2 border-bottom py-2 small"><div><span class="badge bg-light text-dark border me-1">{{ entry.kind === 'COUNT' ? '実残確認' : ['CASH_SALE', 'CORRECTION'].includes(entry.kind) ? '売上計算変動' : '受取記録' }}</span>{{ entry.label }}<div class="text-muted">{{ datetime(entry.created_at) }}</div></div><strong>{{ yen(entry.amount) }}</strong></div>
        </details>
        <p v-if="!row.can_count" class="small text-muted border-top pt-2 mt-2 mb-0">実残の記録は現在の営業日で行ってください。</p>
        <details v-else-if="drafts[row.room]" class="border-top pt-2 mt-2"><summary class="small">実際に数えた現金を記録する（任意）</summary>
        <form class="pt-2" @submit.prevent="save(row)">
          <div class="row g-2 align-items-end"><div class="col-sm-4"><label :for="`room-cash-count-${row.room}`" class="form-label small">今、実際に数えた現金</label><input :id="`room-cash-count-${row.room}`" v-model="drafts[row.room].actual_cash_amount" type="number" min="0" step="1" class="form-control" placeholder="未入力" :disabled="saving[row.room]" /></div><div class="col-sm-5"><label :for="`room-cash-memo-${row.room}`" class="form-label small">メモ（任意）</label><input :id="`room-cash-memo-${row.room}`" v-model="drafts[row.room].memo" class="form-control" placeholder="確認内容・差額の理由など" :disabled="saving[row.room]" /></div><div class="col-sm-3"><button type="submit" class="btn btn-outline-primary w-100" :disabled="!validCashCount(drafts[row.room].actual_cash_amount) || Object.values(saving).some(Boolean) || loading || !!error || conflicts[row.room]">{{ saving[row.room] ? '記録中…' : '実残を記録' }}</button></div></div>
          <p class="form-text mb-0">残金の確認記録です。給与や受取額は変わりません。現金がない場合は「0」を入力してください。</p>
          <div v-if="rowErrors[row.room]" class="alert alert-danger small mt-2 mb-0" role="alert">{{ rowErrors[row.room] }}</div>
          <div v-if="saved[row.room]" class="text-success small mt-2" role="status">{{ saved[row.room] }}</div>
        </form>
        </details>
      </div>
    </article>
    </template>
  </section>
</template>
