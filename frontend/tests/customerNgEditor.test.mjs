import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick, reactive } from 'vue'

const root = dirname(fileURLToPath(import.meta.url))
const renderer = createRenderer({
  createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null,
  insert() {}, remove() {}, patchProp() {},
})

async function mountEditor({ id = 'new', query = {}, fail = false, customer = null } = {}) {
  const props = reactive({ id })
  const calls = [], routes = [], saved = []
  const api = {
    getCasts: async () => [{ id: 2, name: '架空セラピスト' }],
    getCustomer: async () => customer,
    getOrdersPage: async q => { calls.push(['visits', q]); return { results: [], count: 0 } },
    getCustomerInvitation: async id => { calls.push(['invitation', id]); return { state: 'NOT_ISSUED' } },
    getCustomerDuplicates: async id => { calls.push(['duplicates', id]); return [] },
    checkCustomerDuplicate: async () => [],
    createCustomer: async body => {
      if (fail) throw new Error('保存できませんでした')
      saved.push(body)
      return { ...body, id: 42, display_name: '保存済みのお客様' }
    },
    updateCustomer: async (id, body) => { saved.push(body); return { ...body, id } },
  }
  globalThis.__customerNgTest = {
    api, route: { query },
    router: { replace: async path => { routes.push(path); if (path === '/op/customers/42') props.id = '42' } },
  }
  const filename = resolve(root, '../src/pages/op/CustomerDetail.vue')
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  let code = compileScript(descriptor, { id: 'customer-ng-editor-test' }).content
    .replace(/import \{ useRouter, useRoute \} from 'vue-router'/, 'const useRouter = () => globalThis.__customerNgTest.router; const useRoute = () => globalThis.__customerNgTest.route')
    .replace(/import LayoutOperator from '[^']+'/g, 'const LayoutOperator = {}')
    .replace(/import AttentionMemo from '[^']+'/g, 'const AttentionMemo = {}')
    .replace(/import \{ api \} from '[^']+'/g, 'const api = globalThis.__customerNgTest.api')
    .replace(/import \{ getAuthRole \} from '[^']+'/g, "const getAuthRole = () => 'manager'")
  const dir = mkdtempSync(join(root, '.customer-ng-test-'))
  try {
    const compiled = join(dir, 'component.mjs'); writeFileSync(compiled, code)
    const component = (await import(pathToFileURL(compiled).href)).default
    component.render = () => null
    const app = renderer.createApp({ render: () => h(component, props) })
    const vm = app.mount({}); await new Promise(r => setImmediate(r)); await nextTick()
    return { state: vm.$.subTree.component.setupState, calls, routes, saved, unmount: () => app.unmount() }
  } finally { rmSync(dir, { recursive: true, force: true }) }
}

test('new customer immediately displays server result and loads detail sections using the new ID', async () => {
  const e = await mountEditor()
  try {
    e.state.form.phone = '09000000001'; e.state.customerCategory = 'CAST_NG'; e.state.form.ng_casts = [2]
    e.state.form.attention_memo = '70分限定\nAルームNG'
    await e.state.save(); await nextTick()
    assert.equal(e.state.customer.id, 42)
    assert.equal(e.state.customer.display_name, '保存済みのお客様')
    assert.equal(e.state.editing, false)
    assert.equal(e.state.isNew, false)
    assert.deepEqual(e.routes, ['/op/customers/42'])
    assert.ok(e.calls.some(([kind, id]) => kind === 'visits' && id.includes('customer=42')))
    assert.ok(e.calls.some(([kind, id]) => kind === 'invitation' && id === '42'))
    assert.ok(e.calls.some(([kind, id]) => kind === 'duplicates' && id === 42))
    assert.deepEqual(e.saved[0].ng_casts, [2])
    assert.equal(e.saved[0].attention_memo, '70分限定\nAルームNG')
  } finally { e.unmount() }
})

test('creation from reservation flow keeps its return route', async () => {
  const e = await mountEditor({ query: { return: '/op/phone' } })
  try { await e.state.save(); assert.deepEqual(e.routes, ['/op/phone']); assert.equal(e.calls.length, 0) }
  finally { e.unmount() }
})

test('failed creation retains editable input and does not navigate', async () => {
  const e = await mountEditor({ fail: true })
  try {
    e.state.form.display_name = '入力保持'; await e.state.save()
    assert.equal(e.state.form.display_name, '入力保持'); assert.equal(e.state.editing, true)
    assert.equal(e.state.editError, '保存できませんでした'); assert.deepEqual(e.routes, [])
  } finally { e.unmount() }
})

test('direct categories preserve legacy bans and serialize existing NG fields', async () => {
  const e = await mountEditor({ id: '5', customer: { id: 5, flag: 'BAN', ban_type: 'NONE', ng_casts: [] } })
  try {
    e.state.startEdit(); assert.equal(e.state.customerCategory, 'BAN')
    for (const [category, flag, ban_type] of [['STORE_BAN','BAN','STORE_BAN'],['CAST_NG','BAN','CAST_NG'],['ATTENTION','ATTENTION','NONE'],['NONE','NONE','NONE']]) {
      e.state.customerCategory = category
      e.state.form.ng_casts = [2]; e.state.form.online_booking_ng = true
      await e.state.save()
      const body = e.saved.at(-1)
      assert.equal(body.flag, flag); assert.equal(body.ban_type, ban_type)
      assert.deepEqual(body.ng_casts, category === 'CAST_NG' ? [2] : [])
      assert.equal(body.online_booking_ng, true)
    }
  } finally { e.unmount() }
})
