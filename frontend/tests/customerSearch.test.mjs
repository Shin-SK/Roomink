import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'

function page() {
  let mounted, changed, timer
  const calls = []
  const source = readFileSync(new URL('../src/pages/op/CustomerList.vue', import.meta.url), 'utf8')
    .split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const context = vm.createContext({
    ref: value => ({ value }), computed: get => ({ get value() { return get() } }),
    useRouter: () => ({}), getAuthRole: () => 'manager', URLSearchParams,
    onMounted: f => { mounted = f }, onBeforeUnmount: () => {},
    watch: (_, f) => { changed = f },
    setTimeout: f => { timer = f; return 1 }, clearTimeout: () => { timer = null },
    api: { getCustomersPage: params => new Promise((resolve, reject) => calls.push({ params, resolve, reject })) },
  })
  vm.runInContext(source, context)
  return { context, calls, mount: () => mounted(), change: () => changed(), flush: () => timer() }
}

test('search and flag go to the server across all pages, with paging reset', async () => {
  const p = page()
  const initial = p.mount()
  p.calls[0].resolve({ count: 1001, results: [{ id: 1 }] })
  await initial
  vm.runInContext('search.value = "ページ外顧客"; flagFilter.value = "ATTENTION"', p.context)
  p.change()
  const search = p.flush()
  assert.match(p.calls[1].params, /offset=0/)
  assert.equal(new URLSearchParams(p.calls[1].params).get('search'), 'ページ外顧客')
  assert.equal(new URLSearchParams(p.calls[1].params).get('flag'), 'ATTENTION')
  p.calls[1].resolve({ count: 51, results: [{ id: 1001 }] })
  await search
  assert.equal(vm.runInContext('filtered.value[0].id', p.context), 1001)
  const next = vm.runInContext('loadCustomers(50)', p.context)
  assert.match(p.calls[2].params, /offset=50/)
  p.calls[2].resolve({ count: 51, results: [{ id: 1002 }] })
  await next
  assert.equal(vm.runInContext('offset.value', p.context), 50)
})

test('stale success and failure cannot overwrite a new query; failures can retry', async () => {
  const p = page()
  const old = p.mount()
  vm.runInContext('search.value = "最新"', p.context)
  p.change()
  const fresh = p.flush()
  p.calls[1].resolve({ count: 1, results: [{ id: 2 }] })
  await fresh
  p.calls[0].resolve({ count: 99, results: [{ id: 1 }] })
  await old
  assert.equal(vm.runInContext('customers.value[0].id', p.context), 2)
  const failed = vm.runInContext('loadCustomers()', p.context)
  p.calls[2].reject(new Error('通信失敗'))
  await failed
  assert.equal(vm.runInContext('error.value', p.context), '通信失敗')
  assert.equal(vm.runInContext('customers.value.length', p.context), 0)
  const retry = vm.runInContext('loadCustomers()', p.context)
  p.calls[3].resolve({ count: 0, results: [] })
  await retry
  assert.equal(vm.runInContext('error.value', p.context), '')
  assert.equal(vm.runInContext('loading.value', p.context), false)
})
