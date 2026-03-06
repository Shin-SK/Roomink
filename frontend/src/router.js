import { createRouter, createWebHistory } from 'vue-router'
import { api } from './api.js'

import Dashboard from './pages/op/Dashboard.vue'
import Schedule from './pages/op/Schedule.vue'
import Phone from './pages/op/Phone.vue'
import OrderDetail from './pages/op/OrderDetail.vue'
import CustomerList from './pages/op/CustomerList.vue'
import CustomerDetail from './pages/op/CustomerDetail.vue'
import Login from './pages/op/Login.vue'
import ShiftList from './pages/op/ShiftList.vue'
import OpShiftRequests from './pages/op/OpShiftRequests.vue'
import Settings from './pages/op/Settings.vue'
import SettingsCasts from './pages/op/SettingsCasts.vue'
import SettingsRooms from './pages/op/SettingsRooms.vue'
import SettingsCourses from './pages/op/SettingsCourses.vue'
import CastToday from './pages/cast/CastToday.vue'
import CastShiftRequests from './pages/cast/CastShiftRequests.vue'
import CuMypage from './pages/cu/CuMypage.vue'
import CuBooking from './pages/cu/CuBooking.vue'
import CuSubmitted from './pages/cu/CuSubmitted.vue'

const routes = [
  { path: '/', redirect: '/op/dashboard' },
  { path: '/op/login', name: 'op-login', component: Login, meta: { public: true } },
  { path: '/op/dashboard', name: 'dashboard', component: Dashboard },
  { path: '/op/schedule', name: 'schedule', component: Schedule },
  { path: '/op/phone', name: 'phone', component: Phone },
  { path: '/op/orders/:id', name: 'order-detail', component: OrderDetail, props: true },
  { path: '/op/customers', name: 'customer-list', component: CustomerList },
  { path: '/op/customers/:id', name: 'customer-detail', component: CustomerDetail, props: true },
  { path: '/op/shifts', name: 'shift-list', component: ShiftList },
  { path: '/op/shift-requests', name: 'op-shift-requests', component: OpShiftRequests },
  { path: '/op/settings', name: 'settings', component: Settings },
  { path: '/op/settings/casts', name: 'settings-casts', component: SettingsCasts },
  { path: '/op/settings/rooms', name: 'settings-rooms', component: SettingsRooms },
  { path: '/op/settings/courses', name: 'settings-courses', component: SettingsCourses },

  // Cast
  { path: '/cast/today', name: 'cast-today', component: CastToday },
  { path: '/cast/shift-requests', name: 'cast-shift-requests', component: CastShiftRequests },

  // Customer
  { path: '/cu/mypage', name: 'cu-mypage', component: CuMypage },
  { path: '/cu/booking', name: 'cu-booking', component: CuBooking },
  { path: '/cu/submitted', name: 'cu-submitted', component: CuSubmitted },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 認証キャッシュ（ページ遷移のたびにme()を叩かないようにする）
let authed = null // null=未確認, true/false

router.beforeEach(async (to) => {
  // /op/* 以外、または public フラグ付きはガード不要
  if (!to.path.startsWith('/op/') || to.meta.public) return

  // キャッシュがあればそれを使う
  if (authed === true) return
  if (authed === false) return { name: 'op-login' }

  // 初回：me()で判定
  try {
    await api.me()
    authed = true
  } catch {
    authed = false
    return { name: 'op-login' }
  }
})

// ログイン/ログアウト時にキャッシュをリセットするヘルパー
export function resetAuthCache() {
  authed = null
}

export default router
