import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick, reactive } from 'vue'

async function mount(api, props) {
  const root = dirname(fileURLToPath(import.meta.url))
  const filename = resolve(root, '../src/components/EnvelopeReceiptCell.vue')
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  const code = compileScript(descriptor, { id: 'envelope-test' }).content
    .replace(/import \{ api \} from [^\n]+/, 'const api = globalThis.__envelopeApi')
  const temporary = mkdtempSync(join(root, '.envelope-test-'))
  globalThis.__envelopeApi = api
  try {
    const compiled = join(temporary, 'component.mjs'); writeFileSync(compiled, code)
    const component = (await import(pathToFileURL(compiled).href)).default
    component.render = () => null
    const renderer = createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, insert() {}, remove() {}, patchProp() {} })
    const app = renderer.createApp({ render: () => h(component, props) })
    const vm = app.mount({}); await nextTick()
    return { state: vm.$.subTree.component.setupState, close: () => app.unmount() }
  } finally { delete globalThis.__envelopeApi; rmSync(temporary, { recursive: true, force: true }) }
}
const entry = { checkout: 1, expected_amount: 15000, actual_amount: null, received: false, memo: '', version: 0, source_revision: 'first' }

test('network retries retain the same request ID and conflicts preserve actual and memo', async () => {
  const calls = []; let conflict = false
  const props = reactive({ entry: { ...entry } })
  const { state, close } = await mount({ saveEnvelopeReceipt: async body => { calls.push(body); throw Object.assign(new Error('offline'), { status: conflict ? 409 : 500 }) } }, props)
  try {
    state.actual = '14000'; state.memo = '千円不足'
    await state.save('receive'); await state.save('receive')
    assert.equal(calls[0].request_id, calls[1].request_id)
    conflict = true; await state.save('receive'); await state.save('receive')
    assert.equal(calls.length, 3)
    props.entry = { ...entry, version: 1, source_revision: 'next' }; await nextTick()
    assert.equal(state.actual, '14000'); assert.equal(state.memo, '千円不足')
    await state.save('receive'); assert.equal(calls[3].source_revision, 'next')
  } finally { close() }
})

test('failed checkbox save restores the persisted state and recheck preserves actual amount', async () => {
  const calls = []
  const { state, close } = await mount({ saveEnvelopeReceipt: async body => { calls.push(body); throw new Error('failed') } }, { entry: { ...entry, received: true, actual_amount: 14000, needs_reconfirmation: true } })
  try {
    const event = { target: { checked: true } }; state.toggle(event)
    await nextTick(); await nextTick()
    assert.equal(event.target.checked, false)
    assert.equal(calls[0].actual_amount, 14000)
  } finally { close() }
})

test('empty and fractional amounts cannot be sent as zero', async () => {
  const calls = []
  const { state, close } = await mount({ saveEnvelopeReceipt: async body => calls.push(body) }, { entry })
  try {
    for (const value of ['', '1.5', '-1', 'invalid']) { state.actual = value; await state.save('receive') }
    assert.equal(calls.length, 0)
  } finally { close() }
})
