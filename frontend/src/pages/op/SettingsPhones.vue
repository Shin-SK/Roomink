<script setup>
import { ref, onMounted } from 'vue'
import QRCode from 'qrcode'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const items = ref([])

const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

const sipLoading = ref(true)
const sipSaving = ref(false)
const sipIssuing = ref(false)
const sipError = ref('')
const sipConfigured = ref(false)
const sipForm = ref({
  sip_username: '',
  sip_password: '',
  sip_domain: 'roomink-reception.sip.twilio.com',
})
const provisioningUrl = ref('')
const provisioningExpiresAt = ref('')
const qrDataUrl = ref('')
const copyMessage = ref('')

function emptyForm() {
  return { phone: '', source_phone: '', label: '', memo: '', is_active: true }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getStorePhones()
    items.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadSipSettings() {
  sipLoading.value = true
  sipError.value = ''
  try {
    const data = await api.getSipProvisioningSettings()
    sipForm.value.sip_username = data.sip_username || ''
    sipForm.value.sip_password = ''
    sipForm.value.sip_domain = data.sip_domain || 'roomink-reception.sip.twilio.com'
    sipConfigured.value = Boolean(data.configured)
  } catch (e) {
    sipError.value = e.message
  } finally {
    sipLoading.value = false
  }
}

onMounted(() => {
  load()
  loadSipSettings()
})

async function saveSipSettings() {
  sipSaving.value = true
  sipError.value = ''
  provisioningUrl.value = ''
  qrDataUrl.value = ''
  try {
    const payload = {
      sip_username: sipForm.value.sip_username,
      sip_domain: sipForm.value.sip_domain,
    }
    if (sipForm.value.sip_password) payload.sip_password = sipForm.value.sip_password
    const data = await api.updateSipProvisioningSettings(payload)
    sipConfigured.value = Boolean(data.configured)
    sipForm.value.sip_password = ''
  } catch (e) {
    sipError.value = e.message
  } finally {
    sipSaving.value = false
  }
}

async function issueProvisioningQr() {
  sipIssuing.value = true
  sipError.value = ''
  copyMessage.value = ''
  try {
    const data = await api.issueSipProvisioningLink()
    provisioningUrl.value = data.provisioning_url
    provisioningExpiresAt.value = data.expires_at
    qrDataUrl.value = await QRCode.toDataURL(data.provisioning_url, {
      errorCorrectionLevel: 'M',
      margin: 2,
      width: 320,
    })
  } catch (e) {
    sipError.value = e.message
  } finally {
    sipIssuing.value = false
  }
}

async function copyProvisioningLink() {
  try {
    await navigator.clipboard.writeText(provisioningUrl.value)
    copyMessage.value = '設定リンクをコピーしました'
  } catch {
    copyMessage.value = 'コピーできませんでした。リンクを長押ししてください。'
  }
}

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(it) {
  editingId.value = it.id
  form.value = {
    phone: it.phone,
    source_phone: it.source_phone || '',
    label: it.label || '',
    memo: it.memo || '',
    is_active: it.is_active,
  }
  formError.value = ''
  showForm.value = true
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const payload = {
      phone: form.value.phone,
      source_phone: form.value.source_phone,
      label: form.value.label,
      memo: form.value.memo,
      is_active: form.value.is_active,
    }
    if (editingId.value) {
      await api.updateStorePhone(editingId.value, payload)
    } else {
      await api.createStorePhone(payload)
    }
    showForm.value = false
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function toggleActive(it) {
  error.value = ''
  try {
    await api.updateStorePhone(it.id, { is_active: !it.is_active })
    await load()
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <LayoutOperator>
    <template #title>CTI電話番号設定</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header">
        <i class="ti ti-qrcode"></i> 受付電話アプリ設定
      </div>
      <div class="card-body">
        <div v-if="sipError" class="alert alert-danger">{{ sipError }}</div>
        <div v-if="sipLoading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>
        <template v-else>
          <p class="text-muted small">
            最初に一度だけSIP IDとパスワードを保存します。受付担当者にはQRコードを読み取ってもらうだけです。
          </p>
          <div class="row g-3">
            <div class="col-md-6">
              <label class="form-label">SIP ID</label>
              <input
                v-model="sipForm.sip_username"
                type="text"
                class="form-control"
                autocomplete="off"
                placeholder="roomink-reception"
              />
            </div>
            <div class="col-md-6">
              <label class="form-label">SIPパスワード</label>
              <input
                v-model="sipForm.sip_password"
                type="password"
                class="form-control"
                autocomplete="new-password"
                :placeholder="sipConfigured ? '変更しない場合は空欄' : '12文字以上'"
              />
            </div>
          </div>
          <details class="mt-3">
            <summary class="small text-muted">接続先の詳細設定</summary>
            <div class="mt-2">
              <label class="form-label">Twilio SIP Domain</label>
              <input v-model="sipForm.sip_domain" type="text" class="form-control" />
            </div>
          </details>
          <div class="d-flex flex-wrap gap-2 mt-3">
            <button
              class="btn btn-outline-primary"
              :disabled="sipSaving || !sipForm.sip_username.trim() || !sipForm.sip_domain.trim()"
              @click="saveSipSettings"
            >
              {{ sipSaving ? '保存中...' : 'SIP設定を保存' }}
            </button>
            <button
              class="btn btn-primary"
              :disabled="sipIssuing || !sipConfigured"
              @click="issueProvisioningQr"
            >
              <i class="ti ti-qrcode text-white"></i>
              {{ sipIssuing ? '発行中...' : '設定用QRを発行' }}
            </button>
          </div>

          <div v-if="qrDataUrl" class="provisioning-card mt-4 text-center">
            <h6>Linphoneで読み取ってください</h6>
            <ol class="text-start small mb-3">
              <li>Linphoneを開く</li>
              <li>「QRコードをスキャン」を選ぶ</li>
              <li>下のQRコードを読み取る</li>
            </ol>
            <img :src="qrDataUrl" class="provisioning-qr" alt="Linphone設定用QRコード" />
            <div class="small text-danger mt-2">10分以内・1台のみ利用できます</div>
            <button class="btn btn-outline-secondary btn-sm mt-2" @click="copyProvisioningLink">
              設定リンクをコピー
            </button>
            <div v-if="copyMessage" class="small text-muted mt-1">{{ copyMessage }}</div>
            <div v-if="provisioningExpiresAt" class="small text-muted mt-1">
              発行日時から10分で失効します
            </div>
          </div>
        </template>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-phone"></i> CTI電話番号一覧</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus text-white"></i> CTI電話番号を追加
        </button>
      </div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!items.length" class="text-muted text-center py-3">
          登録されたCTI電話番号はありません
        </div>

        <table v-else class="table table-hover mb-0 align-middle">
          <thead>
            <tr>
              <th>CTI着信番号</th>
              <th>店舗の既存受付番号</th>
              <th>表示名</th>
              <th>メモ</th>
              <th style="width: 80px;">有効</th>
              <th style="width: 140px;"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in items" :key="it.id">
              <td>{{ it.phone }}</td>
              <td>{{ it.source_phone || '—' }}</td>
              <td>{{ it.label || '—' }}</td>
              <td>{{ it.memo || '—' }}</td>
              <td>
                <span v-if="it.is_active" class="badge bg-success">有効</span>
                <span v-else class="badge bg-secondary">無効</span>
              </td>
              <td class="text-nowrap">
                <button class="btn btn-outline-secondary btn-sm me-1" @click="openEdit(it)">
                  <i class="ti ti-edit"></i> 編集
                </button>
                <button class="btn btn-sm" :class="it.is_active ? 'btn-outline-danger' : 'btn-outline-success'" @click="toggleActive(it)">
                  {{ it.is_active ? '無効化' : '有効化' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Form modal -->
    <div v-if="showForm" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showForm = false">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editingId ? 'CTI電話番号を編集' : 'CTI電話番号を追加' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

            <div class="mb-3">
              <label class="form-label">CTI着信番号 <span class="text-danger">*</span></label>
              <input v-model="form.phone" type="text" class="form-control" placeholder="Twilioで取得した番号" />
            </div>
            <div class="mb-3">
              <label class="form-label">店舗の既存受付番号</label>
              <input v-model="form.source_phone" type="text" class="form-control" placeholder="任意（転送元の記録用）" />
            </div>
            <div class="mb-3">
              <label class="form-label">表示名</label>
              <input v-model="form.label" type="text" class="form-control" />
            </div>
            <div class="mb-3">
              <label class="form-label">メモ</label>
              <textarea v-model="form.memo" class="form-control" rows="2"></textarea>
            </div>
            <div class="mb-3 form-check">
              <input v-model="form.is_active" type="checkbox" class="form-check-input" id="phoneIsActive" />
              <label class="form-check-label" for="phoneIsActive">有効</label>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showForm = false">キャンセル</button>
            <button class="btn btn-primary" :disabled="saving || !form.phone.trim()" @click="onSave">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.provisioning-card {
  max-width: 420px;
  padding: 1rem;
  border: 1px solid #dce8e6;
  border-radius: 12px;
  background: #f8fcfb;
}
.provisioning-qr {
  display: block;
  width: min(100%, 320px);
  height: auto;
  margin: 0 auto;
  border-radius: 8px;
  background: #fff;
}
</style>
