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
  if (error?.status !== 400) {
    return `${text}\n申請一覧で保存状況を確認してから、もう一度お試しください。`
  }
  const guidance = text.includes('同じ時間帯に申請中のシフトがあります')
    ? '申請一覧で既存の申請をご確認ください。別の日を申請する場合は、重複している日を選択解除してください。'
    : '入力内容を確認して、もう一度申請してください。'
  return `今回選択した日付の申請は、すべて保存されていません。\n${text}\n${guidance}`
}
