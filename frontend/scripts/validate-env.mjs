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
        const key = line.slice(0, separator).trim()
        const value = line.slice(separator + 1).trim().replace(/^['"]|['"]$/g, '')
        return [key, value]
      }),
  )
}

const root = process.cwd()
const environment = String(
  process.env.ROOMINK_ENV || process.env.VITE_ROOMINK_ENV || 'production',
).toLowerCase()
const fileValues = readEnvFile(path.join(root, `.env.${environment}`))
const apiBaseUrl = String(process.env.VITE_API_BASE_URL ?? fileValues.VITE_API_BASE_URL ?? '').trim()

if (environment === 'staging') {
  if (!apiBaseUrl) {
    throw new Error(
      'Staging build blocked: VITE_API_BASE_URL must point to the isolated staging API.',
    )
  }
  const parsed = new URL(apiBaseUrl)
  if (parsed.protocol !== 'https:') {
    throw new Error('Staging build blocked: VITE_API_BASE_URL must use https.')
  }
  if (parsed.hostname === 'api.roomink.net' || parsed.hostname.includes('roomink-0315e6e58623')) {
    throw new Error('Staging build blocked: the production Roomink API cannot be used.')
  }
}

console.log(`Environment validation passed (${environment}).`)
