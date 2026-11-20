import test from 'node:test'
import assert from 'node:assert/strict'
import { freePendingTimeline } from '../src/freePendingTimeline.js'

const order = (id, start, end, extra = {}) => ({ id, cast_id: 9, is_free_pending: true, status: 'REQUESTED', start: `2026-11-21T${start}:00+09:00`, end: `2026-11-21T${end}:00+09:00`, ...extra })
test('overlapping requests stay individually visible; adjoining requests reuse space', () => {
  const source = [order(1, '12:00', '13:00'), order(2, '12:30', '14:00'), order(3, '13:00', '14:00')]
  const before = JSON.stringify(source)
  const result = freePendingTimeline(source)
  assert.equal(result.casts.length, 2)
  assert.equal(result.orders[0].cast_id, result.orders[2].cast_id)
  assert.notEqual(result.orders[0].cast_id, result.orders[1].cast_id)
  assert.deepEqual(result.orders.map(o => o.id), [1, 2, 3])
  assert.equal(JSON.stringify(source), before)
})
test('assigned and cancelled requests leave the pending area without creating reservations', () => {
  assert.deepEqual(freePendingTimeline([order(1, '12:00', '13:00', { is_free_pending: false }), order(2, '12:00', '13:00', { status: 'CANCELLED' })]).orders, [])
})
test('overnight requests and different queue ids share the same pending area', () => {
  const result = freePendingTimeline([order(1, '23:00', '23:59'), { ...order(2, '23:30', '23:59', { cast_id: 10 }), end: '2026-11-22T01:00:00+09:00' }])
  assert.equal(result.casts.length, 2)
  assert.deepEqual([...result.queueIds], [9, 10])
})
