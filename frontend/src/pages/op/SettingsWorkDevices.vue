<script setup>
import { computed, onMounted, ref } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const message = ref('')
const data = ref({ stores: [], devices: [] })
const approval = ref({ code: '', store_ids: [] })
const routes = ref({ stores: [], work_available: false })

const allStoresSelected = computed(() => (
  data.value.stores.length > 0 && approval.value.store_ids.length === data.value.stores.length
))

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.getWorkDevices()
    routes.value = await api.getVoiceRoutes()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function normalizeCode() {
  approval.value.code = approval.value.code.toUpperCase().replace(/[^23456789A-HJ-NP-Z]/g, '').slice(0, 8)
}

async function changeReceiver(store) {
  const receiver = store.voice_receiver === 'work' ? 'groundwire' : 'work'
  if (!window.confirm(`「${store.name}」の次の着信から、${receiver === 'work' ? 'Roomink Work' : 'Groundwire'}で受けます。切り替えますか？`)) return
  saving.value = true; error.value = ''; message.value = ''
  try {
    const result = await api.setVoiceRoute(store.id, receiver)
    store.voice_receiver = result.voice_receiver
    message.value = '受信先を切り替えました。進行中の通話は変更されません。'
  } catch (e) { error.value = e.message }
  finally { saving.value = false }
}

function toggleAllStores() {
  approval.value.store_ids = allStoresSelected.value
    ? []
    : data.value.stores.map(store => store.id)
}

