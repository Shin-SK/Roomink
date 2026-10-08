<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import { resetAuthCache, getAuthIsSuperuser, getAuthRole } from '../router.js'
import UserAvatar from './UserAvatar.vue'
import CtiIncomingPanel from './CtiIncomingPanel.vue'
import OperatorNotifications from './OperatorNotifications.vue'
import OperatorSidebarIcon from './OperatorSidebarIcon.vue'

const route = useRoute()
const router = useRouter()
const sidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const currentUser = ref(null)
const pendingShiftRequests = ref(0)
let shiftReqTimer = null
const SIDEBAR_COLLAPSED_KEY = 'roomink-operator-sidebar-collapsed'

async function loadPendingShiftRequests() {
  try {
    const data = await api.getOpShiftRequests('status=REQUESTED')
    pendingShiftRequests.value = Array.isArray(data) ? data.length : 0
  } catch { /* ignore */ }
}

onMounted(async () => {
  try {
    sidebarCollapsed.value = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  } catch { /* ignore unavailable storage */ }
  try { currentUser.value = await api.me() } catch { /* ignore */ }
  await loadPendingShiftRequests()
  shiftReqTimer = setInterval(loadPendingShiftRequests, 60000)
})

const isManager = computed(() => {
  // currentUser(api.me 結果) を優先、未取得時は router の authCache(getAuthRole) を fallback
  return currentUser.value?.role === 'manager' || currentUser.value?.is_superuser || getAuthRole() === 'manager'
})

const isSuperuser = computed(() => currentUser.value?.is_superuser || getAuthIsSuperuser())

const navItems = computed(() => {
  const items = [
    { to: '/op/dashboard', icon: 'home', label: 'ホーム', page: 'dashboard' },
    { to: '/op/schedule', icon: 'calendar', label: '予約タイムライン', page: 'schedule' },
    { to: '/op/rooms', icon: 'door', label: 'ルーム', page: 'room-schedule' },
    { to: '/op/phone', icon: 'clipboard-plus', label: '予約作成', page: 'phone' },
    { to: '/op/customers', icon: 'users', label: '顧客管理', page: 'customer-list' },
    { to: '/op/shifts', icon: 'clock', label: 'シフト管理', page: 'shift-list' },
    { to: '/op/shift-requests', icon: 'calendar-check', label: 'シフト申請', page: 'op-shift-requests' },
    { to: '/op/cast-expenses', icon: 'receipt', label: '雑費管理', page: 'cast-expenses' },
    { to: '/op/cast-notes', icon: 'notebook', label: 'ノート', page: 'cast-notes' },
  ]
  if (isSuperuser.value) {
    items.unshift({ to: '/platform', icon: 'building-community', label: 'Roomink運営', page: 'platform' })
  }
  if (isManager.value) {
    items.push(
      { to: '/op/sales', icon: 'chart-bar', label: '売上確認', page: 'sales' },
      { to: '/op/sales-summary', icon: 'report-money', label: '売上集計', page: 'sales-summary' },
      { to: '/op/daily-settlement', icon: 'calculator', label: '日給一覧', page: 'daily-settlement' },
      { to: '/op/cast-checkouts', icon: 'door-exit', label: '退勤提出', page: 'cast-checkouts' },
      { to: '/op/cast-adjustments', icon: 'cash-banknote', label: '調整金', page: 'cast-adjustments' },
      { to: '/op/support', icon: 'lifebuoy', label: '問い合わせ', page: 'support-inbox' },
    )
  }
  items.push(
    { to: '/op/point-logs', icon: 'star', label: 'ポイント', page: 'point-logs' },
    { to: '/account/security', icon: 'shield-lock', label: 'ログインと安全', page: 'account-security' },
    { to: '/op/settings', icon: 'settings', label: '設定', page: 'settings' },
  )
  return items
})

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

function toggleDesktopSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(sidebarCollapsed.value))
  } catch { /* ignore unavailable storage */ }
}

