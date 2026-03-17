import { createRouter, createWebHistory } from 'vue-router'
import { api } from './api.js'

// Eager: 初回表示に必要なページのみ
import Dashboard from './pages/op/Dashboard.vue'
import Login from './pages/op/Login.vue'

// Lazy: それ以外は遅延ロード
const Schedule = () => import('./pages/op/Schedule.vue')
const Phone = () => import('./pages/op/Phone.vue')
const OrderDetail = () => import('./pages/op/OrderDetail.vue')
const CustomerList = () => import('./pages/op/CustomerList.vue')
const CustomerDetail = () => import('./pages/op/CustomerDetail.vue')
const ShiftList = () => import('./pages/op/ShiftList.vue')
const OpShiftRequests = () => import('./pages/op/OpShiftRequests.vue')
const Settings = () => import('./pages/op/Settings.vue')
const SettingsCasts = () => import('./pages/op/SettingsCasts.vue')
const SettingsRooms = () => import('./pages/op/SettingsRooms.vue')
const SettingsCourses = () => import('./pages/op/SettingsCourses.vue')
const SettingsOptions = () => import('./pages/op/SettingsOptions.vue')
const SettingsExtensions = () => import('./pages/op/SettingsExtensions.vue')
const SettingsNominationFees = () => import('./pages/op/SettingsNominationFees.vue')
const SettingsDiscounts = () => import('./pages/op/SettingsDiscounts.vue')
const SettingsMedia = () => import('./pages/op/SettingsMedia.vue')
const SettingsCsvImport = () => import('./pages/op/SettingsCsvImport.vue')
const RoomSchedule = () => import('./pages/op/RoomSchedule.vue')
const CastToday = () => import('./pages/cast/CastToday.vue')
const CastShiftRequests = () => import('./pages/cast/CastShiftRequests.vue')
const CuMypage = () => import('./pages/cu/CuMypage.vue')
const CuBooking = () => import('./pages/cu/CuBooking.vue')
const CuSubmitted = () => import('./pages/cu/CuSubmitted.vue')

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
  { path: '/op/rooms', name: 'room-schedule', component: RoomSchedule },
  { path: '/op/settings', name: 'settings', component: Settings },
  { path: '/op/settings/casts', name: 'settings-casts', component: SettingsCasts },
  { path: '/op/settings/rooms', name: 'settings-rooms', component: SettingsRooms },
  { path: '/op/settings/courses', name: 'settings-courses', component: SettingsCourses },
  { path: '/op/settings/options', name: 'settings-options', component: SettingsOptions },
  { path: '/op/settings/extensions', name: 'settings-extensions', component: SettingsExtensions },
  { path: '/op/settings/nomination-fees', name: 'settings-nomination-fees', component: SettingsNominationFees },
  { path: '/op/settings/discounts', name: 'settings-discounts', component: SettingsDiscounts },
  { path: '/op/settings/media', name: 'settings-media', component: SettingsMedia },
  { path: '/op/settings/csv-import', name: 'settings-csv-import', component: SettingsCsvImport },

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
