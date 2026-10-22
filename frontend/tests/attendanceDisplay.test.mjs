import test from 'node:test'
import assert from 'node:assert/strict'
import { attendanceState, filterAttendance, scheduledTime } from '../src/attendanceDisplay.js'

const shifts = Array.from({ length: 41 }, (_, i) => ({ id:i+1, cast_id:i+1, cast_name:i<2?'同じ名前':`セラピスト${i}`, scheduled_start:'2026-10-22T11:00:00+09:00', alerts:i%10===0?['未退勤']:[], clocked_in_at:i%3?'2026-10-22T11:01:00+09:00':null, clocked_out_at:i%4===1?'2026-10-22T14:00:00+09:00':null }))
test('a forty-person roster keeps all rows and brings only flagged shifts to the top', () => {
  const result=filterAttendance(shifts)
  assert.equal(result.length,41)
  assert.deepEqual(new Set(result.slice(0,5).map(s=>s.id)),new Set([1,11,21,31,41]))
  assert.deepEqual(shifts.map(s=>s.id),Array.from({length:41},(_,i)=>i+1))
})
test('search, status and cast identity compose without merging identical names', () => {
  assert.equal(filterAttendance(shifts,{query:'同じ名前'}).length,2)
  assert.equal(filterAttendance(shifts,{query:'同じ名前',castId:'2'})[0].id,2)
  assert.equal(filterAttendance(shifts,{status:'review'}).length,5)
  assert.ok(filterAttendance(shifts,{status:'working'}).every(s=>s.clocked_in_at&&!s.clocked_out_at))
  assert.equal(filterAttendance(shifts,{query:'存在しない'}).length,0)
  assert.equal(attendanceState({is_absent:true}).label,'欠勤')
})
test('scheduled times use extended hours while attendance remains an actual clock time', () => {
  assert.equal(scheduledTime('2026-10-23T05:00:00+09:00','2026-10-22'),'29:00')
  assert.equal(scheduledTime('2026-10-22T11:00:00+09:00','2026-10-22'),'11:00')
})
