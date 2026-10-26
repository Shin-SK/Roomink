export function dateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
export function parseDay(value) {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day, 12)
}
export function addDays(value, amount) {
  const day = parseDay(value)
  day.setDate(day.getDate() + amount)
  return dateKey(day)
}
export function movePeriod(value, mode, direction) {
  if (mode === 'week') return addDays(value, direction * 7)
  const date = parseDay(value)
  const target = new Date(date.getFullYear(), date.getMonth() + direction, 1, 12)
  target.setDate(Math.min(date.getDate(), new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate()))
  return dateKey(target)
}
export function calendarDays(value, mode) {
  const date = parseDay(value)
  if (mode === 'month') date.setDate(1)
  date.setDate(date.getDate() - (date.getDay() + 6) % 7)
  const start = dateKey(date)
  return Array.from({ length: mode === 'week' ? 7 : 42 }, (_, i) => addDays(start, i))
}
export function shiftMinutes(shift) {
  const minute = (extended, plain, offset) => {
    const [hour, min] = (extended || plain || '00:00').split(':').map(Number)
    return hour * 60 + min + (extended ? 0 : Number(offset || 0) * 1440)
  }
  const start = minute(shift.start_time_extended, shift.start_time, shift.start_day_offset)
  let end = minute(shift.end_time_extended, shift.end_time, shift.end_day_offset)
  if (end <= start) end += 1440
  return { start, end }
}
export function layoutDayEvents(shifts) {
  const sorted = shifts.map(shift => ({ shift, ...shiftMinutes(shift) })).sort((a, b) => a.start - b.start || a.end - b.end || a.shift.id - b.shift.id)
  let group = [], end = -1
  const result = []
  const finish = () => {
    const lanes = []
    for (const item of group) {
      let lane = lanes.findIndex(until => until <= item.start)
      if (lane < 0) lane = lanes.length
      lanes[lane] = item.end
      item.lane = lane
    }
    result.push(...group.map(item => ({ ...item, columns: lanes.length, groupStart: group[0].start, groupEnd: Math.max(...group.map(row => row.end)) })))
    group = []
  }
  for (const item of sorted) {
    if (item.start >= end && group.length) finish()
    group.push(item)
    end = Math.max(group.length === 1 ? -1 : end, item.end)
  }
  finish()
  return result
}

// Dense overlap groups use the calendar's familiar "+N" affordance rather than
// squeezing names into a few pixels. The complete day remains in the list.
export function compactDayEvents(shifts) {
  const items = layoutDayEvents(shifts)
  const visible = [], overflow = new Map()
  for (const item of items) {
    if (item.columns <= 3 || item.lane < 2) {
      visible.push({ ...item, columns: Math.min(item.columns, 3) })
    } else {
      const key = `${item.groupStart}-${item.groupEnd}`
      if (!overflow.has(key)) overflow.set(key, { start: item.groupStart, end: item.groupEnd, columns: 3, lane: 2, count: 0, key })
      overflow.get(key).count++
    }
  }
  return { visible, overflow: [...overflow.values()] }
}
