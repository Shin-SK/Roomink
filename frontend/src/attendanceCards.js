// Match by shift ID: names are neither unique nor stable identifiers.
export function attendanceCards(alerts = [], casts = [], notClockedIn = []) {
  const shifts = new Map()
  for (const cast of casts) {
    for (const shift of cast.shifts || []) shifts.set(shift.id, { cast, shift })
  }
  const cards = new Map()
  for (const alert of alerts) {
    if (alert.alert_level !== 'ONE_HOUR') continue
    const { cast, shift } = shifts.get(alert.shift_id) || {}
    if (shift?.is_absent) continue
    cards.set(alert.shift_id, {
      id: alert.shift_id,
      name: cast?.name || alert.cast_name,
      avatar: cast?.avatar_url || '',
      time: alert.start_time_extended || shift?.start_time_extended || alert.start_time,
      room: alert.room_name || shift?.room_name || 'ルーム未定',
      late: Boolean(alert.has_started),
      label: alert.has_started ? '開始超過・未確認' : '出勤確認待ち',
      minutes: alert.minutes_until_start,
    })
  }
  for (const entry of notClockedIn) {
    const { cast, shift } = shifts.get(entry.id) || {}
    // A refreshed schedule may already contain a clock-in while LINE polling is older.
    if (!shift || shift.is_absent || shift.clocked_in_at) continue
    const existing = cards.get(entry.id)
    cards.set(entry.id, {
      id: entry.id,
      name: cast.name,
      avatar: cast.avatar_url || '',
      time: shift.start_time_extended || entry.start_time,
      room: shift.room_name || 'ルーム未定',
      late: true,
      label: existing ? '未出勤・未確認' : '未出勤',
      minutes: existing?.minutes ?? -Infinity,
    })
  }
  return [...cards.values()].sort((a, b) => Number(b.late) - Number(a.late)
    || (a.time || '').localeCompare(b.time || '') || a.id - b.id)
}
