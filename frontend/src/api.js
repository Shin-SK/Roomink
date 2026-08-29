const API_ORIGIN = import.meta.env.VITE_API_BASE_URL || ''
const BASE = `${API_ORIGIN}/api`

function getCookie(name) {
  const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)')
  return v ? v.pop() : ''
}

// 電話番号正規化: 全角→半角、+81/81 → 0、数字以外を除去
export function normalizePhone(raw) {
  if (raw == null) return ''
  let s = String(raw)
    .replace(/[０-９]/g, ch => String.fromCharCode(ch.charCodeAt(0) - 0xFEE0))
    .replace(/[－−ー―‐]/g, '-')
    .trim()
  if (s.startsWith('+81')) s = '0' + s.slice(3)
  s = s.replace(/\D/g, '')
  if (s.startsWith('81') && s.length >= 11) s = '0' + s.slice(2)
  return s
}

async function request(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: API_ORIGIN ? 'include' : 'same-origin',
  }
  if (method !== 'GET') {
    opts.headers['X-CSRFToken'] = getCookie('csrftoken')
  }
  if (body !== undefined) opts.body = JSON.stringify(body)

  const res = await fetch(`${BASE}${path}`, opts)
  const data = await res.json().catch(() => null)

  if (!res.ok) {
    const msg =
      data?.detail ||
      (typeof data === 'object' && data !== null
        ? Object.values(data).flat().join('\n')
        : '') ||
      `Error ${res.status}`
    const err = new Error(msg)
    // 呼び出し側で detail 以外（週次シフトの日別エラー等）も参照できるようにする
    err.data = data
    err.status = res.status
    throw err
  }
  return data
}

async function upload(path, formData) {
  const opts = {
    method: 'POST',
    headers: { 'X-CSRFToken': getCookie('csrftoken') },
    credentials: API_ORIGIN ? 'include' : 'same-origin',
    body: formData,
  }
  const res = await fetch(`${BASE}${path}`, opts)
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const msg = data?.detail || `Error ${res.status}`
    throw new Error(msg)
  }
  return data
}

// ページネーション対応: results 配列があればそちらを返す
async function listRequest(method, path) {
  const data = await request(method, path)
  if (data && typeof data === 'object' && Array.isArray(data.results)) {
    return data.results
  }
  return data
}

