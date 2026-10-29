import test from 'node:test'
import assert from 'node:assert/strict'
import { castAttendanceState, segmentTimeline } from '../src/timelineSegments.js'

const casts = [
  { id:1, shifts:[] }, { id:2, shifts:[{}] },
  { id:3, shifts:[{clocked_in_at:'now'}] },
  { id:4, shifts:[{clocked_in_at:'in',clocked_out_at:'out'}] },
  { id:5, shifts:[{is_absent:true}] },
  { id:6, shifts:[{clocked_in_at:'in',clocked_out_at:'out'},{}] },
]
test('attendance segments use actual clock records and preserve later shifts', () => {
  assert.deepEqual(casts.map(castAttendanceState), ['unscheduled','before','working','finished','absent','before'])
  assert.deepEqual(segmentTimeline(casts, [], 'scheduled').map(c=>c.id), [2,3,4,5,6])
  for (const [state, ids] of [['working',[3]],['finished',[4]],['absent',[5]],['before',[2,6]],['all',[1,2,3,4,5,6]]])
    assert.deepEqual(segmentTimeline(casts, [], state).map(c=>c.id),ids)
})
test('reservations remain visible even without shifts or outside the chosen segment', () => {
  const orders = [{cast_id:'1',status:'CONFIRMED'},{cast_id:2,status:'CANCELLED'}]
  assert.deepEqual(segmentTimeline(casts,orders,'working').map(c=>c.id),[1,3])
  assert.equal(casts.length,6)
})
