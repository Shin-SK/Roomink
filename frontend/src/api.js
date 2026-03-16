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

export const api = {
  // Auth
  login: (username, password) => request('POST', '/auth/login/', { username, password }),
  logout: () => request('POST', '/auth/logout/'),
  me: () => request('GET', '/auth/me/'),

  // Schedule
  getSchedule: (date) => request('GET', `/op/schedule/?date=${date}`),

  // Orders
  getOrders: (params = '') => request('GET', `/orders/${params ? '?' + params : ''}`),
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
  getCustomers: () => request('GET', '/customers/'),
  getCustomer: (id) => request('GET', `/customers/${id}/`),
  createCustomer: (body) => request('POST', '/customers/', body),
  updateCustomer: (id, body) => request('PATCH', `/customers/${id}/`, body),

  // Casts
  getCasts: () => request('GET', '/casts/'),
  createCast: (body) => request('POST', '/casts/', body),
  updateCast: (id, body) => request('PATCH', `/casts/${id}/`, body),
  deleteCast: (id) => request('DELETE', `/casts/${id}/`),

  // Courses
  getCourses: () => request('GET', '/courses/'),
  createCourse: (body) => request('POST', '/courses/', body),
  updateCourse: (id, body) => request('PATCH', `/courses/${id}/`, body),
  deleteCourse: (id) => request('DELETE', `/courses/${id}/`),

  // Options
  getOptions: () => request('GET', '/options/'),
  createOption: (body) => request('POST', '/options/', body),
  updateOption: (id, body) => request('PATCH', `/options/${id}/`, body),
  deleteOption: (id) => request('DELETE', `/options/${id}/`),

  // Rooms
  getRooms: () => request('GET', '/rooms/'),
  createRoom: (body) => request('POST', '/rooms/', body),
  updateRoom: (id, body) => request('PATCH', `/rooms/${id}/`, body),
  deleteRoom: (id) => request('DELETE', `/rooms/${id}/`),

  // Extensions
  getExtensions: () => request('GET', '/extensions/'),
  createExtension: (body) => request('POST', '/extensions/', body),
  updateExtension: (id, body) => request('PATCH', `/extensions/${id}/`, body),
  deleteExtension: (id) => request('DELETE', `/extensions/${id}/`),

  // NominationFees
  getNominationFees: () => request('GET', '/nomination-fees/'),
  createNominationFee: (body) => request('POST', '/nomination-fees/', body),
  updateNominationFee: (id, body) => request('PATCH', `/nomination-fees/${id}/`, body),
  deleteNominationFee: (id) => request('DELETE', `/nomination-fees/${id}/`),

  // Discounts
  getDiscounts: () => request('GET', '/discounts/'),
  createDiscount: (body) => request('POST', '/discounts/', body),
  updateDiscount: (id, body) => request('PATCH', `/discounts/${id}/`, body),
  deleteDiscount: (id) => request('DELETE', `/discounts/${id}/`),

  // Media
  getMedia: () => request('GET', '/media/'),
  createMedium: (body) => request('POST', '/media/', body),
  updateMedium: (id, body) => request('PATCH', `/media/${id}/`, body),
  deleteMedium: (id) => request('DELETE', `/media/${id}/`),

  // Shifts
  getShifts: (params = '') => request('GET', `/shifts/${params ? '?' + params : ''}`),
  createShift: (body) => request('POST', '/shifts/', body),
  updateShift: (id, body) => request('PATCH', `/shifts/${id}/`, body),
  deleteShift: (id) => request('DELETE', `/shifts/${id}/`),

  // Cast
  getCastToday: (date) => request('GET', `/cast/today/?date=${date}`),
  ackOrder: (id) => request('POST', `/cast/orders/${id}/ack/`),
  getCastShiftRequests: (params = '') => request('GET', `/cast/shift-requests/${params ? '?' + params : ''}`),
  createCastShiftRequest: (body) => request('POST', '/cast/shift-requests/', body),
  updateCastShiftRequest: (id, body) => request('PATCH', `/cast/shift-requests/${id}/`, body),
  cancelCastShiftRequest: (id) => request('POST', `/cast/shift-requests/${id}/cancel/`),

  // Op ShiftRequests
  getOpShiftRequests: (params = '') => request('GET', `/op/shift-requests/${params ? '?' + params : ''}`),
  approveShiftRequest: (id, body) => request('POST', `/op/shift-requests/${id}/approve/`, body),
  rejectShiftRequest: (id, body) => request('POST', `/op/shift-requests/${id}/reject/`, body),

  // Customer
  customerSignup: (phone, password, display_name) => request('POST', '/cu/signup/', { phone, password, display_name }),
  getCustomerStores: () => request('GET', '/cu/stores/'),
  getCustomerMypage: (storeId) => request('GET', `/cu/mypage/${storeId ? '?store=' + storeId : ''}`),
  getBookingOptions: (storeId) => request('GET', `/cu/booking/options/${storeId ? '?store=' + storeId : ''}`),
  getAvailableSlots: (castId, date, storeId) => request('GET', `/cu/available-slots/?cast=${castId}&date=${date}${storeId ? '&store=' + storeId : ''}`),
  createCustomerBooking: (body, storeId) => request('POST', `/cu/bookings/${storeId ? '?store=' + storeId : ''}`, body),

  // CTI
  getCtiQueue: () => request('GET', '/op/cti/queue/'),
  ctiCallStart: (id) => request('POST', `/op/cti/calls/${id}/start/`),
  ctiCallDone: (id) => request('POST', `/op/cti/calls/${id}/done/`),
  ctiCallAddNote: (id, body) => request('POST', `/op/cti/calls/${id}/notes/`, { body }),

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
