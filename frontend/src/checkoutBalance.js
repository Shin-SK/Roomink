// Display the existing settlement balance without changing the settlement calculation.
export function checkoutBalanceDisplay(available, roomCash, officeCash = 0) {
  const closing = available - roomCash - officeCash
  if (available < 0) return { label: '精算残額', amount: closing, tone: 'text-danger', isShortage: false }
  if (closing > 0) return { label: '不足', amount: closing, tone: 'text-danger', isShortage: true }
  if (closing < 0) return { label: '受取超過', amount: -closing, tone: 'text-danger', isShortage: false }
  return { label: '不足なし', amount: 0, tone: 'text-success', isShortage: false }
}
