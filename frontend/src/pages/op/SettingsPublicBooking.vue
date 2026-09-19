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
const storeSlug = ref('')
const contactPhone = ref('')
const contactPhoneMemo = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getPublicBookingSettings()
    storeName.value = data.store_name || ''
    bookingUrl.value = data.public_booking_url || ''
    notice.value = data.public_booking_notice || ''
    storeSlug.value = data.store_slug || ''
    contactPhone.value = data.guest_contact_phone || ''
    contactPhoneMemo.value = data.guest_contact_phone_memo || ''
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
    const data = await api.updatePublicBookingSettings({
      public_booking_notice: notice.value,
      store_slug: storeSlug.value,
      guest_contact_phone: contactPhone.value,
      guest_contact_phone_memo: contactPhoneMemo.value,
    })
    notice.value = data.public_booking_notice || ''
    storeSlug.value = data.store_slug || ''
    bookingUrl.value = data.public_booking_url || ''
    contactPhone.value = data.guest_contact_phone || ''
    contactPhoneMemo.value = data.guest_contact_phone_memo || ''
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
          <label class="form-label mt-3">URL識別子</label>
          <div class="input-group">
            <span class="input-group-text">/s/</span>
            <input
              v-model.trim="storeSlug"
              class="form-control"
              maxlength="80"
              pattern="[a-z0-9-]+"
              placeholder="rs-spa"
            />
          </div>
          <div class="alert alert-warning py-2 px-3 mt-2 mb-0 small">
            変更すると今後発行するURLが変わります。配布済みの古いURLは新しいURLへ引き継がれますが、通常は変更しないでください。
          </div>
        </div>
      </div>

      <div class="card mb-3">
        <div class="card-header"><i class="ti ti-phone"></i> お客様向け問い合わせ番号</div>
        <div class="card-body">
          <label class="form-label">予約確認ページに表示する電話番号</label>
          <input
            v-model.trim="contactPhone"
            class="form-control"
            type="tel"
            maxlength="32"
            inputmode="tel"
            placeholder="例：03-0000-0000"
          />
          <div class="form-text">
            この番号だけがお客様の予約確認ページに表示されます。CTIの内部番号は公開されません。
          </div>

          <label class="form-label mt-3">運営メモ（お客様には表示されません）</label>
          <textarea
            v-model="contactPhoneMemo"
            class="form-control"
            rows="3"
            maxlength="500"
            placeholder="例：クラコール開通後、本番の受付番号へ差し替える"
          ></textarea>
          <div class="d-flex justify-content-between form-text">
            <span>番号の差し替え予定や確認事項を残せます。</span>
            <span>{{ contactPhoneMemo.length }}/500</span>
          </div>

          <div v-if="contactPhoneMemo" class="alert alert-warning py-2 px-3 mt-3 mb-0 small">
            <i class="ti ti-note"></i> {{ contactPhoneMemo }}
          </div>
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
        </div>
      </div>

      <button class="btn btn-primary w-100 mt-3" :disabled="saving" @click="save">
        <i class="ti ti-device-floppy"></i> {{ saving ? '保存中...' : '設定を保存' }}
      </button>
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
