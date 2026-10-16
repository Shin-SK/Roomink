import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick } from 'vue'

const root = dirname(fileURLToPath(import.meta.url))
const renderer = createRenderer({
  createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null,
  insert() {}, remove() {}, patchProp() {},
})

async function mountSource(relative, props, transform = code => code) {
  const filename = resolve(root, relative)
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  let code = compileScript(descriptor, { id: 'order-edit-test' }).content
  code = transform(code).replace(/from (['"])(\.[^'"]+)\1/g, (_, quote, specifier) => (
    `from ${quote}${pathToFileURL(resolve(dirname(filename), specifier)).href}${quote}`
  ))
  const temporary = mkdtempSync(join(root, '.order-edit-test-'))
  try {
    const compiled = join(temporary, 'component.mjs')
    writeFileSync(compiled, code)
    const component = (await import(pathToFileURL(compiled).href)).default
    component.render = () => null
    const app = renderer.createApp({ render: () => h(component, props) })
    const vm = app.mount({})
    await new Promise(resolve => setImmediate(resolve))
    await nextTick()
    return { state: vm.$.subTree.component.setupState, unmount: () => app.unmount() }
  } finally {
    rmSync(temporary, { recursive: true, force: true })
  }
}

const initial = {
  id: 1, cast: 1, customer: 1, course: 1, course_price: 20000,
  business_date: '2026-10-16', start_time_extended: '12:00', end_time_extended: '13:00',
  start: '2026-10-16T03:00:00Z', end: '2026-10-16T04:00:00Z',
  option_ids: [3], options: ['既存'], options_price: 5000, total_price: 25000,
  payment_method: 'CASH', card_include_options: false, updated_at: '2026-10-16T08:00:00.123456Z',
}
const latest = { ...initial, option_ids: [3, 4], options: ['既存', '追加'], options_price: 7000, total_price: 27000, updated_at: '2026-10-16T08:01:00.123456Z' }
const conflict = () => Object.assign(new Error('予約が更新されています'), { status: 409 })

test('operator conflict preserves the draft while latest data is inspected; replacing it requires confirmation', async () => {
  const api = {
    getCustomers: async () => [{ id: 1 }], getCasts: async () => [{ id: 1 }],
    getCourses: async () => [{ id: 1, name: '60分', price: 20000, duration: 60 }],
    getOptions: async () => [{ id: 3, name: '既存', price: 5000 }, { id: 4, name: '追加', price: 2000 }],
    getExtensions: async () => [], getNominationFees: async () => [], getMedia: async () => [],
    getDiscounts: async () => [], getPaymentFeeSettings: async () => ({}),
    getCustomerReservationContext: async () => ({}), getOrder: async () => latest,
    updateOrder: async (id, patch) => {
      assert.equal(id, 1)
      assert.equal(patch.memo, '入力中')
      assert.equal(patch.expected_updated_at, initial.updated_at)
      assert.equal('options' in patch, false)
      throw conflict()
    },
  }
  const { state, unmount } = await mountSource('../src/components/OrderForm.vue', {
    mode: 'edit', orderId: 1, initialOrder: initial, apiClient: api,
  })
  const previousConfirm = globalThis.confirm
  try {
    assert.equal(state.loading, false)
    state.form.memo = '入力中'
    await state.submitEdit()
    assert.equal(state.editConflict, true)
    assert.equal(state.form.memo, '入力中')
    await state.checkLatestOrder()
    assert.equal(state.latestOrder.total_price, 27000)
    assert.equal(state.form.memo, '入力中')
    assert.deepEqual([...state.form.options], [3])
    globalThis.confirm = () => false
    state.restartWithLatestOrder()
    assert.equal(state.form.memo, '入力中')
    globalThis.confirm = () => true
    state.restartWithLatestOrder()
    assert.equal(state.editConflict, false)
    assert.deepEqual([...state.form.options], [3, 4])
    assert.equal(state.editBaseline.updated_at, latest.updated_at)
  } finally {
    globalThis.confirm = previousConfirm
    unmount()
  }
})

test('after conflict recovery, removing a newly added discount and extension saves against the latest baseline', async () => {
  const noExtras = { ...initial, discount: null, extension: null, extension_duration: 0, extension_price: 0 }
  const withExtras = { ...latest, discount: 9, extension: 8, extension_duration: 30, extension_price: 5000, end_time_extended: '13:30' }
  const patches = []
  const api = {
    getCustomers: async () => [{ id: 1 }], getCasts: async () => [{ id: 1 }],
    getCourses: async () => [{ id: 1, name: '60分', price: 20000, duration: 60 }],
    getOptions: async () => [], getExtensions: async () => [{ id: 8, duration: 30, price: 5000, is_active: true }],
    getNominationFees: async () => [], getMedia: async () => [],
    getDiscounts: async () => [{ id: 9, name: '割引', discount_type: 'fixed', value: 1000, is_active: true }],
    getPaymentFeeSettings: async () => ({}), getCustomerReservationContext: async () => ({}),
    getOrder: async () => withExtras,
    updateOrder: async (id, patch) => { patches.push(patch); if (patches.length === 1) throw conflict(); return { ...withExtras, ...patch } },
  }
  const { state, unmount } = await mountSource('../src/components/OrderForm.vue', {
    mode: 'edit', orderId: 1, initialOrder: noExtras, apiClient: api,
  })
  const previousConfirm = globalThis.confirm
  try {
    state.form.memo = '変更'
    await state.submitEdit()
    assert.equal(state.editConflict, true)
    await state.checkLatestOrder()
    globalThis.confirm = () => true
    state.restartWithLatestOrder()
    assert.equal(state.form.discount, 9)
    assert.equal(state.form.extension, 8)
    state.form.discount = ''
    state.selectExtensionTemplate('')
    await nextTick()
    await state.submitEdit()
    assert.equal(patches.length, 2)
    assert.equal(patches[1].expected_updated_at, withExtras.updated_at)
    assert.equal(patches[1].discount, null)
    assert.equal(patches[1].extension, null)
    assert.equal(patches[1].extension_duration, 0)
    assert.equal(patches[1].extension_price, 0)
    assert.equal('options' in patches[1], false)
  } finally { globalThis.confirm = previousConfirm; unmount() }
})

test('cast conflict uses the version at editor-open and keeps selected options during latest-data inspection', async () => {
  const castInitial = { ...initial, options: [{ id: 3, name: '既存' }] }
  const castLatest = { ...latest, options: [{ id: 3, name: '既存' }, { id: 4, name: '追加' }] }
  let latestRequested = false
  globalThis.__castApiForTests = {
    getCastToday: async () => ({ date: '2026-10-16', orders: [latestRequested ? castLatest : castInitial] }),
    updateCastOrderOptions: async (id, ids, version) => {
      assert.deepEqual([...ids], [4])
      assert.equal(version, initial.updated_at)
      throw conflict()
    },
  }
  const transform = code => code
    .replace(/import LayoutCast from [^\n]+/, 'const LayoutCast = {}')
    .replace(/import \{ api \} from [^\n]+/, 'const api = globalThis.__castApiForTests')
  const { state, unmount } = await mountSource('../src/pages/cast/CastOrders.vue', {}, transform)
  const previousConfirm = globalThis.confirm
  try {
    state.openOptionEditor(castInitial)
    state.optionDraftIds = [4]
    await state.saveOptions(castInitial)
    assert.equal(state.optionConflict, true)
    latestRequested = true
    await state.checkLatestOptions(castInitial)
    assert.deepEqual([...state.optionDraftIds], [4])
    globalThis.confirm = () => true
    state.restartOptions(castInitial)
    assert.deepEqual([...state.optionDraftIds], [3, 4])
    assert.equal(state.optionVersion, latest.updated_at)
    assert.equal(state.optionConflict, false)
  } finally {
    globalThis.confirm = previousConfirm
    delete globalThis.__castApiForTests
    unmount()
  }
})

test('quick payment changes restore the displayed method on conflict and can load the current version', async () => {
  let refreshed = false
  globalThis.__detailApiForTests = {
    getOrder: async () => refreshed ? latest : initial,
    getExtensions: async () => [], getNominationFees: async () => [], getDiscounts: async () => [],
    getPaymentFeeSettings: async () => ({}), getOrderSmsLogs: async () => [],
    updateOrder: async (id, patch) => {
      assert.equal(patch.expected_updated_at, initial.updated_at)
      assert.equal(patch.payment_method, 'CARD')
      assert.equal('options' in patch, false)
      throw conflict()
    },
  }
  const transform = code => code
    .replace(/import \{ useRouter \} from [^\n]+/, 'const useRouter = () => ({})')
    .replace(/import LayoutOperator from [^\n]+/, 'const LayoutOperator = {}')
    .replace(/import OrderForm from [^\n]+/, 'const OrderForm = {}')
    .replace(/import \{ api \} from [^\n]+/, 'const api = globalThis.__detailApiForTests')
    .replace(/import \{ getAuthRole \} from [^\n]+/, 'const getAuthRole = () => "staff"')
  const { state, unmount } = await mountSource('../src/pages/op/OrderDetail.vue', { id: 1 }, transform)
  try {
    assert.equal(state.order.payment_method, 'CASH')
    const event = { target: { value: 'CARD' } }
    await state.updatePaymentMethod(event)
    assert.equal(event.target.value, 'CASH')
    assert.equal(state.paymentMethodSaving, false)
    assert.match(state.paymentMethodError, /予約が更新/)
    refreshed = true
    await state.reloadPaymentOrder()
    assert.equal(state.order.updated_at, latest.updated_at)
    assert.equal(state.paymentMethodError, '')
  } finally {
    delete globalThis.__detailApiForTests
    unmount()
  }
})
