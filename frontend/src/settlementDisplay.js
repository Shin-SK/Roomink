// Operational settlement excludes payment surcharges/costs tracked in sales reports.
export function settlementStoreShare(row) {
  if (row?.total_sales == null || row?.compensation == null) return null
  return Number(row.total_sales) - Number(row.compensation)
}

// Display estimates only: never substitute net_pay (which includes points),
// or the actual cash handoff recorded at checkout.
export function settlementCashBalance(row) {
  if (row?.cash_sales_total == null || row?.compensation == null) return null
  const cash = Number(row.cash_sales_total)
  const compensation = Number(row.compensation)
  if (!Number.isFinite(cash) || !Number.isFinite(compensation)) return null
  return {
    deposit: Math.max(0, cash - compensation),
    shortfall: Math.max(0, compensation - cash),
  }
}

export function settlementCashTotals(rows) {
  const balances = rows.map(settlementCashBalance)
  if (balances.some(balance => balance === null)) return null
  return balances.reduce((total, balance) => ({
    deposit: total.deposit + balance.deposit,
    shortfall: total.shortfall + balance.shortfall,
  }), { deposit: 0, shortfall: 0 })
}
