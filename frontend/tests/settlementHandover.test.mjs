import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick, reactive } from 'vue'

async function mount(api, props) {
  const root = dirname(fileURLToPath(import.meta.url))
  const filename = resolve(root, '../src/components/SettlementHandover.vue')
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  const code = compileScript(descriptor, { id: 'handover-test' }).content
    .replace(/import \{ api \} from [^\n]+/, 'const api = globalThis.__handoverApi')
    .replace(/import \{ useRoute \} from [^\n]+/, 'const useRoute = () => ({query: {store: "1"}})')
  const temporary = mkdtempSync(join(root, '.handover-test-'))
  globalThis.__handoverApi = api
  try {
    const compiled = join(temporary, 'component.mjs'); writeFileSync(compiled, code)
    const component = (await import(pathToFileURL(compiled).href)).default
    component.render = () => null
    const renderer = createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, insert() {}, remove() {}, patchProp() {} })
    const app = renderer.createApp({ render: () => h(component, props) })
    const vm = app.mount({}); await nextTick()
    return { state: vm.$.subTree.component.setupState, close: () => app.unmount() }
  } finally { delete globalThis.__handoverApi; rmSync(temporary, { recursive: true, force: true }) }
}
const row = { cast_id: 4, receivable_amount: 10000, office_cash_paid_amount: 0, can_register_by_store: true, settlement_source_revision: 'first' }

test('blank is not zero; zero needs a reason; invalid amounts cannot be submitted', async () => {
  const calls = []
  const { state, close } = await mount({ registerCheckoutByStore: async body => calls.push(body) }, { row, date: '2026-11-16' })
  try {
    state.reason = '確認済み'
    for (const value of ['', '-1', '1.5', '1e3', '10001']) { state.amount = value; await state.save() }
    assert.equal(calls.length, 0)
    state.amount = '0'; state.reason = ''; await state.save(); assert.equal(calls.length, 0)
    state.reason = '受取なしと本人に確認'; await state.save()
    assert.equal(calls[0].room_cash_taken_amount, 0)
  } finally { close() }
})

test('retries reuse one ID and 409 prevents blind resubmission', async () => {
  const calls = []; let conflict = false
  const props = reactive({ row: { ...row }, date: '2026-11-16' })
  const { state, close } = await mount({ registerCheckoutByStore: async body => { calls.push(body); throw Object.assign(new Error('offline'), { status: conflict ? 409 : 500 }) } }, props)
  try {
    state.amount = '9000'; state.reason = '確認済み'
    await state.save(); await state.save()
    assert.equal(calls[0].request_id, calls[1].request_id)
    conflict = true; await state.save(); await state.save(); assert.equal(calls.length, 3)
    props.row = { ...row, settlement_source_revision: 'updated' }; await nextTick()
    assert.equal(state.amount, '9000')
    await state.save(); assert.equal(calls[3].source_revision, 'updated')
  } finally { close() }
})

test('date change clears money and reason; locked days cannot be registered', async () => {
  const calls = []
  const props = reactive({ row: { ...row }, date: '2026-11-16', locked: false })
  const { state, close } = await mount({ registerCheckoutByStore: async body => calls.push(body) }, props)
  try {
    state.amount = '9000'; state.reason = '確認済み'; props.date = '2026-11-15'; await nextTick()
    assert.equal(state.amount, ''); assert.equal(state.reason, '')
    state.amount = '9000'; state.reason = '確認済み'; props.locked = true; await nextTick(); await state.save()
    assert.equal(calls.length, 0)
  } finally { close() }
})
