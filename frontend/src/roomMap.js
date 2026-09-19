export function roomMapHref(room) {
  const configuredUrl = String(room?.room_map_url || room?.map_url || '').trim()
  if (/^https?:\/\//i.test(configuredUrl)) return configuredUrl

  const address = String(room?.room_address || room?.address || '').trim()
  if (!address) return ''
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`
}
