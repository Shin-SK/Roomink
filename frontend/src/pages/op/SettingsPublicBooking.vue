<script setup>
import { onMounted, ref } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const saving = ref(false)
const copied = ref(false)
const error = ref('')
const success = ref('')
const storeName = ref('')
const bookingUrl = ref('')
const notice = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getPublicBookingSettings()
    storeName.value = data.store_name || ''
    bookingUrl.value = data.public_booking_url || ''
    notice.value = data.public_booking_notice || ''
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    const data = await api.updatePublicBookingSettings({ public_booking_notice: notice.value })
    notice.value = data.public_booking_notice || ''
    success.value = '保存しました'
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

async function copyUrl() {
  await navigator.clipboard.writeText(bookingUrl.value)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

onMounted(load)
</script>

<template>
  <LayoutOperator>
    <template #title>Web予約設定</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>
    <div v-if="loading" class="text-center py-4"><span class="spinner-border text-primary"></span></div>

    <template v-else>
      <div class="card mb-3">
        <div class="card-header"><i class="ti ti-link"></i> {{ storeName }} 専用Web予約URL</div>
        <div class="card-body">
          <div class="input-group">
            <input :value="bookingUrl" class="form-control" readonly />
            <button class="btn btn-outline-primary" type="button" @click="copyUrl">
              <i class="ti ti-copy"></i> {{ copied ? 'コピー済み' : 'コピー' }}
            </button>
          </div>
          <div class="form-text">このURLでは店舗選択を表示せず、この店舗の予約情報だけを表示します。</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><i class="ti ti-alert-circle"></i> 予約前の注意事項</div>
        <div class="card-body">
          <textarea
            v-model="notice"
            class="form-control"
            rows="8"
            maxlength="3000"
            placeholder="例：&#10;●割引をご希望の場合は、備考欄へ割引名をご入力ください。&#10;&#10;●SMSが届かない場合は店舗へお問い合わせください。"
          ></textarea>
          <div class="d-flex justify-content-between form-text">
            <span>改行を保ったままWeb予約画面へ表示します。</span>
            <span>{{ notice.length }}/3000</span>
          </div>
          <div v-if="notice" class="booking-notice-preview mt-3">{{ notice }}</div>
          <button class="btn btn-primary w-100 mt-3" :disabled="saving" @click="save">
            <i class="ti ti-device-floppy"></i> {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </template>
  </LayoutOperator>
</template>

<style scoped>
.booking-notice-preview {
  white-space: pre-wrap;
  background: #fff7e6;
  border: 1px solid #f3d7a2;
  border-radius: 10px;
  padding: 14px;
  color: #594515;
  font-size: .9rem;
}
</style>
