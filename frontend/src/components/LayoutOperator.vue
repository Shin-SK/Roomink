<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import { resetAuthCache } from '../router.js'
import UserAvatar from './UserAvatar.vue'

const route = useRoute()
const router = useRouter()
const sidebarOpen = ref(false)
const currentUser = ref(null)

onMounted(async () => {
  try { currentUser.value = await api.me() } catch { /* ignore */ }
})

const navItems = [
  { to: '/op/dashboard', icon: 'ti-home', label: 'ホーム', page: 'dashboard' },
  { to: '/op/schedule', icon: 'ti-calendar', label: '予約タイムライン', page: 'schedule' },
  { to: '/op/rooms', icon: 'ti-door', label: 'ルーム', page: 'room-schedule' },
  { to: '/op/phone', icon: 'ti-clipboard-plus', label: '予約作成', page: 'phone' },
  { to: '/op/customers', icon: 'ti-users', label: '顧客管理', page: 'customer-list' },
  { to: '/op/shifts', icon: 'ti-clock', label: 'シフト管理', page: 'shift-list' },
  { to: '/op/shift-requests', icon: 'ti-calendar-check', label: 'シフト申請', page: 'op-shift-requests' },
  { to: '/op/cast-expenses', icon: 'ti-receipt', label: '雑費管理', page: 'cast-expenses' },
  { to: '/op/daily-settlement', icon: 'ti-calculator', label: '日給一覧', page: 'daily-settlement' },
  { to: '/op/point-logs', icon: 'ti-star', label: 'ポイント', page: 'point-logs' },
  { to: '/op/settings', icon: 'ti-settings', label: '設定', page: 'settings' },
]

const footerItems = [
  { to: '/op/dashboard', icon: 'ti-home', label: 'ホーム', page: 'dashboard' },
  { to: '/op/schedule', icon: 'ti-timeline-event-exclamation', label: '予約', page: 'schedule' },
  { to: '/op/phone', icon: 'ti-plus', label: '新規', page: 'phone' },
  { to: '/op/rooms', icon: 'ti-door', label: 'ルーム', page: 'rooms' },
  { to: '/op/customers', icon: 'ti-users', label: '顧客', page: 'customer-list' },
]

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function closeSidebar() {
  sidebarOpen.value = false
}

async function onLogout() {
  try { await api.logout() } catch { /* ignore */ }
  resetAuthCache()
  router.push('/login')
}

function onDocClick(e) {
  const sidebar = document.querySelector('.sidebar')
  const btn = document.querySelector('.mobile-menu-btn')
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
  <div class="app-wrapper">
    <!-- Sidebar (matches sidebar-operator.html) -->
    <aside class="sidebar" :class="{ show: sidebarOpen }">
      <div class="sidebar-header">
        <router-link to="/op/dashboard" class="sidebar-brand" @click="closeSidebar">
          <img style="height: 40px;" src="/logo.svg" alt="Roomink Logo">
        </router-link>
      </div>
      <nav class="sidebar-nav">
        <ul class="nav-item">
          <li v-for="item in navItems" :key="item.to">
            <router-link
              :to="item.to"
              class="nav-link"
              :class="{ active: item.to === '/op/settings' ? route.path.startsWith('/op/settings') : route.path === item.to }"
              @click="closeSidebar"
            >
              <i class="ti" :class="item.icon"></i>{{ item.label }}
            </router-link>
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
      <!-- Header (matches header.html) -->
      <header class="app-header position-relative">
        <button class="mobile-menu-btn" @click.stop="toggleSidebar">
          <i class="ti ti-menu-2"></i>
        </button>
        <h1 class="position-absolute top-50 start-50 translate-middle m-0 d-flex align-items-center gap-2">
          <img src="/icon.svg" alt="ホーム" style="height: 32px;">
          <!-- <span v-if="currentUser?.store_name" class="store-name">{{ currentUser.store_name }}</span> -->
        </h1>
        <div class="header-actions">
          <slot name="actions"></slot>
        </div>
        <router-link to="/op/profile" class="header-avator">
          <UserAvatar :name="currentUser?.display_name" :avatar-url="currentUser?.avatar_url" :size="32" />
        </router-link>
      </header>

      <main class="container">
        <slot></slot>
      </main>

      <!-- Footer (matches footer.html) -->
      <footer class="footer position-fixed bottom-0 w-100 p-3 bg-white border-top">
        <div class="container d-flex align-items-center justify-content-between">
          <button
            v-for="item in footerItems"
            :key="item.to"
            class="btn border-0 p-0"
          >
            <router-link
              :to="item.to"
              class="nav-link"
              :class="{ active: route.path === item.to }"
            >
              <i class="ti" :class="item.icon"></i>
              <small>{{ item.label }}</small>
            </router-link>
          </button>
        </div>
      </footer>
    </div>
  </div>
</template>
