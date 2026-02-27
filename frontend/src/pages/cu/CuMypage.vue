<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../../api.js'

const route = useRoute()

const loading = ref(true)
const error = ref('')
const customer = ref(null)
const nextReservation = ref(null)
const favorites = ref([])
const recommended = ref([])
const history = ref([])
const activeTab = ref('fav')

const stores = ref([])
const drawerOpen = ref(false)
const selectedStoreId = ref(null)

const currentStoreName = computed(() => {
  const s = stores.value.find(s => s.store_id === selectedStoreId.value)
  return s ? s.store_name : ''
})

const storeQ = computed(() => selectedStoreId.value ? '?store=' + selectedStoreId.value : '')

onMounted(async () => {
  try {
    const storeData = await api.getCustomerStores()
    stores.value = storeData.stores

    if (route.query.store) {
      selectedStoreId.value = Number(route.query.store)
    } else if (stores.value.length === 1) {
      selectedStoreId.value = stores.value[0].store_id
    } else if (stores.value.length > 1) {
      drawerOpen.value = true
      loading.value = false
      return
    }

    const data = await api.getCustomerMypage(selectedStoreId.value)
    customer.value = data.customer
    nextReservation.value = data.next_reservation
    favorites.value = data.favorites
    recommended.value = data.recommended
    history.value = data.history
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function switchStore(storeId) {
  drawerOpen.value = false
  window.location.href = '/cu/mypage?store=' + storeId
}

function formatYen(n) {
  return `¥${Number(n).toLocaleString()}`
}

function formatDate(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  const days = ['日','月','火','水','木','金','土']
  const mm = String(d.getMonth()+1).padStart(2,'0')
  const dd = String(d.getDate()).padStart(2,'0')
  const hh = String(d.getHours()).padStart(2,'0')
  const mi = String(d.getMinutes()).padStart(2,'0')
  return `${d.getFullYear()}-${mm}-${dd} (${days[d.getDay()]}) ${hh}:${mi}`
}

function formatDateRange(start, end) {
  const s = formatDate(start)
  const e = new Date(end)
  const hh = String(e.getHours()).padStart(2,'0')
  const mi = String(e.getMinutes()).padStart(2,'0')
  return `${s} – ${hh}:${mi}`
}

function statusLabel(s) {
  const m = { REQUESTED: '申請中', CONFIRMED: '承認済', IN_PROGRESS: '施術中', DONE: '完了', CANCELLED: 'キャンセル' }
  return m[s] || s
}

function statusBadge(s) {
  if (s === 'CONFIRMED') return 'badge-approved'
  if (s === 'REQUESTED') return 'badge-pending'
  return 'badge-primary'
}
</script>

<template>
  <div class="customer-layout has-bottomnav">
    <!-- Store Drawer -->
    <div v-if="stores.length > 1" class="rk-store-overlay" :class="{ show: drawerOpen }" @click="drawerOpen = false"></div>
    <aside v-if="stores.length > 1" class="rk-store-drawer" :class="{ show: drawerOpen }">
      <div class="rk-store-drawer__header">
        <span>店舗を選択</span>
        <button class="btn-close" @click="drawerOpen = false"></button>
      </div>
      <div class="rk-store-drawer__list">
        <button
          v-for="s in stores" :key="s.store_id"
          class="rk-store-drawer__item" :class="{ active: s.store_id === selectedStoreId }"
          @click="switchStore(s.store_id)"
        >
          <div class="rk-store-drawer__logo">
            <i class="ti ti-building-store" style="font-size:20px; color:var(--rk-primary)"></i>
          </div>
          <span class="rk-store-drawer__name">{{ s.store_name }}</span>
        </button>
      </div>
    </aside>

    <header class="customer-header">
      <div class="customer-nav">
        <a href="/cu/mypage"><img src="/icon.svg" alt="" style="width: 24px;"></a>
        <button v-if="stores.length > 1" class="rk-store-btn" @click="drawerOpen = true">
          <i class="ti ti-building-store"></i>
          {{ currentStoreName }}
          <i class="ti ti-chevron-down" style="font-size:14px;"></i>
        </button>
      </div>
    </header>

    <main class="customer-content container">
      <div style="max-width: 640px; margin: 0 auto;">

        <div v-if="loading" class="text-center py-5">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

        <template v-else>
          <!-- あいさつ -->
          <p class="text-muted mb-3">こんにちは、{{ customer.display_name }}様</p>

          <!-- 予約カード -->
          <div v-if="nextReservation" class="rk-booking-card mb-4">
            <div class="rk-booking-card__label"><i class="ti ti-calendar-event"></i> 次回のご予約</div>
            <div class="rk-booking-card__date">{{ formatDateRange(nextReservation.start, nextReservation.end) }}</div>
            <div class="rk-booking-card__info"><i class="ti ti-user"></i> {{ nextReservation.cast_name }} / {{ nextReservation.course_name }}</div>
            <div class="rk-booking-card__info"><i class="ti ti-currency-yen"></i> {{ formatYen(nextReservation.total_price) }}</div>
            <span class="rk-booking-card__badge">{{ statusLabel(nextReservation.status) }}</span>
          </div>

          <!-- 予約なし -->
          <div v-else class="rk-booking-card rk-booking-card--empty mb-4">
            <div class="rk-booking-card__label"><i class="ti ti-calendar-off"></i> 次回のご予約</div>
            <p class="mb-2" style="font-size:1.125rem; font-weight:600;">次回予約はありません</p>
            <a :href="'/cu/booking' + storeQ" class="rk-booking-card__cta">予約する</a>
          </div>

          <!-- タブUI -->
          <div id="fav" class="mb-4">
            <nav class="rk-tabs">
              <button class="rk-tabs__btn" :class="activeTab === 'fav' ? 'active' : ''" @click="activeTab = 'fav'"><i class="ti ti-heart"></i> 推し</button>
              <button class="rk-tabs__btn" :class="activeTab === 'foryou' ? 'active' : ''" @click="activeTab = 'foryou'"><i class="ti ti-stars"></i> おすすめ</button>
              <button class="rk-tabs__btn" :class="activeTab === 'picks' ? 'active' : ''" @click="activeTab = 'picks'"><i class="ti ti-sparkles"></i> 運営</button>
            </nav>

            <!-- 推し -->
            <div v-if="activeTab === 'fav'">
              <div v-if="favorites.length > 0" v-for="fav in favorites" :key="fav.id" class="rk-fav-card">
                <img v-if="fav.avatar_url" :src="fav.avatar_url" :alt="fav.name" class="rk-fav-card__img">
                <div v-else class="rk-fav-card__img d-flex align-items-center justify-content-center bg-light" style="height:240px;">
                  <i class="ti ti-user" style="font-size:64px; color:var(--rk-primary)"></i>
                </div>
                <div class="rk-fav-card__body">
                  <div class="d-flex align-items-center justify-content-between mb-2">
                    <h4 class="mb-0 fw-bold">{{ fav.name }}</h4>
                    <span class="badge badge-approved">推しセラピスト</span>
                  </div>
                  <p class="text-muted mb-3">指名回数: {{ fav.visit_count }}回 / 累計: {{ formatYen(fav.total_spend) }}</p>
                  <a :href="`/cu/booking?cast=${fav.id}${selectedStoreId ? '&store=' + selectedStoreId : ''}`" class="btn btn-primary btn-block">
                    <i class="ti ti-calendar-plus"></i> {{ fav.name }}を指名予約
                  </a>
                </div>
              </div>
              <div v-else class="text-muted text-center py-4">まだ推しセラピストはいません</div>
            </div>

            <!-- おすすめ -->
            <div v-if="activeTab === 'foryou'">
              <p class="text-muted small mb-2">おすすめのセラピスト</p>
              <div class="rk-hscroll">
                <div v-for="r in recommended" :key="r.id" class="rk-hscroll__card">
                  <img v-if="r.avatar_url" :src="r.avatar_url" :alt="r.name" class="rk-hscroll__img">
                  <div v-else class="rk-hscroll__img d-flex align-items-center justify-content-center bg-light">
                    <i class="ti ti-user" style="font-size:40px; color:var(--rk-primary)"></i>
                  </div>
                  <div class="rk-hscroll__body">
                    <div class="rk-hscroll__name">{{ r.name }}</div>
                    <a :href="`/cu/booking?cast=${r.id}${selectedStoreId ? '&store=' + selectedStoreId : ''}`" class="btn btn-sm btn-primary w-100">予約する</a>
                  </div>
                </div>
              </div>
              <div v-if="recommended.length === 0" class="text-muted text-center py-4">おすすめはまだありません</div>
            </div>

            <!-- 運営おすすめ -->
            <div v-if="activeTab === 'picks'">
              <div class="rk-campaign">
                <div class="rk-campaign__title"><i class="ti ti-discount-2"></i> 新規セラピストデビュー！</div>
                <div class="rk-campaign__text">キャンペーン情報は随時更新されます</div>
              </div>
            </div>
          </div>

          <!-- 来店履歴 -->
          <div class="mb-4" id="history">
            <div class="rk-section-header"><i class="ti ti-history"></i> 来店履歴</div>
            <div class="card">
              <div class="card-body p-0 px-3">
                <div v-for="h in history" :key="h.id" class="rk-history-item">
                  <div>
                    <div class="rk-history-date">{{ h.date }}</div>
                    <div class="rk-history-meta">{{ h.cast_name }} / {{ h.course_name }}</div>
                  </div>
                  <div class="d-flex align-items-center gap-2">
                    <span class="fw-bold">{{ formatYen(h.total_price) }}</span>
                  </div>
                </div>
                <div v-if="history.length === 0" class="text-muted text-center py-3">履歴はありません</div>
              </div>
            </div>
          </div>

          <!-- 登録情報 -->
          <div class="mb-4">
            <div class="rk-section-header"><i class="ti ti-user"></i> 登録情報</div>
            <div class="card">
              <div class="card-body">
                <table class="table table-sm mb-0">
                  <tbody>
                    <tr><th style="width:120px;">お名前</th><td>{{ customer.display_name }}</td></tr>
                    <tr><th>電話番号</th><td>{{ customer.phone }}</td></tr>
                    <tr><th>来店回数</th><td>{{ customer.total_visits }}回</td></tr>
                    <tr><th>累計利用額</th><td>{{ formatYen(customer.total_spend) }}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

        </template>
      </div>
    </main>

    <!-- Fixed Bottom Nav -->
    <nav class="rk-bottomnav">
      <a :href="'/cu/mypage' + storeQ" class="rk-bottomnav__item active">
        <i class="ti ti-home"></i>HOME
      </a>
      <a :href="'/cu/booking' + storeQ" class="rk-bottomnav__item">
        <i class="ti ti-calendar-plus"></i>予約
      </a>
      <a :href="'/cu/mypage' + storeQ + '#fav'" class="rk-bottomnav__item">
        <i class="ti ti-heart"></i>推し
      </a>
      <a href="tel:03-1234-5678" class="rk-bottomnav__item">
        <i class="ti ti-phone"></i>問い合わせ
      </a>
    </nav>
  </div>
</template>
