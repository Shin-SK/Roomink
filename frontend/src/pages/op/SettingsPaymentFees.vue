<script setup>
import { ref, onMounted } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref('')

const form = ref({
  cash_fee_rate: 0,
  paypay_fee_rate: 5,
  card_fee_rate: 10,
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getPaymentFeeSettings()
    form.value.cash_fee_rate = data.cash_fee_rate
    form.value.paypay_fee_rate = data.paypay_fee_rate
    form.value.card_fee_rate = data.card_fee_rate
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    await api.updatePaymentFeeSettings(form.value)
    success.value = '保存しました'
    setTimeout(() => { success.value = '' }, 3000)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <LayoutOperator>
    <template #title>決済料率設定</template>

    <div class="alert alert-info small">
      <i class="ti ti-info-circle"></i>
      カードの率は、お客様のカード決済額へ上乗せする率です。上乗せ分は店舗配分に含まれます。
      現金・PayPayの率は店舗側手数料の参考値として、売上集計・退勤提出・日給一覧に表示します。
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <div v-if="loading" class="text-center py-3">
      <div class="spinner-border text-primary"></div>
    </div>

    <div v-else class="card">
      <div class="card-header"><i class="ti ti-percentage"></i> 決済方法別 料率（%）</div>
      <div class="card-body">
        <div class="mb-3">
          <label class="form-label">現金（店舗側手数料・参考値）</label>
          <div class="input-group" style="max-width: 200px;">
            <input v-model.number="form.cash_fee_rate" type="number" min="0" max="100" class="form-control" />
            <span class="input-group-text">%</span>
          </div>
        </div>
        <div class="mb-3">
          <label class="form-label">PayPay（店舗側手数料・参考値）</label>
          <div class="input-group" style="max-width: 200px;">
            <input v-model.number="form.paypay_fee_rate" type="number" min="0" max="100" class="form-control" />
            <span class="input-group-text">%</span>
          </div>
        </div>
        <div class="mb-3">
          <label class="form-label">カード（お客様決済への上乗せ率）</label>
          <div class="input-group" style="max-width: 200px;">
            <input v-model.number="form.card_fee_rate" type="number" min="0" max="100" class="form-control" />
            <span class="input-group-text">%</span>
          </div>
        </div>
        <button class="btn btn-primary" :disabled="saving" @click="onSave">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>
  </LayoutOperator>
</template>
