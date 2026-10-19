export function roomCashYen(amount) {
  return amount === null || amount === undefined ? '残高未確認' : `${Number(amount).toLocaleString('ja-JP')}円`
}

export function validCashCount(value) {
  return value !== null && value !== undefined && String(value).trim() !== '' && Number.isSafeInteger(Number(value)) && Number(value) >= 0
}

export function roomCashDrafts(rooms, previous = {}, preserve = false) {
  return Object.fromEntries(rooms.map(row => [row.room, preserve && previous[row.room] ? previous[row.room] : {
    actual_cash_amount: '', memo: '', request_id: null,
  }]))
}
