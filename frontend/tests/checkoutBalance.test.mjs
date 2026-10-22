import test from 'node:test'
import assert from 'node:assert/strict'
import { checkoutBalanceDisplay } from '../src/checkoutBalance.js'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h } from 'vue'

test('shows unpaid compensation as a shortage, including carryover in the available amount', () => {
  assert.deepEqual(checkoutBalanceDisplay(31000, 26000), {
    label: '不足', amount: 5000, tone: 'text-danger', isShortage: true,
  })
  assert.equal(checkoutBalanceDisplay(5000 + 31000, 26000).amount, 10000)
})

test('office payments reduce the shortage and full payment has no shortage', () => {
  assert.equal(checkoutBalanceDisplay(31000, 26000, 2000).amount, 3000)
  assert.equal(checkoutBalanceDisplay(31000, 26000, 5000).label, '不足なし')
  assert.equal(checkoutBalanceDisplay(0, 0).isShortage, false)
})

test('overpayment and negative entitlement are never described as a shortage', () => {
  assert.equal(checkoutBalanceDisplay(31000, 32000).label, '受取超過')
  assert.equal(checkoutBalanceDisplay(31000, 32000).amount, 1000)
  assert.deepEqual(checkoutBalanceDisplay(-1000, 0), {
    label: '精算残額', amount: -1000, tone: 'text-danger', isShortage: false,
  })
})

test('checkout uses live input on new and returned forms, and recorded payments after submission', async () => {
  const root = dirname(fileURLToPath(import.meta.url))
  const filename = resolve(root, '../src/pages/cast/CastMypage.vue')
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  const code = compileScript(descriptor, { id: 'checkout-balance-test' }).content
    .replace(/import LayoutCast from [^\n]+/, 'const LayoutCast = {}')
    .replace(/import RoomCashPanel from [^\n]+/, 'const RoomCashPanel = {}')
    .replace(/import CastAttendanceCard from [^\n]+/, 'const CastAttendanceCard = {}')
    .replace(/import \{ api \} from [^\n]+/, 'const api = {}')
    .replace(/onMounted\(async \(\) =>/, '(() => {})(async () =>')
    .replace(/from (['"])(\.[^'"]+)\1/g, (_, quote, specifier) => `from ${quote}${pathToFileURL(resolve(dirname(filename), specifier)).href}${quote}`)
  const temporary = mkdtempSync(join(root, '.checkout-balance-test-'))
  let app
  try {
    const compiled = join(temporary, 'component.mjs')
    writeFileSync(compiled, code)
    const component = (await import(pathToFileURL(compiled).href)).default
    component.render = () => null
    const renderer = createRenderer({
      createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
      setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null,
      insert() {}, remove() {}, patchProp() {},
    })
    app = renderer.createApp({ render: () => h(component) })
    const vm = app.mount({})
    const state = vm.$.subTree.component.setupState
    state.checkoutData = { compensation: 31000, cash_sales_total: 35000 }
    state.checkoutForm.room_cash_taken_amount = 26000
    assert.equal(state.checkoutBalance.amount, 5000)
    assert.equal(state.checkoutDeposit.deposit, 9000)
    state.checkoutData.cash_sales_total = 4000
    assert.equal(state.checkoutDeposit.deposit, 0)
    assert.equal(state.checkoutDeposit.withdrawal, 22000)
    state.checkoutData.checkout = {
      status: 'RETURNED', compensation_amount: 31000, room_cash_taken_amount: 10000,
      office_cash_paid_amount: 2000,
    }
    assert.equal(state.checkoutBalance.amount, 3000)
    state.checkoutForm.room_cash_taken_amount = 29000
    assert.equal(state.checkoutBalance.label, '不足なし')
    state.checkoutData.checkout.status = 'SUBMITTED'
    assert.equal(state.checkoutCarryover.roomCash, 10000)
    assert.equal(state.checkoutDeposit.withdrawal, 6000)
    assert.equal(state.checkoutBalance.amount, 19000)
  } finally {
    app?.unmount()
    rmSync(temporary, { recursive: true, force: true })
  }
})
