<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const route = useRoute()
const search = ref(''), rows = ref([]), selected = ref(null), count = ref(0), offset = ref(0)
const loading = ref(false), detailLoading = ref(false), error = ref(''), detailError = ref('')
let listRequest = 0, detailRequest = 0
async function load(reset = false) {
  if (reset) offset.value = 0
  const token = ++listRequest
  loading.value = true; error.value = ''; rows.value = []
  try {
    const params = new URLSearchParams({ search: search.value.trim(), limit: '20', offset: String(offset.value) })
    if (/^[1-9]\d*$/.test(String(route.query.customer || ''))) params.set('customer', route.query.customer)
    const result = await api.getLegacyHistories(params.toString())
    if (token !== listRequest) return
    rows.value = result.results || []; count.value = result.count || 0
  } catch (e) { if (token === listRequest) error.value = e.message || '履歴を読み込めませんでした' }
  finally { if (token === listRequest) loading.value = false }
}
async function open(id) {
  const token = ++detailRequest
  detailLoading.value = true; detailError.value = ''; selected.value = null
  try { const data = await api.getLegacyHistory(id); if (token === detailRequest) selected.value = data }
  catch (e) { if (token === detailRequest) detailError.value = e.message || '履歴を開けませんでした' }
  finally { if (token === detailRequest) detailLoading.value = false }
}
function page(delta) { offset.value += delta * 20; load() }
onMounted(async () => {
  await load()
  if (/^[1-9]\d*$/.test(String(route.query.id || ''))) await open(route.query.id)
})
</script>

<template>
  <LayoutOperator>
    <template #title>旧システムの利用履歴</template>
    <router-link to="/op/customers" class="btn btn-outline-secondary btn-sm mb-3">顧客管理へ戻る</router-link>
    <p class="small text-muted">旧システムのオーダー記録を参照できます。Roominkの予約・売上には含みません。元データに完了・キャンセルの区分はありません。</p>
    <form class="d-flex gap-2 mb-3" @submit.prevent="load(true)"><label class="visually-hidden" for="legacy-search">旧顧客ID・名前・電話番号</label><input id="legacy-search" v-model="search" class="form-control" placeholder="旧顧客ID・名前・電話番号で検索" /><button class="btn btn-primary flex-shrink-0" :disabled="loading">検索</button></form>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <div v-if="loading" role="status">読み込み中…</div>
    <template v-else-if="!error">
      <p class="small">{{ count }}人の履歴<span v-if="count">（{{ offset + 1 }}〜{{ Math.min(offset + 20, count) }}件）</span></p>
      <p v-if="!rows.length" class="text-muted">該当する旧システムの履歴はありません。</p>
      <div v-for="row in rows" :key="row.id" class="legacy-person border rounded p-3 mb-2">
        <div><strong>{{ row.display_name }}</strong><div class="small text-muted">旧顧客ID {{ row.legacy_customer_id }} · {{ row.phone || '電話番号なし' }}</div><div class="small">{{ row.visit_count }}件 <span v-if="!row.customer" class="text-muted">· Roomink顧客との紐付けは未確認</span></div></div>
        <button type="button" class="btn btn-outline-primary btn-sm" @click="open(row.id)">履歴を見る</button>
      </div>
      <div class="d-flex gap-2 my-3"><button class="btn btn-outline-secondary btn-sm" :disabled="offset === 0" @click="page(-1)">前へ</button><button class="btn btn-outline-secondary btn-sm" :disabled="offset + 20 >= count" @click="page(1)">次へ</button></div>
    </template>
    <section class="mt-4" aria-label="選んだ顧客の旧履歴" aria-live="polite">
      <p v-if="detailLoading">履歴を開いています…</p>
      <p v-if="detailError" class="alert alert-danger" role="alert">{{ detailError }}</p>
      <div v-if="selected" class="card"><div class="card-header">{{ selected.display_name }}の旧オーダー履歴（{{ selected.visit_count }}件）</div><div class="card-body"><p class="small text-muted">旧顧客ID {{ selected.legacy_customer_id }}。Roominkでの完了利用履歴とは別の記録です。</p><p class="legacy-text">{{ selected.history_text }}</p></div></div>
    </section>
  </LayoutOperator>
</template>

<style scoped>
.legacy-person{display:flex;align-items:center;justify-content:space-between;gap:12px}.legacy-person>div{min-width:0;overflow-wrap:anywhere}.legacy-person button{flex-shrink:0;min-height:44px}.legacy-text{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.9;margin:0}
@media(max-width:480px){.legacy-person{align-items:flex-start;flex-direction:column}}
</style>
