// Use date arithmetic without the browser's local timezone (including month/year rollover).
export function courseEndTime(startTime, courseMinutes, extensionMinutes = 0) {
  const match = /^(\d{1,2}):(\d{2})$/.exec((startTime || '').trim())
  if (!match || Number(match[2]) > 59) return null
  const minutes = Number(match[1]) * 60 + Number(match[2]) + Number(courseMinutes) + Number(extensionMinutes)
  if (!Number.isFinite(minutes) || minutes < 0) return null
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
}

export function reservationDateTime(date, time) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date || '')) return null
  const match = /^(\d{1,2}):(\d{2})$/.exec((time || '').trim())
  if (!match) return null
  const hour = Number(match[1]), minute = Number(match[2])
  if (minute > 59 || hour * 60 + minute > 29 * 60) return null
  const day = new Date(`${date}T00:00:00Z`)
  if (Number.isNaN(day.getTime()) || day.toISOString().slice(0, 10) !== date) return null
  day.setUTCDate(day.getUTCDate() + Math.floor(hour / 24))
  const normalizedTime = `${String(hour).padStart(2, '0')}:${match[2]}`
  const actual = `${day.toISOString().slice(0, 10)} ${String(hour % 24).padStart(2, '0')}:${match[2]}`
  return { normalizedTime, actual }
}
