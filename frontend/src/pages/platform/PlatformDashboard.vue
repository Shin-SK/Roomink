<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api.js'
import { resetAuthCache } from '../../router.js'

const router = useRouter()
const loading = ref(true)
const switchingId = ref(null)
const error = ref('')
const data = ref({ stores: [], active_store_id: null, month: '' })

const totals = computed(() => data.value.stores.reduce((sum, store) => ({
  stores: sum.stores + 1,
  calls: sum.calls + store.calls.count,
  seconds: sum.seconds + store.calls.duration_seconds,
  sms: sum.sms + store.sms.used_segments,
}), { stores: 0, calls: 0, seconds: 0, sms: 0 }))

function formatDuration(seconds) {
  const value = Number(seconds || 0)
  const hours = Math.floor(value / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  if (hours) return `${hours}時間${minutes}分`
  return `${minutes}分`
}

function formatPhone(value) {
  const digits = String(value || '').replace(/\D/g, '')
  if (digits.length === 11) return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`
  if (digits.length === 10) return `${digits.slice(0, 2)}-${digits.slice(2, 6)}-${digits.slice(6)}`
  return value || '未設定'
}

function formatDate(value) {
  if (!value) return '記録なし'
  return new Intl.DateTimeFormat('ja-JP', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.getPlatformDashboard()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

async function openStore(store) {
  switchingId.value = store.id
  error.value = ''
  try {
    await api.setPlatformActiveStore(store.id)
    resetAuthCache()
    router.push('/op/dashboard')
  } catch (err) {
    error.value = err.message
  } finally {
    switchingId.value = null
  }
}

async function openPhoneSettings(store) {
  switchingId.value = store.id
  error.value = ''
  try {
    await api.setPlatformActiveStore(store.id)
    resetAuthCache()
    router.push('/op/settings/phones')
  } catch (err) {
    error.value = err.message
  } finally {
    switchingId.value = null
  }
}

async function logout() {
  try { await api.logout() } catch { /* ignore */ }
  resetAuthCache()
  router.push('/login')
}

onMounted(load)
</script>

<template>
  <div class="platform-page">
    <header class="platform-header">
      <img src="/logo.svg" alt="Roomink" class="platform-logo">
      <div class="platform-header__actions">
        <router-link to="/op/settings/phones" class="btn btn-outline-primary btn-sm">
          <i class="ti ti-phone"></i> 電話設定
        </router-link>
        <button class="btn btn-outline-secondary btn-sm" @click="logout">ログアウト</button>
      </div>
    </header>

    <main class="platform-main">
      <div class="platform-title">
        <div>
          <p class="platform-kicker">ROOMINK OPERATIONS</p>
          <h1>運営ダッシュボード</h1>
          <p>{{ data.month }} の通信利用と稼働状況</p>
        </div>
      </div>

      <div v-if="error" class="alert alert-danger">{{ error }}</div>
      <div v-if="loading" class="platform-loading"><span class="spinner-border text-primary"></span></div>
      <template v-else>
        <section class="platform-summary">
          <article><span>店舗</span><strong>{{ totals.stores }}</strong></article>
          <article><span>通話</span><strong>{{ totals.calls }}件</strong></article>
          <article><span>通話時間</span><strong>{{ formatDuration(totals.seconds) }}</strong></article>
          <article><span>SMS</span><strong>{{ totals.sms }}通分</strong></article>
        </section>

        <section class="platform-grid">
          <article v-for="store in data.stores" :key="store.id" class="store-ops-card">
            <div class="store-ops-card__head">
              <div>
                <div class="store-ops-card__name">{{ store.name }}</div>
                <div class="store-ops-card__slug">/s/{{ store.slug }}</div>
              </div>
              <span class="ops-status" :class="store.connection_ready ? 'is-ready' : 'is-warning'">
                {{ store.connection_ready ? '接続準備済み' : '要確認' }}
              </span>
            </div>

            <dl class="ops-details">
              <div><dt>店舗番号</dt><dd>{{ formatPhone(store.contact_phone) }}</dd></div>
              <div><dt>受付番号</dt><dd>{{ store.phones.map((phone) => formatPhone(phone.phone)).join(' / ') || '未設定' }}</dd></div>
              <div><dt>受付端末</dt><dd>{{ store.devices.map((device) => device.label).join(' / ') || '未設定' }}</dd></div>
              <div><dt>最終着信</dt><dd>{{ formatDate(store.calls.last_at) }}</dd></div>
            </dl>

            <div class="ops-metrics">
              <div><span>通話</span><strong>{{ store.calls.count }}件</strong><small>{{ formatDuration(store.calls.duration_seconds) }}</small></div>
              <div><span>未対応</span><strong :class="{ 'text-danger': store.calls.unresolved }">{{ store.calls.unresolved }}件</strong><small>現在</small></div>
              <div><span>SMS</span><strong>{{ store.sms.used_segments }}通分</strong><small>{{ store.sms.current_block_limit }}通分まで</small></div>
              <div><span>月額見込</span><strong>{{ store.sms.billed_price.toLocaleString() }}円</strong><small v-if="store.sms.billing_exempt">検証店免除</small><small v-else>税込別</small></div>
            </div>

            <div class="store-ops-card__actions">
              <button class="btn btn-primary" :disabled="switchingId === store.id" @click="openStore(store)">
                {{ switchingId === store.id ? '切替中…' : 'この店舗の画面を開く' }}
              </button>
              <button class="btn btn-outline-primary" :disabled="switchingId === store.id" @click="openPhoneSettings(store)">
                電話設定
              </button>
            </div>
          </article>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.platform-page { min-height: 100dvh; background: #f5f8f7; color: #22312e; }
.platform-header { min-height: 72px; padding: 14px clamp(18px, 4vw, 48px); display: flex; align-items: center; justify-content: space-between; gap: 16px; background: #fff; border-bottom: 1px solid #dce6e3; position: sticky; top: 0; z-index: 10; }
.platform-logo { height: 42px; max-width: 180px; }
.platform-header__actions { display: flex; gap: 8px; }
.platform-main { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 38px 0 72px; }
.platform-kicker { margin: 0 0 5px; color: #2a9d8f; font-size: .74rem; font-weight: 800; letter-spacing: .14em; }
.platform-title h1 { margin: 0; font-size: clamp(1.7rem, 4vw, 2.35rem); font-weight: 800; }
.platform-title p:last-child { margin: 7px 0 0; color: #687873; }
.platform-loading { min-height: 300px; display: grid; place-items: center; }
.platform-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 28px 0; }
.platform-summary article { padding: 18px 20px; background: #fff; border: 1px solid #dce6e3; border-radius: 14px; }
.platform-summary span { display: block; color: #71817c; font-size: .82rem; }
.platform-summary strong { display: block; margin-top: 5px; font-size: 1.5rem; }
.platform-grid { display: grid; gap: 18px; }
.store-ops-card { padding: 24px; background: #fff; border: 1px solid #dce6e3; border-radius: 18px; box-shadow: 0 8px 28px rgba(34, 49, 46, .05); }
.store-ops-card__head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.store-ops-card__name { font-size: 1.25rem; font-weight: 800; }
.store-ops-card__slug { color: #7a8985; font-size: .82rem; }
.ops-status { padding: 5px 10px; border-radius: 999px; font-size: .76rem; font-weight: 700; white-space: nowrap; }
.ops-status.is-ready { color: #137b69; background: #e1f6f0; }
.ops-status.is-warning { color: #a45c12; background: #fff0dc; }
.ops-details { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 24px; padding: 18px 0; margin: 0; }
.ops-details div { display: grid; grid-template-columns: 82px 1fr; gap: 8px; }
.ops-details dt { color: #7a8985; font-size: .78rem; }
.ops-details dd { margin: 0; font-weight: 600; overflow-wrap: anywhere; }
.ops-metrics { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid #e1e9e7; border-radius: 12px; overflow: hidden; }
.ops-metrics > div { padding: 14px; border-right: 1px solid #e1e9e7; }
.ops-metrics > div:last-child { border-right: 0; }
.ops-metrics span, .ops-metrics small { display: block; color: #71817c; font-size: .75rem; }
.ops-metrics strong { display: block; margin: 3px 0; font-size: 1.08rem; }
.store-ops-card__actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
@media (max-width: 720px) {
  .platform-header { align-items: flex-start; }
  .platform-logo { height: 34px; }
  .platform-header__actions { flex-direction: column; }
  .platform-main { width: min(100% - 24px, 1180px); padding-top: 24px; }
  .platform-summary { grid-template-columns: repeat(2, 1fr); }
  .store-ops-card { padding: 18px; }
  .ops-details { grid-template-columns: 1fr; }
  .ops-metrics { grid-template-columns: repeat(2, 1fr); }
  .ops-metrics > div:nth-child(2) { border-right: 0; }
  .ops-metrics > div:nth-child(-n+2) { border-bottom: 1px solid #e1e9e7; }
  .store-ops-card__actions { flex-direction: column; }
}
</style>
