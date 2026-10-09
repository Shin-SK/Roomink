<script setup>
import { computed, onMounted, ref } from 'vue'
import QRCode from 'qrcode'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const devices = ref([])
const configured = ref(false)
const deviceLabel = ref('')
const creating = ref(false)
const issuingId = ref(null)
const setupUrl = ref('')
const qrDataUrl = ref('')
const copied = ref('')

const activeDevices = computed(() => devices.value.filter(item => item.is_active))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const settings = await api.getSipProvisioningSettings()
    configured.value = Boolean(settings.configured)
    devices.value = await api.getSipReceptionDevices()
  } catch (e) {
    error.value = e.message || '初期設定を読み込めませんでした。'
  } finally {
    loading.value = false
  }
}

async function showSetup(data) {
  setupUrl.value = data.provisioning_url
  qrDataUrl.value = await QRCode.toDataURL(data.provisioning_url, {
    errorCorrectionLevel: 'M', margin: 2, width: 320,
  })
}

async function createDevice() {
  creating.value = true
  error.value = ''
  try {
    const data = await api.createSipReceptionDevice({ label: deviceLabel.value.trim() })
    deviceLabel.value = ''
    await showSetup(data)
    devices.value = await api.getSipReceptionDevices()
  } catch (e) {
    error.value = e.message || '設定ページを発行できませんでした。'
  } finally {
    creating.value = false
  }
}

async function issueSetup(device) {
  issuingId.value = device.id
  error.value = ''
  try {
    const data = await api.issueSipReceptionDeviceLink(device.id)
    await showSetup(data)
    devices.value = await api.getSipReceptionDevices()
  } catch (e) {
    error.value = e.message || '設定ページを発行できませんでした。'
  } finally {
    issuingId.value = null
  }
}

async function copySetupUrl() {
  try {
    await navigator.clipboard.writeText(setupUrl.value)
    copied.value = '設定ページのURLをコピーしました。'
  } catch {
    copied.value = 'コピーできませんでした。URLを長押ししてコピーしてください。'
  }
}

onMounted(load)
</script>

<template>
  <LayoutOperator>
    <template #title>初期設定</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div class="intro card mb-4">
      <div class="card-body">
        <span class="badge text-bg-primary mb-2">まずここから</span>
        <h2 class="h4">開業前の初期設定</h2>
        <p class="mb-0 text-muted">必要な設定を順番に進めます。受付電話は、端末へ設定値をコピーして実際に着信するところまで確認します。</p>
      </div>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading" class="text-center py-5"><div class="spinner-border text-primary"></div></div>

    <template v-else>
      <section class="card mb-4">
        <div class="card-body">
          <div class="step-heading">
            <span>1</span>
            <div><h2 class="h5 mb-1">着信アプリを設定する</h2><p class="small text-muted mb-0">受付用iPhoneにGroundwireを設定します。</p></div>
          </div>

          <div v-if="!configured" class="alert alert-warning mt-3 mb-0">
            この店舗の電話接続は、Roomink運営側でまだ準備中です。
          </div>
          <template v-else>
            <div v-if="!activeDevices.length" class="mt-3">
              <p class="small mb-2">まず、設定するiPhoneの名前を入力してください。</p>
              <div class="input-group">
                <input v-model="deviceLabel" class="form-control" maxlength="80" placeholder="例：フラッグシップ受付iPhone" @keyup.enter="createDevice">
                <button class="btn btn-primary" :disabled="creating || !deviceLabel.trim()" @click="createDevice">
                  {{ creating ? '発行中...' : '設定ページを発行' }}
                </button>
              </div>
            </div>
            <div v-else class="mt-3">
              <p class="small mb-2">設定する端末を選び、「設定ページを表示」を押してください。</p>
              <div v-for="device in activeDevices" :key="device.id" class="device-row">
                <div><strong>{{ device.label }}</strong><small>{{ device.provisioned_at ? '設定済み。再設定すると古い情報は使えなくなります。' : 'まだ設定を完了していません。' }}</small></div>
                <button class="btn btn-primary btn-sm" :disabled="issuingId === device.id" @click="issueSetup(device)">
                  {{ issuingId === device.id ? '発行中...' : '設定ページを表示' }}
                </button>
              </div>
            </div>
          </template>
        </div>
      </section>

      <section v-if="qrDataUrl" class="card setup-card mb-4">
        <div class="card-body text-center">
          <span class="badge text-bg-success mb-2">設定ページを発行しました</span>
          <h2 class="h5">このiPhoneでQRコードを読み取ってください</h2>
          <ol class="text-start small mx-auto instruction-list">
            <li>iPhone標準カメラでQRコードを読み取る</li>
            <li>開いたページの値を、Groundwireの各欄へコピーする</li>
            <li>保存後、Groundwireが接続済みになることを確認する</li>
          </ol>
          <img :src="qrDataUrl" class="qr" alt="Groundwire設定ページのQRコード">
          <p class="small text-danger mt-2 mb-2">このページは10分以内・1台だけ利用できます。</p>
          <button class="btn btn-outline-secondary btn-sm" @click="copySetupUrl">設定ページのURLをコピー</button>
          <p v-if="copied" class="small text-muted mt-2 mb-0">{{ copied }}</p>
        </div>
      </section>

      <section class="card">
        <div class="card-body">
          <div class="step-heading"><span>2</span><div><h2 class="h5 mb-1">実際に着信するか確認する</h2><p class="small text-muted mb-0">外部回線から受付番号へ電話し、着信・通話の両方を確認して完了です。</p></div></div>
        </div>
      </section>
    </template>
  </LayoutOperator>
</template>

<style scoped>
.step-heading,.device-row { display:flex; align-items:center; gap: .75rem; }
.step-heading > span { width: 2rem; height: 2rem; display:grid; place-items:center; border-radius:50%; background:#2A9D8F; color:#fff; font-weight:700; flex:0 0 auto; }
.device-row { justify-content:space-between; padding: .85rem 0; border-top:1px solid #eee; }
.device-row small { display:block; color:#6c757d; margin-top:.2rem; }
.setup-card { border: 2px solid #2A9D8F; }
.qr { width:min(100%, 280px); background:#fff; }
.instruction-list { max-width: 420px; line-height:1.8; }
@media (max-width: 576px) { .device-row { align-items:flex-start; } .device-row button { flex:0 0 auto; } }
</style>
