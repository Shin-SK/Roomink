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
