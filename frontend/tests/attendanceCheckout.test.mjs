import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h } from 'vue'

async function mount(api) {
  const root = dirname(fileURLToPath(import.meta.url))
  const filename = resolve(root, '../src/pages/cast/CastMypage.vue')
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  const code = compileScript(descriptor, { id: 'attendance-checkout-test' }).content
    .replace(/import (LayoutCast|RoomCashPanel|CastAttendanceCard) from [^\n]+/g, (_, name) => `const ${name} = {}`)
    .replace(/import \{ api \} from [^\n]+/, 'const api = globalThis.__attendanceCheckoutApi')
    .replace(/onMounted\(async \(\) =>/, '(() => {})(async () =>')
    .replace(/from (['"])(\.[^'"]+)\1/g, (_, quote, specifier) => `from ${quote}${pathToFileURL(resolve(dirname(filename), specifier)).href}${quote}`)
  const temporary = mkdtempSync(join(root, '.attendance-checkout-test-'))
  globalThis.__attendanceCheckoutApi = api
  try {
    const compiled = join(temporary, 'component.mjs')
    writeFileSync(compiled, code)
    const component = (await import(pathToFileURL(compiled).href)).default
    component.render = () => null
    const renderer = createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, insert() {}, remove() {}, patchProp() {} })
    const app = renderer.createApp({ render: () => h(component) })
    const vm = app.mount({})
    return { state: vm.$.subTree.component.setupState, unmount: () => app.unmount() }
  } finally { delete globalThis.__attendanceCheckoutApi; rmSync(temporary, { recursive: true, force: true }) }
}

test('an open checkout keeps its displayed business day across polling and sends that exact day', async () => {
  let reads = 0
  let submitted
  let finishSubmission
  const { state, unmount } = await mount({
    getCastCheckout: async date => { reads++; return { date: date || '2026-10-21', current_business_date: '2026-10-22', can_submit: true } },
    submitCastCheckout: async body => { submitted = body; await new Promise(resolve => { finishSubmission = resolve }) },
    getCastAdjustmentsMypage: async () => ({}),
  })
  try {
    await state.loadCheckout()
    state.openCheckoutModal()
    await state.loadCheckout()
    assert.equal(reads, 1)
    state.checkoutForm.checklist_json = Object.fromEntries(state.CHECKLIST_ITEMS.map(item => [item.key, true]))
    const first = state.submitCheckout()
    await state.submitCheckout()
    assert.equal(submitted.date, '2026-10-21')
    finishSubmission()
    await first
    assert.equal(reads, 2)
    assert.equal(state.showCheckoutModal, false)
  } finally { unmount() }
})

test('a late response cannot overwrite a newly selected day; failed loads prevent opening a stale form', async () => {
  let finishOld
  const api = { getCastCheckout: date => date === '2026-10-20' ? new Promise(resolve => { finishOld = resolve }) : Promise.resolve({ date, can_submit: true }) }
  const { state, unmount } = await mount(api)
  try {
    state.checkoutDate = '2026-10-20'
    const old = state.loadCheckout()
    state.checkoutDate = '2026-10-21'
    await state.loadCheckout()
    finishOld({ date: '2026-10-20', can_submit: true })
    await old
    assert.equal(state.checkoutData.date, '2026-10-21')
    api.getCastCheckout = async () => { throw new Error('通信に失敗しました') }
    state.checkoutDate = '2026-10-19'
    await state.loadCheckout()
    state.openCheckoutModal()
    assert.equal(state.showCheckoutModal, false)
    assert.equal(state.checkoutLoadError, '通信に失敗しました')
  } finally { unmount() }
})
