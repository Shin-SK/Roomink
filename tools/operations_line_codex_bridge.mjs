#!/usr/bin/env node
/**
 * Roomink運営LINE → ローカルCodex の一方向bridge。
 *
 * CodexのApp Serverをインターネットに公開しない。Roomink APIを短時間ポーリング
 * するだけなので、Macが停止中は案件が「起動待ち」のまま残る。
 *
 * 必要な環境変数:
 *   ROOMINK_OPS_API_BASE_URL       例: https://<roomink-api>/api
 *   ROOMINK_OPS_BRIDGE_TOKEN       Herokuと共有する十分に長いランダム値
 *   ROOMINK_CODEX_PROJECT_ID       Codex App ServerのRoomink project ID
 *   ROOMINK_OPS_REPOSITORY         Roominkのgit root
 *   ROOMINK_OPS_WORKTREE_ROOT      案件別worktreeの親ディレクトリ
 * 任意:
 *   ROOMINK_CODEX_CLI              Codex CLIの絶対パス
 *   ROOMINK_OPS_WORKTREE_BASE      初期値 origin/main
 *   ROOMINK_OPS_BRIDGE_INTERVAL_MS 初期値 15000
 */

import { spawn } from 'node:child_process'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import readline from 'node:readline'

const env = process.env
const config = {
  apiBaseUrl: (env.ROOMINK_OPS_API_BASE_URL || '').replace(/\/$/, ''),
  bridgeToken: env.ROOMINK_OPS_BRIDGE_TOKEN || '',
  projectId: env.ROOMINK_CODEX_PROJECT_ID || '',
  repository: env.ROOMINK_OPS_REPOSITORY || '',
  worktreeRoot: env.ROOMINK_OPS_WORKTREE_ROOT || '',
  worktreeBase: env.ROOMINK_OPS_WORKTREE_BASE || 'origin/main',
  codexCli: env.ROOMINK_CODEX_CLI || '/Applications/ChatGPT.app/Contents/Resources/codex',
  intervalMs: Number(env.ROOMINK_OPS_BRIDGE_INTERVAL_MS || 15000),
}

function requireConfig() {
  for (const [key, value] of Object.entries(config)) {
    if (['worktreeBase', 'intervalMs', 'codexCli'].includes(key)) continue
    if (!value) throw new Error(`Missing required environment variable for ${key}`)
  }
}

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ['ignore', 'pipe', 'pipe'], ...options })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (chunk) => { stdout += chunk })
    child.stderr.on('data', (chunk) => { stderr += chunk })
    child.on('error', reject)
    child.on('close', (code) => {
      if (code === 0) resolve(stdout.trim())
      else reject(new Error(`${command} failed (${code}): ${stderr.trim() || stdout.trim()}`))
    })
  })
}

async function api(pathname, options = {}) {
  const response = await fetch(`${config.apiBaseUrl}${pathname}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${config.bridgeToken}`,
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  })
  if (response.status === 204) return null
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(`Roomink bridge API ${response.status}: ${data.detail || 'unknown error'}`)
  return data
}

class AppServer {
  constructor() {
    this.nextId = 1
    this.pending = new Map()
  }

  async start() {
    this.child = spawn(config.codexCli, ['app-server'], { stdio: ['pipe', 'pipe', 'ignore'] })
    this.lines = readline.createInterface({ input: this.child.stdout })
    this.lines.on('line', (line) => this.receive(line))
    this.child.on('error', (error) => this.failAll(error))
    this.child.on('close', (code) => this.failAll(new Error(`Codex App Server exited (${code})`)))
    await this.request('initialize', {
      clientInfo: { name: 'roomink_operations_line_bridge', title: 'Roomink Operations LINE bridge', version: '1.0.0' },
      capabilities: { experimentalApi: true },
    })
    this.notify('initialized', {})
  }

  receive(line) {
    let message
    try { message = JSON.parse(line) } catch { return }
    if (message.id === undefined) return
    const request = this.pending.get(message.id)
    if (!request) return
    this.pending.delete(message.id)
    if (message.error) request.reject(new Error(message.error.message || 'Codex App Server request failed'))
    else request.resolve(message.result)
  }

  request(method, params) {
    const id = this.nextId++
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.child.stdin.write(`${JSON.stringify({ id, method, params })}\n`)
    })
  }

  notify(method, params) {
    this.child.stdin.write(`${JSON.stringify({ method, params })}\n`)
  }

  failAll(error) {
    for (const request of this.pending.values()) request.reject(error)
    this.pending.clear()
  }

  async close() {
    this.lines?.close()
    this.child?.stdin.end()
    this.child?.kill()
  }
}

