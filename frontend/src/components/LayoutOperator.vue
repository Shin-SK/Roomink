<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const sidebarOpen = ref(false)

const navItems = [
  { to: '/op/dashboard', icon: 'ti-home', label: 'ホーム', page: 'dashboard' },
  { to: '/op/schedule', icon: 'ti-calendar', label: '予約タイムライン', page: 'schedule' },
  { to: '/op/phone', icon: 'ti-phone', label: '電話予約', page: 'phone' },
]

const footerItems = [
  { to: '/op/dashboard', icon: 'ti-home', label: 'ホーム', page: 'dashboard' },
  { to: '/op/schedule', icon: 'ti-timeline-event-exclamation', label: '予約', page: 'schedule' },
  { to: '/op/phone', icon: 'ti-phone', label: '電話', page: 'phone' },
]

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function closeSidebar() {
  sidebarOpen.value = false
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
              :class="{ active: route.path === item.to }"
              @click="closeSidebar"
            >
              <i class="ti" :class="item.icon"></i>{{ item.label }}
            </router-link>
          </li>
        </ul>
      </nav>
    </aside>

    <!-- Main content -->
    <div class="main-content">
      <!-- Header (matches header.html) -->
      <header class="app-header">
        <button class="mobile-menu-btn" @click.stop="toggleSidebar">
          <i class="ti ti-menu-2"></i>
        </button>
        <h1 class="header-title d-flex align-items-center gap-2 w-100">
          <img src="/icon.svg" alt="ホーム" style="height: 40px;"><slot name="title">Roomink</slot>
        </h1>
        <div class="header-actions">
          <slot name="actions"></slot>
        </div>
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
