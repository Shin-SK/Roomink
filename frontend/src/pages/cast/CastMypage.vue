<script setup>
import { ref, computed, onMounted } from 'vue'
import LayoutCast from '../../components/LayoutCast.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const castName = ref('')
const avatarUrl = ref('')
const shift = ref(null)
const orders = ref([])
const totalOrders = ref(0)
const unconfirmedCount = ref(0)
const lineLinked = ref(false)
const lineLinkCode = ref('')
const lineAddFriendUrl = ref('')
const showLineModal = ref(false)
const codeCopied = ref(false)
const totalPoints = ref(0)
const pointHistory = ref([])
const todaySales = ref(null)

// 調整金（Phase 3-E）
const adjustments = ref({ open_total: 0, open: [], resolved_recent: [] })
const adjustmentsLoading = ref(true)
const showResolvedAdjustments = ref(false)

// ノート/施術マニュアル（Phase 4）
const notes = ref({ categories: [], pinned: [], recent: [] })
const notesLoading = ref(true)
const showAllNotes = ref(false)
const selectedNote = ref(null)

// 出勤確認（Phase 3-B-1）
const shiftConfirm = ref(null)
const shiftConfirmLoading = ref(true)
const confirmingShift = ref(false)
const confirmShiftError = ref('')

// 退勤（Phase 3-A）
const CHECKLIST_ITEMS = [
  { key: 'room_cleaned', label: '部屋の片付け・清掃をした' },
  { key: 'items_returned', label: '備品を返却した' },
  { key: 'cash_confirmed', label: '現金・売上を確認した' },
  { key: 'report_done', label: '特記事項があれば運営へ報告した' },
]

const checkoutData = ref(null)
const showCheckoutModal = ref(false)
const checkoutForm = ref(emptyCheckoutForm())
const checkoutSaving = ref(false)
const checkoutError = ref('')

function emptyCheckoutForm() {
  return {
    actual_take_home_amount: 0,
    cast_memo: '',
    checklist_json: Object.fromEntries(CHECKLIST_ITEMS.map(i => [i.key, false])),
  }
}

const checkoutIsReadOnly = computed(() => {
  const co = checkoutData.value?.checkout
  return !!co && co.status !== 'RETURNED'
})

// 決済手数料見込み（参考値）。提出済みならスナップショット値、未提出なら現在の見込みを表示
const feeEstimate = computed(() => {
  const co = checkoutData.value?.checkout
  if (co) {
    return { fee: co.payment_fee_estimate ?? 0, net: co.net_sales_after_payment_fee ?? 0 }
  }
  return {
    fee: checkoutData.value?.payment_fee_estimate ?? 0,
    net: checkoutData.value?.net_sales_after_payment_fee ?? 0,
  }
})

function checkoutStatusLabel(s) {
  return { SUBMITTED: '提出済み（未確認）', REVIEWED: '確認済み', RETURNED: '差戻し' }[s] || s
}