async function createWorktree(caseId) {
  const worktreePath = path.join(config.worktreeRoot, `operations-case-${caseId}`)
  await mkdir(config.worktreeRoot, { recursive: true })
  // The path is deterministic: a retried dispatch continues in the same isolated worktree.
  try {
    await run('git', ['-C', worktreePath, 'rev-parse', '--show-toplevel'])
    return worktreePath
  } catch {
    await run('git', ['-C', config.repository, 'worktree', 'add', '--detach', worktreePath, config.worktreeBase])
    return worktreePath
  }
}

function caseTitle(job) {
  return `Roomink #${job.case_id}｜${job.store_name}｜${job.summary.slice(0, 45)}`
}

function preparedPrompt(job) {
  return [
    'これはRoomink運営LINEから作成された案件です。',
    `案件番号: ${job.case_id}`,
    `店舗: ${job.store_name}`,
    `種別: ${job.category}`,
    `要約: ${job.summary}`,
    `本文: ${job.source || '（本文なし）'}`,
    '',
    'まだ「修正開始」は承認されていません。RoominkのAGENTS.mdと運用資料を確認し、',
    '要件・影響範囲・検証方法だけを整理して待機してください。ファイル変更、外部送信、',
    'ステージング・本番反映は行わないでください。',
  ].join('\n')
}

function startPrompt(job) {
  return [
    '運営側がSlackの「修正開始」を押しました。',
    'この案件を実装してください。RoominkのAGENTS.mdとroomink-releaseの手順を厳守し、',
    'まず実装前の確認を報告してから進めてください。ステージング確認までは進められますが、',
    '本番反映は必ずユーザーの明示承認を待ってください。',
    `案件番号: ${job.case_id}`,
    `要約: ${job.summary}`,
  ].join('\n')
}

async function handleJob(server, job) {
  if (job.action === 'CREATE_THREAD') {
    const worktreePath = job.codex_worktree_path || await createWorktree(job.case_id)
    const started = await server.request('thread/start', {
      cwd: worktreePath,
      sandbox: 'workspace-write',
      projectId: config.projectId,
      sessionStartSource: 'startup',
    })
    const threadId = started.thread.id
    await server.request('thread/name/set', { threadId, name: caseTitle(job) })
    // This makes the prepared request visible in the actual Codex task, while forbidding changes.
    await server.request('turn/start', {
      threadId,
      cwd: worktreePath,
      input: [{ type: 'text', text: preparedPrompt(job) }],
    })
    await api(`/internal/operations-line/codex/${job.case_id}/complete/`, {
      method: 'POST',
      body: JSON.stringify({
        success: true,
        codex_thread_id: threadId,
        codex_thread_url: `codex://threads/${threadId}`,
        codex_worktree_path: worktreePath,
      }),
    })
    return
  }

  if (job.action === 'START_WORK') {
    if (!job.codex_thread_id) throw new Error('Codex thread is not available for this case')
    const worktreePath = job.codex_worktree_path || await createWorktree(job.case_id)
    // Steer preserves the prepared case context. If the preflight turn has ended, start a new turn.
    const read = await server.request('thread/read', { threadId: job.codex_thread_id, includeTurns: true })
    const activeTurn = read.thread.turns.find((turn) => turn.status === 'inProgress')
    if (activeTurn) {
      await server.request('turn/steer', {
        threadId: job.codex_thread_id,
        expectedTurnId: activeTurn.id,
        input: [{ type: 'text', text: startPrompt(job) }],
      })
    } else {
      await server.request('turn/start', {
        threadId: job.codex_thread_id,
        cwd: worktreePath,
        input: [{ type: 'text', text: startPrompt(job) }],
      })
    }
    await api(`/internal/operations-line/codex/${job.case_id}/complete/`, {
      method: 'POST', body: JSON.stringify({ success: true }),
    })
    return
  }
  throw new Error(`Unsupported bridge action: ${job.action}`)
}

async function pollOnce(server) {
  const job = await api('/internal/operations-line/codex/next/')
  if (!job) return false
  try {
    await handleJob(server, job)
  } catch (error) {
    await api(`/internal/operations-line/codex/${job.case_id}/complete/`, {
      method: 'POST', body: JSON.stringify({ success: false, error: error.message }),
    }).catch(() => {})
    throw error
  }
  return true
}

async function main() {
  requireConfig()
  const once = process.argv.includes('--once')
  const server = new AppServer()
  await server.start()
  try {
    do {
      try { await pollOnce(server) } catch (error) { console.error(`[operations-line-bridge] ${error.message}`) }
      if (!once) await new Promise((resolve) => setTimeout(resolve, config.intervalMs))
    } while (!once)
  } finally {
    await server.close()
  }
}

main().catch((error) => {
  console.error(`[operations-line-bridge] ${error.message}`)
  process.exitCode = 1
})
