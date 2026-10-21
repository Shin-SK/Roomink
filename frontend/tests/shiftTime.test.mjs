import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeShiftTime } from '../src/shiftTime.js'

test('business midnight remains distinct from calendar midnight', () => {
  assert.deepEqual(normalizeShiftTime('24:00'), { time: '00:00', dayOffset: 1 })
  assert.deepEqual(normalizeShiftTime('00:00'), { time: '00:00', dayOffset: 0 })
  assert.deepEqual(normalizeShiftTime('29:00'), { time: '05:00', dayOffset: 1 })
  assert.deepEqual(normalizeShiftTime('２４：３０'), { time: '00:30', dayOffset: 1 })
  assert.deepEqual(normalizeShiftTime('2430'), { time: '00:30', dayOffset: 1 })
  assert.deepEqual(normalizeShiftTime('18:00'), { time: '18:00', dayOffset: 0 })
})

test('invalid overnight boundaries do not silently clamp to 23:00', () => {
  for (const input of ['29:01', '30:00', '24:60', '', '2:00', '24:00:00']) {
    assert.throws(() => normalizeShiftTime(input))
  }
})
