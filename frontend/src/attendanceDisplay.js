export function attendanceState(shift) {
  if (shift.is_absent) return { key: 'absent', label: '欠勤', tone: 'muted' }
  if (shift.clocked_out_at) return { key: 'done', label: '退勤済み', tone: 'muted' }
  if (shift.clocked_in_at) return { key: 'working', label: '勤務中', tone: 'green' }
  return { key: 'waiting', label: '未出勤', tone: 'muted' }
}
export function attendanceTime(value) {
  return value ? new Intl.DateTimeFormat('ja-JP', { timeZone: 'Asia/Tokyo', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '—'
}
export function attendanceDate(value) {
  if (!value) return ''
  const [, month, day] = value.split('-').map(Number)
  return `${month}/${day}`
}
export function scheduledTime(value, day) {
  if (!value) return '—'
  const localDay = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(value))
  const label = attendanceTime(value)
  const offset = Math.round((Date.parse(`${localDay}T00:00:00Z`) - Date.parse(`${day}T00:00:00Z`)) / 86400000)
  return `${String(Number(label.split(':')[0]) + 24 * offset).padStart(2, '0')}:${label.split(':')[1]}`
}
export function filterAttendance(shifts, { query = '', status = 'all', castId = '' } = {}) {
  const search = query.trim().toLocaleLowerCase('ja-JP')
  return shifts.filter(shift => (!castId || String(shift.cast_id) === String(castId))
    && (!search || shift.cast_name.toLocaleLowerCase('ja-JP').includes(search))
    && (status === 'all' || (status === 'review' ? !!shift.alerts?.length : attendanceState(shift).key === status)))
    .slice().sort((a, b) => Number(!!b.alerts?.length) - Number(!!a.alerts?.length)
      || a.scheduled_start.localeCompare(b.scheduled_start) || a.cast_name.localeCompare(b.cast_name, 'ja') || a.id - b.id)
}