function openSupport() {
  closeSidebar()
  window.dispatchEvent(new CustomEvent('roomink-support-open'))
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

onMounted(() => {
  document.addEventListener('click', onDocClick)
  window.addEventListener('shift-requests-changed', loadPendingShiftRequests)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  window.removeEventListener('shift-requests-changed', loadPendingShiftRequests)
  if (shiftReqTimer) clearInterval(shiftReqTimer)
})
</script>

<template>
  <div class="app-wrapper operator-layout" :class="{ 'is-sidebar-collapsed': sidebarCollapsed }">
    <!-- Sidebar (matches sidebar-operator.html) -->
    <aside class="sidebar operator-sidebar" :class="{ show: sidebarOpen }">
      <div class="sidebar-header">
        <router-link to="/op/dashboard" class="sidebar-brand" @click="closeSidebar">
          <img class="sidebar-logo" src="/logo.svg" alt="Roomink">
        </router-link>
        <button
          type="button"
          class="sidebar-collapse-toggle"
          :aria-label="sidebarCollapsed ? 'サイドバーを広げる' : 'サイドバーを小さくする'"
          :aria-expanded="!sidebarCollapsed"
          @click="toggleDesktopSidebar"
        >
          <OperatorSidebarIcon :name="sidebarCollapsed ? 'chevron-right' : 'chevron-left'" />
        </button>
      </div>
      <nav class="sidebar-nav">
        <ul class="nav-item">
          <li v-for="item in navItems" :key="item.to">
            <router-link
              :to="item.to"
              class="nav-link"
              :class="{ active: item.to === '/op/settings' ? route.path.startsWith('/op/settings') : route.path === item.to }"
              :title="sidebarCollapsed ? item.label : undefined"
              @click="closeSidebar"
            >
              <OperatorSidebarIcon :name="item.icon" />
              <span class="nav-label">{{ item.label }}</span>
              <span
                v-if="item.page === 'op-shift-requests' && pendingShiftRequests > 0"
                class="sidebar-nav-badge badge bg-danger rounded-pill ms-2"
              >{{ pendingShiftRequests }}</span>
            </router-link>
          </li>
          <li>
            <button
              type="button"
              class="nav-link sidebar-help-button"
              :title="sidebarCollapsed ? 'ヘルプ・使い方' : undefined"
              @click="openSupport"
            >
              <OperatorSidebarIcon name="help-circle" />
              <span class="nav-label">ヘルプ・使い方</span>
            </button>
          </li>
        </ul>
      </nav>
      <div class="sidebar-footer">
        <router-link
          v-if="currentUser?.store_name"
          to="/account/stores"
          class="sidebar-store-switch"
          :title="sidebarCollapsed ? `操作中：${currentUser.store_name}` : undefined"
          @click="closeSidebar"
        >
          <OperatorSidebarIcon name="building-community" />
          <span class="sidebar-store-copy"><small>操作中</small><strong>{{ currentUser.store_name }}</strong></span>
        </router-link>
        <router-link
          to="/op/profile"
          class="sidebar-profile-link"
          :title="sidebarCollapsed ? 'プロフィール' : undefined"
          @click="closeSidebar"
        >
          <UserAvatar :name="currentUser?.display_name" :avatar-url="currentUser?.avatar_url" :size="34" />
          <span class="sidebar-profile-link__copy">
            <strong>{{ currentUser?.display_name || 'プロフィール' }}</strong>
            <small>プロフィール</small>
          </span>
        </router-link>
        <button
          class="btn btn-outline-primary btn-block"
          :title="sidebarCollapsed ? 'ログアウト' : undefined"
          aria-label="ログアウト"
          @click="onLogout"
        >
          <OperatorSidebarIcon name="logout" /><span class="logout-label">ログアウト</span>
        </button>
      </div>
    </aside>

    <!-- Main content -->
    <div class="main-content">
      <!-- Header (matches header.html) -->
      <header class="app-header position-relative">
        <div class="mobile-header-start">
          <button class="mobile-menu-btn" aria-label="メニューを開く" :aria-expanded="sidebarOpen" @click.stop="toggleSidebar">
            <i class="ti" :class="sidebarOpen ? 'ti-x' : 'ti-menu-2'"></i>
          </button>
          <router-link to="/op/dashboard" class="mobile-header-brand" aria-label="Roomink ホーム">
            <img src="/logo.svg" alt="Roomink">
          </router-link>
        </div>
        <div class="header-actions">
          <slot name="actions"></slot>
          <OperatorNotifications v-if="currentUser" />
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

    <CtiIncomingPanel v-if="currentUser" />
  </div>
</template>

<style scoped>
.operator-sidebar,
.operator-layout > .main-content {
  transition: width 0.24s ease, margin-left 0.24s ease;
}

.operator-sidebar :deep(.operator-sidebar-icon) {
  margin-right: 0.75rem;
}

.sidebar-header {
  position: relative;
}

/* The compact-sidebar control is desktop-only. On mobile, the hamburger is
   the single clear menu affordance. */
.sidebar-collapse-toggle {
  display: none;
}

.sidebar-logo {
  width: 32px;
  height: 32px;
  object-fit: contain;
}

.sidebar-help-button {
  width: calc(100% - 1rem);
  border: 0;
  background: transparent;
  text-align: left;
}

.sidebar-footer .btn {
  width: 100%;
}

.sidebar-profile-link {
  display: flex;
  align-items: center;
  gap: .65rem;
  margin-bottom: .75rem;
  padding: .65rem;
  border: 1px solid #dbe6e3;
  border-radius: 8px;
  color: inherit;
  text-decoration: none;
}

.sidebar-profile-link:hover,
.sidebar-profile-link:focus-visible {
  color: inherit;
  background: #f5fbf9;
  border-color: var(--rk-primary);
}

.sidebar-profile-link__copy { display: grid; min-width: 0; line-height: 1.2; }
.sidebar-profile-link__copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: .82rem; }
.sidebar-profile-link__copy small { margin-top: .15rem; color: var(--bs-secondary-color); font-size: .68rem; }

