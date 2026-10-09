import fs from 'node:fs'
import path from 'node:path'

function readEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {}
  return Object.fromEntries(
    fs.readFileSync(filePath, 'utf8')
      .split(/\r?\n/)
      .map(line => line.trim())
      .filter(line => line && !line.startsWith('#') && line.includes('='))
      .map(line => {
        const separator = line.indexOf('=')
        return [line.slice(0, separator).trim(), line.slice(separator + 1).trim().replace(/^['"]|['"]$/g, '')]
      }),
  )
}

const root = process.cwd()
const environment = String(process.env.ROOMINK_ENV || process.env.VITE_ROOMINK_ENV || 'production').toLowerCase()
const fileValues = readEnvFile(path.join(root, `.env.${environment}`))
const configuredApiUrl = String(process.env.VITE_API_BASE_URL ?? fileValues.VITE_API_BASE_URL ?? '').trim()
// Production must keep using the Cloudflare-proxied API hostname. Falling back
// to Heroku's direct hostname would bypass the origin access lock.
const apiUrl = (configuredApiUrl || 'https://api.roomink.net').replace(/\/$/, '')
const apiHost = new URL(apiUrl).hostname

if (environment === 'staging' && (apiHost === 'api.roomink.net' || apiHost.includes('roomink-0315e6e58623'))) {
  throw new Error('Staging redirect generation blocked: the production Roomink API cannot be used.')
}

fs.writeFileSync(
  path.join(root, 'dist', '_redirects'),
  `/api/*  ${apiUrl}/api/:splat  200\n/admin/*  ${apiUrl}/admin/  302!\n/*    /index.html   200\n`,
)

const apiOrigin = new URL(apiUrl).origin
const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  `connect-src 'self' ${apiOrigin} https://api.cloudinary.com https://*.ingest.sentry.io`,
].join('; ')

fs.writeFileSync(
  path.join(root, 'dist', '_headers'),
  `/*
  Content-Security-Policy: ${contentSecurityPolicy}
  Cross-Origin-Opener-Policy: same-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Referrer-Policy: strict-origin-when-cross-origin
  Strict-Transport-Security: max-age=31536000
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
`,
)

console.log(`Netlify redirects generated for ${environment}: ${apiHost}`)