export const api = {
  // Auth
  csrf: () => request('GET', '/auth/csrf/'),
  login: (username, password) => request('POST', '/auth/login/', { username, password }),
  logout: () => request('POST', '/auth/logout/'),
  me: () => request('GET', '/auth/me/'),
  updateProfile: (body) => request('PATCH', '/auth/profile/', body),

  // Schedule
  getSchedule: (date) => request('GET', `/op/schedule/?date=${date}`),
  getRoomSchedule: (date) => request('GET', `/op/room-schedule/?date=${date}`),

  // Orders
  getOrders: (params = '') => listRequest('GET', `/orders/${params ? '?' + params : '?limit=200'}`),
  getOrder: (id) => request('GET', `/orders/${id}/`),
  updateOrder: (id, body) => request('PATCH', `/orders/${id}/`, body),
  createOrder: (body) => request('POST', '/orders/', body),
  confirmOrder: (id) => request('POST', `/orders/${id}/confirm/`),
  sendCardPaymentRequest: (id) => request('POST', `/orders/${id}/send-card-payment-request/`),
  confirmCardPayment: (id) => request('POST', `/orders/${id}/confirm-card-payment/`),
  cancelOrder: (id) => request('POST', `/orders/${id}/cancel/`),
  doneOrder: (id) => request('POST', `/orders/${id}/done/`),
  applyExtension: (id, body) => request('POST', `/orders/${id}/apply_extension/`, body),
  applyNominationFee: (id, nomination_fee_id) => request('POST', `/orders/${id}/apply_nomination_fee/`, { nomination_fee_id }),
  applyDiscount: (id, discount_id) => request('POST', `/orders/${id}/apply_discount/`, { discount_id }),
  applyMedium: (id, medium_id) => request('POST', `/orders/${id}/apply_medium/`, { medium_id }),
  linkOrderServiceRecipient: (id, customer_id) => request(
    'POST',
    `/orders/${id}/link-service-recipient/`,
    { customer_id },
  ),
  opOrderCastAck: (id) => request('POST', `/op/orders/${id}/cast-ack/`),

  // Customers
  getCustomers: (params = '') => listRequest('GET', `/customers/${params ? '?' + params : '?limit=1000'}`),
  getCustomer: (id) => request('GET', `/customers/${id}/`),
  createCustomer: (body) => request('POST', '/customers/', body),
  updateCustomer: (id, body) => request('PATCH', `/customers/${id}/`, body),
  getCustomerInvitation: (id) => request('GET', `/op/customers/${id}/invitation/`),
  reissueCustomerInvitation: (id) => request('POST', `/op/customers/${id}/invitation/`, {}),
  getCustomerDuplicates: (id) => request('GET', `/customers/${id}/duplicates/`),
  mergeCustomer: (keepId, mergeId) => request('POST', `/customers/${keepId}/merge/`, { merge_id: mergeId }),
  checkCustomerDuplicate: (phone, name) => {
    const params = new URLSearchParams()
    if (phone) params.set('phone', phone)
    if (name) params.set('name', name)
    return request('GET', `/customers/check-duplicate/?${params}`)
  },
  searchCustomerByPhone: async (phone) => {
    const normalized = normalizePhone(phone)
    if (!normalized || normalized.length < 6) return []
    return listRequest('GET', `/customers/?phone=${encodeURIComponent(normalized)}`)
  },

  // Casts
  getCasts: () => listRequest('GET', '/casts/?limit=200'),
  createCast: (body) => request('POST', '/casts/', body),
  updateCast: (id, body) => request('PATCH', `/casts/${id}/`, body),
  deleteCast: (id) => request('DELETE', `/casts/${id}/`),

  // Staffs
  getStaffs: () => listRequest('GET', '/staffs/?limit=200'),
  createStaff: (body) => request('POST', '/staffs/', body),
  updateStaff: (id, body) => request('PATCH', `/staffs/${id}/`, body),
  deleteStaff: (id) => request('DELETE', `/staffs/${id}/`),

  // Courses
  getCourses: () => listRequest('GET', '/courses/?limit=200'),
  createCourse: (body) => request('POST', '/courses/', body),
  updateCourse: (id, body) => request('PATCH', `/courses/${id}/`, body),
  deleteCourse: (id) => request('DELETE', `/courses/${id}/`),

  // Options
  getOptions: () => listRequest('GET', '/options/?limit=200'),
  createOption: (body) => request('POST', '/options/', body),
  updateOption: (id, body) => request('PATCH', `/options/${id}/`, body),
  deleteOption: (id) => request('DELETE', `/options/${id}/`),

  // Rooms
  getRooms: () => listRequest('GET', '/rooms/?limit=200'),
  createRoom: (body) => request('POST', '/rooms/', body),
  updateRoom: (id, body) => request('PATCH', `/rooms/${id}/`, body),
  deleteRoom: (id) => request('DELETE', `/rooms/${id}/`),

  // Extensions
  getExtensions: () => listRequest('GET', '/extensions/?limit=200'),
  createExtension: (body) => request('POST', '/extensions/', body),
  updateExtension: (id, body) => request('PATCH', `/extensions/${id}/`, body),
  deleteExtension: (id) => request('DELETE', `/extensions/${id}/`),

  // NominationFees
  getNominationFees: () => listRequest('GET', '/nomination-fees/?limit=200'),
  createNominationFee: (body) => request('POST', '/nomination-fees/', body),
  updateNominationFee: (id, body) => request('PATCH', `/nomination-fees/${id}/`, body),
  deleteNominationFee: (id) => request('DELETE', `/nomination-fees/${id}/`),

  // Discounts
  getDiscounts: () => listRequest('GET', '/discounts/?limit=200'),
  createDiscount: (body) => request('POST', '/discounts/', body),
  updateDiscount: (id, body) => request('PATCH', `/discounts/${id}/`, body),
  deleteDiscount: (id) => request('DELETE', `/discounts/${id}/`),

  // Media
  getMedia: () => listRequest('GET', '/media/?limit=200'),
  createMedium: (body) => request('POST', '/media/', body),
  updateMedium: (id, body) => request('PATCH', `/media/${id}/`, body),
  deleteMedium: (id) => request('DELETE', `/media/${id}/`),

  // PointLogs
  getPointLogs: (params = '') => listRequest('GET', `/point-logs/${params ? '?' + params : '?limit=500'}`),
  createPointLog: (body) => request('POST', '/point-logs/', body),
  updatePointLog: (id, body) => request('PATCH', `/point-logs/${id}/`, body),
  deletePointLog: (id) => request('DELETE', `/point-logs/${id}/`),

  // CastExpenses
  getCastExpenses: (params = '') => listRequest('GET', `/cast-expenses/${params ? '?' + params : '?limit=500'}`),
  createCastExpense: (body) => request('POST', '/cast-expenses/', body),
  updateCastExpense: (id, body) => request('PATCH', `/cast-expenses/${id}/`, body),
  deleteCastExpense: (id) => request('DELETE', `/cast-expenses/${id}/`),

  // CastExpenseTemplates（固定雑費テンプレ）
  getCastExpenseTemplates: (castId) => listRequest('GET', `/cast-expense-templates/?cast=${castId}&limit=200`),
  createCastExpenseTemplate: (body) => request('POST', '/cast-expense-templates/', body),
  updateCastExpenseTemplate: (id, body) => request('PATCH', `/cast-expense-templates/${id}/`, body),
  setCastExpenseTemplateActive: (id, isActive) => request('PATCH', `/cast-expense-templates/${id}/`, { is_active: isActive }),
  getCastExpenseTemplateHistories: (castId) => listRequest('GET', `/cast-expense-template-histories/?cast=${castId}&limit=200`),
  getCastExpenseTemplateHistoriesByTemplate: (templateId) => listRequest('GET', `/cast-expense-template-histories/?template=${templateId}&limit=200`),

  // Shifts
  getShifts: (params = '') => listRequest('GET', `/shifts/${params ? '?' + params : '?limit=500'}`),
  createShift: (body) => request('POST', '/shifts/', body),
  updateShift: (id, body) => request('PATCH', `/shifts/${id}/`, body),
  deleteShift: (id) => request('DELETE', `/shifts/${id}/`),
  clockInShift: (id) => request('POST', `/shifts/${id}/clock-in/`),
  clearClockInShift: (id) => request('POST', `/shifts/${id}/clear-clock-in/`),

  // Cast unavailable times（休憩・遅刻・早退・中抜け等）
  getCastUnavailableTimes: (date) => listRequest('GET', `/cast-unavailable-times/?date=${date}&limit=500`),
  createCastUnavailableTime: (body) => request('POST', '/cast-unavailable-times/', body),
  updateCastUnavailableTime: (id, body) => request('PATCH', `/cast-unavailable-times/${id}/`, body),
  deleteCastUnavailableTime: (id) => request('DELETE', `/cast-unavailable-times/${id}/`),

  // 週次シフト入力（1キャスト×1週間まとめて登録）
  getWeeklyShifts: (castId, weekStart) => request('GET', `/op/shifts/weekly/?cast=${castId}&week_start=${weekStart}`),
  createWeeklyShifts: (body) => request('POST', '/op/shifts/weekly/', body),

  // タイムライン並び替え（キャスト別表示の display_order）
  getScheduleCastOrder: (date) => request('GET', `/op/schedule-cast-order/?date=${date}`),
  saveScheduleCastOrder: (body) => request('POST', '/op/schedule-cast-order/', body),

  // SMS文面設定 / SMS送信履歴
  getSmsTemplates: () => request('GET', '/op/sms-templates/'),
  previewSmsTemplate: (body) => request('POST', '/op/sms-templates/', body),
  updateSmsTemplates: (items, cardPaymentUrl) => request('PUT', '/op/sms-templates/', {
    items,
    card_payment_url: cardPaymentUrl,
  }),
  getPublicBookingSettings: () => request('GET', '/op/public-booking-settings/'),
  updatePublicBookingSettings: (body) => request('PATCH', '/op/public-booking-settings/', body),
  getSipProvisioningSettings: () => request('GET', '/op/sip-provisioning/settings/'),
  updateSipProvisioningSettings: (body) => request('PATCH', '/op/sip-provisioning/settings/', body),
  getSipReceptionDevices: () => request('GET', '/op/sip-reception-devices/'),
  createSipReceptionDevice: (body) => request('POST', '/op/sip-reception-devices/', body),
  issueSipReceptionDeviceLink: (id) => request('POST', `/op/sip-reception-devices/${id}/provision/`, {}),
  deactivateSipReceptionDevice: (id) => request('POST', `/op/sip-reception-devices/${id}/deactivate/`, {}),
  getOrderSmsLogs: (id) => request('GET', `/op/orders/${id}/sms-logs/`),

  // Cast
  getCastToday: (date = '') => request(
    'GET',
    date ? `/cast/today/?date=${date}` : '/cast/today/',
  ),
  getCastTodaySales: () => request('GET', '/cast/today-sales/'),
  ackOrder: (id) => request('POST', `/cast/orders/${id}/ack/`),
  getCastLineLink: () => request('GET', '/cast/line-link/'),
  castLineLinkAction: (action) => request('POST', '/cast/line-link/', { action }),
  getCastPoints: () => request('GET', '/cast/points/'),
  getCastCheckout: () => request('GET', '/cast/checkout/'),
  submitCastCheckout: (body) => request('POST', '/cast/checkout/', body),
  getCastShiftConfirm: () => request('GET', '/cast/shift-confirm/'),
  confirmCastShift: (shiftId) => request('POST', '/cast/shift-confirm/', { shift_id: shiftId }),

  // Cast Checkouts（manager側: 退勤提出一覧/確認）
  getCastCheckouts: (params = '') => listRequest('GET', `/cast-checkouts/${params ? '?' + params : '?limit=200'}`),
  // count/next/previous を保持したまま返す版（ページネーションUI用）
  getCastCheckoutsPage: (params = '') => request('GET', `/cast-checkouts/${params ? '?' + params : ''}`),
  getCastCheckoutDetail: (id) => request('GET', `/cast-checkouts/${id}/`),
  updateCastCheckoutManagerMemo: (id, managerMemo) => request('PATCH', `/cast-checkouts/${id}/`, { manager_memo: managerMemo }),
  reviewCastCheckout: (id, managerMemo) => request('POST', `/cast-checkouts/${id}/review/`, managerMemo !== undefined ? { manager_memo: managerMemo } : {}),
  returnCastCheckout: (id, managerMemo) => request('POST', `/cast-checkouts/${id}/return_to_cast/`, managerMemo !== undefined ? { manager_memo: managerMemo } : {}),
  resetCastCheckout: (id) => request('POST', `/cast-checkouts/${id}/reset_to_submitted/`),
  getCastCheckoutsExportUrl: (params = '') => `${BASE}/cast-checkouts/export_csv/${params ? '?' + params : ''}`,

  // Cast Adjustments（調整金台帳, Phase 3-E / manager側）
  getCastAdjustments: (params = '') => listRequest('GET', `/cast-adjustments/${params ? '?' + params : '?limit=500'}`),
  createCastAdjustment: (body) => request('POST', '/cast-adjustments/', body),
  updateCastAdjustment: (id, body) => request('PATCH', `/cast-adjustments/${id}/`, body),
  resolveCastAdjustment: (id, resolvedMemo) => request('POST', `/cast-adjustments/${id}/resolve/`, resolvedMemo !== undefined ? { resolved_memo: resolvedMemo } : {}),
  voidCastAdjustment: (id, resolvedMemo) => request('POST', `/cast-adjustments/${id}/void/`, resolvedMemo !== undefined ? { resolved_memo: resolvedMemo } : {}),
  getCastAdjustmentsExportUrl: (params = '') => `${BASE}/cast-adjustments/export_csv/${params ? '?' + params : ''}`,

  // Cast Adjustments（cast本人側）
  getCastAdjustmentsMypage: () => request('GET', '/cast/adjustments/'),

  // Cast Notes（ノート/施術マニュアル, manager側）
  getCastNotes: (params = '') => listRequest('GET', `/cast-notes/${params ? '?' + params : '?limit=200'}`),
  createCastNote: (body) => request('POST', '/cast-notes/', body),
  updateCastNote: (id, body) => request('PATCH', `/cast-notes/${id}/`, body),
  deleteCastNote: (id) => request('DELETE', `/cast-notes/${id}/`),
  publishCastNote: (id) => request('POST', `/cast-notes/${id}/publish/`),
  unpublishCastNote: (id) => request('POST', `/cast-notes/${id}/unpublish/`),
  archiveCastNote: (id) => request('POST', `/cast-notes/${id}/archive/`),
  moveCastNote: (id, direction) => request('POST', `/cast-notes/${id}/move/`, { direction }),
  placeCastNote: (id, targetId, position) => request('POST', `/cast-notes/${id}/place/`, { target_id: targetId, position }),
  pinCastNote: (id) => request('POST', `/cast-notes/${id}/pin/`),
  unpinCastNote: (id) => request('POST', `/cast-notes/${id}/unpin/`),

  // Cast Notes（cast本人側）
  getCastNotesMypage: (params = '') => request('GET', `/cast/notes/${params ? '?' + params : ''}`),

  // Shift Confirm Alerts（出勤確認アラート土台, Phase 3-F / Phase 4で通知ログ土台を追加）
  getShiftConfirmAlerts: () => request('GET', '/op/shift-confirm-alerts/'),
  getShiftConfirmNotificationLogs: (params = '') => listRequest('GET', `/shift-confirm-notification-logs/${params ? '?' + params : '?limit=200'}`),
  markShiftConfirmNotificationTest: (shiftId, body) => request('POST', `/op/shift-confirm-alerts/${shiftId}/mark_notification_test/`, body),

  // Payment Fee Settings（決済手数料設定, 参考値）
  getPaymentFeeSettings: () => request('GET', '/op/payment-fee-settings/'),
  updatePaymentFeeSettings: (body) => request('PATCH', '/op/payment-fee-settings/', body),

  getCastShiftRequests: (params = '') => listRequest('GET', `/cast/shift-requests/${params ? '?' + params : '?limit=200'}`),
  createCastShiftRequest: (body) => request('POST', '/cast/shift-requests/', body),
  createCastShiftRequestsBulk: (body) => request('POST', '/cast/shift-requests/bulk-create/', body),
  updateCastShiftRequest: (id, body) => request('PATCH', `/cast/shift-requests/${id}/`, body),
  cancelCastShiftRequest: (id) => request('POST', `/cast/shift-requests/${id}/cancel/`),

  // Op ShiftRequests
  getOpShiftRequests: (params = '') => listRequest('GET', `/op/shift-requests/${params ? '?' + params : '?limit=200'}`),
  approveShiftRequest: (id, body) => request('POST', `/op/shift-requests/${id}/approve/`, body),
  rejectShiftRequest: (id, body) => request('POST', `/op/shift-requests/${id}/reject/`, body),

  // Op ShiftRequests CSV戻し承認の土台（v1: export → preview → apply）
  getOpShiftRequestsExportUrl: (params = '') => `${BASE}/op/shift-requests/export_csv/${params ? '?' + params : ''}`,
  importShiftRequestsPreview: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return upload('/op/shift-requests/import_preview/', fd)
  },
  applyShiftRequestsImport: (rows) => request('POST', '/op/shift-requests/import_apply/', { rows }),

  // Customer
  customerLogin: (phone, password, storeSlug = '') => request('POST', '/cu/login/', { phone, password, store_slug: storeSlug }),
  getCustomerActivation: (token, storeSlug = '') => request('POST', '/cu/activate/preview/', { token, store_slug: storeSlug }),
  activateCustomer: (token, password, passwordConfirm) => request('POST', '/cu/activate/', { token, password, password_confirm: passwordConfirm }),
  getStoreListPublic: () => request('GET', '/cu/store-list/'),
  getPublicBookingOptions: (storeId, date, storeSlug = '') => request(
    'GET',
    `/public/booking/options/?${storeSlug ? `store_slug=${encodeURIComponent(storeSlug)}` : `store=${storeId}`}${date ? `&date=${date}` : ''}`,
  ),
  getPublicBookingSlots: (storeId, castId, courseId, date, storeSlug = '') => request(
    'GET',
    `/public/booking/slots/?${storeSlug ? `store_slug=${encodeURIComponent(storeSlug)}` : `store=${storeId}`}&cast=${castId}&course=${courseId}&date=${date}`,
  ),
  requestPublicBookingVerification: (body) => request('POST', '/public/booking/request-verification/', body),
  confirmPublicBooking: (verificationId, code) => request(
    'POST',
    '/public/booking/confirm/',
    { verification_id: verificationId, code },
  ),
  getCustomerStores: () => request('GET', '/cu/stores/'),
  getCustomerMypage: (storeId, storeSlug = '') => request('GET', `/cu/mypage/${storeSlug ? '?store_slug=' + encodeURIComponent(storeSlug) : (storeId ? '?store=' + storeId : '')}`),
  getBookingOptions: (storeId, storeSlug = '') => request('GET', `/cu/booking/options/${storeSlug ? '?store_slug=' + encodeURIComponent(storeSlug) : (storeId ? '?store=' + storeId : '')}`),
  getAvailableSlots: (castId, date, storeId, storeSlug = '') => request('GET', `/cu/available-slots/?cast=${castId}&date=${date}${storeSlug ? '&store_slug=' + encodeURIComponent(storeSlug) : (storeId ? '&store=' + storeId : '')}`),
  createCustomerBooking: (body, storeId, storeSlug = '') => request('POST', `/cu/bookings/${storeSlug ? '?store_slug=' + encodeURIComponent(storeSlug) : (storeId ? '?store=' + storeId : '')}`, body),
  getCustomerReservation: (id, storeId, storeSlug = '') => request('GET', `/cu/reservations/${id}/${storeSlug ? '?store_slug=' + encodeURIComponent(storeSlug) : (storeId ? '?store=' + storeId : '')}`),

  // CTI
  getCtiQueue: () => request('GET', '/op/cti/queue/'),
  ctiCallStart: (id) => request('POST', `/op/cti/calls/${id}/start/`),
  ctiCallDone: (id) => request('POST', `/op/cti/calls/${id}/done/`),
  ctiCallAddNote: (id, body) => request('POST', `/op/cti/calls/${id}/notes/`, { body }),

  // Op CallLogs (Phase 3: 手動架電履歴)
  getCallLogs: (params = '') => {
    const qs = typeof params === 'string'
      ? params
      : new URLSearchParams(params).toString()
    return listRequest('GET', `/op/call-logs/${qs ? '?' + qs : ''}`)
  },
  createCallLog: (body) => request('POST', '/op/call-logs/', body),
  addCallNote: (callLogId, body) => request('POST', `/op/call-logs/${callLogId}/add-note/`, { body }),

  // Store Phones (CTI電話番号設定)
  getStorePhones: () => listRequest('GET', '/op/store-phones/?limit=200'),
  createStorePhone: (body) => request('POST', '/op/store-phones/', body),
  updateStorePhone: (id, body) => request('PATCH', `/op/store-phones/${id}/`, body),

  // LINE Alerts
  getLineAlerts: () => request('GET', '/op/line-alerts/'),
  getShiftEndAlerts: () => request('GET', '/op/shift-end-alerts/'),

  // LINE Settings (store)
  getLineSettings: () => request('GET', '/op/line-settings/'),
  updateLineSettings: (body) => request('PATCH', '/op/line-settings/', body),

  // Daily Settlement
  getDailySettlement: (date) => request('GET', `/op/daily-settlement/?date=${date}`),
  lockDailySettlement: (body) => request('POST', '/op/daily-settlement/lock/', body),
  unlockDailySettlement: (body) => request('POST', '/op/daily-settlement/unlock/', body),
  getDailySettlementExportUrl: (date) => `${BASE}/op/daily-settlement/export/?date=${date}`,

  // Sales
  getSalesSummary: (params) => request('GET', `/op/sales-summary/?${params}`),
  getSalesExportUrl: (params) => `${BASE}/op/sales-export.csv?${params}`,
  getCustomersExportUrl: () => `${BASE}/op/customers-export.csv`,

  // Sales Dashboard (Phase 3-D)
  getSalesDashboard: (params) => request('GET', `/op/sales-dashboard/?${params}`),
  getSalesDashboardExportUrl: (params) => `${BASE}/op/sales-dashboard-export.csv?${params}`,

  // CSV Import
  csvPreview: (model, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return upload(`/op/csv-import/?model=${model}&preview=1`, fd)
  },
  csvImport: (model, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return upload(`/op/csv-import/?model=${model}`, fd)
  },
  getCsvTemplateUrl: (model) => `${BASE}/op/csv-import/template/?model=${model}`,
}
