import test from 'node:test'
import assert from 'node:assert/strict'
import { settlementStoreShare } from '../src/settlementDisplay.js'

test('the operational share excludes card surcharges while keeping the accounting snapshot intact', () => {
  const row = { total_sales: 52000, compensation: 31000, store_allocation: 23600, customer_payment_surcharge: 2600 }
  assert.equal(settlementStoreShare(row), 21000)
  assert.equal(row.store_allocation, 23600)
  assert.equal(row.customer_payment_surcharge, 2600)
})

test('zero and negative shares remain valid; missing legacy amounts are not invented', () => {
  assert.equal(settlementStoreShare({ total_sales: 0, compensation: 1000 }), -1000)
  assert.equal(settlementStoreShare({ total_sales: 1000, compensation: 1000 }), 0)
  assert.equal(settlementStoreShare({ store_allocation: 23600 }), null)
})
