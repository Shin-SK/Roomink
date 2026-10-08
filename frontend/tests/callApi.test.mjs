import test from 'node:test'
import assert from 'node:assert/strict'

globalThis.window = { location: { search: '?store=99' }, sessionStorage: { getItem: () => '', setItem() {}, removeItem() {} } }
globalThis.document = { cookie: '' }
const { callApi, api } = await import('../src/api.js')
const { setSelectedStoreId, selectedStoreId } = await import('../src/storeSelection.js')

test('interleaved call forms remain bound to their calls after dashboard selection changes', async () => {
  const requests = []
  globalThis.fetch = async (url, options) => { requests.push({ url, ...options }); return { ok: true, json: async () => ({}) } }
  const a = callApi(11), b = callApi(22)
  await a.getCustomers()
  await b.getCasts()
  setSelectedStoreId(100)
  await a.createOrder({ customer: 1 })
  await b.getSchedule('2026-10-09')
  assert.deepEqual(requests.map(r => r.headers['X-Roomink-Call']), ['11', '22', '11', '22'])
  assert.ok(requests.every(r => !r.headers['X-Roomink-Store']))
  assert.equal(selectedStoreId(), '100')
  await api.getCtiWorkQueue()
  assert.equal(requests.at(-1).headers['X-Roomink-Store'], undefined)
})
