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

const sidebarItems = [
  { to: '/cast/mypage', icon: 'ti-home', label: 'マイページ' },
  { to: '/cast/orders', icon: 'ti-calendar-event', label: 'タイムライン' },
  { to: '/cast/shift-requests', icon: 'ti-calendar-check', label: 'シフト申請' },
  { to: '/cast/profile', icon: 'ti-user', label: 'プロフィール' },
]

const footerItems = [
  { to: '/cast/mypage', icon: 'ti-home', label: 'ホーム' },
  { to: '/cast/orders', icon: 'ti-calendar-event', label: 'タイムライン' },
  { to: '/cast/shift-requests', icon: 'ti-calendar-check', label: 'シフト申請' },
  { to: '/cast/profile', icon: 'ti-user', label: 'プロフィール' },
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
  router.push('/cast/login')
}

function onDocClick(e) {
  const sidebar = document.querySelector('.cast-sidebar')
  const btn = document.querySelector('.cast-menu-btn')
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
    <!-- Sidebar -->
    <aside class="sidebar cast-sidebar" :class="{ show: sidebarOpen }">
      <div class="sidebar-header">
        <router-link to="/cast/mypage" class="sidebar-brand" @click="closeSidebar">
          <img style="height: 40px;" src="/logo.svg" alt="Roomink Logo">
        </router-link>
      </div>
      <nav class="sidebar-nav">
        <ul class="nav-item">
          <li v-for="item in sidebarItems" :key="item.to">
            <router-link
              :to="item.to"
              class="nav-link"
              :class="{ active: route.path === item.to }"
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
      <!-- Header -->
      <header class="app-header position-relative">
        <button class="mobile-menu-btn cast-menu-btn" @click.stop="toggleSidebar">
          <i class="ti ti-menu-2"></i>
        </button>
        <h1 class="position-absolute top-50 start-50 translate-middle m-0 d-flex align-items-center gap-2">
          <!-- <img src="/icon.svg" alt="ホーム" style="height: 32px;"> -->
          <span v-if="currentUser?.store_name" class="store-name">{{ currentUser.store_name }}</span>
        </h1>
        <div class="header-actions">
          <slot name="actions"></slot>
        </div>
        <router-link to="/cast/profile" class="header-avator">
          <UserAvatar :name="currentUser?.display_name" :avatar-url="currentUser?.avatar_url" :size="32" />
        </router-link>
      </header>

      <main class="container">
        <slot></slot>
      </main>

      <!-- Footer -->
      <footer class="footer position-fixed bottom-0 w-100 p-3 bg-white border-top">
        <div class="container d-flex align-items-center justify-content-around">
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
