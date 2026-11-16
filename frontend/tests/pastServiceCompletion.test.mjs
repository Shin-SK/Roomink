import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h } from 'vue'

async function mount(api) {
  const root = dirname(fileURLToPath(import.meta.url))
  const filename = resolve(root, '../src/pages/cast/CastOrders.vue')
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  const code = compileScript(descriptor, { id: 'past-service-test' }).content
    .replace(/import LayoutCast from [^\n]+/, 'const LayoutCast = {}')
    .replace(/import \{ api \} from [^\n]+/, 'const api = globalThis.__pastServiceApi')
    .replace('onMounted(() => loadOrders())', '')
  const temporary = mkdtempSync(join(root, '.past-service-test-'))
  globalThis.__pastServiceApi = api
  try {
    const compiled = join(temporary, 'component.mjs')
    writeFileSync(compiled, code)
    const component = (await import(pathToFileURL(compiled).href)).default
    component.render = () => null
    const renderer = createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, insert() {}, remove() {}, patchProp() {} })
    const app = renderer.createApp({ render: () => h(component) })
    const vm = app.mount({})
    return { state: vm.$.subTree.component.setupState, unmount: () => app.unmount() }
  } finally { delete globalThis.__pastServiceApi; rmSync(temporary, { recursive: true, force: true }) }
}

test('yesterday permits only unfinished service completion; future and locked days stay read-only', async () => {
  const { state, unmount } = await mount({})
  try {
    state.currentBusinessDate = '2026-11-16'
    state.selectedDate = '2026-11-15'
    for (const status of ['IN_PROGRESS', 'PENDING_FINALIZE']) assert.equal(state.canCompletePastOrder({ status }), true)
    for (const status of ['REQUESTED', 'CONFIRMED', 'DONE', 'CANCELLED']) assert.equal(state.canCompletePastOrder({ status }), false)
    state.isLocked = true
    assert.equal(state.canCompletePastOrder({ status: 'IN_PROGRESS' }), false)
    state.isLocked = false
    state.selectedDate = '2026-11-17'
    assert.equal(state.canCompletePastOrder({ status: 'IN_PROGRESS' }), false)
  } finally { unmount() }
})

test('refresh after the business-day cutoff uses server current day without changing the selected reservation day', async () => {
  let currentDay = '2026-11-15'
  const { state, unmount } = await mount({ getCastToday: async date => ({ date: date || currentDay, current_business_date: currentDay, is_locked: false, orders: [{ id: 1, status: 'IN_PROGRESS' }], total_orders: 1 }) })
  try {
    await state.loadOrders()
    assert.equal(state.isCurrentBusinessDate, true)
    currentDay = '2026-11-16'
    await state.loadOrders('2026-11-15')
    assert.equal(state.selectedDate, '2026-11-15')
    assert.equal(state.isCurrentBusinessDate, false)
    assert.equal(state.canCompletePastOrder(state.orders[0]), true)
  } finally { unmount() }
})
