import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick, reactive } from 'vue'
import { roomCashYen, validCashCount, roomCashDrafts } from '../src/roomCashDisplay.js'

test('unknown cash is never formatted as zero; a confirmed zero remains zero', () => {
  assert.equal(roomCashYen(null), '残高未確認')
  assert.equal(roomCashYen(undefined), '残高未確認')
  assert.equal(roomCashYen(0), '0円')
  assert.equal(roomCashYen(26000), '26,000円')
  assert.equal(roomCashYen(-5000), '-5,000円')
})

test('counts require an explicit nonnegative whole yen amount, never default the previous count', () => {
  for (const value of ['', ' ', null, undefined, -1, 1.5, 'invalid', Infinity]) assert.equal(validCashCount(value), false)
  for (const value of [0, '0', 26000]) assert.equal(validCashCount(value), true)
  const rows = [{ room: 1, actual_cash_amount: 26000 }]
  assert.equal(roomCashDrafts(rows)[1].actual_cash_amount, '')
  assert.equal(roomCashDrafts(rows, { 1: { actual_cash_amount: '25000' } }, true)[1].actual_cash_amount, '25000')
})

const baseRoom = { room: 1, room_name: 'Aルーム', revision: 'first', expected_cash_amount: 26000, actual_cash_amount: null, balance_known: true, can_count: true, casts: [] }

test('full collection only fills the amount; registration and retry use the same request ID', async () => {
  const previousWindow = globalThis.window
  globalThis.window = { confirm: () => true }
  const calls = []
  const { state, unmount } = await mountPanel({ saveRoomCashCount: async body => { calls.push(body); throw new Error('offline') } },
    { row: { ...baseRoom, expected_cash_amount: 15000 }, date: '2026-10-22', disabled: false }, '../src/components/RoomCashCollection.vue')
  try {
    state.fillAll()
    assert.equal(state.amount, '15000')
    assert.equal(state.after, 0)
    assert.equal(calls.length, 0)
    state.amount = '10000'
    assert.equal(state.after, 5000)
    await state.submit(); await state.submit()
    assert.equal(calls.length, 2)
    assert.equal(calls[0].request_id, calls[1].request_id)
    assert.equal(calls[0].amount, 10000)
    assert.equal(calls[0].operation, 'collect')
    state.amount = '16000'
    await state.submit()
    assert.equal(calls.length, 2)
  } finally { unmount(); globalThis.window = previousWindow }
})

test('collection conflict preserves input through refresh, then submits against the new revision', async () => {
  const previousWindow = globalThis.window
  globalThis.window = { confirm: () => true }
  const calls = []
  const props = reactive({ row: { ...baseRoom }, date: '2026-10-22', disabled: false })
  const { state, unmount } = await mountPanel({ saveRoomCashCount: async body => {
    calls.push(body)
    if (calls.length === 1) throw Object.assign(new Error('conflict'), { status: 409 })
    return { rooms: [] }
  } }, props, '../src/components/RoomCashCollection.vue')
  try {
    state.amount = '10000'; state.memo = '回収備考'
    await state.submit(); await state.submit()
    assert.equal(calls.length, 1)
    props.row = { ...baseRoom, revision: 'latest', expected_cash_amount: 20000 }
    await nextTick()
    assert.equal(state.amount, '10000')
    assert.equal(state.memo, '回収備考')
    await state.submit()
    assert.equal(calls[1].expected_revision, 'latest')
    assert.equal(state.amount, '')
    assert.match(state.success, /10,000円の回収を登録/)
    props.row = { ...baseRoom, revision: 'saved' }
    await nextTick()
    assert.match(state.success, /登録しました/)
  } finally { unmount(); globalThis.window = previousWindow }
})

