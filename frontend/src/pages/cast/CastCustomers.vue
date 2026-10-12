<script setup>
import { onMounted, ref } from 'vue'
import LayoutCast from '../../components/LayoutCast.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const query = ref('')
const customers = ref([])
const selected = ref(null)
const detailLoading = ref(false)
const memoDraft = ref('')
const saving = ref(false)
const saved = ref(false)

async function loadCustomers() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getCastCustomers(query.value.trim())
    customers.value = data.customers || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function openCustomer(customer) {
  selected.value = null
  detailLoading.value = true
  error.value = ''
  saved.value = false
  try {
    selected.value = await api.getCastCustomer(customer.id)
    memoDraft.value = selected.value.memo || ''
  } catch (e) {
    error.value = e.message
  } finally {
    detailLoading.value = false
  }
}

async function saveMemo() {
  if (!selected.value) return
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    const data = await api.updateCastCustomerMemo(selected.value.id, memoDraft.value)
    selected.value.memo = data.memo || ''
    memoDraft.value = selected.value.memo
    const item = customers.value.find(customer => customer.id === selected.value.id)
    if (item) item.memo = selected.value.memo
    saved.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

function formatDate(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric', month: 'numeric', day: 'numeric', weekday: 'short',
  }).format(new Date(value))
}

onMounted(loadCustomers)
</script>

<template>
  <LayoutCast>
    <div class="d-flex align-items-center justify-content-between mb-3">
      <div>
        <h2 class="h4 fw-bold mb-1">お客様</h2>
        <p class="text-muted small mb-0">これまで担当したお客様の利用履歴と自分用メモです。</p>
      </div>
    </div>

    <form class="input-group mb-3" @submit.prevent="loadCustomers">
      <input v-model="query" class="form-control" placeholder="お客様名で検索" maxlength="50">
      <button class="btn btn-outline-primary" type="submit"><i class="ti ti-search"></i> 検索</button>
    </form>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading" class="text-center py-5"><span class="spinner-border text-primary"></span></div>
    <div v-else-if="customers.length === 0" class="card"><div class="card-body text-center text-muted py-5">利用履歴のあるお客様はまだいません。</div></div>

    <div v-else class="customer-list">
      <button
        v-for="customer in customers"
        :key="customer.id"
        type="button"
        class="card customer-card text-start"
        @click="openCustomer(customer)"
      >
        <div class="card-body">
          <div class="d-flex justify-content-between gap-3">
            <div>
              <div class="fw-bold">{{ customer.display_name }}</div>
              <div class="small text-muted mt-1">最終利用 {{ formatDate(customer.last_visit_at) }}</div>
            </div>
            <span class="badge text-bg-light align-self-start">{{ customer.visit_count }}回利用</span>
          </div>
          <div v-if="customer.nomination_labels.length" class="mt-2">
            <span v-for="label in customer.nomination_labels" :key="label" class="badge text-bg-warning me-1">{{ label }}</span>
          </div>
          <p v-if="customer.memo" class="memo-preview mb-0 mt-2">{{ customer.memo }}</p>
        </div>
      </button>
    </div>

    <div v-if="detailLoading" class="detail-backdrop"><span class="spinner-border text-primary"></span></div>
    <div v-if="selected" class="detail-backdrop" @click.self="selected = null">
      <section class="detail-panel">
        <button class="btn-close float-end" type="button" aria-label="閉じる" @click="selected = null"></button>
        <h3 class="h5 fw-bold mb-1">{{ selected.display_name }}</h3>
        <div class="text-muted small mb-3">利用履歴 {{ selected.history.length }}件</div>

        <label class="form-label fw-bold">お客様メモ（自分のみ）</label>
        <textarea v-model="memoDraft" class="form-control" rows="5" maxlength="2000" placeholder="好みや施術時の引き継ぎを入力"></textarea>
        <div class="d-flex justify-content-between form-text"><span>他のセラピストやお客様には表示されません。</span><span>{{ memoDraft.length }}/2000</span></div>
        <button class="btn btn-primary w-100 mt-2" :disabled="saving" @click="saveMemo">
          {{ saving ? '保存中…' : 'メモを保存' }}
        </button>
        <div v-if="saved" class="text-success small text-center mt-2">保存しました</div>

        <h4 class="h6 fw-bold mt-4 mb-2">利用履歴</h4>
        <div v-for="order in selected.history" :key="order.id" class="history-row">
          <div class="fw-bold">{{ formatDate(order.start) }}</div>
          <div class="small text-muted">{{ order.course_name }}<span v-if="order.nomination_label"> ・ {{ order.nomination_label }}</span></div>
        </div>
      </section>
    </div>
  </LayoutCast>
</template>

<style scoped>
.customer-list { display: grid; gap: 10px; }
.customer-card { width: 100%; border-color: #dfe7e4; color: inherit; }
.customer-card:hover { border-color: #2a9d8f; background: #fbfffd; }
.memo-preview { white-space: pre-wrap; color: #55635f; font-size: .85rem; line-height: 1.5; }
.detail-backdrop { position: fixed; inset: 0; z-index: 1100; display: flex; align-items: flex-end; justify-content: center; padding: 16px; background: rgba(20, 31, 28, .42); }
.detail-panel { width: min(620px, 100%); max-height: 88vh; overflow-y: auto; padding: 22px; border-radius: 20px 20px 12px 12px; background: #fff; box-shadow: 0 16px 50px rgba(0, 0, 0, .18); }
.history-row { padding: 12px 0; border-top: 1px solid #e8eeec; }
@media (min-width: 768px) { .detail-backdrop { align-items: center; } .detail-panel { border-radius: 20px; } }
</style>
