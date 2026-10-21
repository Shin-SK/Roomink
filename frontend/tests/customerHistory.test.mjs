import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'

function page(id = '7', denied = false) {
  let mounted
  const calls = []
  const source = readFileSync(new URL('../src/pages/op/CustomerDetail.vue', import.meta.url), 'utf8')
    .split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const context = vm.createContext({
    ref: value => ({ value }), computed: get => ({ get value() { return get() } }),
    defineProps: () => ({ id }), useRouter: () => ({}), useRoute: () => ({ query: {} }),
    getAuthRole: () => 'manager', watch: () => {}, onMounted: callback => { mounted = callback },
    api: {
      getCasts: async () => [],
      getCustomer: async () => { if (denied) throw new Error('not found'); return { id } },
      getCustomerInvitation: async () => ({}), getCustomerDuplicates: async () => [],
      getOrdersPage: async params => {
        calls.push(params)
        const offset = Number(new URLSearchParams(params).get('offset'))
        return { count: 22, results: Array.from({ length: Math.min(20, 22-offset) }, (_, i) => ({ id: offset+i+1 })) }
      },
    }, URLSearchParams,
  })
  vm.runInContext(source, context)
  return { context, calls, mount: () => mounted() }
}

test('opening customer detail loads completed visits, then appends the next page', async () => {
  const p = page()
  await p.mount()
  await Promise.resolve()
  assert.equal(p.calls.length, 1, 'initial navigation must load the history')
  assert.equal(p.calls[0], 'customer=7&status=DONE&ordering=-start&limit=20&offset=0')
  assert.equal(vm.runInContext('visits.value.length', p.context), 20)
  await vm.runInContext('loadVisits()', p.context)
  assert.ok(p.calls[1].endsWith('offset=20'))
  assert.equal(vm.runInContext('new Set(visits.value.map(v => v.id)).size', p.context), 22)
  assert.equal(vm.runInContext('visitCount.value', p.context), 22)
})

test('new or inaccessible customers do not request visit data', async () => {
  for (const p of [page('new'), page('8', true)]) {
    await p.mount()
    assert.equal(p.calls.length, 0)
  }
})
