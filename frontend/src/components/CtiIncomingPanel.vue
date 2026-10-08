<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { api, callApi } from '../api.js'
import OrderForm from './OrderForm.vue'

const calls = ref([]), drafts = ref([]), activeId = ref(null)
const isOpen = ref(false), loading = ref(true), error = ref(''), filter = ref(''), busy = ref(false)
const panel = ref(null), toggle = ref(null)
let timer, disposed = false, polling = false, previousFocus = null
const draft = computed(() => drafts.value.find(d => d.id === activeId.value))
const stores = computed(() => [...new Map(calls.value.map(c => [c.store_id, c.store_name])).entries()])
const visibleCalls = computed(() => calls.value.filter(c => !filter.value || String(c.store_id) === filter.value))
const newCount = computed(() => calls.value.filter(c => c.status === 'NEW').length)
const numericPhone = value => /^\d{10,15}$/.test(value || '')
const phoneLabel = value => numericPhone(value) ? value : '非通知・番号不明'
const time = iso => new Date(iso).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })
const attentionLabel = value => value === 'BAN' ? '受付前に確認・利用制限あり' : '受付時の注意事項'
const denied = e => [401, 403, 404].includes(e.status)
function blockDraft(d) { d.blocked = true; d.context = null; d.client = null }

async function refresh() {
  if (disposed || polling) return
  polling = true
  try {
    const data = await api.getCtiWorkQueue()
    if (disposed) return
    await Promise.all(drafts.value.filter(d => !d.blocked).map(async d => {
      try { const ctx = await api.getCtiCallContext(d.id); if (!disposed) { d.context = ctx; d.offline = false } }
      catch (e) { if (denied(e)) blockDraft(d); else d.offline = true }
    }))
    calls.value = data.calls || []
    error.value = ''
  } catch (e) {
    calls.value = []
    error.value = '着信情報を更新できません。接続と所属店舗をご確認ください。'
    drafts.value.forEach(d => { if (denied(e)) blockDraft(d); else d.offline = true })
  } finally { loading.value = false; polling = false }
}
async function cycle() { await refresh(); if (!disposed) timer = setTimeout(cycle, document.hidden ? 30000 : 5000) }
async function openPanel() {
  previousFocus = document.activeElement
  isOpen.value = true
  await nextTick(); panel.value?.focus(); await refresh()
}
function closePanel() {
  isOpen.value = false
  nextTick(() => { if (previousFocus?.isConnected) previousFocus.focus(); else toggle.value?.focus() })
}
async function openDraft(call) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const context = await api.getCtiCallContext(call.id)
    const existing = drafts.value.find(d => d.id === call.id)
    if (existing?.blocked) drafts.value = drafts.value.filter(d => d.id !== call.id)
    if (!existing || existing.blocked) drafts.value.push({ id: call.id, context, client: callApi(call.id), blocked: false, result: null })
    activeId.value = call.id
    await callApi(call.id).markSeen()
    await nextTick(); panel.value?.querySelector('.cti-detail')?.focus()
  } catch { error.value = 'この着信を開けません。権限と接続をご確認ください。' }
  finally { busy.value = false }
}
async function changeStatus(call, action) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await callApi(call.id)[action](); await refresh() }
  catch (e) { error.value = e.message || '更新できませんでした。' }
  finally { busy.value = false }
}
function discardDraft(id) {
  const entry = drafts.value.find(d => d.id === id)
  if (!entry?.result && !entry?.blocked && !window.confirm('この着信の予約入力を破棄しますか？')) return
  drafts.value = drafts.value.filter(d => d.id !== id); activeId.value = null
}
function created(entry, result) { entry.result = result }
function keydown(event) {
  if (!isOpen.value) return
  if (event.key === 'Escape') { event.preventDefault(); closePanel(); return }
  if (event.key !== 'Tab') return
  const nodes = [...panel.value.querySelectorAll('button,a,input,select,textarea,[tabindex="0"]')].filter(el => !el.disabled && el.getClientRects().length)
  const first = nodes[0], last = nodes.at(-1)
  if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.value)) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
