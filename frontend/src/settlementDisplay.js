// Operational settlement excludes payment surcharges/costs tracked in sales reports.
export function settlementStoreShare(row) {
  if (row?.total_sales == null || row?.compensation == null) return null
  return Number(row.total_sales) - Number(row.compensation)
}
