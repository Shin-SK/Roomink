import test from 'node:test'
import assert from 'node:assert/strict'

let sequence = 0
async function selection({ saved = '', search = '', unavailable = false } = {}) {
  const values = new Map([['roomink-active-store', saved]])
  let navigated = null
  globalThis.window = {
    location: { search, assign: url => { navigated = url } },
    sessionStorage: {
      getItem: key => { if (unavailable) throw new Error('disabled'); return values.get(key) },
      setItem: (key, value) => { if (unavailable) throw new Error('disabled'); values.set(key, value) },
      removeItem: key => values.delete(key),
    },
  }
  const module = await import(`../src/storeSelection.js?test=${sequence++}`)
  return { ...module, values, navigated: () => navigated }
}

test('no selected store keeps the existing default behavior', async () => {
  const state = await selection()
  assert.equal(state.selectedStoreId(), '')
  assert.equal(state.scopedExportUrl('/api/export/'), '/api/export/')
})

test('a URL store wins over tab storage for a reservation popup', async () => {
  const state = await selection({ saved: '1', search: '?popup=1&store=2' })
  assert.equal(state.selectedStoreId(), '2')
})

test('changing storage cannot silently redirect requests from a mounted form', async () => {
  const state = await selection({ saved: '1' })
  state.values.set('roomink-active-store', '2')
  assert.equal(state.selectedStoreId(), '1')
})

test('explicit switch persists the target and reloads on a safe entry page', async () => {
  const state = await selection({ saved: '1' })
  state.openStore(2)
  assert.equal(state.navigated(), '/op/dashboard?store=2')
  assert.equal(state.values.get('roomink-active-store'), '2')
  assert.equal(state.selectedStoreId(), '1')
})

test('exports preserve both the selected store and other filters', async () => {
  const state = await selection({ saved: '3' })
  assert.equal(state.scopedExportUrl('/api/export/'), '/api/export/?_store=3')
  assert.equal(state.scopedExportUrl('/api/export/?range=today'), '/api/export/?range=today&_store=3')
})

test('invalid IDs are discarded and login/logout can clear selection', async () => {
  for (const saved of ['-1', 'abc', '９', '1&admin=true']) {
    const state = await selection({ saved })
    assert.equal(state.selectedStoreId(), '')
  }
  const state = await selection({ saved: '2' })
  state.setSelectedStoreId(null)
  assert.equal(state.selectedStoreId(), '')
  assert.equal(state.values.has('roomink-active-store'), false)
})

test('store URL works even when browser storage is disabled', async () => {
  const state = await selection({ unavailable: true, search: '?store=3' })
  assert.equal(state.selectedStoreId(), '3')
  state.openStore(2)
  assert.equal(state.navigated(), '/op/dashboard?store=2')
})
