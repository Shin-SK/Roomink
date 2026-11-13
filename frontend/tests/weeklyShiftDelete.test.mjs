import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick } from 'vue'

async function mount(api) {
  const root = dirname(fileURLToPath(import.meta.url))
  const filename = resolve(root, '../src/pages/op/ShiftWeekly.vue')
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  const code = compileScript(descriptor, { id: 'weekly-delete-test' }).content
    .replace(/import LayoutOperator from [^\n]+/, 'const LayoutOperator = {}')
    .replace(/import \{ api \} from [^\n]+/, 'const api = globalThis.__weeklyDeleteApi')
    .replace(/onMounted\(async \(\) =>/, ';(() => {})(async () =>')
    .replace(/from (['"])(\.[^'"]+)\1/g, (_, q, s) => `from ${q}${pathToFileURL(resolve(dirname(filename), s)).href}${q}`)
  const temporary = mkdtempSync(join(root, '.weekly-delete-test-'))
  globalThis.__weeklyDeleteApi = api
  try {
    const compiled = join(temporary, 'component.mjs')
    writeFileSync(compiled, code)
    const component = (await import(pathToFileURL(compiled).href)).default
    component.render = () => null
    const renderer = createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, insert() {}, remove() {}, patchProp() {} })
    const app = renderer.createApp({ render: () => h(component) })
    const vm = app.mount({})
    return { state: vm.$.subTree.component.setupState, unmount: () => app.unmount() }
  } finally { delete globalThis.__weeklyDeleteApi; rmSync(temporary, { recursive: true, force: true }) }
}

const week = id => ({ days: [{ existing_shifts: [{ id, start_time: '18:00', end_time: '23:00' }] }] })

test('deletion requires confirmation and sends only the confirmed selection once', async () => {
  const calls = []
  let finish
  const { state, unmount } = await mount({ getWeeklyShifts: async () => week(1), deleteWeeklyShifts: async body => { calls.push(body); await new Promise(r => { finish = r }); return { deleted_count: 1 } } })
  try {
    state.selectedCast = 7
    await nextTick()
    await state.loadWeek()
    await state.deleteSelected()
    assert.equal(calls.length, 0)
    state.selectedShiftIds = [1, 999]
    state.confirmDeletion()
    assert.deepEqual(state.deleteConfirmation.shifts.map(s => s.id), [1])
    state.selectedShiftIds = []
    const pending = state.deleteSelected()
    await state.deleteSelected()
    assert.equal(calls.length, 1)
    assert.equal(calls[0].cast, 7)
    assert.deepEqual(calls[0].shift_ids, [1])
    finish()
    await pending
    assert.equal(state.deleteConfirmation, null)
    assert.deepEqual(state.selectedShiftIds, [])
    assert.equal(state.success, '1件のシフトを削除しました')
  } finally { unmount() }
})

test('rejected deletion keeps selection and rows, reports dates and never auto-retries', async () => {
  let calls = 0
  const { state, unmount } = await mount({ getWeeklyShifts: async () => week(1), deleteWeeklyShifts: async () => { calls++; throw Object.assign(new Error('1件も削除していません'), { data: { errors: [{ date: '2026-11-13', detail: '予約があります' }] } }) } })
  try {
    state.selectedCast = 7
    await nextTick()
    await state.loadWeek()
    state.selectedShiftIds = [1]
    state.confirmDeletion()
    await state.deleteSelected()
    assert.equal(calls, 1)
    assert.equal(state.existingShifts.length, 1)
    assert.deepEqual(state.selectedShiftIds, [1])
    assert.equal(state.errorFor('2026-11-13'), '予約があります')
    assert.equal(state.deleteConfirmation, null)
  } finally { unmount() }
})

test('switching weeks cancels confirmation and discards older responses', async () => {
  let finishOld
  let delayed = false
  const { state, unmount } = await mount({ getWeeklyShifts: async () => delayed ? new Promise(r => { finishOld = r }) : week(2) })
  try {
    state.selectedCast = 7
    await nextTick()
    await state.loadWeek()
    state.selectedShiftIds = [2]
    state.confirmDeletion()
    delayed = true
    const old = state.loadWeek()
    assert.equal(state.deleteConfirmation, null)
    assert.deepEqual(state.selectedShiftIds, [])
    delayed = false
    state.shiftWeek(7)
    await nextTick()
    await state.loadWeek()
    finishOld(week(1))
    await old
    assert.equal(state.existingShifts[0].id, 2)
  } finally { unmount() }
})
