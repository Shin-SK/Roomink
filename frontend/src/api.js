const API_ORIGIN = import.meta.env.VITE_API_BASE_URL || ''
const BASE = `${API_ORIGIN}/api`

function getCookie(name) {
  const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)')
  return v ? v.pop() : ''
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
    throw new Error(msg)
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
  cancelOrder: (id) => request('POST', `/orders/${id}/cancel/`),
  doneOrder: (id) => request('POST', `/orders/${id}/done/`),
  applyExtension: (id, extension_id) => request('POST', `/orders/${id}/apply_extension/`, { extension_id }),
  applyNominationFee: (id, nomination_fee_id) => request('POST', `/orders/${id}/apply_nomination_fee/`, { nomination_fee_id }),
  applyDiscount: (id, discount_id) => request('POST', `/orders/${id}/apply_discount/`, { discount_id }),
  applyMedium: (id, medium_id) => request('POST', `/orders/${id}/apply_medium/`, { medium_id }),

  // Customers
  getCustomers: (params = '') => listRequest('GET', `/customers/${params ? '?' + params : '?limit=1000'}`),
  getCustomer: (id) => request('GET', `/customers/${id}/`),
  createCustomer: (body) => request('POST', '/customers/', body),
  updateCustomer: (id, body) => request('PATCH', `/customers/${id}/`, body),

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

  // Shifts
  getShifts: (params = '') => listRequest('GET', `/shifts/${params ? '?' + params : '?limit=500'}`),
  createShift: (body) => request('POST', '/shifts/', body),
  updateShift: (id, body) => request('PATCH', `/shifts/${id}/`, body),
  deleteShift: (id) => request('DELETE', `/shifts/${id}/`),

  // Cast
  getCastToday: (date) => request('GET', `/cast/today/?date=${date}`),
  ackOrder: (id) => request('POST', `/cast/orders/${id}/ack/`),
  getCastShiftRequests: (params = '') => listRequest('GET', `/cast/shift-requests/${params ? '?' + params : '?limit=200'}`),
  createCastShiftRequest: (body) => request('POST', '/cast/shift-requests/', body),
  updateCastShiftRequest: (id, body) => request('PATCH', `/cast/shift-requests/${id}/`, body),
  cancelCastShiftRequest: (id) => request('POST', `/cast/shift-requests/${id}/cancel/`),

  // Op ShiftRequests
  getOpShiftRequests: (params = '') => listRequest('GET', `/op/shift-requests/${params ? '?' + params : '?limit=200'}`),
  approveShiftRequest: (id, body) => request('POST', `/op/shift-requests/${id}/approve/`, body),
  rejectShiftRequest: (id, body) => request('POST', `/op/shift-requests/${id}/reject/`, body),

  // Customer
  customerSignup: (phone, password, display_name, store_id) => request('POST', '/cu/signup/', { phone, password, display_name, store_id }),
  getStoreListPublic: () => request('GET', '/cu/store-list/'),
  getCustomerStores: () => request('GET', '/cu/stores/'),
  getCustomerMypage: (storeId) => request('GET', `/cu/mypage/${storeId ? '?store=' + storeId : ''}`),
  getBookingOptions: (storeId) => request('GET', `/cu/booking/options/${storeId ? '?store=' + storeId : ''}`),
  getAvailableSlots: (castId, date, storeId) => request('GET', `/cu/available-slots/?cast=${castId}&date=${date}${storeId ? '&store=' + storeId : ''}`),
  createCustomerBooking: (body, storeId) => request('POST', `/cu/bookings/${storeId ? '?store=' + storeId : ''}`, body),
  getCustomerReservation: (id) => request('GET', `/cu/reservations/${id}/`),

  // CTI
  getCtiQueue: () => request('GET', '/op/cti/queue/'),
  ctiCallStart: (id) => request('POST', `/op/cti/calls/${id}/start/`),
  ctiCallDone: (id) => request('POST', `/op/cti/calls/${id}/done/`),
  ctiCallAddNote: (id, body) => request('POST', `/op/cti/calls/${id}/notes/`, { body }),

  // Sales
  getSalesSummary: (params) => request('GET', `/op/sales-summary/?${params}`),
  getSalesExportUrl: (params) => `${BASE}/op/sales-export.csv?${params}`,

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
}
