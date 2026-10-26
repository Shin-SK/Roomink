import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { calendarDays, movePeriod, parseDay } from '../src/shiftCalendar.js'

test('period navigation ignores late results and late failures, and stops fetching after leaving', async () => {
  const source = readFileSync(new URL('../src/pages/op/ShiftList.vue', import.meta.url), 'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const pending = [], params = []
  let dispose
  const context = vm.createContext({
    ref: value => ({ value }), computed: get => ({ get value() { return get() } }),
    watch: () => {}, onMounted: () => {}, onBeforeUnmount: callback => { dispose = callback },
    nextTick: async () => {}, document: { getElementById: () => null }, clearInterval: () => {},
    calendarDays, movePeriod, parseDay,
    api: { getShifts: query => { params.push(query); return new Promise((resolve, reject) => pending.push({ resolve, reject })) } },
  })
  vm.runInContext(source, context)
  vm.runInContext("calendarAnchor.value = '2026-12-01'", context)
  const old = vm.runInContext('loadShifts()', context)
  vm.runInContext("calendarAnchor.value = '2027-01-01'", context)
  const current = vm.runInContext('loadShifts()', context)
  assert.match(params[0], /date__gte=2026-11-30&date__lte=2027-01-10/)
  assert.match(params[1], /date__gte=2026-12-28&date__lte=2027-02-07/)
  pending[1].resolve([{ id: 2 }]); await current
  pending[0].resolve([{ id: 1 }]); await old
  assert.equal(vm.runInContext('shifts.value[0].id', context), 2)
  const failure = vm.runInContext('loadShifts()', context)
  const latest = vm.runInContext('loadShifts()', context)
  pending[3].resolve([{ id: 3 }]); await latest
  pending[2].reject(new Error('old period failed')); await failure
  assert.equal(vm.runInContext('shifts.value[0].id', context), 3)
  assert.equal(vm.runInContext('error.value', context), '')
  assert.equal(vm.runInContext('loading.value', context), false)
  dispose()
  await vm.runInContext('loadShifts()', context)
  assert.equal(params.length, 4)
})
