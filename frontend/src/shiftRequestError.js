function messages(value, label = '') {
  if (Array.isArray(value)) return value.flatMap((item) => messages(item, label))
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([key, item]) => {
      const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key)
      const nextLabel = match ? `${Number(match[2])}/${Number(match[3])}` : label
      return messages(item, nextLabel)
    })
  }
  return typeof value === 'string' && value.trim()
    ? [`${label ? `${label}：` : ''}${value.trim()}`]
    : []
}

export function shiftRequestError(error) {
  const details = messages(error?.data)
  const fallback = error?.message && error.message !== '[object Object]'
    ? error.message
    : '申請結果を確認できませんでした。'
  const text = [...new Set(details)].join('\n') || fallback
  if (error?.status === 400 && text.includes('同じ時間帯に申請中のシフトがあります')) {
    return '申請済みのシフトと重なっています。赤い欄を確認してください。'
  }
  if (error?.status !== 400) {
    return `${text}\n申請一覧で保存状況を確認してから、もう一度お試しください。`
  }
  const guidance = text.includes('同じ時間帯に申請中のシフトがあります')
    ? '申請一覧で既存の申請をご確認ください。別の日を申請する場合は、重複している日を選択解除してください。'
    : '入力内容を確認して、もう一度申請してください。'
  return `今回選択した日付の申請は、すべて保存されていません。\n${text}\n${guidance}`
}

function interval(row) {
  const day = Date.parse(`${row.date}T00:00:00Z`) / 60000
  const minutes = (value) => {
    const [h, m] = String(value).split(':').map(Number)
    return h * 60 + m
  }
  return [day + minutes(row.start_time) + 1440 * (row.start_day_offset || 0),
    day + minutes(row.end_time) + 1440 * (row.end_day_offset || 0)]
}

function clock(value, offset) {
  const [h, m] = String(value).split(':').map(Number)
  const hour = h + 24 * (offset || 0)
  return `${hour >= 24 ? '翌' : ''}${hour % 24}:${String(m).padStart(2, '0')}`
}

export function shiftRequestFieldErrors(error, days, requests) {
  if (error?.status !== 400 || !error.data) return {}
  const result = {}
  for (const [date, detail] of Object.entries(error.data)) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue
    const text = messages(detail).join('\n')
    const day = days.find((item) => item.date === date && item.enabled)
    if (!day) continue
    let message = text
    if (text.includes('同じ時間帯に申請中のシフトがあります')) {
      const [start, end] = interval(day)
      const overlaps = requests.filter((row) => {
        if (row.status !== 'REQUESTED') return false
        const [a, b] = interval(row)
        return start < b && a < end
      })
      message = overlaps.length
        ? overlaps.map((row) => `この日は${row.date === date ? '' : `${Number(row.date.slice(5,7))}/${Number(row.date.slice(8))}の`}${clock(row.start_time, row.start_day_offset)}〜${clock(row.end_time, row.end_day_offset)}で申請済みです。`).join('\n')
        : 'この時間には申請中のシフトがあります。'
    }
    result[date] = message
  }
  return result
}
