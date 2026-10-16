import test from 'node:test'
import assert from 'node:assert/strict'
import { changedOrderFields } from '../src/orderEdit.js'

const order = {
  updated_at: '2026-10-16T08:00:00.123456Z', cast: 1, course: 2,
  option_ids: [3, 4], payment_method: 'CASH', card_include_options: false,
  memo: '', service_recipient_name: '', nomination_fee: 5,
}

test('payment-only edits do not send unchanged options, cast, course or nomination', () => {
  assert.deepEqual(changedOrderFields(order, {
    cast: 1, course: 2, options: [3, 4], payment_method: 'CARD',
    card_include_options: true, nomination_fee: 5, memo: '',
  }), { payment_method: 'CARD', card_include_options: true, expected_updated_at: order.updated_at })
})

test('explicit add and removal carry the original version without mutating the baseline', () => {
  assert.deepEqual(changedOrderFields(order, { options: [] }), { options: [], expected_updated_at: order.updated_at })
  assert.deepEqual(changedOrderFields(order, { options: [3, 4, 6] }).options, [3, 4, 6])
  assert.deepEqual(order.option_ids, [3, 4])
})

test('checkbox order and numeric string IDs are not treated as changes', () => {
  assert.deepEqual(changedOrderFields(order, { options: ['4', '3'], cast: '1', course: '2', nomination_fee: '5' }), {})
})

test('empty and null IDs match, but explicit nomination removal is saved', () => {
  assert.deepEqual(changedOrderFields({ ...order, medium: null }, { medium: null }), {})
  assert.deepEqual(changedOrderFields(order, { nomination_fee: null }), { nomination_fee: null, expected_updated_at: order.updated_at })
})

test('date/time corrections preserve the atomic date/time group required by the API', () => {
  const initial = { ...order, business_date: '2026-10-16', start_time_extended: '25:00', end_time_extended: '26:00' }
  assert.deepEqual(changedOrderFields(initial, { business_date: '2026-10-16', start_time_extended: '25:00', end_time_extended: '26:30' }), {
    business_date: '2026-10-16', start_time_extended: '25:00', end_time_extended: '26:30', expected_updated_at: order.updated_at,
  })
})
