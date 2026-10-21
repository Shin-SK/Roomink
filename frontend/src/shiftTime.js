export function normalizeShiftTime(value, label = '時刻') {
  let text = String(value || '').trim()
    .replace(/[０-９]/g, digit => String.fromCharCode(digit.charCodeAt(0) - 0xfee0))
    .replace('：', ':')
  if (/^\d{4}$/.test(text)) text = `${text.slice(0, 2)}:${text.slice(2)}`
  if (!/^\d{2}:\d{2}$/.test(text)) throw new Error(`${label}はHH:MM形式で入力してください（例: 24:00）`)
  const [hour, minute] = text.split(':').map(Number)
  if (hour > 29 || minute > 59 || (hour === 29 && minute !== 0)) {
    throw new Error(`${label}は00:00〜29:00で入力してください`)
  }
  return { time: `${String(hour % 24).padStart(2, '0')}:${String(minute).padStart(2, '0')}`, dayOffset: hour >= 24 ? 1 : 0 }
}
