export const timelineSegments = [
  ['scheduled', 'シフトあり'], ['before', '出勤前'], ['working', '出勤中'],
  ['finished', '退勤済み'], ['absent', '当欠'], ['all', '全員'],
]

export function castAttendanceState(cast) {
  const shifts = cast.shifts || []
  if (!shifts.length) return 'unscheduled'
  const active = shifts.filter(shift => !shift.is_absent)
  if (!active.length) return 'absent'
  if (active.some(shift => shift.clocked_in_at && !shift.clocked_out_at)) return 'working'
  if (active.every(shift => shift.clocked_out_at)) return 'finished'
  return 'before'
}

export function segmentTimeline(casts, orders, segment) {
  // Keep visible reservations even when the associated shift is missing or
  // belongs to a different attendance segment. Never change the source data.
  const reserved = new Set(orders.filter(order => order.status !== 'CANCELLED').map(order => Number(order.cast_id)))
  return casts.filter(cast => segment === 'all'
    || (segment === 'scheduled' ? cast.shifts?.length : castAttendanceState(cast) === segment)
    || reserved.has(Number(cast.id)))
}
