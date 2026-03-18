<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import { resetAuthCache } from '../router.js'
import UserAvatar from './UserAvatar.vue'

const route = useRoute()
const router = useRouter()

const stores = ref([])
const selectedStoreId = ref(null)
const drawerOpen = ref(false)
const sidebarOpen = ref(false)
const currentUser = ref(null)

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
    }
  } catch { /* ignore */ }
  try { currentUser.value = await api.me() } catch { /* ignore */ }
})

const sidebarItems = [
  { to: '/cu/mypage', icon: 'ti-home', label: 'マイページ' },
  { to: '/cu/booking', icon: 'ti-calendar-plus', label: '予約' },
  { to: '/cu/contact', icon: 'ti-help', label: 'お問い合わせ' },
]

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function closeSidebar() {
  sidebarOpen.value = false
}

function switchStore(storeId) {
  drawerOpen.value = false
  window.location.href = route.path + '?store=' + storeId
}

async function onLogout() {
  try { await api.logout() } catch { /* ignore */ }
  resetAuthCache()
  router.push('/cu/login')
}

function onDocClick(e) {
  const sidebar = document.querySelector('.cu-sidebar')
  const btn = document.querySelector('.cu-menu-btn')
  if (
    sidebarOpen.value &&
    sidebar && !sidebar.contains(e.target) &&
    btn && !btn.contains(e.target)
  ) {
    sidebarOpen.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div class="customer-layout has-bottomnav">
    <!-- Store Drawer (多店舗切替) -->
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

    <!-- Sidebar -->
    <aside class="sidebar cu-sidebar" :class="{ show: sidebarOpen }">
      <div class="sidebar-header">
        <router-link to="/cu/mypage" class="sidebar-brand" @click="closeSidebar">
          <img style="height: 40px;" src="/logo.svg" alt="Roomink Logo">
        </router-link>
      </div>
      <nav class="sidebar-nav">
        <ul class="nav-item">
          <li v-for="item in sidebarItems" :key="item.to">
            <router-link
              :to="item.to + storeQ"
              class="nav-link"
              :class="{ active: route.path === item.to }"
              @click="closeSidebar"
            >
              <i class="ti" :class="item.icon"></i>{{ item.label }}
            </router-link>
          </li>
          <li v-if="stores.length > 1">
            <a class="nav-link" href="#" @click.prevent="drawerOpen = true; closeSidebar()">
              <i class="ti ti-building-store"></i>店舗切替
            </a>
          </li>
        </ul>
      </nav>
      <div class="sidebar-footer" style="padding: 1rem; margin-top: auto;">
        <button class="btn btn-outline-primary btn-block" @click="onLogout">
          <i class="ti ti-logout"></i> ログアウト
        </button>
      </div>
    </aside>

    <!-- Main content -->
    <div class="main-content">
      <!-- Header (op と同じ構造: メニューボタン / アイコン / アバター) -->
      <header class="app-header position-relative">
        <button class="mobile-menu-btn cu-menu-btn" @click.stop="toggleSidebar">
          <i class="ti ti-menu-2"></i>
        </button>
        <h1 class="position-absolute top-50 start-50 translate-middle m-0 d-flex align-items-center gap-2">
          <span v-if="currentStoreName" class="store-name">{{ currentStoreName }}</span>
          <span v-else-if="currentUser?.store_name" class="store-name">{{ currentUser.store_name }}</span>
        </h1>
        <div class="header-actions">
          <slot name="actions"></slot>
        </div>
        <router-link to="/cu/profile" class="header-avator">
          <UserAvatar :name="currentUser?.display_name" :avatar-url="currentUser?.avatar_url" :size="32" />
        </router-link>
      </header>

      <main class="container">
        <div style="max-width: 640px; margin: 0 auto;">
          <slot :store-id="selectedStoreId" :store-q="storeQ" :stores="stores" :drawer-open="drawerOpen"></slot>
        </div>
      </main>

      <!-- Fixed Bottom Nav -->
      <footer class="footer position-fixed bottom-0 w-100 p-3 bg-white border-top">
        <div class="container d-flex align-items-center justify-content-around">
          <button class="btn border-0 p-0">
            <router-link :to="'/cu/mypage' + storeQ" class="nav-link" :class="{ active: route.path === '/cu/mypage' }">
              <i class="ti ti-home"></i>
              <small>ホーム</small>
            </router-link>
          </button>
          <button class="btn border-0 p-0">
            <router-link :to="'/cu/booking' + storeQ" class="nav-link" :class="{ active: route.path === '/cu/booking' }">
              <i class="ti ti-plus"></i>
              <small>予約</small>
            </router-link>
          </button>
          <button class="btn border-0 p-0">
            <a :href="'/cu/mypage' + storeQ + '#fav'" class="nav-link">
              <i class="ti ti-heart"></i>
              <small>推し</small>
            </a>
          </button>
        </div>
      </footer>
    </div>
  </div>
</template>