async function approve() {
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    const result = await api.approveWorkDevice(approval.value)
    message.value = `${result.detail}（${result.device_label}）`
    approval.value = { code: '', store_ids: [] }
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

const actionLabel = action => ({ pause: '受付を停止', resume: '受付を再開', revoke: '連携を解除' })[action]

async function setAction(device, action) {
  const label = actionLabel(action)
  const caution = action === 'revoke' ? '解除後は、この端末で再度連携操作が必要です。\n' : ''
  if (!window.confirm(`${caution}「${device.label}」の${label}を実行しますか？`)) return
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    const updated = await api.setWorkDeviceAction(device.id, action)
    const index = data.value.devices.findIndex(item => item.id === device.id)
    if (index >= 0) data.value.devices[index] = updated
    message.value = `「${device.label}」の${label}が完了しました。`
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

function formatDate(value) {
  if (!value) return 'まだ通信していません'
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

function statusClass(status) {
  return {
    active: 'text-bg-success',
    paused: 'text-bg-warning',
    revoked: 'text-bg-secondary',
  }[status] || 'text-bg-light'
}

onMounted(load)
</script>

<template>
  <LayoutOperator>
    <template #title>Roomink Work端末</template>

    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <div v-if="message" class="alert alert-success" role="status">{{ message }}</div>

    <div class="foundation-note mb-4">
      <i class="ti ti-info-circle"></i>
      <div>
        <strong>受信アプリ用の端末管理</strong>
        <p class="mb-0">店舗の受信先とRoomink Workの端末を管理します。Groundwireの接続は、受信先を切り替えても維持されます。</p>
      </div>
    </div>

    <section class="card mb-4" aria-labelledby="work-setup-title">
      <div class="card-body p-3 p-md-4">
        <h2 id="work-setup-title" class="h5">初期設定：Roomink Workを使い始める</h2>
        <div class="work-apps my-3">
          <div class="work-app"><img src="/app-icons/roomink-work.png" alt="Roomink Workのアプリアイコン" width="64" height="64"><div><strong>Roomink Work</strong><p class="small text-muted mb-0">これから使う受付アプリ</p></div></div>
          <div class="work-app"><img src="/app-icons/groundwire.jpg" alt="Groundwireのアプリアイコン" width="64" height="64"><div><strong>Groundwire</strong><p class="small text-muted mb-0">削除せず、予備として残すアプリ</p></div></div>
        </div>
        <p>最初の受信先はGroundwireです。Workへのログインや端末連携だけでは、店舗の受信先は変わりません。</p>
        <div class="alert alert-warning">
          <strong>Groundwireは削除せず、接続設定も残してください。</strong>
          <div class="small mt-1">Workで受けられないときに戻すために使います。長期間使わないと着信の登録が切れる場合があるため、切り戻す前にGroundwireを開き、接続状態を確認してください。</div>
        </div>
        <ol class="work-setup-steps">
          <li><strong>受付用iPhoneにWorkを入れる</strong><p>運営から案内されたリンクからインストールしてください。</p></li>
          <li><strong>ログイン・端末連携をする</strong><p>個人端末は実際に使う人のRoominkアカウントでログインし、受ける店舗を選びます。共用端末はアプリの連携コードを、この画面の「共用端末を連携」で管理者が承認します。</p></li>
          <li><strong>アプリで対象店舗の着信をONにする</strong><p>Workの「設定」で店舗名と着信ONを確認します。この端末のON/OFFと、店舗の受信先の切り替えは別の操作です。</p></li>
          <li><strong>管理者が店舗の受信先を切り替える</strong><p>下の「店舗の受信先」で、対象店舗の「Workに切り替える」を押します。管理権限のない方は、店舗の管理者へ依頼してください。</p></li>
          <li><strong>着信を確認して使用開始</strong><p>店舗番号に電話をかけ、Workの着信・双方の声・Roominkの着信表示と履歴を確認してください。不調な場合はGroundwireへ戻します。</p></li>
        </ol>
        <a class="btn btn-outline-primary" href="#work-receiver">店舗の受信先へ進む</a>
      </div>
    </section>

    <section id="work-receiver" class="card mb-4">
      <div class="card-body p-3 p-md-4">
        <h2 class="h5">店舗の受信先</h2>
        <p class="small text-muted">切り替えは次の着信から有効です。受信ONの有効なWork端末がない場合は既存のGroundwireへ接続します。端末が鳴らない・声が聞こえない場合は、ここでGroundwireへ戻してください。</p>
        <div v-for="store in routes.stores" :key="store.id" class="d-flex flex-wrap align-items-center gap-2 border-top py-3">
          <strong class="me-auto">{{ store.name }}</strong>
          <span>{{ store.voice_receiver === 'work' ? 'Roomink Work' : 'Groundwire' }}</span>
          <button class="btn btn-outline-primary btn-sm" :disabled="saving || (!routes.work_available && store.voice_receiver !== 'work')" @click="changeReceiver(store)">
            {{ store.voice_receiver === 'work' ? 'Groundwireに戻す' : 'Workに切り替える' }}
          </button>
        </div>
        <p v-if="!routes.work_available" class="small text-muted mb-0">Workへの切り替えは準備中です。Groundwireへの切り戻しは利用できます。</p>
      </div>
    </section>

    <section class="card mb-4" aria-labelledby="work-recovery-title">
      <div class="card-body p-3 p-md-4">
        <h2 id="work-recovery-title" class="h5">着信できないとき</h2>
        <p><strong>Workが鳴らない・声が聞こえない：</strong>Groundwireを開いて接続を確認し、上の対象店舗を「Groundwireに戻す」に切り替えてください。次の着信から有効です。進行中の通話は移動しません。</p>
        <p><strong>この設定画面を開けない・切り替えられない：</strong>運営へ連絡してください。この画面が使えない場合の復旧は、運営が電話経路側で対応します。</p>
        <p class="mb-0"><strong>電話サービス全体の障害：</strong>運営と連携し、元回線の転送を解除して元の電話で受けます。解除方法と受ける電話は、使用開始前に店舗ごとに確認します。</p>
      </div>
    </section>

    <section class="card approval-card mb-4">
      <div class="card-body p-3 p-md-4">
        <div class="section-heading">
          <span class="section-icon"><i class="ti ti-device-mobile-plus"></i></span>
          <div>
            <h2 class="h5 mb-1">共用端末を連携</h2>
            <p class="small text-muted mb-0">端末に表示された8文字のコードを入力してください。コードは発行から10分間有効です。</p>
          </div>
        </div>

        <form class="approval-form mt-4" @submit.prevent="approve">
          <div>
            <label for="link-code" class="form-label fw-semibold">連携コード</label>
            <input
              id="link-code"
              v-model="approval.code"
              class="form-control link-code"
              inputmode="text"
              autocomplete="one-time-code"
              maxlength="8"
              placeholder="ABCD2345"
              required
              @input="normalizeCode"
            >
          </div>

          <fieldset>
            <legend class="form-label fw-semibold mb-1">着信を受ける店舗</legend>
            <button type="button" class="btn btn-link btn-sm p-0 mb-2" @click="toggleAllStores">
              {{ allStoresSelected ? 'すべて解除' : 'すべて選択' }}
            </button>
            <div class="store-options">
              <label v-for="store in data.stores" :key="store.id" class="store-option">
                <input v-model="approval.store_ids" class="form-check-input" type="checkbox" :value="store.id">
                <span>{{ store.name }}</span>
              </label>
            </div>
          </fieldset>

          <div class="approval-action">
            <button
              class="btn btn-primary w-100"
              :disabled="saving || approval.code.length !== 8 || !approval.store_ids.length"
            >
              <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
              {{ saving ? '承認中...' : 'この端末を承認' }}
            </button>
          </div>
        </form>
      </div>
    </section>

    <section class="mb-4">
      <div class="d-flex align-items-center justify-content-between gap-2 mb-3">
        <div>
          <h2 class="h5 mb-1">連携済み端末</h2>
          <p class="small text-muted mb-0">受付停止はいつでも再開できます。連携解除は端末の認証情報も無効にします。</p>
        </div>
        <button class="btn btn-outline-secondary btn-sm flex-shrink-0" :disabled="loading" @click="load">
          <i class="ti ti-refresh"></i> 更新
        </button>
      </div>

      <div v-if="loading" class="text-center py-5"><div class="spinner-border text-primary"></div></div>
      <div v-else-if="!data.devices.length" class="empty-state">
        <i class="ti ti-device-mobile-off"></i>
        <p class="mb-1 fw-semibold">連携済みの端末はありません</p>
        <p class="small text-muted mb-0">端末側でコードを発行して、上のフォームから承認できます。</p>
      </div>
      <div v-else class="device-grid">
        <article v-for="device in data.devices" :key="device.id" class="device-card">
          <div class="device-card__top">
            <div class="device-mark"><i class="ti ti-device-mobile"></i></div>
            <div class="min-width-0">
              <h3 class="h6 text-break mb-1">{{ device.label }}</h3>
              <div class="small text-muted">{{ device.kind_label }}・{{ device.platform_label }}</div>
            </div>
            <span class="badge ms-auto" :class="statusClass(device.status)">{{ device.status_label }}</span>
          </div>

          <dl class="device-details">
            <div>
              <dt>{{ device.kind === 'personal' ? '利用者' : '承認者' }}</dt>
              <dd>{{ device.owner || device.approved_by || '—' }}</dd>
            </div>
            <div>
              <dt>最終通信</dt>
              <dd>{{ formatDate(device.last_seen_at) }}</dd>
            </div>
          </dl>

          <div class="store-chips">
            <span
              v-for="store in device.stores"
              :key="store.id"
              class="store-chip"
              :class="{ 'store-chip--off': !store.is_receiving || !store.is_entitled }"
            >
              <i class="ti" :class="store.is_receiving && store.is_entitled ? 'ti-phone-call' : 'ti-phone-off'"></i>
              {{ store.name }}
              <small v-if="!store.is_entitled">権限なし</small>
              <small v-else-if="!store.is_receiving">受付停止</small>
            </span>
          </div>

          <div v-if="device.status !== 'revoked'" class="device-actions">
            <button
              v-if="device.status === 'active'"
              class="btn btn-outline-warning btn-sm"
              :disabled="saving"
              @click="setAction(device, 'pause')"
            ><i class="ti ti-player-pause"></i> 受付を停止</button>
            <button
              v-else
              class="btn btn-outline-success btn-sm"
              :disabled="saving"
              @click="setAction(device, 'resume')"
            ><i class="ti ti-player-play"></i> 受付を再開</button>
            <button class="btn btn-outline-danger btn-sm" :disabled="saving" @click="setAction(device, 'revoke')">
              <i class="ti ti-unlink"></i> 連携を解除
            </button>
          </div>
          <p v-else class="small text-muted mt-3 mb-0"><i class="ti ti-lock"></i> この端末の認証情報は無効です。</p>
        </article>
      </div>
    </section>
  </LayoutOperator>
</template>

<style scoped>
.work-apps { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 1rem; }
.work-app { display: flex; align-items: center; gap: 1rem; padding: 1rem; border: 1px solid var(--bs-border-color); border-radius: .75rem; }
.work-app img { border-radius: 14px; border: 1px solid var(--bs-border-color); flex-shrink: 0; }
.work-setup-steps { padding-left: 1.5rem; }
.work-setup-steps li { padding-left: .25rem; margin-bottom: 1rem; }
.work-setup-steps p { margin: .35rem 0 0; color: var(--bs-secondary-color); line-height: 1.7; }
#work-receiver { scroll-margin-top: 5rem; }
.foundation-note {
  display: flex;
  gap: 0.8rem;
  padding: 1rem;
  border: 1px solid #bfe2dd;
  border-radius: 14px;
  background: #f0faf8;
  color: #265f58;
}
.foundation-note > i { margin-top: 0.15rem; font-size: 1.25rem; }
.foundation-note p { margin-top: 0.2rem; font-size: 0.86rem; color: #47756f; }
.approval-card { border: 0; box-shadow: 0 8px 28px rgba(24, 55, 51, 0.08); }
.section-heading { display: flex; align-items: center; gap: 0.85rem; }
.section-icon {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  border-radius: 12px;
  background: #e6f6f3;
  color: var(--rk-primary, #2a9d8f);
  font-size: 1.3rem;
}
.approval-form { display: grid; grid-template-columns: minmax(190px, 0.8fr) minmax(260px, 1.4fr) minmax(180px, 0.7fr); align-items: end; gap: 1.5rem; }
.link-code { text-transform: uppercase; letter-spacing: 0.16em; font-size: 1.15rem; font-weight: 700; }
.store-options { display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; }
.store-option { display: inline-flex; align-items: center; gap: 0.45rem; cursor: pointer; }
.device-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.device-card { padding: 1.15rem; border: 1px solid #e8eceb; border-radius: 16px; background: #fff; box-shadow: 0 4px 18px rgba(24, 55, 51, 0.05); }
.device-card__top { display: flex; align-items: center; gap: 0.75rem; }
.device-mark { display: grid; place-items: center; width: 40px; height: 40px; flex: 0 0 40px; border-radius: 12px; background: #f1f5f4; color: #47756f; font-size: 1.2rem; }
.min-width-0 { min-width: 0; }
.device-details { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; padding: 0.9rem 0; margin: 0.9rem 0; border-top: 1px solid #eef1f0; border-bottom: 1px solid #eef1f0; }
.device-details dt { color: #7a8683; font-size: 0.72rem; font-weight: 500; }
.device-details dd { margin: 0.15rem 0 0; font-size: 0.86rem; font-weight: 600; word-break: break-word; }
.store-chips { display: flex; flex-wrap: wrap; gap: 0.45rem; }
.store-chip { display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.35rem 0.55rem; border-radius: 999px; background: #e8f7f3; color: #287368; font-size: 0.76rem; font-weight: 600; }
.store-chip small { padding-left: 0.15rem; font-size: 0.66rem; }
.store-chip--off { background: #f1f2f2; color: #777f7d; }
.device-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem; }
.empty-state { padding: 3.5rem 1rem; border: 1px dashed #cfd8d6; border-radius: 16px; text-align: center; background: #fafcfb; }
.empty-state > i { display: block; margin-bottom: 0.75rem; color: #8ca19d; font-size: 2.2rem; }

@media (max-width: 991.98px) {
  .approval-form { grid-template-columns: 1fr 1.4fr; }
  .approval-action { grid-column: 1 / -1; }
}
@media (max-width: 767.98px) {
  .approval-form, .device-grid { grid-template-columns: 1fr; }
  .approval-action { grid-column: auto; }
  .device-card { padding: 1rem; }
}
@media (max-width: 420px) {
  .device-details { grid-template-columns: 1fr; }
  .device-actions .btn { flex: 1 1 auto; }
}
</style>
