import * as Sentry from '@sentry/vue'
import { scrubPasswordResetUrl, scrubPasswordResetBreadcrumb } from './passwordResetLink.js'

function scrubEvent(event) {
  if (event.request) {
    event.request.url = scrubPasswordResetUrl(event.request.url)
    delete event.request.data
    delete event.request.cookies
    if (event.request.headers) {
      for (const key of Object.keys(event.request.headers)) {
        if (['authorization', 'cookie', 'x-csrftoken'].includes(key.toLowerCase())) {
          delete event.request.headers[key]
        }
      }
    }
  }
  if (event.breadcrumbs) event.breadcrumbs = event.breadcrumbs.map(scrubPasswordResetBreadcrumb)
  return event
}

export function initializeMonitoring(app) {
  const dsn = (import.meta.env.VITE_SENTRY_DSN || '').trim()
  if (!dsn) return false

  Sentry.init({
    app,
    dsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || 'production',
    release: import.meta.env.VITE_SENTRY_RELEASE || undefined,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    beforeSend: scrubEvent,
    beforeBreadcrumb: scrubPasswordResetBreadcrumb,
  })
  return true
}
