export function routeStoreSlug(route) {
  return typeof route.params.storeSlug === 'string' ? route.params.storeSlug : ''
}

export function customerPath(route, page = 'mypage', id = null) {
  const slug = routeStoreSlug(route)
  if (!slug) {
    if (page === 'reservation') return `/cu/reservations/${id}`
    return `/cu/${page}`
  }
  const base = `/s/${encodeURIComponent(slug)}`
  if (['login', 'signup', 'activate'].includes(page)) return `${base}/${page}`
  if (page === 'reservation') return `${base}/mypage/reservations/${id}`
  if (page === 'mypage') return `${base}/mypage`
  return `${base}/mypage/${page}`
}

export function storeApiQuery(storeId, storeSlug = '') {
  if (storeSlug) return `?store_slug=${encodeURIComponent(storeSlug)}`
  if (storeId) return `?store=${storeId}`
  return ''
}
