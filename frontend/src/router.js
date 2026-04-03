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
const SettingsStaffs = () => import('./pages/op/SettingsStaffs.vue')
const SettingsCsvImport = () => import('./pages/op/SettingsCsvImport.vue')
const SettingsLine = () => import('./pages/op/SettingsLine.vue')
const SettingsManual = () => import('./pages/op/SettingsManual.vue')
const ManualArticle = () => import('./pages/op/ManualArticle.vue')
const CastExpenses = () => import('./pages/op/CastExpenses.vue')
const DailySettlement = () => import('./pages/op/DailySettlement.vue')
const PointLogs = () => import('./pages/op/PointLogs.vue')
const RoomSchedule = () => import('./pages/op/RoomSchedule.vue')
const Profile = () => import('./pages/op/Profile.vue')
const CastMypage = () => import('./pages/cast/CastMypage.vue')
const CastOrders = () => import('./pages/cast/CastOrders.vue')
const CastShiftRequests = () => import('./pages/cast/CastShiftRequests.vue')
const CastProfile = () => import('./pages/cast/CastProfile.vue')
const CuLogin = () => import('./pages/cu/CuLogin.vue')
const CuSignup = () => import('./pages/cu/CuSignup.vue')
const CuMypage = () => import('./pages/cu/CuMypage.vue')
const CuBooking = () => import('./pages/cu/CuBooking.vue')
const CuSubmitted = () => import('./pages/cu/CuSubmitted.vue')
const CuReservation = () => import('./pages/cu/CuReservation.vue')
const CuProfile = () => import('./pages/cu/CuProfile.vue')
const CuContact = () => import('./pages/cu/CuContact.vue')

const routes = [
  { path: '/', redirect: '/op/dashboard' },
  { path: '/login', name: 'login', component: Login, meta: { public: true } },
  { path: '/op/login', redirect: '/login' },
  { path: '/op/dashboard', name: 'dashboard', component: Dashboard },
  { path: '/op/schedule', name: 'schedule', component: Schedule },
  { path: '/op/phone', name: 'phone', component: Phone },
  { path: '/op/orders/:id', name: 'order-detail', component: OrderDetail, props: true },
  { path: '/op/customers', name: 'customer-list', component: CustomerList },
  { path: '/op/customers/:id', name: 'customer-detail', component: CustomerDetail, props: true },
  { path: '/op/shifts', name: 'shift-list', component: ShiftList },
  { path: '/op/shift-requests', name: 'op-shift-requests', component: OpShiftRequests },
  { path: '/op/rooms', name: 'room-schedule', component: RoomSchedule },
  { path: '/op/cast-expenses', name: 'cast-expenses', component: CastExpenses },
  { path: '/op/daily-settlement', name: 'daily-settlement', component: DailySettlement },
  { path: '/op/point-logs', name: 'point-logs', component: PointLogs },
  { path: '/op/settings', name: 'settings', component: Settings },
  { path: '/op/settings/casts', name: 'settings-casts', component: SettingsCasts },
  { path: '/op/settings/staffs', name: 'settings-staffs', component: SettingsStaffs },
  { path: '/op/settings/rooms', name: 'settings-rooms', component: SettingsRooms },
  { path: '/op/settings/courses', name: 'settings-courses', component: SettingsCourses },
  { path: '/op/settings/options', name: 'settings-options', component: SettingsOptions },
  { path: '/op/settings/extensions', name: 'settings-extensions', component: SettingsExtensions },
  { path: '/op/settings/nomination-fees', name: 'settings-nomination-fees', component: SettingsNominationFees },
  { path: '/op/settings/discounts', name: 'settings-discounts', component: SettingsDiscounts },
  { path: '/op/settings/media', name: 'settings-media', component: SettingsMedia },
  { path: '/op/settings/csv-import', name: 'settings-csv-import', component: SettingsCsvImport },
  { path: '/op/settings/line', name: 'settings-line', component: SettingsLine },
  { path: '/op/settings/manual', name: 'settings-manual', component: SettingsManual },
  { path: '/op/settings/manual/:slug', name: 'manual-article', component: ManualArticle, props: true },
  { path: '/op/profile', name: 'op-profile', component: Profile },

  // Cast
  { path: '/cast/login', redirect: '/login' },
  { path: '/cast/mypage', name: 'cast-mypage', component: CastMypage },
  { path: '/cast/orders', name: 'cast-orders', component: CastOrders },
  { path: '/cast/shift-requests', name: 'cast-shift-requests', component: CastShiftRequests },
  { path: '/cast/profile', name: 'cast-profile', component: CastProfile },

  // Customer
  { path: '/cu/login', name: 'cu-login', component: CuLogin, meta: { public: true } },
  { path: '/cu/signup', name: 'cu-signup', component: CuSignup, meta: { public: true } },
  { path: '/cu/mypage', name: 'cu-mypage', component: CuMypage },
  { path: '/cu/booking', name: 'cu-booking', component: CuBooking },
  { path: '/cu/submitted', name: 'cu-submitted', component: CuSubmitted },
  { path: '/cu/reservations/:id', name: 'cu-reservation', component: CuReservation, props: true },
  { path: '/cu/profile', name: 'cu-profile', component: CuProfile },
  { path: '/cu/contact', name: 'cu-contact', component: CuContact },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

// 認証キャッシュ（role を含む）
let authCache = null // null=未確認, { authed: true, role: '...' } or { authed: false }

async function ensureAuth() {
  if (authCache) return authCache
  try {
    const me = await api.me()
    authCache = { authed: true, role: me.role }
  } catch {
    authCache = { authed: false, role: null }
  }
  return authCache
}

function homeForRole(role) {
  return role === 'cast' ? '/cast/mypage' : '/op/dashboard'
}

router.beforeEach(async (to) => {
  const isOp = to.path.startsWith('/op/')
  const isCast = to.path.startsWith('/cast/')
  const isCu = to.path.startsWith('/cu/')

  // public ページはガード不要
  if (to.meta.public) return

  // /cu/* のガード（op/cast とは別系統）
  if (isCu) {
    const auth = await ensureAuth()
    if (!auth.authed) return { name: 'cu-login', query: { next: to.fullPath } }
    return
  }

  // /op/* と /cast/* 以外はガード不要
  if (!isOp && !isCast) return

  const auth = await ensureAuth()

  // 未ログイン → 統一ログインページへ
  if (!auth.authed) {
    return { name: 'login', query: { next: to.fullPath } }
  }

  // role 別アクセス制御
  if (auth.role === 'cast') {
    // cast が /op/* に来た場合、/op/profile (castAllowed) 以外は拒否
    if (isOp && !to.meta.castAllowed) return { path: '/cast/mypage' }
  } else {
    // staff / manager が /cast/* に来た場合は拒否
    if (isCast) return { path: '/op/dashboard' }
  }
})

// ログイン/ログアウト時にキャッシュをリセットするヘルパー
export function resetAuthCache() {
  authCache = null
}

export function getAuthRole() {
  return authCache?.role || null
}

export default router
