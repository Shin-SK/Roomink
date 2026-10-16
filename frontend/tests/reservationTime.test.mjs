import test from 'node:test'
import assert from 'node:assert/strict'
import { reservationDateTime, courseEndTime } from '../src/reservationTime.js'

test('course changes include extensions and preserve extended hours across midnight', () => {
  assert.equal(courseEndTime('14:40', 120), '16:40')
  assert.equal(courseEndTime('14:40', 70, 30), '16:20')
  assert.equal(courseEndTime('23:30', 90, 30), '25:30')
  assert.equal(courseEndTime('28:00', 60), '29:00')
  assert.equal(reservationDateTime('2026-10-16', courseEndTime('28:30', 60)), null)
  assert.equal(courseEndTime('12:99', 60), null)
})

test('24+ input previews the next calendar day across month/year and leap day', () => {
  for (const [date, time, actual] of [
    ['2026-10-14', '23:55', '2026-10-14 23:55'],
    ['2026-10-14', '24:00', '2026-10-15 00:00'],
    ['2026-10-14', '25:00', '2026-10-15 01:00'],
    ['2026-12-31', '28:55', '2027-01-01 04:55'],
    ['2028-02-28', '29:00', '2028-02-29 05:00'],
  ]) assert.equal(reservationDateTime(date, time).actual, actual)
})

test('invalid or incomplete input is rejected rather than clipped or rolled over', () => {
  for (const [date, time] of [
    ['2026-02-29', '24:00'], ['2026-10-14', '29:01'], ['2026-10-14', '30:00'],
    ['2026-10-14', '25:60'], ['', '25:00'], ['2026-10-14', '25:'],
  ]) assert.equal(reservationDateTime(date, time), null)
  assert.equal(reservationDateTime('2026-10-14', '1:05').normalizedTime, '01:05')
})
