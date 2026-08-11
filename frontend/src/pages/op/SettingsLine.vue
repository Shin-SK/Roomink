<script setup>
import { ref, onMounted, computed } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref('')
const copied = ref('')

const form = ref({
  line_is_enabled: false,
  line_add_friend_url: '',
  line_channel_secret: '',
  line_channel_access_token: '',
  line_morning_enabled: true,
  line_morning_time: '09:00',
  line_two_hours_enabled: true,
  line_fifteen_minutes_enabled: true,
  line_shift_end_alert_enabled: false,
})
const webhookUrl = ref('')
const operationsLinked = ref(false)
const operationsRecipientType = ref('')
const operationsLinkCode = ref('')

const isManager = computed(() => getAuthRole() === 'manager')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getLineSettings()
    form.value.line_is_enabled = data.line_is_enabled
    form.value.line_add_friend_url = data.line_add_friend_url
    form.value.line_channel_secret = data.line_channel_secret
    form.value.line_channel_access_token = data.line_channel_access_token
    form.value.line_morning_enabled = data.line_morning_enabled
    form.value.line_morning_time = data.line_morning_time
    form.value.line_two_hours_enabled = data.line_two_hours_enabled
    form.value.line_fifteen_minutes_enabled = data.line_fifteen_minutes_enabled
    form.value.line_shift_end_alert_enabled = data.line_shift_end_alert_enabled
    webhookUrl.value = data.line_webhook_url
    operationsLinked.value = data.line_operations_linked
    operationsRecipientType.value = data.line_operations_recipient_type
    operationsLinkCode.value = data.line_operations_link_code
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function unlinkOperations() {
  if (!window.confirm('現在の運営通知先を解除しますか？')) return
  saving.value = true
  error.value = ''
  try {
    const data = await api.updateLineSettings({ line_operations_unlink: true })
    operationsLinked.value = data.line_operations_linked
    operationsRecipientType.value = data.line_operations_recipient_type
    operationsLinkCode.value = data.line_operations_link_code
    form.value.line_shift_end_alert_enabled = data.line_shift_end_alert_enabled
    success.value = '運営通知先を解除しました'
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

async function regenerateOperationsCode() {
  saving.value = true
  error.value = ''
  try {
    const data = await api.updateLineSettings({ line_operations_regenerate_code: true })
    operationsLinkCode.value = data.line_operations_link_code
    success.value = '連携コードを再発行しました'
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

const operationsRecipientLabel = computed(() => ({
  user: '個人トーク',
  group: 'グループ',
  room: '複数人トーク',
}[operationsRecipientType.value] || '登録済みトーク'))

async function onSave() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    await api.updateLineSettings(form.value)
    success.value = '保存しました'
    setTimeout(() => { success.value = '' }, 3000)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

function copyToClipboard(text, label) {
  navigator.clipboard.writeText(text)
  copied.value = label
  setTimeout(() => { copied.value = '' }, 2000)
}

onMounted(load)
</script>

<template>
  <LayoutOperator>
    <template #title>LINE連携設定</template>

    <router-link to="/op/settings" class="btn btn-sm btn-outline-secondary mb-3">
      <i class="ti ti-arrow-left"></i> 設定に戻る
    </router-link>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-secondary"></div>
    </div>

    <template v-else-if="!isManager">
      <div class="alert alert-warning">この設定はマネージャーのみ編集できます。</div>
    </template>

    <template v-else>
      <!-- LINE連携 有効/無効 + Webhook URL -->
      <div class="card mb-4">
        <div class="card-body">
          <div class="mb-3">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" id="lineEnabled" v-model="form.line_is_enabled">
              <label class="form-check-label fw-bold" for="lineEnabled">LINE連携を有効にする</label>
            </div>
            <div class="form-text">通常はONのままで問題ありません</div>
          </div>

          <div>
            <label class="form-label fw-bold">Webhook URL（LINE Developers に貼り付け）</label>
            <div class="input-group">
              <input type="text" class="form-control bg-light" :value="webhookUrl" readonly>
              <button class="btn btn-outline-secondary" type="button" @click="copyToClipboard(webhookUrl, 'webhook')">
                <i class="ti" :class="copied === 'webhook' ? 'ti-check' : 'ti-copy'"></i>
                {{ copied === 'webhook' ? 'コピー済' : 'コピー' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 通知設定 -->
      <div class="card mb-4">
        <div class="card-body">
          <h6 class="card-title mb-3"><i class="ti ti-bell"></i> 通知設定</h6>

          <div class="mb-3">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" id="morningEnabled" v-model="form.line_morning_enabled">
              <label class="form-check-label" for="morningEnabled">朝通知を送信する</label>
            </div>
            <div v-if="form.line_morning_enabled" class="mt-2 ms-4">
              <label class="form-label small">送信時刻</label>
              <input type="time" class="form-control form-control-sm" style="max-width: 140px" v-model="form.line_morning_time">
            </div>
          </div>

          <div class="mb-3">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" id="twoHoursEnabled" v-model="form.line_two_hours_enabled">
              <label class="form-check-label" for="twoHoursEnabled">出勤2時間前通知を送信する</label>
            </div>
          </div>

          <div>
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" id="fifteenMinEnabled" v-model="form.line_fifteen_minutes_enabled">
              <label class="form-check-label" for="fifteenMinEnabled">出勤15分前通知を送信する</label>
            </div>
          </div>

          <hr>

          <div class="form-check form-switch">
            <input
              class="form-check-input"
              type="checkbox"
              id="shiftEndAlertEnabled"
              v-model="form.line_shift_end_alert_enabled"
              :disabled="!operationsLinked"
            >
            <label class="form-check-label" for="shiftEndAlertEnabled">シフト終了70分前の受付終了確認を運営へ送信する</label>
          </div>
          <div class="form-text">
            その先に有効な予約がない場合だけ、登録済みの運営トークへ送信します。
          </div>
        </div>
      </div>

      <!-- 運営通知先 -->
      <div class="card mb-4">
        <div class="card-body">
          <h6 class="card-title mb-3"><i class="ti ti-users"></i> 運営通知先</h6>

          <div v-if="operationsLinked" class="alert alert-success py-2">
            <i class="ti ti-circle-check"></i>
            {{ operationsRecipientLabel }}を通知先として登録済みです。
          </div>
          <div v-else class="alert alert-warning py-2">
            運営通知先はまだ登録されていません。
          </div>

          <template v-if="!operationsLinked">
            <p class="small mb-2">通知を受け取りたい個人トークまたはグループで、LINE公式アカウントへ次のコードを送ってください。</p>
            <div class="input-group mb-2" style="max-width: 360px">
              <input type="text" class="form-control fw-bold" :value="operationsLinkCode" readonly>
              <button class="btn btn-outline-secondary" type="button" @click="copyToClipboard(operationsLinkCode, 'operations')">
                <i class="ti" :class="copied === 'operations' ? 'ti-check' : 'ti-copy'"></i>
                {{ copied === 'operations' ? 'コピー済' : 'コピー' }}
              </button>
            </div>
            <div class="d-flex flex-wrap gap-2">
              <button class="btn btn-sm btn-outline-primary" type="button" :disabled="loading" @click="load">
                連携状況を更新
              </button>
              <button class="btn btn-sm btn-outline-secondary" type="button" :disabled="saving" @click="regenerateOperationsCode">
                コードを再発行
              </button>
            </div>
          </template>
          <button v-else class="btn btn-sm btn-outline-danger" type="button" :disabled="saving" @click="unlinkOperations">
            運営通知先を解除
          </button>
        </div>
      </div>

      <!-- 設定手順ガイド -->
      <div class="card mb-4">
        <div class="card-body">
          <h6 class="card-title mb-3"><i class="ti ti-info-circle"></i> 設定手順</h6>
          <ol class="mb-0 small">
            <li class="mb-1"><a href="https://developers.line.biz/console/" target="_blank" rel="noopener">LINE Developers</a> でプロバイダー &gt; チャネルを作成（Messaging API）</li>
            <li class="mb-1">チャネルの「Messaging API設定」タブで Webhook URL に上記の URL を設定</li>
            <li class="mb-1">「チャネル基本設定」の Channel secret と「Messaging API設定」の Channel access token をコピー</li>
            <li class="mb-0">下の入力欄に貼り付けて「保存」</li>
          </ol>
        </div>
      </div>

      <!-- 設定フォーム -->
      <div class="card">
        <div class="card-body">

          <div class="mb-3">
            <label class="form-label fw-bold">友だち追加URL</label>
            <input type="url" class="form-control" v-model="form.line_add_friend_url" placeholder="https://line.me/R/ti/p/...">
            <div class="form-text">LINE公式アカウントの友だち追加リンク</div>
          </div>

          <div class="mb-3">
            <label class="form-label fw-bold">Channel secret</label>
            <div class="input-group">
              <input type="password" class="form-control" v-model="form.line_channel_secret" placeholder="Channel secret を入力">
              <button class="btn btn-outline-secondary" type="button" @click="copyToClipboard(form.line_channel_secret, 'secret')">
                <i class="ti" :class="copied === 'secret' ? 'ti-check' : 'ti-copy'"></i>
              </button>
            </div>
          </div>

          <div class="mb-3">
            <label class="form-label fw-bold">Channel access token</label>
            <div class="input-group">
              <input type="password" class="form-control" v-model="form.line_channel_access_token" placeholder="Channel access token を入力">
              <button class="btn btn-outline-secondary" type="button" @click="copyToClipboard(form.line_channel_access_token, 'token')">
                <i class="ti" :class="copied === 'token' ? 'ti-check' : 'ti-copy'"></i>
              </button>
            </div>
          </div>

          <button class="btn btn-primary" :disabled="saving" @click="onSave">
            <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
            保存
          </button>
        </div>
      </div>
    </template>
  </LayoutOperator>
</template>
