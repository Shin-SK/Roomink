<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { routeStoreSlug } from '../../customerStore.js'

const route = useRoute()
const storeSlug = routeStoreSlug(route)

const stored = sessionStorage.getItem('roomink-public-booking-result')
let parsedResult = null
try {
  parsedResult = stored ? JSON.parse(stored) : null
} catch {
  parsedResult = null
}
const result = ref(parsedResult)

const startText = computed(() => {
  if (!result.value?.start) return ''
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'short',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(result.value.start))
})

function formatYen(value) {
  return `¥${Number(value || 0).toLocaleString()}`
}
</script>

<template>
  <div class="complete-page">
    <main class="complete-card">
      <img src="/logo.svg" alt="Roomink" class="complete-logo">
      <div class="complete-icon"><i class="ti ti-check"></i></div>
      <p class="complete-kicker">RESERVATION CONFIRMED</p>
      <h1>ご予約が確定しました</h1>
      <p class="text-muted">予約内容とお客様ページのご案内をSMSでお送りしました。</p>

      <div v-if="result" class="reservation-summary text-start">
        <div><span>予約番号</span><strong>#{{ result.id }}</strong></div>
        <div><span>店舗</span><strong>{{ result.store_name }}</strong></div>
        <div><span>日時</span><strong>{{ startText }}</strong></div>
        <div><span>担当</span><strong>{{ result.cast_name }}</strong></div>
        <div><span>コース</span><strong>{{ result.course_name }}</strong></div>
        <div><span>料金</span><strong>{{ formatYen(result.total_price) }}</strong></div>
        <div v-if="result.room_name"><span>ルーム</span><strong>{{ result.room_name }}</strong></div>
        <div v-if="result.room_address"><span>住所</span><strong>{{ result.room_address }}</strong></div>
      </div>
      <div v-else class="alert alert-info text-start">
        予約内容はSMSに記載されたURLから確認できます。
      </div>

      <div v-if="result?.sms_status && !['SENT', 'DUMMY'].includes(result.sms_status)" class="alert alert-warning text-start">
        予約は確定していますが、案内SMSの送信を確認できませんでした。店舗へお問い合わせください。
      </div>
      <p v-if="result?.account_setup_required" class="small text-muted">
        初めてのお客様には、SMSでパスワード設定用URLをご案内しています。
      </p>

      <router-link :to="storeSlug ? `/s/${storeSlug}/booking` : '/booking'" class="btn btn-outline-primary mt-3">別の予約をする</router-link>
    </main>
  </div>
</template>

<style scoped>
.complete-page { min-height: 100vh; background: #f6faf9; padding: 48px 12px; display: grid; place-items: start center; }
.complete-card { width: min(620px, 100%); background: #fff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 36px; text-align: center; box-shadow: 0 10px 28px rgba(15, 23, 42, .07); }
.complete-logo { width: 130px; height: auto; margin: 0 auto 28px; }
.complete-kicker { color: #2a9d8f; font-size: .78rem; font-weight: 900; letter-spacing: .13em; margin-bottom: 5px; }
.complete-card h1 { font-size: 1.7rem; font-weight: 800; margin-bottom: 10px; }
.complete-icon { width: 84px; height: 84px; margin: 0 auto 22px; border-radius: 50%; display: grid; place-items: center; background: #e8f6f3; color: #2a9d8f; font-size: 2.5rem; }
.reservation-summary { margin: 28px 0 18px; padding: 16px 20px; background: #f4f8f7; border-radius: 13px; }
.reservation-summary > div { display: flex; justify-content: space-between; gap: 22px; padding: 9px 0; border-bottom: 1px solid #e5eaee; }
.reservation-summary > div:last-child { border-bottom: 0; }
.reservation-summary span { color: #6c7883; flex-shrink: 0; }
@media (max-width: 576px) {
  .complete-page { padding-top: 20px; }
  .complete-card { padding: 26px 18px; }
  .reservation-summary > div { flex-direction: column; gap: 2px; }
}
</style>
