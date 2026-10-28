import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { shiftRequestError, shiftRequestFieldErrors } from '../src/shiftRequestError.js'
import { normalizeShiftTime } from '../src/shiftTime.js'

test('date-keyed nested conflict explains the date, rollback and next action', () => {
  const text = shiftRequestError({ status: 400, message: '[object Object]', data: {
    '2026-11-06': { non_field_errors: ['同じ時間帯に申請中のシフトがあります'] },
  } })
  assert.match(text, /申請済みのシフトと重なっています/)
  assert.match(text, /赤い欄/)
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
    onMounted() {}, nextTick: async () => {}, normalizeShiftTime, shiftRequestError, shiftRequestFieldErrors,
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
  assert.match(vm.runInContext('formError.value', context), /申請済みのシフトと重なっています/)
  assert.match(vm.runInContext("dayErrors.value['2026-11-06']", context), /申請中のシフトがあります/)
  vm.runInContext("clearDayError('2026-11-06')", context)
  assert.equal(vm.runInContext('formError.value', context), '')
})

test('field error gives only the matching requested shift time, with overnight clock notation', () => {
  const errors = shiftRequestFieldErrors({status:400,data:{'2026-11-06':{non_field_errors:['同じ時間帯に申請中のシフトがあります']}}},
    [{date:'2026-11-06',enabled:true,start_time:'20:00',end_time:'29:00'}],
    [{date:'2026-11-06',status:'REQUESTED',start_time:'20:30:00',end_time:'05:00:00',end_day_offset:1},
     {date:'2026-11-06',status:'CANCELLED',start_time:'12:00',end_time:'22:00'}])
  assert.deepEqual(errors, {'2026-11-06':'この日は20:30〜翌5:00で申請済みです。'})
})

test('field error handles a previous business day overlap and excludes touching boundaries', () => {
  const error = {status:400,data:{'2027-01-01':{non_field_errors:['同じ時間帯に申請中のシフトがあります']}}}
  const days = [{date:'2027-01-01',enabled:true,start_time:'00:00',end_time:'04:00'}]
  const rows = [
    {date:'2026-12-31',status:'REQUESTED',start_time:'20:30',end_time:'05:00',end_day_offset:1},
    {date:'2027-01-01',status:'REQUESTED',start_time:'04:00',end_time:'12:00'},
    {date:'2027-01-01',status:'APPROVED',start_time:'00:00',end_time:'04:00'},
  ]
  assert.deepEqual(shiftRequestFieldErrors(error,days,rows), {'2027-01-01':'この日は12/31の20:30〜翌5:00で申請済みです。'})
  assert.deepEqual(shiftRequestFieldErrors(error,[{...days[0],enabled:false}],rows), {})
})

test('stale or missing request data never invents a conflicting time', () => {
  const error={status:400,data:{'2026-11-06':{non_field_errors:['同じ時間帯に申請中のシフトがあります']}}}
  assert.deepEqual(shiftRequestFieldErrors(error,[{date:'2026-11-06',enabled:true,start_time:'20:00',end_time:'29:00'}],[]), {'2026-11-06':'この時間には申請中のシフトがあります。'})
  assert.deepEqual(shiftRequestFieldErrors({status:403,data:error.data},[],[]), {})
})
