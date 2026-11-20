import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

const source = fs.readFileSync(new URL('../src/pages/op/Schedule.vue', import.meta.url), 'utf8')
function harness() {
  const requests = []
  const ref = value => ({ value })
  const context = { selectedDate: ref('2026-11-21'), casts: ref([]), orders: ref([]), unavailableTimes: ref([]), kpi: ref({}), scheduleError: ref(''), loading: ref(false), highlightId: ref(null), scheduleRequest: 0,
    api: { getSchedule: () => new Promise((resolve, reject) => requests.push({ resolve, reject })) } }
  vm.createContext(context)
  vm.runInContext(source.slice(source.indexOf('async function fetchSchedule('), source.indexOf('async function fetchRoomSchedule(')), context)
  return { context, requests }
}
const response = id => ({ casts: [], orders: [{ id }], kpi: {} })
test('a late poll cannot overwrite a newer response or a newly selected day', async () => {
  const { context: c, requests } = harness()
  const first = c.fetchSchedule({ background: true })
  const second = c.fetchSchedule({ background: true })
  requests[1].resolve(response(2)); await second
  requests[0].resolve(response(1)); await first
  assert.equal(c.orders.value[0].id, 2)
  const third = c.fetchSchedule({ background: true })
  c.selectedDate.value = '2026-11-22'
  requests[2].resolve(response(3)); await third
  assert.equal(c.orders.value[0].id, 2)
})
test('background failure preserves displayed reservations and reports stale data', async () => {
  const { context: c, requests } = harness()
  c.orders.value = [{ id: 8 }]
  const request = c.fetchSchedule({ background: true })
  assert.equal(c.loading.value, false)
  requests[0].reject(new Error('offline')); await request
  assert.equal(c.orders.value[0].id, 8)
  assert.match(c.scheduleError.value, /前回取得時/)
  const next = c.fetchSchedule({ background: true })
  requests[1].resolve(response(9)); await next
  assert.equal(c.scheduleError.value, '')
  assert.equal(c.orders.value[0].id, 9)
})