onMounted(async () => {
  try {
    const data = await api.getCastToday()
    castName.value = data.cast_name
    avatarUrl.value = data.avatar_url
    shift.value = data.shift
    orders.value = data.orders
    totalOrders.value = data.total_orders
    unconfirmedCount.value = data.unconfirmed_count
    lineLinked.value = data.line_linked || false
    lineLinkCode.value = data.line_link_code || ''
    lineAddFriendUrl.value = data.line_add_friend_url || ''
    if (!lineLinked.value) showLineModal.value = true
    // ポイント取得
    try {
      const pts = await api.getCastPoints()
      totalPoints.value = pts.total_points || 0
      pointHistory.value = pts.history || []
    } catch (_) { /* ポイント取得失敗は致命的でない */ }
    // 本日の売上/給与見込み取得
    try {
      todaySales.value = await api.getCastTodaySales()
    } catch (_) { /* 取得失敗は致命的でない */ }
    // 退勤状況取得
    await loadCheckout()
    // 出勤確認状況取得
    await loadShiftConfirm()
    // 調整金取得
    await loadAdjustments()
    // ノート取得
    await loadNotes()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

async function loadCheckout() {
  try {
    checkoutData.value = await api.getCastCheckout()
  } catch (_) { /* 取得失敗は致命的でない */ }
}

async function loadShiftConfirm() {
  shiftConfirmLoading.value = true
  try {
    shiftConfirm.value = await api.getCastShiftConfirm()
  } catch (_) { /* 取得失敗は致命的でない */ } finally {
    shiftConfirmLoading.value = false
  }
}

async function loadAdjustments() {
  adjustmentsLoading.value = true
  try {
    adjustments.value = await api.getCastAdjustmentsMypage()
  } catch (_) { /* 取得失敗は致命的でない */ } finally {
    adjustmentsLoading.value = false
  }
}

async function loadNotes() {
  notesLoading.value = true
  try {
    const data = await api.getCastNotesMypage()
    notes.value = {
      categories: data?.categories || [],
      pinned: Array.isArray(data?.pinned) ? data.pinned : [],
      recent: Array.isArray(data?.recent) ? data.recent : [],
    }
  } catch (_) { /* 取得失敗は致命的でない */ } finally {
    notesLoading.value = false
  }
}

function openNote(n) {
  selectedNote.value = n
}

async function onConfirmShift() {
  if (!shiftConfirm.value?.shift?.id || confirmingShift.value) return
  confirmingShift.value = true
  confirmShiftError.value = ''
  try {
    shiftConfirm.value = await api.confirmCastShift(shiftConfirm.value.shift.id)
  } catch (e) {
    confirmShiftError.value = e.message
  } finally {
    confirmingShift.value = false
  }
}

const WEEK_LABELS = ['日', '月', '火', '水', '木', '金', '土']
function formatShiftDateLabel(dateStr) {
  if (!dateStr) return ''
  const [y, m, d] = dateStr.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  return `${m}月${d}日(${WEEK_LABELS[dt.getDay()]})`
}

function openCheckoutModal() {
  const co = checkoutData.value?.checkout
  if (co && co.status === 'RETURNED') {
    checkoutForm.value = {
      actual_take_home_amount: co.actual_take_home_amount,
      cast_memo: co.cast_memo,
      checklist_json: { ...emptyCheckoutForm().checklist_json, ...(co.checklist_json || {}) },
    }
  } else if (!co) {
    checkoutForm.value = emptyCheckoutForm()
  }
  checkoutError.value = ''
  showCheckoutModal.value = true
}

async function submitCheckout() {
  checkoutSaving.value = true
  checkoutError.value = ''
  try {
    const body = {
      actual_take_home_amount: Number(checkoutForm.value.actual_take_home_amount) || 0,
      cast_memo: checkoutForm.value.cast_memo,
      checklist_json: checkoutForm.value.checklist_json,
    }
    await api.submitCastCheckout(body)
    await loadCheckout()
    showCheckoutModal.value = false
  } catch (e) {
    checkoutError.value = e.message
  } finally {
    checkoutSaving.value = false
  }
}

async function doAck(order) {
  try {
    const updated = await api.ackOrder(order.id)
    const idx = orders.value.findIndex(o => o.id === order.id)
    if (idx !== -1) orders.value[idx] = updated
    unconfirmedCount.value = orders.value.filter(o => o.is_unconfirmed).length
  } catch (e) {
    alert(e.message)
  }
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function displayStartTime(order) {
  return order.start_time_extended || formatTime(order.start)
}

function displayEndTime(order) {
  return order.end_time_extended || formatTime(order.end)
}

function copyCode() {
  navigator.clipboard.writeText(lineLinkCode.value)
  codeCopied.value = true
  setTimeout(() => { codeCopied.value = false }, 2000)
}

function openLineFriend() {
  window.open(lineAddFriendUrl.value, '_blank')
}

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}

function durationMin(order) {
  const s = new Date(order.start)
  const e = new Date(order.end)
  return Math.round((e - s) / 60000)
}
</script>

<template>
  <LayoutCast>
      <div v-if="loading" class="text-center py-5">
        <div class="spinner-border text-primary"></div>
      </div>

      <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

      <template v-else>
        <!-- ページヘッダー -->
        <div class="ca-page-header d-flex align-items-center gap-3 mb-4">
          <div
            v-if="!avatarUrl"
            class="rounded-circle flex-shrink-0 d-flex align-items-center justify-content-center bg-light"
            style="width: 72px; aspect-ratio: 1/1;"
          >
            <i class="ti ti-user" style="font-size: 28px; color: var(--rk-primary)"></i>
          </div>
          <img
            v-else
            :src="avatarUrl"
            class="rounded-circle flex-shrink-0"
            style="width: 72px; aspect-ratio: 1/1; object-fit: cover;"
            alt=""
          >
          <div class="flex-grow-1">
            <div class="ca-page-header__title">{{ castName }}様</div>
            <div class="ca-page-header__sub" v-if="shift">
              <span class="time">
                <i class="ti ti-calendar-event"></i>{{ shift.start_time }}-{{ shift.end_time_extended || shift.end_time }}</span>
              <span class="room">
                <i class="ti ti-door"></i>{{ shift.room_name }}</span>
            </div>
          </div>
        </div>

        <!-- 出勤確認（Phase 3-B-1） -->
        <div class="rk-section-header"><i class="ti ti-calendar-check"></i> 出勤確認</div>
        <div class="card mb-3">
          <div class="card-body">
            <div v-if="shiftConfirmLoading" class="text-muted text-center py-2 small">読み込み中...</div>
            <div v-else-if="!shiftConfirm || !shiftConfirm.shift" class="text-muted text-center py-2 small">
              本日の出勤予定はありません
            </div>
            <template v-else>
              <div v-if="confirmShiftError" class="alert alert-danger py-2 small">{{ confirmShiftError }}</div>
              <div class="d-flex justify-content-between align-items-center mb-2">
                <div>
                  <div class="fw-bold">
                    {{ formatShiftDateLabel(shiftConfirm.shift.date) }}
                    <span class="small text-muted">{{ shiftConfirm.is_today ? '（本日）' : '（次回シフト）' }}</span>
                  </div>
                  <div class="small text-muted">
                    <i class="ti ti-clock"></i> {{ shiftConfirm.shift.start_time }}–{{ shiftConfirm.shift.end_time_extended || shiftConfirm.shift.end_time }}
                    <span v-if="shiftConfirm.shift.room_name"><i class="ti ti-door"></i> {{ shiftConfirm.shift.room_name }}</span>
                  </div>
                </div>
              </div>
              <div v-if="shiftConfirm.shift.confirmed_at" class="alert alert-success py-2 px-3 small mb-0">
                <i class="ti ti-circle-check"></i> 出勤確認済み（{{ formatTime(shiftConfirm.shift.confirmed_at) }}）
              </div>
              <template v-else>
                <button
                  class="btn btn-primary w-100 mb-2"
                  :disabled="confirmingShift"
                  @click="onConfirmShift"
                >
                  {{ confirmingShift ? '送信中...' : '出勤確認する' }}
                </button>
                <div class="small text-muted">
                  出勤2時間前までに確認してください。未確認のまま1時間前を過ぎると店舗側に表示されます。
                </div>
              </template>
            </template>
          </div>
        </div>

        <!-- サマリーカード -->
        <div class="row g-2 mb-3">
          <div class="col-6">
            <div class="card text-center mb-0">
              <div class="card-body p-3">
                <div class="small text-muted mb-2">本日の予約</div>
                <div class="fs-4 fw-bold">{{ totalOrders }}本</div>
              </div>
            </div>
          </div>
          <div class="col-6">
            <div class="card text-center mb-0">
              <div class="card-body p-3">
                <div class="small text-muted mb-2">未確認</div>
                <div class="fs-4 fw-bold" :class="unconfirmedCount > 0 ? 'text-danger' : ''">{{ unconfirmedCount }}本</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 本日の売上/給与見込みカード -->
        <div v-if="todaySales" class="card mb-3">
          <div class="card-body">
            <div class="fw-bold mb-2"><i class="ti ti-currency-yen text-primary"></i> 本日の売上/給与見込み</div>
            <div class="row g-2 text-center mb-2">
              <div class="col-4">
                <div class="small text-muted mb-1">完了済み</div>
                <div class="fw-bold">{{ todaySales.done_count }}本</div>
              </div>
              <div class="col-4">
                <div class="small text-muted mb-1">売上</div>
                <div class="fw-bold">{{ formatYen(todaySales.total_sales) }}</div>
              </div>
              <div class="col-4">
                <div class="small text-muted mb-1">給与見込み</div>
                <div class="fw-bold text-primary">{{ formatYen(todaySales.estimated_pay) }}</div>
              </div>
            </div>
            <div class="small text-muted">完了済みの予約を元にした見込みです。最終精算額とは異なる場合があります。</div>
          </div>
        </div>

        <!-- ポイントカード -->
        <div v-if="totalPoints !== 0 || pointHistory.length" class="card mb-3">
          <div class="card-body">
            <div class="d-flex align-items-center justify-content-between mb-2">
              <div class="fw-bold"><i class="ti ti-star text-warning"></i> ポイント</div>
              <div class="fs-4 fw-bold">{{ totalPoints }} pt</div>
            </div>
            <div v-if="pointHistory.length" class="small">
              <div v-for="p in pointHistory.slice(0, 5)" :key="p.id" class="d-flex justify-content-between text-muted border-bottom py-1">
                <span>{{ p.date }} {{ p.reason || '' }}</span>
                <span :class="p.points >= 0 ? 'text-success' : 'text-danger'" class="fw-bold">{{ p.points >= 0 ? '+' : '' }}{{ p.points }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 調整金（Phase 3-E） -->
        <div class="rk-section-header"><i class="ti ti-cash-banknote"></i> 調整金</div>
        <div class="card mb-3">
          <div class="card-body">
            <div v-if="adjustmentsLoading" class="text-muted text-center py-2 small">読み込み中...</div>
            <template v-else>
              <div class="d-flex justify-content-between align-items-center mb-2">
                <span class="fw-bold">未解消合計</span>
                <span class="fs-5 fw-bold" :class="adjustments.open_total >= 0 ? 'text-success' : 'text-danger'">
                  {{ adjustments.open_total >= 0 ? '+' : '' }}{{ formatYen(adjustments.open_total) }}
                </span>
              </div>

              <div v-if="adjustments.open?.length">
                <div v-for="a in adjustments.open" :key="a.id" class="d-flex justify-content-between border-bottom py-2 small">
                  <div>
                    <div class="fw-bold">{{ a.title }}</div>
                    <div class="text-muted">{{ a.date }}<span v-if="a.memo"> ・ {{ a.memo }}</span></div>
                  </div>
                  <div class="fw-bold flex-shrink-0 ms-2" :class="a.amount >= 0 ? 'text-success' : 'text-danger'">
                    {{ a.amount >= 0 ? '+' : '' }}{{ formatYen(a.amount) }}
                  </div>
                </div>
              </div>
              <div v-else class="text-muted small text-center py-2">未解消の調整金はありません</div>

              <div v-if="adjustments.resolved_recent?.length" class="mt-2">
                <button
                  class="btn btn-link btn-sm p-0 text-muted"
                  @click="showResolvedAdjustments = !showResolvedAdjustments"
                >
                  解消済み履歴（{{ adjustments.resolved_recent.length }}件）{{ showResolvedAdjustments ? 'を閉じる' : 'を見る' }}
                </button>
                <div v-if="showResolvedAdjustments" class="mt-2">
                  <div
                    v-for="a in adjustments.resolved_recent"
                    :key="a.id"
                    class="d-flex justify-content-between border-bottom py-2 small text-muted"
                  >
                    <div>
                      <div>{{ a.title }}</div>
                      <div>{{ a.date }} 解消済</div>
                    </div>
                    <div class="flex-shrink-0 ms-2">{{ a.amount >= 0 ? '+' : '' }}{{ formatYen(a.amount) }}</div>
                  </div>
                </div>
              </div>

              <div class="small text-muted mt-2">この金額は最終精算ではなく、店舗確認用の調整メモです。</div>
            </template>
          </div>
        </div>

        <!-- ノート/施術マニュアル（Phase 4） -->
        <div class="rk-section-header"><i class="ti ti-notebook"></i> ノート/マニュアル</div>
        <div class="card mb-3">
          <div class="card-body">
            <div v-if="notesLoading" class="text-muted text-center py-2 small">読み込み中...</div>
            <template v-else-if="!notes.pinned.length && !notes.recent.length">
              <div class="text-muted text-center py-2 small">まだノートはありません</div>
            </template>
            <template v-else>
              <template v-if="notes.pinned.length">
                <div class="small fw-bold text-muted mb-1"><i class="ti ti-pin text-warning"></i> ピン留め</div>
                <div
                  v-for="n in notes.pinned"
                  :key="'pinned-' + n.id"
                  class="d-flex justify-content-between align-items-center border-bottom py-2 small"
                  style="cursor: pointer;"
                  @click="openNote(n)"
                >
                  <div>
                    <span v-if="n.category" class="badge bg-light text-dark border me-1">{{ n.category }}</span>
                    <span class="fw-bold">{{ n.title }}</span>
                  </div>
                  <i class="ti ti-chevron-right text-muted"></i>
                </div>
              </template>
              <template v-if="notes.recent.length">
                <div class="small fw-bold text-muted mb-1 mt-2"><i class="ti ti-news"></i> 新着</div>
                <div
                  v-for="n in (showAllNotes ? notes.recent : notes.recent.slice(0, 5))"
                  :key="'recent-' + n.id"
                  class="d-flex justify-content-between align-items-center border-bottom py-2 small"
                  style="cursor: pointer;"
                  @click="openNote(n)"
                >
                  <div>
                    <span v-if="n.category" class="badge bg-light text-dark border me-1">{{ n.category }}</span>
                    <span>{{ n.title }}</span>
                  </div>
                  <i class="ti ti-chevron-right text-muted"></i>
                </div>
                <button
                  v-if="notes.recent.length > 5"
                  class="btn btn-link btn-sm p-0 mt-2"
                  @click="showAllNotes = !showAllNotes"
                >{{ showAllNotes ? '閉じる' : `もっと見る（${notes.recent.length}件）` }}</button>
              </template>
            </template>
          </div>
        </div>

        <!-- ノート詳細モーダル -->
        <Teleport to="body">
          <div v-if="selectedNote" class="line-modal-overlay" @click.self="selectedNote = null">
            <div class="line-modal" style="max-width: 520px;">
              <div class="line-modal-header">
                <span class="fw-bold fs-5">{{ selectedNote.title }}</span>
                <button class="btn btn-sm btn-light rounded-circle" @click="selectedNote = null" style="width: 32px; height: 32px; padding: 0;">
                  <i class="ti ti-x"></i>
                </button>
              </div>
              <div class="line-modal-body">
                <div v-if="selectedNote.category" class="mb-2">
                  <span class="badge bg-light text-dark border">{{ selectedNote.category }}</span>
                </div>
                <div class="small text-muted mb-3" v-if="selectedNote.published_at">
                  公開日: {{ formatTime(selectedNote.published_at) === '' ? '' : selectedNote.published_at.slice(0, 10) }}
                </div>
                <div style="white-space: pre-wrap;">{{ selectedNote.body }}</div>
                <div v-if="selectedNote.video_url" class="mt-3 small">
                  <a :href="selectedNote.video_url" target="_blank" rel="noopener"><i class="ti ti-video"></i> 関連動画リンク</a>
                </div>
              </div>
              <div class="line-modal-footer">
                <button class="btn btn-outline-secondary w-100" @click="selectedNote = null">閉じる</button>
              </div>
            </div>
          </div>
        </Teleport>

        <!-- LINE連携カード -->
        <div v-if="lineLinked" class="card mb-3 border-success">
          <div class="card-body">
            <div class="d-flex align-items-center gap-3">
              <div class="flex-shrink-0">
                <div class="rounded-circle d-flex align-items-center justify-content-center bg-success" style="width: 40px; height: 40px;">
                  <i class="ti ti-brand-line" style="font-size: 20px; color: #fff;"></i>
                </div>
              </div>
              <div class="flex-grow-1">
                <div class="fw-bold mb-1">LINE連携</div>
                <div class="small text-success"><i class="ti ti-check"></i> 連携済み — リマインド通知が届きます</div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="card mb-3 border-warning border-2" style="cursor: pointer;" @click="showLineModal = true">
          <div class="card-body">
            <div class="d-flex align-items-center gap-3">
              <div class="flex-shrink-0">
                <div class="rounded-circle d-flex align-items-center justify-content-center bg-warning" style="width: 40px; height: 40px;">
                  <i class="ti ti-brand-line" style="font-size: 20px; color: #fff;"></i>
                </div>
              </div>
              <div class="flex-grow-1">
                <div class="fw-bold mb-1">LINE連携が必要です</div>
                <div class="small text-muted">タップして連携手順を確認 <i class="ti ti-chevron-right"></i></div>
              </div>
            </div>
          </div>
        </div>

        <!-- LINE連携モーダル -->
        <Teleport to="body">
          <div v-if="showLineModal && !lineLinked" class="line-modal-overlay" @click.self="showLineModal = false">
            <div class="line-modal">
              <div class="line-modal-header">
                <div class="d-flex align-items-center gap-2">
                  <div class="rounded-circle d-flex align-items-center justify-content-center" style="width: 36px; height: 36px; background: #06C755;">
                    <i class="ti ti-brand-line" style="font-size: 18px; color: #fff;"></i>
                  </div>
                  <span class="fw-bold fs-5">LINE連携</span>
                </div>
                <button class="btn btn-sm btn-light rounded-circle" @click="showLineModal = false" style="width: 32px; height: 32px; padding: 0;">
                  <i class="ti ti-x"></i>
                </button>
              </div>

              <div class="line-modal-body">
                <p class="text-muted small mb-3">出勤リマインドを受け取るためにLINE連携が必要です。</p>

                <!-- ステップ -->
                <div class="line-step">
                  <div class="line-step-num">1</div>
                  <div class="line-step-content">
                    <div class="fw-bold mb-2">連携コードをコピー</div>
                    <div class="line-code-box" @click="copyCode">
                      <span class="line-code">{{ lineLinkCode }}</span>
                      <span class="line-code-copy" :class="{ copied: codeCopied }">
                        <i :class="codeCopied ? 'ti ti-check' : 'ti ti-copy'"></i>
                        {{ codeCopied ? 'コピー済' : 'コピー' }}
                      </span>
                    </div>
                  </div>
                </div>

                <div class="line-step">
                  <div class="line-step-num">2</div>
                  <div class="line-step-content">
                    <div class="fw-bold mb-2">公式LINEを友だち追加してコードを送信</div>
                    <button class="btn w-100 text-white fw-bold" style="background: #06C755;" @click="openLineFriend">
                      <i class="ti ti-brand-line me-1"></i> 友だち追加する
                    </button>
                    <div class="small text-muted mt-2">友だち追加後、トーク画面でコピーしたコードを送信してください</div>
                  </div>
                </div>

                <div class="line-step">
                  <div class="line-step-num">3</div>
                  <div class="line-step-content">
                    <div class="fw-bold">連携完了！</div>
                    <div class="small text-muted mb-2">コード送信後、自動で連携されます。</div>
                    <button class="btn btn-sm btn-outline-success w-100" @click="location.reload()">
                      <i class="ti ti-refresh me-1"></i> ページを再読み込み
                    </button>
                  </div>
                </div>
              </div>

              <div class="line-modal-footer">
                <button class="btn btn-outline-secondary w-100" @click="showLineModal = false">あとで設定する</button>
              </div>
            </div>
          </div>
        </Teleport>

        <!-- 未確認警告カード -->
        <div v-if="unconfirmedCount > 0" class="alert alert-warning d-flex align-items-center gap-3 mb-4">
          <i class="ti ti-alert-triangle fs-4 flex-shrink-0"></i>
          <div class="flex-grow-1">
            <div class="fw-bold mb-1">未確認の予約があります</div>
            <div class="small">予約一覧から「確認する」ボタンを押してください</div>
          </div>
        </div>

        <!-- 予約一覧 -->
        <div class="rk-section-header"><i class="ti ti-calendar-event"></i> 予約一覧</div>

        <div
          v-for="order in orders"
          :key="order.id"
          class="card mb-3"
          :class="order.is_unconfirmed ? 'border-warning border-2' : ''"
        >
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-start mb-2">
              <div>
                <div class="fw-bold fs-5">{{ displayStartTime(order) }} – {{ displayEndTime(order) }}</div>
                <div class="small text-muted">{{ durationMin(order) }}分</div>
              </div>
              <span
                class="badge"
                :class="order.is_unconfirmed ? 'badge-unconfirmed' : 'badge-approved'"
              >{{ order.is_unconfirmed ? '未確認' : '確認済' }}</span>
            </div>
            <div class="small text-muted mb-2">
              <div><i class="ti ti-door"></i> {{ order.room_name }}</div>
              <div><i class="ti ti-currency-yen"></i> {{ formatYen(order.course_price) }}</div>
            </div>
            <div class="bg-light p-2 rounded small mb-3">
              <i class="ti ti-note"></i> {{ order.memo || '備考なし' }}
            </div>
            <button
              v-if="order.is_unconfirmed"
              class="btn btn-sm btn-warning w-100"
              @click="doAck(order)"
            >
              <i class="ti ti-check"></i> 確認する
            </button>
            <button
              v-else
              class="btn btn-sm btn-outline-primary w-100"
              disabled
            >
              <i class="ti ti-check"></i> 確認済
            </button>
          </div>
        </div>

        <div v-if="orders.length === 0" class="text-muted text-center py-4">
          本日の予約はありません
        </div>

        <!-- 退勤 -->
        <div class="rk-section-header"><i class="ti ti-door-exit"></i> 退勤</div>

        <div v-if="checkoutData?.checkout" class="card mb-3">
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <span class="fw-bold"><i class="ti ti-clipboard-check text-primary"></i> 本日の退勤提出</span>
              <span
                class="badge"
                :class="{
                  SUBMITTED: 'badge-unconfirmed',
                  REVIEWED: 'badge-approved',
                  RETURNED: 'bg-danger',
                }[checkoutData.checkout.status]"
              >{{ checkoutStatusLabel(checkoutData.checkout.status) }}</span>
            </div>
            <div class="small text-muted mb-2">提出日時: {{ formatTime(checkoutData.checkout.submitted_at) }}</div>
            <div v-if="checkoutData.checkout.status === 'RETURNED'" class="alert alert-warning py-2 px-3 small mb-2">
              運営から差戻しされました。内容を確認して再提出してください。
              <div v-if="checkoutData.checkout.manager_memo" class="mt-1">「{{ checkoutData.checkout.manager_memo }}」</div>
            </div>
            <button class="btn btn-sm w-100" :class="checkoutIsReadOnly ? 'btn-outline-primary' : 'btn-warning'" @click="openCheckoutModal">
              <i class="ti ti-eye"></i> {{ checkoutIsReadOnly ? '提出内容を見る' : '内容を確認して再提出する' }}
            </button>
          </div>
        </div>

        <button v-else class="btn btn-primary w-100 mb-3" @click="openCheckoutModal">
          <i class="ti ti-door-exit"></i> 退勤する
        </button>

        <!-- 退勤モーダル -->
        <Teleport to="body">
          <div v-if="showCheckoutModal" class="line-modal-overlay" @click.self="showCheckoutModal = false">
            <div class="line-modal" style="max-width: 520px;">
              <div class="line-modal-header">
                <span class="fw-bold fs-5"><i class="ti ti-door-exit"></i> 退勤{{ checkoutIsReadOnly ? '内容' : '' }}</span>
                <button class="btn btn-sm btn-light rounded-circle" @click="showCheckoutModal = false" style="width: 32px; height: 32px; padding: 0;">
                  <i class="ti ti-x"></i>
                </button>
              </div>

              <div class="line-modal-body">
                <div v-if="checkoutError" class="alert alert-danger py-2 small">{{ checkoutError }}</div>

                <!-- 見込みサマリー -->
                <div class="bg-light rounded p-2 mb-3">
                  <div class="row g-2 text-center">
                    <div class="col-4">
                      <div class="small text-muted mb-1">完了済み</div>
                      <div class="fw-bold">{{ checkoutData?.done_count ?? 0 }}本</div>
                    </div>
                    <div class="col-4">
                      <div class="small text-muted mb-1">売上</div>
                      <div class="fw-bold">{{ formatYen(checkoutData?.total_sales ?? 0) }}</div>
                    </div>
                    <div class="col-4">
                      <div class="small text-muted mb-1">給与見込み</div>
                      <div class="fw-bold text-primary">{{ formatYen(checkoutData?.estimated_pay ?? 0) }}</div>
                    </div>
                  </div>
                  <div class="row g-2 text-center mt-1 pt-2 border-top">
                    <div class="col-6">
                      <div class="small text-muted mb-1">決済手数料見込み<span class="d-block" style="font-size: 0.7rem;">(参考値)</span></div>
                      <div class="small text-danger">-{{ formatYen(feeEstimate.fee) }}</div>
                    </div>
                    <div class="col-6">
                      <div class="small text-muted mb-1">手数料差引後売上<span class="d-block" style="font-size: 0.7rem;">(参考値)</span></div>
                      <div class="small">{{ formatYen(feeEstimate.net) }}</div>
                    </div>
                  </div>
                </div>

                <!-- 固定雑費テンプレ -->
                <div v-if="checkoutData?.expense_templates?.length" class="mb-3">
                  <div class="fw-bold small mb-1"><i class="ti ti-receipt"></i> 固定雑費</div>
                  <div v-for="t in checkoutData.expense_templates" :key="t.id" class="d-flex justify-content-between small border-bottom py-1">
                    <span>{{ t.name }}</span>
                    <span>{{ formatYen(t.amount) }}</span>
                  </div>
                </div>

                <!-- 読み取り専用表示（提出済み・確認済み） -->
                <template v-if="checkoutIsReadOnly">
                  <div class="mb-2">
                    <div class="small text-muted mb-1">実際の持ち帰り金額</div>
                    <div class="fw-bold">{{ formatYen(checkoutData.checkout.actual_take_home_amount) }}</div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted mb-1">チェックリスト</div>
                    <div v-for="item in CHECKLIST_ITEMS" :key="item.key" class="small">
                      <i class="ti" :class="checkoutData.checkout.checklist_json?.[item.key] ? 'ti-square-check text-success' : 'ti-square text-muted'"></i>
                      {{ item.label }}
                    </div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted mb-1">メモ</div>
                    <div class="bg-light p-2 rounded small">{{ checkoutData.checkout.cast_memo || 'なし' }}</div>
                  </div>
                  <div v-if="checkoutData.checkout.manager_memo" class="mb-2">
                    <div class="small text-muted mb-1">運営からのメモ</div>
                    <div class="bg-light p-2 rounded small">{{ checkoutData.checkout.manager_memo }}</div>
                  </div>
                </template>

                <!-- 入力フォーム（未提出 or 差戻し後） -->
                <template v-else>
                  <div class="mb-3">
                    <label class="form-label small fw-bold">実際の持ち帰り金額</label>
                    <input v-model.number="checkoutForm.actual_take_home_amount" type="number" min="0" class="form-control" />
                  </div>
                  <div class="mb-3">
                    <label class="form-label small fw-bold">退勤チェックリスト</label>
                    <div v-for="item in CHECKLIST_ITEMS" :key="item.key" class="form-check">
                      <input
                        v-model="checkoutForm.checklist_json[item.key]"
                        type="checkbox"
                        class="form-check-input"
                        :id="'chk-' + item.key"
                      />
                      <label class="form-check-label small" :for="'chk-' + item.key">{{ item.label }}</label>
                    </div>
                  </div>
                  <div class="mb-2">
                    <label class="form-label small fw-bold">メモ</label>
                    <textarea v-model="checkoutForm.cast_memo" class="form-control" rows="3" placeholder="運営への連絡事項があれば入力してください"></textarea>
                  </div>
                </template>

                <div class="small text-muted mt-2">表示金額は完了済み予約を元にした見込みです。最終精算額とは異なる場合があります。</div>
              </div>

              <div class="line-modal-footer">
                <div v-if="!checkoutIsReadOnly" class="d-flex gap-2">
                  <button class="btn btn-outline-secondary flex-grow-1" @click="showCheckoutModal = false">キャンセル</button>
                  <button class="btn btn-primary flex-grow-1" :disabled="checkoutSaving" @click="submitCheckout">
                    {{ checkoutSaving ? '送信中...' : '退勤提出する' }}
                  </button>
                </div>
                <button v-else class="btn btn-outline-secondary w-100" @click="showCheckoutModal = false">閉じる</button>
              </div>
            </div>
          </div>
        </Teleport>

        <!-- 注意事項 -->
        <div class="card mb-3">
          <button class="card-header btn btn-link w-100 text-start d-flex justify-content-between align-items-center" data-bs-toggle="collapse" data-bs-target="#castNotes" aria-expanded="false">
            <span><i class="ti ti-info-circle"></i> 注意事項</span>
            <i class="ti ti-chevron-down"></i>
          </button>
          <div class="collapse" id="castNotes">
            <div class="card-body">
              <ul class="mb-0 ps-3">
                <li>予約内容を確認したら「確認する」ボタンを押してください</li>
                <li>予約開始15分前までに準備を完了してください</li>
                <li>遅刻やキャンセルの連絡があった場合は、すぐに運営に報告してください</li>
                <li>顧客情報は絶対に外部に漏らさないでください</li>
              </ul>
            </div>
          </div>
        </div>

        <a href="tel:03-1234-5678" class="card text-decoration-none text-reset mb-4 mt-4">
          <div class="card-body d-flex align-items-center gap-3">
            <div class="flex-shrink-0">
              <div class="rounded-circle d-flex align-items-center justify-content-center bg-light" style="width: 44px; height: 44px;">
                <i class="ti ti-phone" style="color: var(--rk-primary); font-size: 22px;"></i>
              </div>
            </div>
            <div class="flex-grow-1">
              <div class="fw-bold mb-1">困ったときは運営へ</div>
              <div class="small text-muted">タップして電話する<i class="ti ti-chevron-right text-muted"></i>
              </div>
            </div>
          </div>
        </a>

        <!-- フッターメッセージ -->
        <div class="text-center mb-5">
          <p class="text-muted" style="font-size: 0.8125rem;">本日もよろしくお願いします！</p>
        </div>

      </template>
  </LayoutCast>
</template>

<style scoped>
.line-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0;
}
.line-modal {
  background: #fff;
  border-radius: 20px 20px 0 0;
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow-y: auto;
  animation: slideUp 0.25s ease-out;
}
@keyframes slideUp {
  from { transform: translateY(100%); }
  to { transform: translateY(0); }
}
.line-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 20px 12px;
  border-bottom: 1px solid #eee;
}
.line-modal-body {
  padding: 20px;
}
.line-modal-footer {
  padding: 12px 20px 24px;
}
.line-step {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}
.line-step-num {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #06C755;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 14px;
}
.line-step-content {
  flex: 1;
  min-width: 0;
}
.line-code-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f5f5f5;
  border: 2px dashed #ccc;
  border-radius: 10px;
  padding: 12px 16px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.line-code-box:active {
  border-color: #06C755;
}
.line-code {
  font-family: monospace;
  font-size: 1.5rem;
  font-weight: bold;
  letter-spacing: 4px;
}
.line-code-copy {
  font-size: 0.75rem;
  color: #888;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.line-code-copy.copied {
  color: #06C755;
}
</style>
