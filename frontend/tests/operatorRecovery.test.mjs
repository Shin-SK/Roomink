import test from 'node:test'
import assert from 'node:assert/strict'

globalThis.window = { location: { search: '?store=99' }, sessionStorage: { getItem: () => '', setItem() {} } }
globalThis.document = { cookie: '' }
const { api } = await import('../src/api.js')
const mismatch = "CSRF Failed: CSRF token from the 'X-Csrftoken' HTTP header incorrect."
const operations = {
  approve: () => api.approveShiftRequest(1, { room: 3 }),
  reject: () => api.rejectShiftRequest(1, {}),
  create: () => api.createShift({ cast: 7 }),
  update: () => api.updateShift(1, { room: 3 }),
  discount: () => api.applyDiscount(1, 7),
  customer: () => api.updateCustomer(1, { online_booking_ng: true }),
}
for (const [name, send] of Object.entries(operations)) {
  test(`${name} recovers only a CSRF rejection with the same store and body`, async () => {
    const mutations = []
    globalThis.fetch = async (url, options) => {
      if (url.endsWith('/auth/csrf/')) return { ok: true, json: async () => ({ csrf_token: 'refreshed' }) }
      mutations.push(options)
      return { ok: mutations.length === 2, status: mutations.length === 1 ? 403 : 200, json: async () => ({ detail: mismatch }) }
    }
    await send()
    assert.equal(mutations.length, 2)
    assert.equal(mutations[1].headers['X-Roomink-Store'], '99')
    assert.equal(mutations[1].headers['X-CSRFToken'], 'refreshed')
    assert.equal(mutations[0].body, mutations[1].body)
  })
  for (const kind of ['permission', 'network']) {
    test(`${name} never repeats a ${kind} failure`, async () => {
      let count = 0
      globalThis.fetch = async () => {
        count++
        if (kind === 'network') throw new TypeError('connection lost')
        return { ok: false, status: 403, json: async () => ({ detail: 'Permission denied' }) }
      }
      await assert.rejects(send)
      assert.equal(count, 1)
    })
  }
}

test('shift pagination retains every row and the selected store', async () => {
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return { ok: true, json: async () => calls.length === 1
      ? { count: 501, results: Array.from({ length: 500 }, (_, id) => ({ id })), next: 'https://api.example/api/shifts/?limit=500&offset=500' }
      : { count: 501, results: [{ id: 500 }], next: null } }
  }
  const shifts = await api.getShifts()
  assert.equal(shifts.length, 501)
  assert.equal(calls[1].url, '/api/shifts/?limit=500&offset=500')
  assert.equal(calls[1].options.headers['X-Roomink-Store'], '99')
})
