<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import OrderForm from '../../components/OrderForm.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

const props = defineProps({
  id: { type: [String, Number], required: true },
})

const router = useRouter()
const order = ref(null)
const loading = ref(true)
const error = ref('')
const acting = ref(false)
const mode = ref('confirm') // 'confirm' | 'edit'
const isManager = computed(() => getAuthRole() === 'manager')

// 実利用者アカウントの手動紐付け（managerのみ）
const recipientCustomers = ref([])
const recipientSearch = ref('')
const selectedRecipientCustomer = ref('')
const recipientLinking = ref(false)
const recipientLinkError = ref('')

const recipientCandidates = computed(() => {
  const query = recipientSearch.value.trim().toLowerCase()
  const items = query
    ? recipientCustomers.value.filter((customer) => (
      `${customer.display_name || ''} ${customer.phone || ''}`.toLowerCase().includes(query)
    ))
    : recipientCustomers.value
  return items.slice(0, 100)
})

// Addon
const addonError = ref('')
const addonActing = ref(false)
const extensions = ref([])
const nominationFees = ref([])
const discounts = ref([])
const selectedExtension = ref(null)
const extensionDuration = ref(0)
const extensionPrice = ref(0)
const selectedNominationFee = ref(null)
const selectedDiscount = ref(null)

// SMS送信履歴（表示のみ。再送信は行わない）
const smsLogs = ref([])
const smsLogsLoading = ref(true)
const smsLogsError = ref('')
const expandedSmsIds = ref([])
const cardSmsActing = ref(false)

const smsStatusCls = {
  SENT: 'bg-success',
  FAILED: 'bg-danger',
  SKIPPED: 'bg-secondary',
  PENDING: 'bg-warning text-dark',
  DUMMY: 'bg-info text-dark',
  CONFIG_MISSING: 'bg-warning text-dark',
}

const statusMap = {
  REQUESTED: { text: '予約リクエスト', cls: 'badge-pending' },
  CONFIRMED: { text: '確定済', cls: 'badge-approved' },
  IN_PROGRESS: { text: '施術中', cls: 'badge-approved' },
  PENDING_FINALIZE: { text: '会計待ち', cls: 'badge-attention' },
  DONE: { text: '完了', cls: 'badge-approved' },
  CANCELLED: { text: 'キャンセル', cls: 'badge-banned' },
}

const displayStatus = computed(() => {
  if (!order.value) return statusMap.REQUESTED
  if (order.value.status === 'CONFIRMED' && order.value.is_unconfirmed) {
    return { text: 'キャスト確認待ち', cls: 'badge-attention' }
  }
  return statusMap[order.value.status] || { text: order.value.status, cls: 'bg-secondary' }
})

const canModify = computed(() => order.value?.can_modify !== false)
const canConfirm = computed(() => canModify.value && order.value?.status === 'REQUESTED')
const canCancel = computed(() =>
  canModify.value && order.value && !['DONE', 'CANCELLED'].includes(order.value.status)
)
const canDone = computed(() =>
  canModify.value && order.value && ['CONFIRMED', 'IN_PROGRESS', 'PENDING_FINALIZE'].includes(order.value.status)
)
// 「次へ進める」ボタンのラベル：確定/施術中→施術終了、会計待ち→会計確定
const doneLabel = computed(() => {
  const s = order.value?.status
  if (s === 'PENDING_FINALIZE') return '会計確定'
  return '施術終了'
})
// キャンセルボタン文言：会計待ち以降は「取消」、それ以前は「キャンセル」
const cancelLabel = computed(() => {
  const s = order.value?.status
  if (s === 'PENDING_FINALIZE') return '会計取消'
  return 'キャンセル'
})
const canEdit = computed(() =>
  canModify.value && order.value && !['DONE', 'CANCELLED'].includes(order.value.status)
)

