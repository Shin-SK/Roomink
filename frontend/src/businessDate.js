// Keep operator pages on the configured business day across local midnight.
export function localBusinessDate(now, boundaryHour) {
  const date = new Date(now)
  if (date.getHours() < boundaryHour) date.setDate(date.getDate() - 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
