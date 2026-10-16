import test from 'node:test'
import assert from 'node:assert/strict'
import { attendanceCards } from '../src/attendanceCards.js'

const casts = [
  { id: 1, name: '同じ名前', avatar_url: 'https://example.test/a.jpg', shifts: [{ id: 10, start_time_extended: '25:00', room_name: 'A' }] },
  { id: 2, name: '同じ名前', avatar_url: 'https://example.test/b.jpg', shifts: [{ id: 20, start_time_extended: '26:00', room_name: 'B' }] },
]
const alert = (id, late = false) => ({ shift_id: id, cast_name: '名前', start_time: '01:00', alert_level: 'ONE_HOUR', has_started: late })

test('same names keep separate avatars and shifts; missing room-view casts still show the alert', () => {
  const cards = attendanceCards([alert(20), alert(10, true), alert(30)], casts)
  assert.deepEqual(cards.map(c => [c.id, c.avatar, c.time]), [
    [10, 'https://example.test/a.jpg', '25:00'], [30, '', '01:00'], [20, 'https://example.test/b.jpg', '26:00'],
  ])
})

test('unclocked and unconfirmed warnings become one card; a confirmed shift can still be unclocked', () => {
  const cards = attendanceCards([alert(10, true)], casts, [{ id: 10 }, { id: 20 }])
  assert.equal(cards.length, 2)
  assert.equal(cards[0].label, '未出勤・未確認')
  assert.equal(cards[1].label, '未出勤')
})

test('absent shifts, two-hour alerts and stale clock-in responses do not create attendance warnings', () => {
  const current = [{ name: 'A', shifts: [{ id: 10, is_absent: true }, { id: 20, clocked_in_at: '2026-10-16T10:00:00Z' }] }]
  assert.deepEqual(attendanceCards([alert(10), { ...alert(30), alert_level: 'TWO_HOURS' }], current, [{ id: 10 }, { id: 20 }, { id: 99 }]), [])
})
