import test from 'node:test'
import assert from 'node:assert/strict'
import { settlementStoreShare, settlementCashBalance, settlementCashTotals } from '../src/settlementDisplay.js'

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

test('cash estimates use after-expense compensation without changing saved accounting or actual handoffs', () => {
  const cases = [
    [24000, 9000, 15000, 0], // Cash, after fixed expenses.
    [0, 9000, 0, 9000], // Card only.
    [4000, 9000, 0, 5000], // Card with options collected in cash.
    [10000, 15000, 0, 5000], // Mixed payments with shortage.
    [24000, 8000, 16000, 0], // Fixed and daily expenses already deducted.
    [9000, 9000, 0, 0],
    [0, 0, 0, 0],
    [0, -6000, 6000, 0],
  ]
  for (const [cash, compensation, deposit, shortfall] of cases) {
    const row = Object.freeze({ cash_sales_total: cash, compensation, net_pay: 999,
      point_total: 999, room_cash_taken_amount: 1, store_allocation: 123 })
    assert.deepEqual(settlementCashBalance(row), { deposit, shortfall })
    assert.equal(row.net_pay, 999)
    assert.equal(row.room_cash_taken_amount, 1)
  }
})

test('different therapists deposits and shortages do not cancel each other', () => {
  assert.deepEqual(settlementCashTotals([
    { cash_sales_total: 24000, compensation: 9000 },
    { cash_sales_total: 0, compensation: 9000 },
  ]), { deposit: 15000, shortfall: 9000 })
})

test('locked legacy snapshots without cash data stay unknown, including their totals', () => {
  assert.equal(settlementCashBalance({ compensation: 9000 }), null)
  assert.equal(settlementCashBalance({ cash_sales_total: 0 }), null)
  assert.equal(settlementCashBalance({ cash_sales_total: 'bad', compensation: 9000 }), null)
  assert.equal(settlementCashTotals([{ compensation: 9000 }]), null)
  assert.deepEqual(settlementCashBalance({ cash_sales_total: '4000', compensation: '9000' }), { deposit: 0, shortfall: 5000 })
})
