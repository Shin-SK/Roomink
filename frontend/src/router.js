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
const ShiftWeekly = () => import('./pages/op/ShiftWeekly.vue')
const SettingsSmsTemplates = () => import('./pages/op/SettingsSmsTemplates.vue')
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
const SettingsPhones = () => import('./pages/op/SettingsPhones.vue')
const SettingsManual = () => import('./pages/op/SettingsManual.vue')
const ManualArticle = () => import('./pages/op/ManualArticle.vue')
const CastExpenses = () => import('./pages/op/CastExpenses.vue')
const CastCheckouts = () => import('./pages/op/CastCheckouts.vue')
const CastAdjustments = () => import('./pages/op/CastAdjustments.vue')
const CastNotes = () => import('./pages/op/CastNotes.vue')
const SettingsPaymentFees = () => import('./pages/op/SettingsPaymentFees.vue')
const DailySettlement = () => import('./pages/op/DailySettlement.vue')
const Sales = () => import('./pages/op/Sales.vue')
const SalesSummary = () => import('./pages/op/SalesSummary.vue')
const PointLogs = () => import('./pages/op/PointLogs.vue')
const RoomSchedule = () => import('./pages/op/RoomSchedule.vue')
const Profile = () => import('./pages/op/Profile.vue')
const CastMypage = () => import('./pages/cast/CastMypage.vue')
const CastOrders = () => import('./pages/cast/CastOrders.vue')
const CastShiftRequests = () => import('./pages/cast/CastShiftRequests.vue')
const CastProfile = () => import('./pages/cast/CastProfile.vue')
const CastManual = () => import('./pages/cast/CastManual.vue')
const CastManualArticle = () => import('./pages/cast/CastManualArticle.vue')
const CuLogin = () => import('./pages/cu/CuLogin.vue')
const CuSignup = () => import('./pages/cu/CuSignup.vue')
const CuActivate = () => import('./pages/cu/CuActivate.vue')
const CuMypage = () => import('./pages/cu/CuMypage.vue')
const CuBooking = () => import('./pages/cu/CuBooking.vue')
const CuSubmitted = () => import('./pages/cu/CuSubmitted.vue')
const CuReservation = () => import('./pages/cu/CuReservation.vue')
const CuProfile = () => import('./pages/cu/CuProfile.vue')
const CuContact = () => import('./pages/cu/CuContact.vue')
const CuHelp = () => import('./pages/cu/CuHelp.vue')
const CuHelpArticle = () => import('./pages/cu/CuHelpArticle.vue')
const PasswordReset = () => import('./pages/PasswordReset.vue')

const routes = [
  { path: '/', redirect: '/op/dashboard' },
  { path: '/login', name: 'login', component: Login, meta: { public: true } },
  { path: '/password-reset', name: 'password-reset', component: PasswordReset, meta: { public: true } },
  { path: '/op/login', redirect: '/login' },
  { path: '/op/dashboard', name: 'dashboard', component: Dashboard },
  { path: '/op/schedule', name: 'schedule', component: Schedule },
  { path: '/op/phone', name: 'phone', component: Phone },
  { path: '/op/orders/:id', name: 'order-detail', component: OrderDetail, props: true },
  { path: '/op/customers', name: 'customer-list', component: CustomerList },
  { path: '/op/customers/:id', name: 'customer-detail', component: CustomerDetail, props: true },
  { path: '/op/shifts', name: 'shift-list', component: ShiftList },
  { path: '/op/shifts/weekly', name: 'shift-weekly', component: ShiftWeekly },
  { path: '/op/shift-requests', name: 'op-shift-requests', component: OpShiftRequests },
  { path: '/op/rooms', name: 'room-schedule', component: RoomSchedule },
  { path: '/op/cast-expenses', name: 'cast-expenses', component: CastExpenses },
  { path: '/op/cast-checkouts', name: 'cast-checkouts', component: CastCheckouts },
  { path: '/op/cast-adjustments', name: 'cast-adjustments', component: CastAdjustments },
  { path: '/op/cast-notes', name: 'cast-notes', component: CastNotes },
  { path: '/op/settings/payment-fees', name: 'settings-payment-fees', component: SettingsPaymentFees },
  { path: '/op/daily-settlement', name: 'daily-settlement', component: DailySettlement },
  { path: '/op/sales', name: 'sales', component: Sales },
  { path: '/op/sales-summary', name: 'sales-summary', component: SalesSummary },
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
  { path: '/op/settings/sms-templates', name: 'settings-sms-templates', component: SettingsSmsTemplates },
  { path: '/op/settings/phones', name: 'settings-phones', component: SettingsPhones },
  { path: '/op/settings/manual', name: 'settings-manual', component: SettingsManual },
  { path: '/op/settings/manual/:slug', name: 'manual-article', component: ManualArticle, props: true },
  { path: '/op/profile', name: 'op-profile', component: Profile },

  // Cast
  { path: '/cast/login', redirect: '/login' },
  { path: '/cast/mypage', name: 'cast-mypage', component: CastMypage },
  { path: '/cast/orders', name: 'cast-orders', component: CastOrders },
  { path: '/cast/shift-requests', name: 'cast-shift-requests', component: CastShiftRequests },
  { path: '/cast/profile', name: 'cast-profile', component: CastProfile },
  { path: '/cast/manual', name: 'cast-manual', component: CastManual },
  { path: '/cast/manual/:slug', name: 'cast-manual-article', component: CastManualArticle, props: true },

  // Customer
  { path: '/cu/login', name: 'cu-login', component: CuLogin, meta: { public: true } },
  { path: '/cu/signup', name: 'cu-signup', component: CuSignup, meta: { public: true } },
  { path: '/cu/activate', name: 'cu-activate', component: CuActivate, meta: { public: true } },
  { path: '/cu/mypage', name: 'cu-mypage', component: CuMypage },
  { path: '/cu/booking', name: 'cu-booking', component: CuBooking },
  { path: '/cu/submitted', name: 'cu-submitted', component: CuSubmitted },
  { path: '/cu/reservations/:id', name: 'cu-reservation', component: CuReservation, props: true },
  { path: '/cu/profile', name: 'cu-profile', component: CuProfile },
  { path: '/cu/contact', name: 'cu-contact', component: CuContact },
  { path: '/cu/help', name: 'cu-help', component: CuHelp },
  { path: '/cu/help/:slug', name: 'cu-help-article', component: CuHelpArticle, props: true },
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
    authCache = { authed: true, role: me.role, roles: me.roles || [me.role] }
  } catch {
    authCache = { authed: false, role: null }
  }
  return authCache
}

function homeForRole(role) {
  if (role === 'cast') return '/cast/mypage'
  if (role === 'customer') return '/cu/mypage'
  return '/op/dashboard'
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
    if (!auth.roles.includes('customer')) return { path: homeForRole(auth.role) }
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
  } else if (auth.role === 'staff' || auth.role === 'manager') {
    // staff / manager が /cast/* に来た場合は拒否
    if (isCast) return { path: '/op/dashboard' }
  } else {
    return { path: homeForRole(auth.role) }
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
