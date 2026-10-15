import test from 'node:test'
import assert from 'node:assert/strict'

globalThis.window = { location: { search: '?store=99' }, sessionStorage: { getItem: () => '', setItem() {} } }
globalThis.document = { cookie: '' }
const { api } = await import('../src/api.js')
const mismatch = "CSRF Failed: CSRF token from the 'X-Csrftoken' HTTP header incorrect."

for (const kind of ['preview', 'apply']) {
  const file = new Blob(['shift_request_id,approved_date\n1,2026-10-19'])
  const rows = [{ shift_request_id: 1, approved_date: '2026-10-19' }]
  const send = () => kind === 'preview' ? api.importShiftRequestsPreview(file) : api.applyShiftRequestsImport(rows)

  test(`${kind}: refreshes a stale tab before submitting, preserves payload and store`, async () => {
    const calls = []
    globalThis.fetch = async (url, opts) => {
      calls.push({ url, ...opts })
      return { ok: true, status: 200, json: async () => url.endsWith('/auth/csrf/') ? { csrf_token: 'latest' } : { ok: true } }
    }
    await send()
    assert.equal(calls.length, 2)
    assert.ok(calls[0].url.endsWith('/auth/csrf/'))
    assert.equal(calls[1].headers['X-CSRFToken'], 'latest')
    assert.equal(calls[1].headers['X-Roomink-Store'], '99')
    if (kind === 'preview') assert.equal(await calls[1].body.get('file').text(), await file.text())
    else assert.deepEqual(JSON.parse(calls[1].body), { rows })
  })

  for (const failure of ['csrf-once', 'csrf-always', 'permission', 'logout', 'network', 'refresh']) {
    test(`${kind}: ${failure} retries only a rejected CSRF request, at most once`, async () => {
      let refreshes = 0
      const posts = []
      globalThis.fetch = async (url, opts) => {
        if (url.endsWith('/auth/csrf/')) {
          refreshes++
          return { ok: failure !== 'refresh', status: failure === 'refresh' ? 503 : 200, json: async () => ({ csrf_token: `token-${refreshes}` }) }
        }
        posts.push(opts)
        if (failure === 'network') throw new TypeError('network failed')
        const ok = failure === 'csrf-once' && posts.length === 2
        return { ok, status: failure === 'logout' ? 401 : ok ? 200 : 403, json: async () => ({ detail: failure.startsWith('csrf') ? mismatch : 'Permission denied' }) }
      }
      if (failure === 'csrf-once') await send()
      else await assert.rejects(send)
      const retried = failure.startsWith('csrf')
      assert.equal(posts.length, failure === 'refresh' ? 0 : retried ? 2 : 1)
      assert.equal(refreshes, retried ? 2 : 1)
      if (retried) {
        assert.equal(posts[1].headers['X-CSRFToken'], 'token-2')
        assert.equal(posts[0].body, posts[1].body)
      }
    })
  }
}
