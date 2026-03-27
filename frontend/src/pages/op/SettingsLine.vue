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
})
const webhookUrl = ref('')

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
    webhookUrl.value = location.origin + data.line_webhook_url
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
      <!-- 設定手順ガイド -->
      <div class="card mb-4">
        <div class="card-body">
          <h6 class="card-title mb-3"><i class="ti ti-info-circle"></i> 設定手順</h6>
          <ol class="mb-0 small">
            <li class="mb-1"><a href="https://developers.line.biz/console/" target="_blank" rel="noopener">LINE Developers</a> でプロバイダー &gt; チャネルを作成（Messaging API）</li>
            <li class="mb-1">チャネルの「Messaging API設定」タブで Webhook URL に下記の URL を設定</li>
            <li class="mb-1">「チャネル基本設定」の Channel secret と「Messaging API設定」の Channel access token をコピー</li>
            <li class="mb-0">下の入力欄に貼り付けて「保存」</li>
          </ol>
        </div>
      </div>

      <!-- Webhook URL (読み取り専用) -->
      <div class="card mb-4">
        <div class="card-body">
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

      <!-- 設定フォーム -->
      <div class="card">
        <div class="card-body">
          <div class="mb-3">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox" id="lineEnabled" v-model="form.line_is_enabled">
              <label class="form-check-label fw-bold" for="lineEnabled">LINE連携を有効にする</label>
            </div>
          </div>

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