.mobile-header-start,
.mobile-header-brand { display: flex; align-items: center; }
.mobile-header-brand img { width: 104px; height: 30px; object-fit: contain; object-position: left center; }

.sidebar-store-switch {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  width: 100%;
  margin-bottom: 0.55rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid rgba(var(--bs-primary-rgb), 0.2);
  border-radius: 8px;
  color: inherit;
  text-decoration: none;
}

.sidebar-store-switch:hover {
  color: inherit;
  background: rgba(var(--bs-primary-rgb), 0.06);
}

.sidebar-store-switch :deep(.operator-sidebar-icon) {
  flex: 0 0 auto;
  margin-right: 0;
}

.sidebar-store-copy {
  min-width: 0;
  display: grid;
  line-height: 1.2;
}

.sidebar-store-copy small {
  color: var(--bs-secondary-color);
  font-size: 0.68rem;
}

.sidebar-store-copy strong {
  overflow: hidden;
  font-size: 0.78rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.logout-label {
  margin-left: 0.35rem;
}

@media (min-width: 992px) {
  .operator-layout > .main-content {
    margin-left: calc(var(--rk-sidebar-width) + 28px);
  }

  .sidebar-collapse-toggle {
    position: absolute;
    right: -26px;
    top: 50%;
    z-index: 4;
    width: 24px;
    height: 48px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transform: translateY(-50%);
    border: 1px solid var(--bs-border-color);
    border-radius: 999px;
    color: var(--bs-secondary);
    background: var(--bs-white);
    box-shadow: 0 3px 10px rgb(15 23 42 / 12%);
    transition: color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
  }

  .sidebar-collapse-toggle:hover,
  .sidebar-collapse-toggle:focus-visible {
    border-color: var(--rk-primary);
    color: var(--rk-primary);
    box-shadow: 0 4px 14px rgb(42 157 143 / 20%);
  }

  .sidebar-collapse-toggle :deep(.operator-sidebar-icon) {
    width: 16px;
    height: 16px;
    margin-right: 0;
  }

  .operator-layout.is-sidebar-collapsed .operator-sidebar {
    width: 76px;
  }

  .operator-layout.is-sidebar-collapsed > .main-content {
    margin-left: 104px;
  }

  .operator-layout.is-sidebar-collapsed .sidebar-header {
    justify-content: center;
    padding-left: 0;
  }

  .operator-layout.is-sidebar-collapsed :deep(.operator-notifications) {
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
  }

  .operator-layout.is-sidebar-collapsed :deep(.nav-link) {
    position: relative;
    justify-content: center;
    min-height: 44px;
    padding: 0.7rem;
  }

  .operator-layout.is-sidebar-collapsed :deep(.nav-link .operator-sidebar-icon) {
    margin-right: 0;
    width: 22px;
    height: 22px;
  }

  .operator-layout.is-sidebar-collapsed .nav-label,
  .operator-layout.is-sidebar-collapsed .logout-label,
  .operator-layout.is-sidebar-collapsed .sidebar-store-copy {
    display: none;
  }

  .operator-layout.is-sidebar-collapsed .sidebar-nav-badge {
    position: absolute;
    top: 3px;
    right: 3px;
    min-width: 18px;
    margin-left: 0 !important;
    padding: 0.2rem 0.35rem;
    font-size: 0.62rem;
  }

  .operator-layout.is-sidebar-collapsed .sidebar-footer {
    padding-inline: 0.7rem;
  }

  .operator-layout.is-sidebar-collapsed .sidebar-footer .btn {
    display: flex;
    align-items: center;
    justify-content: center;
    padding-inline: 0;
  }

  .operator-layout.is-sidebar-collapsed .sidebar-store-switch {
    justify-content: center;
    padding-inline: 0;
  }

  .operator-layout.is-sidebar-collapsed .sidebar-profile-link {
    justify-content: center;
    padding-inline: 0;
  }

  .operator-layout.is-sidebar-collapsed .sidebar-profile-link__copy { display: none; }
}
</style>
