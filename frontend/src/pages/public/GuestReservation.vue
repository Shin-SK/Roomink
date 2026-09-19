<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../../api.js'

const route = useRoute()
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const reservation = ref(null)
const paymentOpened = ref(false)

const stateClass = computed(() => ({
  REQUESTED: 'is-pending',
  PAYMENT_REQUIRED: 'is-payment',
  CONFIRMED: 'is-confirmed',
  IN_PROGRESS: 'is-confirmed',
  COMPLETED: 'is-completed',
  CANCELLED: 'is-cancelled',
}[reservation.value?.state] || 'is-pending'))

const dateText = computed(() => {
  if (!reservation.value?.start) return ''
  const start = new Date(reservation.value.start)
  const end = new Date(reservation.value.end)
  const date = new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'short',
  }).format(start)
  const time = new Intl.DateTimeFormat('ja-JP', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
  return `${date} ${time.format(start)}〜${time.format(end)}`
})

const cardPaymentBase = computed(() => Math.max(
  0,
  Number(reservation.value?.total_price || 0) - Number(reservation.value?.cash_due_on_site || 0),
))

const cardPaymentFee = computed(() => Math.max(
  0,
  Number(reservation.value?.payment_amount || 0) - cardPaymentBase.value,
))

function formatYen(value) {
  return `¥${Number(value || 0).toLocaleString()}`
}

function phoneHref(value) {
  return `tel:${String(value || '').replace(/[^\d+]/g, '')}`
}

function formatTimelineDate(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('ja-JP', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value))
}

