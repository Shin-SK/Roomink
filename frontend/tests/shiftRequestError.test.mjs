import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { shiftRequestError } from '../src/shiftRequestError.js'
import { normalizeShiftTime } from '../src/shiftTime.js'

test('date-keyed nested conflict explains the date, rollback and next action', () => {
  const text = shiftRequestError({ status: 400, message: '[object Object]', data: {
    '2026-11-06': { non_field_errors: ['同じ時間帯に申請中のシフトがあります'] },
  } })
  assert.match(text, /11\/6：同じ時間帯に申請中のシフトがあります/)
  assert.match(text, /すべて保存されていません/)
  assert.match(text, /選択解除/)
  assert.doesNotMatch(text, /object Object|non_field_errors/)
})

test('field and list errors retain all human-readable reasons', () => {
  const text = shiftRequestError({ status: 400, data: { items: [
    { start_time: ['開始時間を確認してください'] },
    { end_time: ['終了時間を確認してください'] },
  ] } })
  assert.match(text, /開始時間を確認してください/)
  assert.match(text, /終了時間を確認してください/)
})

test('multiple date errors keep their dates and remove duplicate messages', () => {
  const text = shiftRequestError({ status: 400, data: {
    '2026-12-31': ['時間を確認してください', '時間を確認してください'],
    '2027-01-01': ['時間を確認してください'],
  } })
  assert.equal(text.match(/12\/31：/g).length, 1)
  assert.match(text, /1\/1：/)
})

test('permission errors do not claim that the request was rolled back', () => {
  const text = shiftRequestError({ status: 403, data: { detail: 'ログインしてください' } })
  assert.match(text, /ログインしてください/)
  assert.doesNotMatch(text, /すべて保存されていません/)
})

test('unknown network outcome asks to check before retrying', () => {
  const text = shiftRequestError(new Error('Failed to fetch'))
  assert.match(text, /申請一覧で保存状況を確認/)
  assert.doesNotMatch(text, /すべて保存されていません/)
})

test('failed bulk save keeps all inputs, reveals the reason and never retries or sends twice', async () => {
  const source = readFileSync(new URL('../src/pages/cast/CastShiftRequests.vue', import.meta.url), 'utf8')
    .split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  let rejectSave, calls = 0, scrolled = 0
  const context = vm.createContext({
    ref: value => ({ value }), computed: get => ({ get value() { return get() } }),
    onMounted() {}, nextTick: async () => {}, normalizeShiftTime, shiftRequestError,
    api: { createCastShiftRequestsBulk: () => {
      calls++
      return new Promise((resolve, reject) => { rejectSave = reject })
    } },
    reveal: { scrollIntoView() { scrolled++ } },
  })
  vm.runInContext(source, context)
  vm.runInContext(`showForm.value = true; formErrorAlert.value = reveal;
    form.value = { memo: 'そのまま保持', days: [6, 7, 8].map(d => ({
      date: '2026-11-0' + d, enabled: true, start_time: '20:00', end_time: '29:00'
    })) };`, context)
  const before = vm.runInContext('JSON.stringify(form.value)', context)
  const saving = vm.runInContext('onSave()', context)
  await vm.runInContext('onSave()', context)
  rejectSave({ status: 400, data: { '2026-11-06': { non_field_errors: ['同じ時間帯に申請中のシフトがあります'] } } })
  await saving
  assert.equal(calls, 1)
  assert.equal(scrolled, 1)
  assert.equal(vm.runInContext('JSON.stringify(form.value)', context), before)
  assert.equal(vm.runInContext('showForm.value', context), true)
  assert.equal(vm.runInContext('saving.value', context), false)
  assert.match(vm.runInContext('formError.value', context), /11\/6：同じ時間帯/)
})
