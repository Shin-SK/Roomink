import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

function panel(save, orderSaving = false) {
  const entry = { id: 11, context: { customer_history: {} }, noteText: '  希望時間が満席  ', client: { saveInquiry: save }, orderSaving, result: null }
  const source = readFileSync(new URL('../src/components/CtiIncomingPanel.vue', import.meta.url), 'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const ctx = vm.createContext({
    ref: value => ({ value }), computed: get => ({ get value() { return get() } }),
    onMounted() {}, onBeforeUnmount() {}, onBeforeRouteLeave() {}, nextTick: async () => {},
    api: { getCtiWorkQueue: async () => ({ calls: [] }), getCtiCallHistory: async () => ({ calls: [] }), getCtiCallContext: async () => entry.context },
    window: { confirm: () => false }, document: { body: { classList: { remove() {} } } },
    setTimeout: () => 0, clearTimeout() {}, entry,
  })
  vm.runInContext(source, ctx)
  vm.runInContext('drafts.value = [entry]', ctx)
  return { entry, ctx, save: () => vm.runInContext('saveInquiry(entry)', ctx) }
}

test('memo completion survives refresh and repeated clicks cannot send concurrently', async () => {
  let resolve, calls = 0
  const p = panel(body => { calls++; assert.equal(body, '希望時間が満席'); return new Promise(r => { resolve = r }) })
  const saving = p.save()
  await p.save()
  assert.equal(calls, 1)
  assert.equal(p.entry.noteText.trim(), '希望時間が満席')
  resolve({ id: 7, body: '希望時間が満席', status: 'DONE' })
  await saving
  assert.equal(p.entry.noteText, '')
  assert.equal(p.entry.result.inquiryOnly, true)
  assert.equal(p.entry.context.customer_history.current_notes[0].id, 7)
})

test('network failure preserves unsaved memo and does not complete reception', async () => {
  const p = panel(async () => { throw new Error('接続できません') })
  await p.save()
  assert.equal(p.entry.noteText, '  希望時間が満席  ')
  assert.equal(p.entry.result, null)
  assert.equal(p.entry.noteError, '接続できません')
  assert.equal(p.entry.noteSaving, false)
})

test('reservation submission blocks memo completion and invalid memos are not sent', async () => {
  let calls = 0
  const p = panel(async () => { calls++ }, true)
  await p.save()
  p.entry.orderSaving = false
  p.entry.noteText = ' '
  await p.save()
  p.entry.noteText = 'a'.repeat(2001)
  await p.save()
  assert.equal(calls, 0)
})

test('opening history is read-only, preserves reception input and ignores a closed pending result', async () => {
  const p = panel(async () => {})
  let resolve, mutations = 0
  p.ctx.api.getCtiCallContext = () => new Promise(r => { resolve = r })
  p.ctx.callApi = () => ({ markSeen: () => mutations++, start: () => mutations++ })
  const opening = vm.runInContext('openHistory({ id: 22 })', p.ctx)
  vm.runInContext('closeHistory()', p.ctx)
  resolve({ customer_name: '履歴のみ' }); await opening
  assert.equal(vm.runInContext('historyContext.value', p.ctx), null)
  assert.equal(mutations, 0)
  assert.equal(p.entry.noteText, '  希望時間が満席  ')
})

test('history day changes discard stale responses and pagination passes the displayed offset', async () => {
  const p = panel(async () => {}), requests = []
  p.ctx.api.getCtiCallHistory = (date, offset) => new Promise(resolve => requests.push({date,offset,resolve}))
  vm.runInContext("historyDate.value = '2026-10-29'",p.ctx)
  const old = vm.runInContext('refreshHistory()',p.ctx)
  vm.runInContext("historyDate.value = '2026-10-30'",p.ctx)
  const current = vm.runInContext('refreshHistory()',p.ctx)
  requests[1].resolve({calls:[{id:2}],date:'2026-10-30',has_more:true});await current
  requests[0].resolve({calls:[{id:1}],date:'2026-10-29'});await old
  assert.equal(vm.runInContext('history.value[0].id',p.ctx),2)
  const more=vm.runInContext('refreshHistory(true)',p.ctx)
  assert.equal(requests[2].date,'2026-10-30');assert.equal(requests[2].offset,1)
  requests[2].resolve({calls:[{id:3}],date:'2026-10-30',has_more:false});await more
  assert.equal(vm.runInContext('history.value.length',p.ctx),2)
})