async function loadReservation(isRefresh = false) {
  if (isRefresh) refreshing.value = true
  else loading.value = true
  error.value = ''
  try {
    reservation.value = await api.getGuestReservation(route.params.token)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function openPayment() {
  paymentOpened.value = true
}

onMounted(() => {
  document.title = 'ご予約内容 | Roomink'
  let robots = document.querySelector('meta[name="robots"]')
  if (!robots) {
    robots = document.createElement('meta')
    robots.name = 'robots'
    document.head.appendChild(robots)
  }
  robots.content = 'noindex,nofollow,noarchive'
  loadReservation()
})
</script>

<template>
  <div class="guest-page">
    <main class="guest-shell">
      <header class="guest-header">
        <img src="/logo.svg" alt="Roomink" class="guest-logo">
        <span>予約確認サービス</span>
      </header>

      <div v-if="loading" class="guest-loading">
        <div class="spinner-border text-primary" role="status"></div>
        <p>予約内容を確認しています</p>
      </div>

      <section v-else-if="error" class="guest-error">
        <i class="ti ti-link-off"></i>
        <h1>予約情報を表示できません</h1>
        <p>{{ error }}</p>
      </section>

      <template v-else-if="reservation">
        <section class="status-card" :class="stateClass">
          <div class="status-label">{{ reservation.state_label }}</div>
          <h1>{{ reservation.title }}</h1>
          <p>{{ reservation.message }}</p>
        </section>

        <section v-if="reservation.payment_required" class="payment-card">
          <div class="section-kicker">CARD PAYMENT</div>
          <h2>カード決済のお手続き</h2>
          <div class="payment-amount">
            <span>決済金額</span>
            <strong>{{ formatYen(reservation.payment_amount) }}</strong>
          </div>
          <div class="payment-breakdown">
            <div>
              <span>カード決済対象額</span>
              <strong>{{ formatYen(cardPaymentBase) }}</strong>
            </div>
            <div>
              <span>カード決済手数料</span>
              <strong>{{ formatYen(cardPaymentFee) }}</strong>
            </div>
          </div>
          <p v-if="reservation.cash_due_on_site" class="payment-note">
            別途、来店時に現金でお支払いいただく金額：{{ formatYen(reservation.cash_due_on_site) }}
          </p>
          <a
            v-if="reservation.payment_url"
            :href="reservation.payment_url"
            target="_blank"
            rel="noopener noreferrer"
            class="payment-button"
            @click="openPayment"
          >
            カード決済へ進む
            <i class="ti ti-external-link"></i>
          </a>
          <div v-else class="alert alert-warning mb-0">
            決済ページを準備しています。店舗へお問い合わせください。
          </div>
          <p class="payment-help">
            決済ページは別画面で開きます。決済後、店舗での確認をもって本予約となります。
          </p>
          <div v-if="paymentOpened" class="payment-waiting">
            <strong>決済後は店舗での確認をお待ちください</strong>
            <span>確認後、予約確定のSMSをお送りします。</span>
          </div>
        </section>

        <section class="detail-card">
          <div class="section-kicker">RESERVATION</div>
          <h2>ご予約内容</h2>
          <dl>
            <div><dt>店舗</dt><dd>{{ reservation.store_name }}</dd></div>
            <div><dt>日時</dt><dd>{{ dateText }}</dd></div>
            <div><dt>担当</dt><dd>{{ reservation.cast_name }}</dd></div>
            <div><dt>コース</dt><dd>{{ reservation.course_name }}</dd></div>
            <div><dt>料金</dt><dd>{{ formatYen(reservation.total_price) }}</dd></div>
            <div><dt>お支払い</dt><dd>{{ reservation.payment_method_label }}</dd></div>
          </dl>
        </section>

        <section v-if="reservation.room_name || reservation.room_address" class="room-card">
          <div class="section-kicker">GUIDANCE</div>
          <h2>当日のご案内</h2>
          <div v-if="reservation.room_name" class="room-name">{{ reservation.room_name }}</div>
          <p v-if="reservation.room_address" class="room-address">{{ reservation.room_address }}</p>
          <p v-if="reservation.room_notice" class="room-notice">{{ reservation.room_notice }}</p>
          <a
            v-if="reservation.room_map_url"
            :href="reservation.room_map_url"
            target="_blank"
            rel="noopener noreferrer"
            class="map-link"
          ><i class="ti ti-map-pin"></i> 地図を開く</a>
        </section>

        <section
          v-else-if="reservation.payment_required"
          class="guidance-pending-card"
        >
          <i class="ti ti-lock"></i>
          <div>
            <h2>当日のご案内について</h2>
            <p>ルーム名・住所・地図は、店舗がカード決済を確認して本予約になった後、このページに表示されます。</p>
          </div>
        </section>

        <section class="timeline-card">
          <div class="section-kicker">TIMELINE</div>
          <h2>予約状況</h2>
          <ol>
            <li v-for="event in reservation.timeline" :key="`${event.type}-${event.occurred_at}`">
              <span class="timeline-dot"></span>
              <div>
                <strong>{{ event.label }}</strong>
                <time>{{ formatTimelineDate(event.occurred_at) }}</time>
              </div>
            </li>
          </ol>
        </section>

        <button class="refresh-button" :disabled="refreshing" @click="loadReservation(true)">
          <i class="ti ti-refresh" :class="{ 'spin': refreshing }"></i>
          {{ refreshing ? '確認中…' : '最新の状態を確認' }}
        </button>

        <section v-if="reservation.contact_phone" class="contact-card">
          <div>
            <div class="section-kicker">CONTACT</div>
            <h2>ご予約店舗へのお問い合わせ</h2>
            <p>予約内容の変更やご不明点は、店舗へ直接お電話ください。</p>
          </div>
          <a :href="phoneHref(reservation.contact_phone)" class="contact-button">
            <i class="ti ti-phone"></i>
            {{ reservation.contact_phone }}
          </a>
        </section>

        <p v-if="!reservation.contact_phone" class="guest-footer">
          決済・予約内容については、ご予約店舗へ直接お問い合わせください。
        </p>
      </template>
    </main>
  </div>
</template>

<style scoped>
.guest-page { min-height: 100vh; background: #f4f7f6; color: #17221f; padding: 0 12px 56px; }
.guest-shell { width: min(620px, 100%); margin: 0 auto; }
.guest-header { min-height: 74px; display: flex; align-items: center; justify-content: space-between; color: #64716d; font-size: .75rem; font-weight: 700; letter-spacing: .05em; }
.guest-logo { width: 112px; height: auto; }
.guest-loading, .guest-error { margin-top: 32px; padding: 52px 24px; border-radius: 22px; background: #fff; text-align: center; box-shadow: 0 10px 30px rgba(18, 40, 33, .06); }
.guest-loading p { margin: 14px 0 0; color: #66736f; }
.guest-error i { font-size: 2.6rem; color: #9a5a5a; }
.guest-error h1 { margin: 16px 0 10px; font-size: 1.35rem; }
.status-card, .payment-card, .detail-card, .room-card, .guidance-pending-card, .timeline-card, .contact-card { margin-bottom: 14px; padding: 24px; border: 1px solid #dfe7e4; border-radius: 20px; background: #fff; box-shadow: 0 7px 24px rgba(18, 40, 33, .045); }
.status-card { border: 0; color: #fff; background: #63736e; }
.status-card.is-payment { background: linear-gradient(135deg, #9c6b19, #c18a2e); }
.status-card.is-confirmed { background: linear-gradient(135deg, #197c6e, #2a9d8f); }
.status-card.is-completed { background: linear-gradient(135deg, #45655f, #667b76); }
.status-card.is-cancelled { background: linear-gradient(135deg, #684a4a, #8b5e5e); }
.status-label { display: inline-flex; padding: 5px 10px; border-radius: 999px; background: rgba(255,255,255,.18); font-size: .75rem; font-weight: 800; }
.status-card h1 { margin: 15px 0 8px; font-size: clamp(1.45rem, 6vw, 1.9rem); font-weight: 900; }
.status-card p { margin: 0; line-height: 1.7; opacity: .92; }
.section-kicker { margin-bottom: 5px; color: #2a9d8f; font-size: .68rem; font-weight: 900; letter-spacing: .14em; }
h2 { margin: 0 0 18px; font-size: 1.15rem; font-weight: 900; }
.payment-card { border-color: #e2c58e; background: #fffdf8; }
.payment-amount { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 14px; padding: 14px 0; border-block: 1px solid #eee1c8; }
.payment-amount span { color: #76674e; font-size: .85rem; }
.payment-amount strong { font-size: 1.65rem; }
.payment-breakdown { display: grid; gap: 8px; margin: -3px 0 14px; padding: 12px 14px; border-radius: 10px; background: #f8f3e8; }
.payment-breakdown > div { display: flex; align-items: center; justify-content: space-between; gap: 14px; color: #625944; font-size: .82rem; }
.payment-breakdown strong { color: #2c2b27; }
.payment-note { color: #705b38; font-size: .8rem; line-height: 1.6; }
.payment-button { min-height: 54px; display: flex; align-items: center; justify-content: center; gap: 8px; border-radius: 13px; background: #1f8174; color: #fff; font-weight: 900; text-decoration: none; box-shadow: 0 6px 16px rgba(31, 129, 116, .22); }
.payment-help { margin: 12px 0 0; color: #6b736f; font-size: .78rem; line-height: 1.65; }
.payment-waiting { display: grid; gap: 3px; margin-top: 14px; padding: 12px; border-radius: 10px; background: #f2ede3; font-size: .8rem; }
.payment-waiting span { color: #6f685a; }
dl { margin: 0; }
dl > div { display: grid; grid-template-columns: 88px 1fr; gap: 14px; padding: 11px 0; border-bottom: 1px solid #edf1ef; }
dl > div:last-child { border-bottom: 0; }
dt { color: #71807b; font-size: .82rem; font-weight: 700; }
dd { margin: 0; font-weight: 800; text-align: right; }
.room-name { margin-bottom: 8px; font-size: 1.2rem; font-weight: 900; }
.room-address, .room-notice { white-space: pre-wrap; line-height: 1.7; }
.room-notice { padding: 12px; border-radius: 10px; background: #f3f7f6; font-size: .84rem; }
.map-link { display: inline-flex; align-items: center; gap: 5px; color: #197c6e; font-weight: 800; text-decoration: none; }
.guidance-pending-card { display: flex; gap: 14px; align-items: flex-start; border-color: #e2c58e; background: #fffdf8; }
.guidance-pending-card > i { flex: 0 0 auto; display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%; background: #f3e6ca; color: #96691f; font-size: 1.1rem; }
.guidance-pending-card h2 { margin-bottom: 8px; }
.guidance-pending-card p { margin: 0; color: #6f685a; font-size: .84rem; line-height: 1.7; }
.timeline-card ol { margin: 0; padding: 0; list-style: none; }
.timeline-card li { position: relative; display: grid; grid-template-columns: 18px 1fr; gap: 10px; padding-bottom: 18px; }
.timeline-card li:not(:last-child)::before { content: ''; position: absolute; left: 6px; top: 13px; bottom: 0; width: 2px; background: #dce8e4; }
.timeline-dot { width: 14px; height: 14px; margin-top: 3px; border: 3px solid #b9d8d1; border-radius: 50%; background: #2a9d8f; z-index: 1; }
.timeline-card li > div { display: flex; justify-content: space-between; gap: 14px; }
.timeline-card strong { font-size: .88rem; }
.timeline-card time { flex: 0 0 auto; color: #7d8a86; font-size: .75rem; }
.refresh-button { width: 100%; min-height: 48px; border: 1px solid #b8cbc5; border-radius: 13px; background: #fff; color: #286e64; font-weight: 800; }
.refresh-button:disabled { opacity: .65; }
.contact-card { display: grid; gap: 15px; }
.contact-card h2 { margin-bottom: 8px; }
.contact-card p { margin: 0; color: #66736f; font-size: .84rem; line-height: 1.65; }
.contact-button { min-height: 52px; display: flex; align-items: center; justify-content: center; gap: 8px; border: 1px solid #197c6e; border-radius: 13px; color: #197c6e; font-size: 1.05rem; font-weight: 900; text-decoration: none; }
.contact-button:hover { background: #eef8f5; color: #176e63; }
.spin { animation: spin .8s linear infinite; }
.guest-footer { margin: 22px 12px 0; color: #7b8783; font-size: .75rem; line-height: 1.65; text-align: center; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 480px) {
  .guest-page { padding-inline: 9px; }
  .status-card, .payment-card, .detail-card, .room-card, .guidance-pending-card, .timeline-card, .contact-card { padding: 20px 17px; border-radius: 17px; }
  .timeline-card li > div { display: grid; gap: 3px; }
  dd { font-size: .9rem; }
}
</style>
