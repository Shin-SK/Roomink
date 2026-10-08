// One store per tab. Switching always reloads the page to discard old forms,
// polling callbacks and cached role/data instead of sending them to another store.
const KEY = 'roomink-active-store'
let selected = ''
try {
  const fromUrl = new URLSearchParams(window.location.search).get('store')
  selected = fromUrl || window.sessionStorage.getItem(KEY) || ''
  if (!/^[1-9]\d{0,17}$/.test(selected)) selected = ''
} catch { /* storage may be unavailable */ }

export function selectedStoreId() { return selected }

export function setSelectedStoreId(id) {
  selected = id ? String(id) : ''
  try {
    if (selected) window.sessionStorage.setItem(KEY, selected)
    else window.sessionStorage.removeItem(KEY)
  } catch { /* URL still carries selection when switching */ }
}

export function openStore(id) {
  // Keep this document pinned to its old store until navigation completes.
  try { window.sessionStorage.setItem(KEY, String(id)) } catch { /* URL fallback */ }
  window.location.assign(`/op/dashboard?store=${encodeURIComponent(id)}`)
}

export function scopedExportUrl(url) {
  if (!selected) return url
  return `${url}${url.includes('?') ? '&' : '?'}_store=${encodeURIComponent(selected)}`
}
