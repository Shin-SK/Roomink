#!/usr/bin/env node
/**
 * Reads the Roomink operations LINE inbox for a Codex conversation.
 * It has no send/reply operation by design.
 *
 * Required environment variables:
 *   ROOMINK_LINE_INBOX_API_BASE_URL   e.g. https://api.roomink.net/api
 *   ROOMINK_LINE_INBOX_READ_TOKEN     matches OPERATIONS_LINE_INBOX_READ_TOKEN
 *
 * Optional:
 *   --limit=20
 *   --download-dir=/absolute/path     download stored image/video/audio/file attachments
 */

import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const baseUrl = (process.env.ROOMINK_LINE_INBOX_API_BASE_URL || '').replace(/\/$/, '')
const token = process.env.ROOMINK_LINE_INBOX_READ_TOKEN || ''
const limit = Math.min(Math.max(Number(process.argv.find((arg) => arg.startsWith('--limit='))?.split('=')[1] || 20), 1), 100)
const downloadDir = process.argv.find((arg) => arg.startsWith('--download-dir='))?.split('=').slice(1).join('=')

if (!baseUrl || !token) {
  throw new Error('Set ROOMINK_LINE_INBOX_API_BASE_URL and ROOMINK_LINE_INBOX_READ_TOKEN.')
}

async function api(relativePath) {
  const response = await fetch(`${baseUrl}${relativePath}`, { headers: { Authorization: `Bearer ${token}` } })
  if (!response.ok) throw new Error(`Roomink inbox API ${response.status}: ${await response.text()}`)
  return response
}

function safeFilename(attachment) {
  const proposed = attachment.filename || `line-attachment-${attachment.id}`
  return proposed.replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 180) || `line-attachment-${attachment.id}`
}

const payload = await (await api(`/internal/operations-line-inbox/recent/?limit=${limit}`)).json()
if (downloadDir) await mkdir(downloadDir, { recursive: true })

for (const message of payload.messages) {
  for (const attachment of message.attachments) {
    if (!downloadDir || attachment.status !== 'STORED') continue
    const content = await (await api(attachment.download_path)).arrayBuffer()
    const destination = path.join(downloadDir, `${message.id}-${attachment.id}-${safeFilename(attachment)}`)
    await writeFile(destination, Buffer.from(content))
    attachment.local_path = destination
  }
}

console.log(JSON.stringify(payload, null, 2))