function beforeUnload(event) { if (drafts.value.some(d => !d.result && !d.blocked)) { event.preventDefault(); event.returnValue = '' } }
onBeforeRouteLeave(() => !drafts.value.some(d => !d.result && !d.blocked) || window.confirm('受付パネルの入力を破棄して移動しますか？'))
onMounted(() => { cycle(); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => { disposed = true; clearTimeout(timer); window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <button ref="toggle" type="button" class="cti-launch" aria-label="着信を表示" :aria-expanded="isOpen" @click="openPanel">
    <i class="ti ti-phone-incoming" aria-hidden="true"></i><span class="cti-launch-label">着信</span><span v-if="newCount || drafts.length" class="cti-count">{{ newCount || drafts.length }}</span>
  </button>
  <span class="visually-hidden" aria-live="polite">未対応の着信 {{ newCount }}件</span>
  <Teleport to="body">
    <div v-show="isOpen" class="cti-overlay" @click.self="closePanel">
      <section ref="panel" class="cti-work" :class="{ editing: activeId }" role="dialog" aria-modal="true" aria-labelledby="cti-title" tabindex="-1" @keydown="keydown">
        <header class="cti-header">
          <div class="cti-heading"><span class="cti-icon"><i class="ti ti-phone-incoming" aria-hidden="true"></i></span><div><h2 id="cti-title">着信・予約受付</h2><p>着信した店舗のまま、予約まで。</p></div></div>
          <button class="cti-close" aria-label="入力を保持して閉じる" @click="closePanel"><i class="ti ti-x" aria-hidden="true"></i></button>
        </header>
        <div v-if="error" class="cti-error" role="alert">{{ error }} <button class="btn btn-sm btn-outline-danger" @click="refresh">再読み込み</button></div>
        <div class="cti-body">
          <aside class="cti-inbox" aria-label="着信一覧">
            <div class="cti-inbox-head"><strong>受付一覧</strong><span>{{ newCount }}件 未対応</span></div>
            <label v-if="stores.length > 1" class="cti-filter">表示する店舗<select v-model="filter" class="form-select form-select-sm"><option value="">すべての所属店舗</option><option v-for="[id, name] in stores" :key="id" :value="String(id)">{{ name }}</option></select></label>
            <div v-if="drafts.length" class="cti-drafts"><span class="cti-caption">入力を再開</span><button v-for="d in drafts" :key="d.id" :class="{ selected: activeId === d.id }" @click="activeId = d.id"><i class="ti ti-pencil" aria-hidden="true"></i><span>{{ d.blocked ? '利用できない着信' : d.context?.store_name }}<small>{{ d.result ? '予約作成済み' : '入力を保持しています' }}</small></span></button></div>
            <div v-if="loading" class="cti-empty" role="status">着信を確認しています…</div>
            <div v-else-if="!visibleCalls.length" class="cti-empty"><i class="ti ti-phone-check" aria-hidden="true"></i><strong>現在、着信はありません</strong><p>新しい着信はここに届きます。</p></div>
            <article v-for="call in visibleCalls" :key="call.id" class="cti-call" :class="{ selected: activeId === call.id }">
              <div class="cti-call-top"><span class="cti-store"><i class="ti ti-building-store" aria-hidden="true"></i>{{ call.store_name }}</span><time>{{ time(call.created_at) }}</time></div>
              <div class="cti-name">{{ call.customer_name || (numericPhone(call.from_phone) ? '新規のお客様' : '非通知のお客様') }}</div>
              <div class="cti-phone">{{ phoneLabel(call.from_phone) }}</div>
              <div class="cti-status"><span class="cti-pill" :class="{ working: call.status !== 'NEW' }">{{ call.status === 'NEW' ? '未対応' : '対応中' }}</span><span v-if="call.is_repeat">再着信</span><span v-if="call.assigned_to">担当：{{ call.assigned_to }}</span></div>
              <p v-if="call.customer_attention?.flag && call.customer_attention.flag !== 'NONE'" class="cti-attention"><i class="ti ti-alert-triangle" aria-hidden="true"></i>{{ attentionLabel(call.customer_attention.flag) }}</p>
              <button class="btn btn-primary w-100" :disabled="busy" @click="openDraft(call)">{{ drafts.some(d => d.id === call.id) ? '予約入力を再開' : 'この店舗で予約作成' }}<i class="ti ti-arrow-right ms-2" aria-hidden="true"></i></button>
              <div class="cti-actions"><button :disabled="busy" @click="changeStatus(call, 'start')">対応開始</button><button :disabled="busy" @click="changeStatus(call, 'done')">対応完了</button><span v-if="call.seen_by_me">確認済み</span></div>
            </article>
          </aside>
          <main class="cti-detail" tabindex="-1" aria-label="着信店舗の予約入力">
            <button v-if="activeId" class="cti-back" @click="activeId = null"><i class="ti ti-arrow-left" aria-hidden="true"></i>着信一覧へ <span>入力は保持されます</span></button>
            <div v-if="!draft" class="cti-welcome"><img src="/icon.svg" alt=""><h3>お客様の電話から、<br>いつもの予約へ。</h3><p>着信を選ぶと、その店舗の顧客と予約内容を表示します。<br>ほかの着信へ移っても、入力はそのまま。</p><div><i class="ti ti-lock" aria-hidden="true"></i>予約先は着信店舗に固定されます</div></div>
            <section v-for="d in drafts" v-show="d.id === activeId" :key="d.id">
              <div v-if="d.blocked" class="alert alert-warning">この着信を確認できなくなりました。所属権限と接続をご確認のうえ、着信一覧から開き直してください。</div>
              <template v-else>
                <div v-if="d.offline" class="alert alert-warning" role="status">通信を確認しています。入力は保持していますが、再接続まで保存できません。</div>
                <div class="cti-context"><span class="cti-caption"><i class="ti ti-lock" aria-hidden="true"></i> この予約の保存先</span><h3>{{ d.context.store_name }}</h3><p>{{ d.context.customer_name || '新規のお客様' }} <span>· {{ phoneLabel(d.context.from_phone) }}</span></p></div>
                <div v-if="d.context.customer_attention && (d.context.customer_attention.flag !== 'NONE' || d.context.customer_attention.staff_memo)" class="cti-attention detail"><strong>{{ attentionLabel(d.context.customer_attention.flag) }}</strong><p>{{ d.context.customer_attention.staff_memo || 'ご予約前に店舗の対応方針をご確認ください。' }}</p></div>
                <div v-if="d.result" class="cti-success" role="status"><i class="ti ti-circle-check" aria-hidden="true"></i><h3>{{ d.result.confirmationError ? '予約を保存しました・確定は未完了' : '予約を作成しました' }}</h3><p>{{ d.context.store_name }}に保存しました。</p><p v-if="d.result.confirmationError">{{ d.result.confirmationError }}</p><a class="btn btn-primary" :href="`/op/schedule?store=${d.context.store_id}&date=${d.result.startDate}&highlight=${d.result.order.id}`" target="_blank" rel="noopener">この店舗のタイムラインを開く</a></div>
                <fieldset v-else :disabled="d.offline" class="border-0 p-0 m-0"><OrderForm :api-client="d.client" :call-bound="true" :initial-phone="numericPhone(d.context.from_phone) ? d.context.from_phone : ''" :initial-customer-id="d.context.customer_id || ''" :embedded="true" :show-flow-hint="false" cancel-label="一覧に戻る（入力を保持）" @cancel="activeId = null" @created="created(d, $event)" /></fieldset>
              </template>
              <button class="cti-discard" @click="discardDraft(d.id)">{{ d.result || d.blocked ? 'この入力タブを閉じる' : 'この入力を破棄' }}</button>
            </section>
          </main>
        </div>
        <footer class="cti-footer"><i class="ti ti-info-circle" aria-hidden="true"></i>通話の応答は受付端末で行ってください。<span>入力は、この画面を開いている間保持されます。</span></footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.cti-launch{position:fixed;right:24px;bottom:100px;z-index:1040;border:0;border-radius:100px;background:#4e9a91;color:#fff;box-shadow:0 6px 22px #245c5430;display:flex;align-items:center;gap:8px;padding:15px 20px;font-weight:700}.cti-launch i{font-size:22px}.cti-count{background:#fff;color:#286a62;border-radius:30px;min-width:24px;padding:1px 6px}
.cti-overlay{position:fixed;inset:0;z-index:1100;background:#172c3252;display:flex;align-items:center;justify-content:center;padding:36px 24px}.cti-work{background:#fff;border-radius:20px;width:min(1120px,100%);height:min(850px,calc(100dvh - 72px));display:flex;flex-direction:column;overflow:hidden;box-shadow:0 24px 80px #162c3438;color:#283b3a;outline:none}.cti-header{padding:20px 24px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e3eeeb;gap:12px}.cti-heading{display:flex;align-items:center;gap:12px}.cti-icon{background:#e8f4f0;color:#3b8178;border-radius:14px;width:46px;height:46px;display:grid;place-items:center;font-size:23px}.cti-work h2{font-size:19px;font-weight:750;margin:0 0 4px}.cti-header p{margin:0;color:#60776c;font-size:12px}.cti-close{background:none;border:0;border-radius:50%;width:44px;height:44px;font-size:22px;color:#6a7e79}.cti-body{display:grid;grid-template-columns:340px minmax(0,1fr);min-height:0;flex:1}.cti-inbox{background:#f5f9f7;border-right:1px solid #e3eeeb;overflow:auto;padding:22px 18px}.cti-inbox-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.cti-inbox-head span,.cti-caption{font-size:12px;font-weight:700;color:#5c7568;letter-spacing:.03em}.cti-filter{font-size:12px;color:#597063;display:block;margin-bottom:18px}.cti-filter select{margin-top:6px}.cti-call{background:#fff;border:1px solid #e1ebe7;border-radius:14px;margin-bottom:12px;padding:16px}.cti-call.selected{border-color:#4e9a91;box-shadow:0 0 0 1px #4e9a91}.cti-call-top{display:flex;gap:8px;align-items:flex-start;justify-content:space-between;margin-bottom:12px}.cti-store{color:#397e72;font-size:12px;font-weight:750;overflow-wrap:anywhere}.cti-store i{margin-right:5px}.cti-call time{font-size:12px;color:#667a72;white-space:nowrap}.cti-name{font-size:17px;font-weight:750;overflow-wrap:anywhere}.cti-phone{font-size:13px;color:#63776c;margin:4px 0 10px}.cti-status{display:flex;gap:8px;align-items:center;flex-wrap:wrap;color:#647368;font-size:12px;margin-bottom:14px}.cti-pill{background:#fbefe2;color:#96511b;padding:4px 8px;border-radius:6px;font-weight:700}.cti-pill.working{background:#e5f2ed;color:#327465}.cti-call .btn{font-size:13px;padding:10px}.cti-actions{display:flex;gap:12px;align-items:center;margin-top:12px}.cti-actions button{background:none;border:0;font-size:12px;color:#49705c;padding:8px 0}.cti-actions span{margin-left:auto;font-size:11px;color:#607467}.cti-detail{padding:24px 28px;overflow:auto;min-width:0;background:#fff;outline:none}.cti-welcome{min-height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:30px 0}.cti-welcome img{width:52px;height:52px;margin-bottom:26px;opacity:.8}.cti-welcome h3{font-size:24px;line-height:1.7;font-weight:700;letter-spacing:.03em}.cti-welcome p{font-size:13px;line-height:2;color:#647d6c;margin-top:12px}.cti-welcome>div{margin-top:20px;font-size:12px;background:#f1f7f4;padding:10px 18px;border-radius:30px;color:#577c6b}.cti-footer{border-top:1px solid #e7eeea;display:flex;gap:6px;padding:12px 24px;font-size:11px;color:#627768}.cti-footer span{margin-left:auto}.cti-context{background:#edf6f1;border-radius:14px;padding:18px 20px;margin-bottom:16px;border-left:4px solid #4e9a91}.cti-context h3{font-size:20px;font-weight:750;margin:8px 0}.cti-context p{font-size:13px;margin:0;overflow-wrap:anywhere}.cti-context p span{font-size:12px;color:#577362}.cti-attention{background:#fff5e6;color:#855521;border-radius:8px;padding:10px;font-size:12px;margin:0 0 12px;overflow-wrap:anywhere}.cti-attention i{margin-right:5px}.cti-attention.detail{padding:14px 18px}.cti-attention p{white-space:pre-wrap;margin:6px 0 0}.cti-back{display:flex;gap:7px;align-items:center;background:none;border:0;padding:0 0 16px;color:#497668;font-size:13px;width:100%}.cti-back span{color:#687c6e;font-size:11px;margin-left:auto}.cti-discard{display:block;margin:18px auto;background:none;border:0;font-size:12px;color:#85665a;padding:10px}.cti-drafts{margin-bottom:18px}.cti-drafts button{display:flex;gap:8px;width:100%;text-align:left;border:1px solid #dbe9e1;border-radius:9px;background:#fff;padding:10px;margin-top:7px;color:#4e7464;font-size:12px}.cti-drafts button.selected{background:#e8f3ed}.cti-drafts small{display:block;font-size:11px;color:#59765f;margin-top:3px}.cti-empty{padding:40px 8px;display:flex;flex-direction:column;text-align:center;color:#637b6c;font-size:12px;gap:12px}.cti-empty i{font-size:28px;color:#60967f}.cti-empty strong{font-size:14px}.cti-error{padding:10px 24px;font-size:12px;background:#fff0ed;color:#984a38}.cti-success{text-align:center;padding:38px 12px}.cti-success>i{font-size:42px;color:#4e9a91}.cti-success h3{font-size:20px;margin:16px 0}.cti-success p{font-size:13px;color:#587363}.cti-work :deep(.card){border:1px solid #e4ece7;border-radius:12px;box-shadow:none}.cti-work :deep(.card-header){background:#f7faf8;font-size:13px}.cti-work :deep(.form-control),.cti-work :deep(.form-select){font-size:14px}.cti-work button:focus-visible,.cti-work a:focus-visible{outline:3px solid #4e9a91;outline-offset:3px}.cti-work button:disabled{opacity:.5}
@media(max-width:767px){.cti-launch{right:18px;bottom:90px;padding:12px 16px}.cti-launch-label{display:none}.cti-overlay{padding:28px 0 0;align-items:stretch}.cti-work{height:100%;border-radius:18px 18px 0 0;max-width:100%}.cti-header{padding:14px 16px}.cti-work h2{font-size:17px}.cti-body{display:flex}.cti-inbox{width:100%;border:0;padding:18px 16px}.cti-detail{display:none;padding:16px;width:100%}.editing .cti-inbox{display:none}.editing .cti-detail{display:block}.cti-footer{padding:10px 16px calc(10px + env(safe-area-inset-bottom));font-size:10px}.cti-footer span{display:none}.cti-error{padding:10px 16px}.cti-context{padding:14px 16px}.cti-context h3{font-size:18px}.cti-work :deep(.form-control),.cti-work :deep(.form-select){font-size:16px}.cti-call .btn{font-size:14px;min-height:44px}.cti-actions button{font-size:12px;min-height:40px}}
</style>