async function mountPanel(api, props, relative = '../src/components/RoomCashPanel.vue', transform = code => code) {
  const root = dirname(fileURLToPath(import.meta.url))
  const filename = resolve(root, relative)
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  const code = transform(compileScript(descriptor, { id: 'room-cash-test' }).content)
    .replace(/import RoomCashCollection from [^\n]+/, 'const RoomCashCollection = {}')
    .replace(/import \{ api \} from [^\n]+/, 'const api = globalThis.__roomCashApi')
    .replace(/from (['"])(\.[^'"]+)\1/g, (_, quote, specifier) => `from ${quote}${pathToFileURL(resolve(dirname(filename), specifier)).href}${quote}`)
  const temporary = mkdtempSync(join(root, '.room-cash-test-'))
  globalThis.__roomCashApi = api
  try {
    const compiled = join(temporary, 'component.mjs')
    writeFileSync(compiled, code)
    const component = (await import(pathToFileURL(compiled).href)).default
    component.render = () => null
    const renderer = createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, insert() {}, remove() {}, patchProp() {} })
    const app = renderer.createApp({ render: () => h(component, props) })
    const vm = app.mount({})
    await nextTick()
    return { state: vm.$.subTree.component.setupState, unmount: () => app.unmount() }
  } finally {
    delete globalThis.__roomCashApi
    rmSync(temporary, { recursive: true, force: true })
  }
}

test('conflicts retain the count and memo, require latest revision, and never change a salary', async () => {
  const previousWindow = globalThis.window
  const bodies = []
  let latest = false
  globalThis.window = { confirm: () => true }
  const api = {
    getRoomCashSummary: async () => ({ rooms: [{ ...baseRoom, revision: latest ? 'latest' : 'first' }] }),
    saveRoomCashCount: async body => { bodies.push(body); if (!latest) throw Object.assign(new Error(), { status: 409 }); return { rooms: [{ ...baseRoom, revision: 'saved', actual_cash_amount: 26000 }] } },
  }
  const { state, unmount } = await mountPanel(api, { date: '2026-10-16' })
  try {
    state.drafts[1].actual_cash_amount = '26000'
    state.drafts[1].memo = '確認済み'
    await state.save(state.rooms[0])
    assert.equal(state.conflicts[1], true)
    assert.equal(state.drafts[1].actual_cash_amount, '26000')
    assert.equal(state.drafts[1].memo, '確認済み')
    await state.save(state.rooms[0])
    assert.equal(bodies.length, 1)
    latest = true
    await state.reload(true)
    assert.equal(state.drafts[1].actual_cash_amount, '26000')
    await state.save(state.rooms[0])
    assert.equal(bodies.length, 2)
    assert.equal(bodies[1].expected_revision, 'latest')
    assert.deepEqual(Object.keys(bodies[1]).sort(), ['actual_cash_amount', 'date', 'expected_revision', 'memo', 'request_id', 'room'])
    assert.equal(state.drafts[1].actual_cash_amount, '')
  } finally { unmount(); globalThis.window = previousWindow }
})

test('changing dates clears drafts and ignores a late response for the previous date', async () => {
  let finishOld
  const props = reactive({ date: '2026-10-15' })
  const { state, unmount } = await mountPanel({ getRoomCashSummary: date => date === '2026-10-15' ? new Promise(resolve => { finishOld = resolve }) : Promise.resolve({ rooms: [{ ...baseRoom, room: 2 }] }) }, props)
  try {
    props.date = '2026-10-16'
    await nextTick(); await nextTick(); await nextTick()
    finishOld({ rooms: [baseRoom] })
    await nextTick(); await nextTick()
    assert.equal(state.rooms[0].room, 2)
    assert.equal(state.drafts[1], undefined)
    assert.equal(state.drafts[2].actual_cash_amount, '')
  } finally { unmount() }
})

test('an old save failure cannot mark the current draft as conflicted after leaving and returning to its date', async () => {
  const previousWindow = globalThis.window
  globalThis.window = { confirm: () => true }
  let rejectSave
  const props = reactive({ date: '2026-10-16' })
  const { state, unmount } = await mountPanel({
    getRoomCashSummary: async () => ({ rooms: [baseRoom] }),
    saveRoomCashCount: () => new Promise((resolve, reject) => { rejectSave = reject }),
  }, props)
  try {
    state.drafts[1].actual_cash_amount = '26000'
    const pending = state.save(state.rooms[0])
    props.date = '2026-10-15'
    await nextTick(); await nextTick()
    props.date = '2026-10-16'
    await nextTick(); await nextTick()
    state.drafts[1].actual_cash_amount = '12000'
    rejectSave(Object.assign(new Error('old conflict'), { status: 409 }))
    await pending
    assert.equal(state.drafts[1].actual_cash_amount, '12000')
    assert.equal(state.conflicts[1], undefined)
    assert.equal(state.rowErrors[1], undefined)
  } finally { unmount(); globalThis.window = previousWindow }
})

test('network retries reuse an ID only for identical contents; past days and failed refresh cannot save', async () => {
  const previousWindow = globalThis.window
  globalThis.window = { confirm: () => true }
  const bodies = []
  let failRead = false
  const { state, unmount } = await mountPanel({
    getRoomCashSummary: async () => { if (failRead) throw new Error('offline'); return { rooms: [baseRoom] } },
    saveRoomCashCount: async body => { bodies.push(body); throw new Error('offline') },
  }, { date: '2026-10-16' })
  try {
    state.drafts[1].actual_cash_amount = '26000'
    await state.save(state.rooms[0]); await state.save(state.rooms[0])
    assert.equal(bodies[0].request_id, bodies[1].request_id)
    state.drafts[1].actual_cash_amount = '25000'
    await state.save(state.rooms[0])
    assert.notEqual(bodies[1].request_id, bodies[2].request_id)
    await state.save({ ...state.rooms[0], can_count: false })
    assert.equal(bodies.length, 3)
    failRead = true
    await state.reload(true)
    await state.save(state.rooms[0])
    assert.equal(bodies.length, 3)
    assert.equal(state.drafts[1].actual_cash_amount, '25000')
  } finally { unmount(); globalThis.window = previousWindow }
})

test('cast mode selects an assigned room, uses only cast endpoints and records only a count', async () => {
  const previousWindow = globalThis.window
  globalThis.window = { confirm: () => true }
  const self = { remaining_receivable_amount: 31000, suggested_take_amount: 26000, shortage_amount: 5000 }
  let recorded
  const dates = []
  const selfRoom = { ...baseRoom, settlement: self }
  const { state, unmount } = await mountPanel({
    getCastRoomCash: async (date, room) => {
      dates.push([date, room])
      return { requires_room_selection: !room, rooms: room ? [selfRoom] : [selfRoom, { ...baseRoom, room: 2 }] }
    },
    saveCastRoomCashCount: async body => { recorded = body; return { rooms: [selfRoom] } },
    getRoomCashSummary: () => { throw new Error('manager endpoint must never be called') },
    saveRoomCashCount: () => { throw new Error('manager endpoint must never be called') },
  }, { date: '2026-10-16', castMode: true })
  try {
    assert.equal(state.needsRoomSelection, true)
    assert.equal(state.roomChoices.length, 2)
    state.selectedRoom = '1'
    state.selectRoom()
    await nextTick(); await nextTick()
    assert.equal(state.needsRoomSelection, false)
    assert.deepEqual(dates[1], ['2026-10-16', '1'])
    assert.deepEqual(state.settlements(state.rooms[0]), [self])
    state.drafts[1].actual_cash_amount = '26000'
    await state.save(state.rooms[0])
    assert.equal(recorded.actual_cash_amount, 26000)
    assert.equal('cast_id' in recorded, false)
    assert.equal('room_cash_taken_amount' in recorded, false)
    assert.equal('compensation_amount' in recorded, false)
  } finally { unmount(); globalThis.window = previousWindow }
})

test('automatic refresh skips count and memo drafts, saving and loading; an idle refresh updates the revision', async () => {
  let reads = 0
  let fail = false
  const { state, unmount } = await mountPanel({ getRoomCashSummary: async () => {
    reads++
    if (fail) throw new Error('最新残金を取得できません')
    return { rooms: [{ ...baseRoom, revision: `read-${reads}`, expected_cash_amount: reads === 1 ? 26000 : 0 }] }
  } }, { date: '2026-10-16' })
  try {
    state.drafts[1].actual_cash_amount = '0'
    assert.equal(await state.refreshWhenIdle(), false)
    state.drafts[1].actual_cash_amount = ''
    state.drafts[1].memo = '数え直し中'
    assert.equal(await state.refreshWhenIdle(), false)
    state.drafts[1].memo = ''
    state.saving[1] = true
    assert.equal(await state.refreshWhenIdle(), false)
    state.saving[1] = false
    state.loading = true
    assert.equal(await state.refreshWhenIdle(), false)
    state.loading = false
    assert.equal(reads, 1)
    assert.equal(state.rooms[0].revision, 'read-1')
    assert.equal(await state.refreshWhenIdle(), true)
    assert.equal(reads, 2)
    assert.equal(state.rooms[0].revision, 'read-2')
    assert.equal(state.rooms[0].expected_cash_amount, 0)
    fail = true
    await state.refreshWhenIdle()
    assert.match(state.error, /最新残金/)
    assert.equal(state.rooms[0].revision, 'read-2')
  } finally { unmount() }
})

test('checkout submission and service completion refresh the real cash panel through loadCheckout', async () => {
  const previousWindow = globalThis.window
  globalThis.window = { confirm: () => true }
  let roomCash = 26000
  let remaining = 31000
  let revision = 1
  let reads = 0
  const api = {
    getCastRoomCash: async () => { reads++; return { rooms: [{ ...baseRoom, revision: `revision-${revision}`, expected_cash_amount: roomCash,
      settlement: { remaining_receivable_amount: remaining, suggested_take_amount: Math.min(roomCash, remaining), shortage_amount: Math.max(0, remaining - roomCash) } }] } },
    getCastCheckout: async () => ({ compensation: 31000, checkout: roomCash === 0 ? { status: 'SUBMITTED', room_cash_taken_amount: 26000 } : null }),
    submitCastCheckout: async body => { assert.equal(body.room_cash_taken_amount, 26000); roomCash = 0; remaining = 5000; revision++ },
    getCastAdjustmentsMypage: async () => ({}),
    completeCastOrder: async () => { roomCash = 10000; remaining = 10000; revision++ },
    getCastTodaySales: async () => ({ estimated_pay: 10000 }),
  }
  const panel = await mountPanel(api, { date: '2026-10-16', castMode: true })
  const parent = await mountPanel(api, {}, '../src/pages/cast/CastMypage.vue', code => code
    .replace(/import LayoutCast from [^\n]+/, 'const LayoutCast = {}')
    .replace(/import RoomCashPanel from [^\n]+/, 'const RoomCashPanel = {}')
    .replace(/onMounted\(async \(\) =>/, '(() => {})(async () =>'))
  try {
    parent.state.checkoutRoomCashPanel = { refreshWhenIdle: panel.state.refreshWhenIdle }
    assert.equal(panel.state.rooms[0].expected_cash_amount, 26000)
    parent.state.checkoutForm.room_cash_taken_amount = 26000
    parent.state.checkoutForm.checklist_json = Object.fromEntries(parent.state.CHECKLIST_ITEMS.map(item => [item.key, true]))
    await parent.state.submitCheckout()
    assert.equal(parent.state.checkoutError, '')
    assert.equal(panel.state.rooms[0].expected_cash_amount, 0)
    assert.equal(panel.state.rooms[0].settlement.remaining_receivable_amount, 5000)
    assert.equal(panel.state.rooms[0].settlement.suggested_take_amount, 0)
    assert.equal(reads, 2)
    await parent.state.completeService({ id: 1 })
    assert.equal(panel.state.rooms[0].expected_cash_amount, 10000)
    assert.equal(panel.state.rooms[0].settlement.remaining_receivable_amount, 10000)
    assert.equal(reads, 3)
    api.getCastTodaySales = async () => { throw new Error('報酬の取得失敗') }
    await parent.state.completeService({ id: 2 })
    assert.equal(reads, 4)
    assert.equal(panel.state.rooms[0].revision, 'revision-4')
    assert.equal(parent.state.actionErrors[2], '報酬の取得失敗')
    panel.state.drafts[1].actual_cash_amount = '9000'
    revision++
    await parent.state.loadCheckout()
    assert.equal(reads, 4)
    assert.equal(panel.state.rooms[0].revision, 'revision-4')
    assert.equal(panel.state.drafts[1].actual_cash_amount, '9000')
  } finally { parent.unmount(); panel.unmount(); globalThis.window = previousWindow }
})
