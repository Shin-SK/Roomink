import test from 'node:test'
import assert from 'node:assert/strict'
import { calendarDays, movePeriod, addDays, shiftMinutes, layoutDayEvents, compactDayEvents } from '../src/shiftCalendar.js'

test('month grid includes all six weeks across year boundaries and leap day', () => {
  const december = calendarDays('2026-12-31', 'month')
  assert.equal(december.length, 42)
  assert.equal(december[0], '2026-11-30')
  assert.equal(december.at(-1), '2027-01-10')
  assert.ok(calendarDays('2028-02-01', 'month').includes('2028-02-29'))
  assert.deepEqual(calendarDays('2027-01-03', 'week'), ['2026-12-28', '2026-12-29', '2026-12-30', '2026-12-31', '2027-01-01', '2027-01-02', '2027-01-03'])
})
test('navigation clamps month end and keeps local dates on DST boundaries', () => {
  assert.equal(movePeriod('2026-01-31', 'month', 1), '2026-02-28')
  assert.equal(movePeriod('2028-01-31', 'month', 1), '2028-02-29')
  assert.equal(movePeriod('2026-12-31', 'month', 1), '2027-01-31')
  assert.equal(movePeriod('2026-01-02', 'week', -1), '2025-12-26')
  assert.equal(addDays('2026-03-08', 1), '2026-03-09')
})
test('extended hours retain their business date and overnight interval', () => {
  assert.deepEqual(shiftMinutes({ start_time_extended: '24:30', end_time_extended: '29:00' }), { start: 1470, end: 1740 })
  assert.deepEqual(shiftMinutes({ start_time: '23:00', end_time: '02:00', end_day_offset: 1 }), { start: 1380, end: 1560 })
  assert.deepEqual(shiftMinutes({ start_time: '23:00', end_time: '02:00' }), { start: 1380, end: 1560 })
})
test('overlapping shifts get separate columns, adjacent shifts reuse the full width', () => {
  const shifts = [{ id: 1, start_time: '10:00', end_time: '14:00' }, { id: 2, start_time: '11:00', end_time: '12:00' }, { id: 3, start_time: '12:00', end_time: '13:00' }, { id: 4, start_time: '14:00', end_time: '15:00' }]
  const rows = layoutDayEvents(shifts)
  assert.equal(rows[0].columns, 2)
  assert.equal(rows[1].lane, rows[2].lane)
  assert.equal(rows[3].columns, 1)
  assert.equal(rows[3].lane, 0)
  assert.deepEqual(layoutDayEvents([]), [])
})

test('dense days keep readable cards and expose every hidden shift through the day list', () => {
  const shifts = Array.from({ length: 12 }, (_, id) => ({ id, start_time: '10:00', end_time: '18:00' }))
  shifts.push({ id: 13, start_time: '19:00', end_time: '20:00' })
  const result = compactDayEvents(shifts)
  assert.equal(result.visible.length, 3)
  assert.equal(result.overflow.length, 1)
  assert.equal(result.overflow[0].count, 10)
  assert.equal(result.overflow[0].columns, 3)
  assert.equal(result.visible.at(-1).columns, 1)
  assert.equal(result.visible.length + result.overflow.reduce((n, group) => n + group.count, 0), shifts.length)
})
