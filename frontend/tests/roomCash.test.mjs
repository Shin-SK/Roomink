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

async function mountPanel(api, props) {
  const root = dirname(fileURLToPath(import.meta.url))
  const filename = resolve(root, '../src/components/RoomCashPanel.vue')
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  const code = compileScript(descriptor, { id: 'room-cash-test' }).content
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