const isCardPayment = computed(() => order.value?.payment_method === 'CARD')
const cardFee = computed(() => {
  if (!isCardPayment.value || !order.value) return 0
  return Math.round((order.value.total_price || 0) * 0.1)
})
const cardTotal = computed(() => (order.value?.total_price || 0) + cardFee.value)
const cardPaymentCompletedSmsSent = computed(() => smsLogs.value.some(log => (
  log.template_type === 'CARD_PAYMENT_CONFIRMED' && ['SENT', 'DUMMY'].includes(log.status)
)))
const canOperateCardPayment = computed(() => (
  canModify.value
  && isCardPayment.value
  && order.value
  && !['REQUESTED', 'CANCELLED'].includes(order.value.status)
))

onMounted(async () => {
  try {
    const [o, exts, nfs, dcs] = await Promise.all([
      api.getOrder(props.id),
      api.getExtensions(),
      api.getNominationFees(),
      api.getDiscounts(),
    ])
    order.value = o
    extensions.value = Array.isArray(exts) ? exts : []
    nominationFees.value = Array.isArray(nfs) ? nfs : []
    discounts.value = Array.isArray(dcs) ? dcs : []
    selectedExtension.value = o.extension ?? null
    extensionDuration.value = o.extension_duration || 0
    extensionPrice.value = o.extension_price || 0
    selectedNominationFee.value = o.nomination_fee ?? null
    selectedDiscount.value = o.discount ?? null
    selectedRecipientCustomer.value = o.service_recipient_customer || ''
    if (isManager.value) {
      try {
        const customers = await api.getCustomers()
        recipientCustomers.value = Array.isArray(customers) ? customers : []
      } catch (e) {
        recipientLinkError.value = e.message || '顧客一覧を取得できませんでした'
      }
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
  fetchSmsLogs()
})

async function fetchSmsLogs() {
  smsLogsLoading.value = true
  smsLogsError.value = ''
  try {
    const list = await api.getOrderSmsLogs(props.id)
    smsLogs.value = Array.isArray(list) ? list : []
  } catch (e) {
    smsLogsError.value = e.message || 'SMS送信履歴の取得に失敗しました'
    smsLogs.value = []
  } finally {
    smsLogsLoading.value = false
  }
}

function toggleSmsBody(id) {
  const i = expandedSmsIds.value.indexOf(id)
  if (i === -1) expandedSmsIds.value.push(id)
  else expandedSmsIds.value.splice(i, 1)
}

function isSmsExpanded(id) {
  return expandedSmsIds.value.includes(id)
}

function smsBodyPreview(body) {
  const s = (body || '').replace(/\n/g, ' ')
  return s.length > 40 ? `${s.slice(0, 40)}…` : s
}

function openEdit() {
  mode.value = 'edit'
}

function closeEdit() {
  mode.value = 'confirm'
}

function onOrderUpdated({ order: updated }) {
  order.value = updated
  mode.value = 'confirm'
}

async function doConfirm() {
  if (!confirm('この予約を確定しますか？')) return
  acting.value = true
  try {
    order.value = await api.confirmOrder(props.id)
    // 「確定済」表示を一瞬見せてからダッシュボードへ戻す
    setTimeout(() => router.push('/op/dashboard'), 1200)
  } catch (e) {
    alert(e.message)
    acting.value = false
  }
}

async function doCancel() {
  const label = cancelLabel.value
  if (!confirm(`この予約を「${label}」にしますか？`)) return
  acting.value = true
  try {
    order.value = await api.cancelOrder(props.id)
  } catch (e) {
    alert(e.message)
  } finally {
    acting.value = false
  }
}

async function doDone() {
  const prevStatus = order.value?.status
  // 会計確定（PENDING_FINALIZE → DONE）の事前チェック：支払い方法必須
  if (prevStatus === 'PENDING_FINALIZE') {
    const pm = order.value?.payment_method
    if (pm !== 'CARD' && pm !== 'CASH' && pm !== 'PAYPAY') {
      alert('支払い方法（カード/現金/PayPay）を選択してから会計確定してください')
      return
    }
  }
  const label = doneLabel.value
  if (!confirm(`この予約を「${label}」にしますか？`)) return
  acting.value = true
  try {
    order.value = await api.doneOrder(props.id)
    // 会計確定（DONE化）まで進めたらダッシュボードへ戻す
    if (prevStatus === 'PENDING_FINALIZE' && order.value?.status === 'DONE') {
      setTimeout(() => router.push('/op/dashboard'), 1200)
      return
    }
  } catch (e) {
    alert(e.message)
  } finally {
    acting.value = false
  }
}

async function sendCardPaymentRequest() {
  if (!confirm('カード決済リンクのSMSを送信しますか？')) return
  cardSmsActing.value = true
  try {
    order.value = await api.sendCardPaymentRequest(props.id)
    await fetchSmsLogs()
  } catch (e) {
    alert(e.message)
  } finally {
    cardSmsActing.value = false
  }
}

async function confirmCardPayment() {
  if (!confirm('カード決済の入金を確認しましたか？\n確認後、ルーム住所のSMSを送信します。')) return
  cardSmsActing.value = true
  try {
    order.value = await api.confirmCardPayment(props.id)
    await fetchSmsLogs()
  } catch (e) {
    alert(e.message)
  } finally {
    cardSmsActing.value = false
  }
}

function formatDt(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

async function doApplyExtension() {
  addonError.value = ''
  addonActing.value = true
  try {
    order.value = await api.applyExtension(props.id, {
      extension_id: selectedExtension.value || null,
      extension_duration: Number(extensionDuration.value) || 0,
      extension_price: Number(extensionPrice.value) || 0,
    })
  } catch (e) {
    addonError.value = e.message
  } finally {
    addonActing.value = false
  }
}

function selectExtensionTemplate() {
  const template = extensions.value.find(e => e.id === Number(selectedExtension.value))
  if (template) {
    extensionDuration.value = template.duration
    extensionPrice.value = template.price
  }
}

function setExtensionDuration(minutes) {
  extensionDuration.value = minutes
  if (minutes === 0) {
    selectedExtension.value = null
    extensionPrice.value = 0
  }
}

async function doApplyNominationFee() {
  addonError.value = ''
  addonActing.value = true
  try {
    order.value = await api.applyNominationFee(props.id, selectedNominationFee.value)
  } catch (e) {
    addonError.value = e.message
  } finally {
    addonActing.value = false
  }
}

async function doApplyDiscount() {
  addonError.value = ''
  addonActing.value = true
  try {
    order.value = await api.applyDiscount(props.id, selectedDiscount.value)
  } catch (e) {
    addonError.value = e.message
  } finally {
    addonActing.value = false
  }
}

async function updatePaymentMethod(value) {
  try {
    order.value = await api.updateOrder(props.id, { payment_method: value })
  } catch (e) {
    alert(e.message)
  }
}

async function saveRecipientCustomerLink() {
  const customerId = selectedRecipientCustomer.value
    ? Number(selectedRecipientCustomer.value)
    : null
  const message = customerId
    ? 'この予約を選択した実利用者アカウントへ紐付けますか？'
    : '実利用者アカウントとの紐付けを解除しますか？'
  if (!confirm(message)) return

  recipientLinkError.value = ''
  recipientLinking.value = true
  try {
    order.value = await api.linkOrderServiceRecipient(props.id, customerId)
    selectedRecipientCustomer.value = order.value.service_recipient_customer || ''
  } catch (e) {
    recipientLinkError.value = e.message || '実利用者アカウントを更新できませんでした'
  } finally {
    recipientLinking.value = false
  }
}
</script>

<template>
  <LayoutOperator>
    <template #title>予約詳細</template>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

    <template v-else-if="order">
      <main class="order">

        <!-- ========== 確認モード ========== -->
        <template v-if="mode === 'confirm'">

          <div v-if="order.is_past_business_day && !canModify" class="alert alert-warning">
            <i class="ti ti-lock"></i>
            過去営業日の予約です。変更できるのはマネージャーのみです。
          </div>

          <div v-if="order.is_off_shift || order.is_room_pending" class="alert alert-warning">
            <div v-if="order.is_off_shift"><strong>シフト外予約</strong>です。</div>
            <div v-if="order.is_room_pending"><strong>ルーム未定</strong>です。シフトとルームを登録してください。</div>
          </div>

          <!-- ステータスバッジ -->
          <div class="text-center mb-3">
            <span
              class="badge fs-6 px-3 py-2"
              :class="displayStatus.cls"
            >{{ displayStatus.text }}</span>
          </div>

          <!-- サマリー -->
          <div class="card mb-3">
            <div class="card-body p-0">
              <table class="table mb-0">
                <tbody>
                  <tr>
                    <th>予約日時</th>
                    <td>{{ formatDt(order.start) }} – {{ formatTime(order.end) }}</td>
                  </tr>
                  <tr>
                    <th>連絡者</th>
                    <td>{{ order.customer_label }}</td>
                  </tr>
                  <tr>
                    <th>ご利用者</th>
                    <td>{{ order.service_recipient_name || '本人' }}</td>
                  </tr>
                  <tr>
                    <th>キャスト</th>
                    <td>{{ order.cast_name }}</td>
                  </tr>
                  <tr>
                    <th>ルーム</th>
                    <td>{{ order.room_name || '未定' }}</td>
                  </tr>
                  <tr>
                    <th>コース</th>
                    <td>{{ order.course_name }}</td>
                  </tr>
                  <tr v-if="order.options && order.options.length">
                    <th>オプション</th>
                    <td>{{ order.options.join(', ') }}</td>
                  </tr>
                  <tr v-if="order.extension_name">
                    <th>延長</th>
                    <td>
                      {{ order.extension_name }}
                      <span v-if="order.extension_duration">（{{ order.extension_duration }}分）</span>
                    </td>
                  </tr>
                  <tr v-if="order.nomination_fee_name">
                    <th>指名料</th>
                    <td>{{ order.nomination_fee_name }}</td>
                  </tr>
                  <tr v-if="order.discount_name">
                    <th>割引</th>
                    <td>{{ order.discount_name }}</td>
                  </tr>
                  <tr v-if="order.medium_name">
                    <th>媒体</th>
                    <td>{{ order.medium_name }}</td>
                  </tr>
                  <tr>
                    <th>支払方法</th>
                    <td>
                      <select
                        :value="order.payment_method || 'UNSET'"
                        class="form-select form-select-sm d-inline-block"
                        style="width: auto;"
                        :disabled="!canModify"
                        @change="updatePaymentMethod($event.target.value)"
                      >
                        <option value="UNSET">未設定</option>
                        <option value="CARD">カード</option>
                        <option value="CASH">現金</option>
                        <option value="PAYPAY">PayPay</option>
                      </select>
                    </td>
                  </tr>
                  <tr v-if="order.memo">
                    <th>メモ</th>
                    <td style="white-space: pre-wrap;">{{ order.memo }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="isManager" class="card mb-4 border-primary-subtle">
            <div class="card-header">
              <i class="ti ti-user-check"></i> 実利用者アカウントの紐付け
            </div>
            <div class="card-body">
              <div class="small text-muted mb-3">
                過去の予約を実際に利用したお客様の履歴へ追加できます。
                元の連絡者・電話番号・SMS送信先・売上情報は変更されません。
              </div>
              <div v-if="order.service_recipient_customer_label" class="alert alert-success py-2 px-3 small">
                現在の紐付け先: {{ order.service_recipient_customer_label }}
              </div>
              <div v-if="recipientLinkError" class="alert alert-danger py-2 px-3 small">
                {{ recipientLinkError }}
              </div>
              <label class="form-label small fw-bold">名前・電話番号で候補を絞り込み</label>
              <input
                v-model="recipientSearch"
                type="search"
                class="form-control form-control-sm mb-2"
                placeholder="例: 山田 / 0901234"
              >
              <div class="d-flex flex-column flex-sm-row gap-2">
                <select v-model="selectedRecipientCustomer" class="form-select form-select-sm">
                  <option value="">紐付けなし</option>
                  <option v-for="customer in recipientCandidates" :key="customer.id" :value="customer.id">
                    {{ customer.display_name || '名称未設定' }}（{{ customer.phone }}）
                  </option>
                </select>
                <button
                  type="button"
                  class="btn btn-primary btn-sm text-nowrap"
                  :disabled="recipientLinking"
                  @click="saveRecipientCustomerLink"
                >
                  {{ recipientLinking ? '保存中...' : '紐付けを保存' }}
                </button>
              </div>
            </div>
          </div>

          <!-- 料金 -->
          <div class="card mb-4">
            <div class="card-body p-0">
              <table class="table table-sm mb-0">
                <tbody>
                  <tr>
                    <td>コース（{{ order.course_name }}）</td>
                    <td class="text-end">{{ order.course_price.toLocaleString() }}円</td>
                  </tr>
                  <tr v-if="order.options_price > 0">
                    <td>オプション</td>
                    <td class="text-end">{{ order.options_price.toLocaleString() }}円</td>
                  </tr>
                  <tr v-if="order.extension_name">
                    <td>延長（{{ order.extension_name }}）</td>
                    <td class="text-end">{{ order.extension_price.toLocaleString() }}円</td>
                  </tr>
                  <tr v-if="order.nomination_fee_name">
                    <td>指名料（{{ order.nomination_fee_name }}）</td>
                    <td class="text-end">{{ order.nomination_fee_price.toLocaleString() }}円</td>
                  </tr>
                  <tr v-if="order.discount_name">
                    <td>割引（{{ order.discount_name }}）</td>
                    <td class="text-end text-danger">−{{ order.discount_amount.toLocaleString() }}円</td>
                  </tr>
                  <tr class="fw-bold">
                    <td>合計</td>
                    <td class="text-end">{{ order.total_price.toLocaleString() }}円</td>
                  </tr>
                  <tr v-if="isCardPayment" class="card-fee-row">
                    <td colspan="2" class="text-end">
                      <div class="order-card-fee">
                        <div class="order-card-fee__total">
                          カード決済時のお客様請求額（目安）:
                          <strong>{{ cardTotal.toLocaleString() }}円</strong>
                        </div>
                        <div class="order-card-fee__breakdown">
                          （{{ order.total_price.toLocaleString() }}円 ＋ 手数料10% {{ cardFee.toLocaleString() }}円）
                        </div>
                        <div class="order-card-fee__hint">※ 売上計上額は手数料を含みません</div>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="canOperateCardPayment" class="card mb-4 border-primary">
            <div class="card-header fw-bold">
              <i class="ti ti-credit-card me-1"></i>カード決済SMS
            </div>
            <div class="card-body">
              <div v-if="order.card_payment_confirmed_at" class="alert alert-success py-2 small">
                決済確認済み：{{ formatDt(order.card_payment_confirmed_at) }}
              </div>
              <div v-if="!order.room" class="alert alert-warning py-2 small">
                2通目を送る前にルームを確定してください。
              </div>
              <div class="d-grid gap-2">
                <button
                  class="btn btn-outline-primary"
                  :disabled="cardSmsActing"
                  @click="sendCardPaymentRequest"
                >
                  <i class="ti ti-link me-1"></i>決済リンクSMSを送信・再送
                </button>
                <button
                  class="btn btn-primary"
                  :disabled="cardSmsActing || !order.room || cardPaymentCompletedSmsSent"
                  @click="confirmCardPayment"
                >
                  <i class="ti ti-check me-1"></i>
                  {{ cardPaymentCompletedSmsSent ? '決済完了・住所SMS送信済み' : '決済確認・住所SMSを送信' }}
                </button>
              </div>
            </div>
          </div>

          <!-- SMS送信履歴（表示のみ） -->
          <div class="card mb-4">
            <div class="card-header d-flex align-items-center justify-content-between">
              <span><i class="ti ti-message-2"></i> SMS送信履歴</span>
              <button
                class="btn btn-outline-secondary btn-sm py-0"
                :disabled="smsLogsLoading"
                @click="fetchSmsLogs"
              >
                <i class="ti ti-refresh"></i> 更新
              </button>
            </div>
            <div class="card-body p-0">
              <div v-if="smsLogsLoading" class="text-muted text-center py-3 small">読み込み中...</div>
              <div v-else-if="smsLogsError" class="alert alert-danger m-3 py-2 px-3 small mb-0">
                {{ smsLogsError }}
              </div>
              <div v-else-if="!smsLogs.length" class="text-muted text-center py-3 small">
                SMS送信履歴はありません
              </div>
              <div v-else>
                <div v-for="log in smsLogs" :key="log.id" class="sms-row">
                  <div class="d-flex align-items-center justify-content-between">
                    <div class="sms-row__meta">
                      <span class="badge me-1" :class="smsStatusCls[log.status] || 'bg-secondary'">
                        {{ log.status_label }}
                      </span>
                      <span class="fw-bold">{{ formatDt(log.sent_at) }}</span>
                    </div>
                    <button class="btn btn-link btn-sm p-0" @click="toggleSmsBody(log.id)">
                      {{ isSmsExpanded(log.id) ? '閉じる' : '本文' }}
                    </button>
                  </div>
                  <div class="sms-row__sub text-muted">
                    {{ log.template_type_label }}
                    ／ 送信先: {{ log.to_phone || '—' }}
                    ／ 支払方法: {{ log.payment_method_label || '—' }}
                    <template v-if="log.created_by_name"> ／ 操作: {{ log.created_by_name }}</template>
                  </div>
                  <div v-if="!isSmsExpanded(log.id)" class="sms-row__preview text-muted">
                    {{ smsBodyPreview(log.body) }}
                  </div>
                  <pre v-else class="sms-row__body">{{ log.body }}</pre>
                  <div v-if="log.error_message" class="sms-row__error">
                    <i class="ti ti-alert-triangle"></i> {{ log.error_message }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- アクション -->
          <div class="d-flex flex-column gap-2 mb-3">
            <button
              v-if="canConfirm"
              class="btn btn-success btn-lg w-100"
              :disabled="acting"
              @click="doConfirm"
            >
              <i class="ti ti-check"></i> 予約確定
            </button>
            <button
              v-if="canDone"
              class="btn btn-primary btn-lg w-100"
              :disabled="acting"
              @click="doDone"
            >
              <i class="ti ti-circle-check"></i> {{ doneLabel }}
            </button>
          </div>

          <div class="d-flex gap-2 mb-4">
            <button
              v-if="canEdit"
              class="btn btn-outline-secondary flex-fill"
              @click="openEdit"
            >
              <i class="ti ti-edit"></i> 修正する
            </button>
            <button
              v-if="canCancel"
              class="btn btn-outline-danger flex-fill"
              :disabled="acting"
              @click="doCancel"
            >
              <i class="ti ti-x"></i> {{ cancelLabel }}
            </button>
          </div>

          <router-link to="/op/schedule" class="btn btn-outline-secondary w-100 mb-2">
            <i class="ti ti-calendar"></i> スケジュールに戻る
          </router-link>

          <div class="text-muted small text-center mt-3">
            Order #{{ order.id }} / 申請: {{ formatDt(order.created_at) }}
          </div>
        </template>

        <!-- ========== 修正モード ========== -->
        <template v-if="mode === 'edit'">

          <div class="d-flex align-items-center justify-content-between mb-3">
            <h5 class="mb-0"><i class="ti ti-edit"></i> 予約修正</h5>
            <button class="btn btn-outline-secondary btn-sm" @click="closeEdit">
              <i class="ti ti-arrow-left"></i> 戻る
            </button>
          </div>

          <!-- 基本情報編集（共通 OrderForm 雛形を利用） -->
          <div class="card mb-4">
            <div class="card-body">
              <OrderForm
                mode="edit"
                :order-id="order.id"
                :initial-order="order"
                :embedded="true"
                @updated="onOrderUpdated"
                @cancel="closeEdit"
              />
            </div>
          </div>

          <!-- addon 適用 -->
          <div class="card mb-4">
            <div class="card-header">
              <i class="ti ti-adjustments"></i> addon 適用
            </div>
            <div class="card-body">
              <div v-if="addonError" class="alert alert-danger py-2 px-3 mb-3" style="font-size:0.875rem;">{{ addonError }}</div>

              <div class="mb-3">
                <label class="form-label small fw-bold">延長</label>
                <div class="d-flex gap-2">
                  <select v-model="selectedExtension" class="form-select form-select-sm" @change="selectExtensionTemplate">
                    <option :value="null">なし</option>
                    <option v-for="e in extensions" :key="e.id" :value="e.id">
                      {{ e.name }}（{{ e.duration }}分 / {{ e.price.toLocaleString() }}円）
                    </option>
                  </select>
                  <button class="btn btn-outline-primary btn-sm" :disabled="addonActing" @click="doApplyExtension">適用</button>
                </div>
                <div class="form-text">候補を選んだ後でも、時間と料金を変更できます。</div>
                <div class="d-flex flex-wrap gap-2 mt-2">
                  <button
                    v-for="minutes in [0, 15, 30, 60]"
                    :key="minutes"
                    type="button"
                    class="btn btn-sm btn-outline-secondary"
                    @click="setExtensionDuration(minutes)"
                  >
                    {{ minutes === 0 ? '延長なし' : `${minutes}分` }}
                  </button>
                </div>
                <div class="row g-2 mt-1">
                  <div class="col-sm-6">
                    <label class="form-label small">延長時間（分）</label>
                    <input v-model.number="extensionDuration" type="number" min="0" max="180" step="5" class="form-control form-control-sm">
                  </div>
                  <div class="col-sm-6">
                    <label class="form-label small">延長料金（円）</label>
                    <input v-model.number="extensionPrice" type="number" min="0" step="100" class="form-control form-control-sm">
                  </div>
                </div>
              </div>

              <div class="mb-3">
                <label class="form-label small fw-bold">指名料</label>
                <div class="d-flex gap-2">
                  <select v-model="selectedNominationFee" class="form-select form-select-sm">
                    <option :value="null">なし</option>
                    <option v-for="n in nominationFees" :key="n.id" :value="n.id">
                      {{ n.name }}（{{ n.price.toLocaleString() }}円）
                    </option>
                  </select>
                  <button class="btn btn-outline-primary btn-sm" :disabled="addonActing" @click="doApplyNominationFee">適用</button>
                </div>
              </div>

              <div class="mb-0">
                <label class="form-label small fw-bold">割引</label>
                <div class="d-flex gap-2">
                  <select v-model="selectedDiscount" class="form-select form-select-sm">
                    <option :value="null">なし</option>
                    <option v-for="d in discounts" :key="d.id" :value="d.id">
                      {{ d.name }}（{{ d.discount_type === 'percent' ? d.value + '%' : d.value.toLocaleString() + '円' }}引き）
                    </option>
                  </select>
                  <button class="btn btn-outline-primary btn-sm" :disabled="addonActing" @click="doApplyDiscount">適用</button>
                </div>
              </div>
            </div>
          </div>

        </template>

      </main>
    </template>
  </LayoutOperator>
</template>

<style scoped>
.sms-row {
  padding: 0.625rem 1rem;
  border-bottom: 1px solid #f0f0f0;
  font-size: 0.85rem;
}
.sms-row:last-child {
  border-bottom: none;
}
.sms-row__sub {
  font-size: 0.75rem;
  margin-top: 2px;
}
.sms-row__preview {
  font-size: 0.78rem;
  margin-top: 4px;
}
.sms-row__body {
  background: #f7f7f7;
  padding: 0.5rem;
  border-radius: 4px;
  white-space: pre-wrap;
  font-size: 0.78rem;
  margin: 4px 0 0;
}
.sms-row__error {
  color: #b91c1c;
  font-size: 0.75rem;
  margin-top: 4px;
}
.card-fee-row td {
  background: #fff7ed;
  border-top: 1px dashed #fb923c;
}
.order-card-fee {
  font-size: 0.85rem;
  color: #7c2d12;
  text-align: right;
  line-height: 1.5;
}
.order-card-fee__total strong {
  color: #c2410c;
  font-size: 1rem;
  margin-left: 4px;
}
.order-card-fee__breakdown {
  font-size: 0.8rem;
  color: #9a3412;
}
.order-card-fee__hint {
  font-size: 0.72rem;
  color: #78350f;
  opacity: 0.85;
}
</style>
