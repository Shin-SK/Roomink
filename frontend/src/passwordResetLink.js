let pendingLink = null

export function scrubPasswordResetUrl(value) {
  if (typeof value !== 'string') return value
  if (/(?:^|\/)password-reset(?:[?#]|$)/.test(value) || /#.*(?:uid|token)=/.test(value)) return value.split(/[?#]/, 1)[0]
  return value
}

export function scrubPasswordResetBreadcrumb(breadcrumb) {
  if (breadcrumb.data) {
    for (const key of ['url', 'from', 'to']) {
      if (key in breadcrumb.data) breadcrumb.data[key] = scrubPasswordResetUrl(breadcrumb.data[key])
    }
  }
  return breadcrumb
}

export function parsePasswordResetFragment(hash) {
  const values = new URLSearchParams(String(hash || '').replace(/^#/, ''))
  if (values.getAll('uid').length !== 1 || values.getAll('token').length !== 1) return null
  const uid = values.get('uid')
  const token = values.get('token')
  if (!uid || !token || uid.length > 64 || token.length > 128) return null
  return { uid, token }
}

export function preparePasswordResetLink(location, history) {
  if (location.pathname !== '/password-reset') return
  pendingLink = parsePasswordResetFragment(location.hash)
  if (location.hash) history.replaceState(history.state, '', location.pathname + location.search)
}

export function takePasswordResetLink() {
  const value = pendingLink
  pendingLink = null
  return value
}
