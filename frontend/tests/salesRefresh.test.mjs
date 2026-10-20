import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'

test('sales refresh serializes requests, coalesces filters and ignores stale results', async () => {
  const source = readFileSync(new URL('../src/pages/op/SalesSummary.vue', import.meta.url), 'utf8')
    .split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const pending = []
  const calls = []
  let timer
  let onChange
  let dispose
  const context = vm.createContext({
    ref: value => ({ value }),
    computed: get => ({ get value() { return get() } }),
    watch: (_refs, callback) => { onChange = callback },
    onMounted: () => {},
    onBeforeUnmount: callback => { dispose = callback },
    getAuthRole: () => 'manager',
    setTimeout: callback => { timer = callback; return 1 },
    clearTimeout: () => { timer = undefined },
    api: { getSalesDashboard: params => {
      calls.push(params)
      return new Promise(resolve => pending.push(resolve))
    } },
  })
  vm.runInContext(source, context)
  const first = vm.runInContext('fetchDashboard()', context)
  vm.runInContext("range.value = 'week'", context)
  onChange()
  await timer()
  vm.runInContext("range.value = 'month'", context)
  onChange()
  await timer()
  assert.equal(calls.length, 1, 'filter changes must not overlap server work')
  pending.shift()({ total_sales: 1 })
  await first
  assert.equal(vm.runInContext('data.value', context), null, 'old result must not replace the selected period')
  const latest = timer()
  assert.equal(calls.length, 2)
  assert.equal(calls[1], 'range=month')
  pending.shift()({ total_sales: 2 })
  await latest
  assert.equal(vm.runInContext('data.value.total_sales', context), 2)
  assert.equal(vm.runInContext('loading.value', context), false)
  dispose()
  await vm.runInContext('fetchDashboard()', context)
  assert.equal(calls.length, 2, 'leaving the page must stop queued refreshes')
})
