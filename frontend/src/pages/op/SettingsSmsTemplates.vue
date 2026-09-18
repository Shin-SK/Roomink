<script setup>
import { computed, onMounted, ref } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

const loading = ref(true)
const usageLoading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')
const items = ref([])
const systemMessages = ref([])
const cardPaymentUrl = ref('')
const usage = ref(null)
const usageMonth = ref('')

const isManager = computed(() => getAuthRole() === 'manager')
const usagePercent = computed(() => {
  if (!usage.value?.current_block_limit) return 0
  return Math.min(100, Math.round(usage.value.used_segments / usage.value.current_block_limit * 100))
})

function yen(value) {
  return `¥${Number(value || 0).toLocaleString('ja-JP')}`
}

async function loadUsage() {
  usageLoading.value = true
  try {
    usage.value = await api.getSmsUsage(usageMonth.value)
    usageMonth.value = usage.value.month
  } catch (e) {
    error.value = e.message
  } finally {
    usageLoading.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [settings] = await Promise.all([api.getSmsTemplates(), loadUsage()])
    items.value = settings.items || []
    systemMessages.value = settings.system_messages || []
    cardPaymentUrl.value = settings.card_payment_url || ''
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
    const data = await api.updateSmsTemplates(
      items.value.map(item => ({
        template_type: item.template_type,
        payment_method: item.payment_method,
        body: item.body,
        is_active: item.is_active,
      })),
      cardPaymentUrl.value,
    )
    items.value = data.items || []
    systemMessages.value = data.system_messages || []
    cardPaymentUrl.value = data.card_payment_url || ''
    success.value = 'カード決済URLを保存しました'
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
    <template #title>SMS・カード決済設定</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>
    <div v-if="!isManager" class="alert alert-warning small">
      閲覧のみ可能です。カード決済URLの変更はマネージャーのみ行えます。
    </div>

    <div v-if="loading" class="text-center py-5">
      <span class="spinner-border text-primary"></span>
    </div>

    <template v-else>
      <div class="card mb-3">
        <div class="card-header d-flex align-items-center justify-content-between gap-2">
          <strong><i class="ti ti-chart-bar"></i> SMS送信数</strong>
          <input
            v-model="usageMonth"
            type="month"
            class="form-control form-control-sm month-input"
            :disabled="usageLoading"
            @change="loadUsage"
          />
        </div>
        <div v-if="usage" class="card-body">
          <div class="d-flex justify-content-between align-items-end gap-3 mb-2">
            <div>
              <div class="display-6 fw-bold">{{ usage.used_segments }}<span class="fs-6 ms-1">通分</span></div>
              <div class="text-muted small">
                現在の料金枠：{{ usage.current_block_limit }}通分まで
                <span v-if="usage.remaining_in_block > 0">（残り{{ usage.remaining_in_block }}通分）</span>
              </div>
            </div>
            <div class="text-end">
              <div class="text-muted small">当月の料金</div>
              <div class="fs-4 fw-bold">{{ yen(usage.billed_price) }}</div>
              <span v-if="usage.billing_exempt" class="badge text-bg-secondary">テスト店舗・課金対象外</span>
            </div>
          </div>
          <div class="progress mb-3" role="progressbar" :aria-valuenow="usagePercent" aria-valuemin="0" aria-valuemax="100">
            <div class="progress-bar" :style="{ width: `${usagePercent}%` }"></div>
          </div>
          <div class="pricing-note small">
            <strong>月額{{ yen(usage.base_monthly_price) }}に200通分を含みます。</strong>
            201通分目からは100通分ごとに{{ yen(usage.extra_block_price) }}が加算されます。
          </div>
          <p class="small text-muted mb-0 mt-2">
            表示上は「通分」です。SMS本文が長く2セグメントになった場合は2通分として数えます。
            キャスト向け通知や、設定不足で送信されなかったSMSは含みません。
          </p>
        </div>
      </div>

      <div class="card mb-3">
        <div class="card-header"><strong><i class="ti ti-credit-card"></i> 店舗のカード決済URL</strong></div>
        <div class="card-body">
          <input
            v-model.trim="cardPaymentUrl"
            type="url"
            class="form-control"
            placeholder="https://..."
            :disabled="!isManager"
          />
          <p class="form-text mb-0">
            カード予約のゲストページから、この店舗が契約している外部決済画面を別タブで開きます。
            Roominkは決済結果を自動判定しません。
          </p>
        </div>
      </div>

      <div class="alert alert-info small">
        <strong>SMSは短い通知だけに固定されています。</strong><br>
        現金・PayPay予約は予約確定時の1通、カード予約は仮予約時と店舗での決済確認後の計2通です。
        詳細、決済ボタン、確定後の住所はすべて同じ予約ページに表示します。
      </div>

      <div v-for="message in systemMessages" :key="message.key" class="card mb-3">
        <div class="card-header d-flex justify-content-between align-items-center gap-2">
          <strong>{{ message.label }}</strong>
          <span class="badge" :class="message.segment_count === 1 ? 'text-bg-success' : 'text-bg-warning'">
            {{ message.segment_count }}通分
          </span>
        </div>
        <div class="card-body">
          <pre class="message-body mb-2">{{ message.body }}</pre>
          <div class="small text-muted">{{ message.encoding }}／本番短縮URLを含むサンプル</div>
        </div>
      </div>

      <button
        v-if="isManager"
        class="btn btn-primary w-100 mb-4"
        :disabled="saving"
        @click="onSave"
      >
        <i class="ti ti-device-floppy"></i> {{ saving ? '保存中...' : 'カード決済URLを保存' }}
      </button>
    </template>
  </LayoutOperator>
</template>

<style scoped>
.month-input {
  width: 145px;
}
.pricing-note {
  padding: 12px;
  border-radius: 8px;
  background: #f6f8fb;
}
.message-body {
  padding: 14px;
  border: 1px solid #e3e6ea;
  border-radius: 8px;
  background: #f8f9fa;
  white-space: pre-wrap;
  font: inherit;
}
</style>
