<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const route = useRoute()
const loading = ref(false)
const error = ref('')
const statusFilter = ref('ESCALATED')
const conversations = ref([])
const selected = ref(null)
const replyText = ref('')
const sendingReply = ref(false)

const statusLabels = {
  OPEN: '対応中',
  ESCALATED: '運営確認待ち',
  RESOLVED: '解決済み',
}

const kindLabels = {
  SUPPORT: '操作・不具合',
  FEATURE: '機能要望',
}

function formatDate(value) {
  if (!value) return '-'
  return new Intl.DateTimeFormat('ja-JP', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

async function loadConversations() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getSupportConversations(statusFilter.value)
    conversations.value = data.results || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function openConversation(id) {
  try {
    selected.value = await api.getSupportConversation(id)
    replyText.value = selected.value.ai_reply_draft || ''
  } catch (e) {
    error.value = e.message
  }
}

async function sendReply() {
  if (!selected.value || replyText.value.trim().length < 2 || sendingReply.value) return
  sendingReply.value = true
  try {
    await api.replySupportConversation(selected.value.id, replyText.value.trim())
    selected.value = null
    replyText.value = ''
    await loadConversations()
  } catch (e) {
    error.value = e.message
  } finally {
    sendingReply.value = false
  }
}

async function cancelAutoReply() {
  if (!selected.value) return
  try {
    await api.cancelSupportAutoReply(selected.value.id)
    selected.value.auto_reply_scheduled_at = null
    selected.value.auto_reply_cancelled_at = new Date().toISOString()
  } catch (e) {
    error.value = e.message
  }
}

async function resolveSelected() {
  if (!selected.value) return
  try {
    await api.resolveSupportConversation(selected.value.id)
    selected.value = null
    await loadConversations()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(async () => {
  await loadConversations()
  const id = Number(route.query.conversation)
  if (id) await openConversation(id)
})
</script>

<template>
  <LayoutOperator>
    <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
      <div>
        <h2 class="h4 mb-1">問い合わせ一覧</h2>
        <p class="text-muted small mb-0">未解決の問い合わせと、ご意見・機能要望を店舗別に確認できます</p>
      </div>
      <select v-model="statusFilter" class="form-select form-select-sm support-filter" @change="loadConversations">
        <option value="ESCALATED">運営確認待ち</option>
        <option value="OPEN">対応中</option>
        <option value="RESOLVED">解決済み</option>
        <option value="">すべて</option>
      </select>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading" class="text-center py-5 text-muted">読み込み中…</div>
    <div v-else-if="conversations.length === 0" class="card border-0 shadow-sm">
      <div class="card-body text-center py-5 text-muted">該当する問い合わせはありません</div>
    </div>
    <div v-else class="support-list">
      <button
        v-for="item in conversations"
        :key="item.id"
        type="button"
        class="support-card"
        @click="openConversation(item.id)"
      >
        <div class="d-flex justify-content-between gap-2">
          <strong>#{{ item.id }} {{ kindLabels[item.kind] }}・{{ statusLabels[item.status] }}</strong>
          <span class="text-muted small">{{ formatDate(item.updated_at) }}</span>
        </div>
        <p>{{ item.latest_message }}</p>
        <div class="support-meta">
          <span><i class="ti ti-user"></i>{{ item.user_role }}</span>
          <span><i class="ti ti-window"></i>{{ item.page_path || '-' }}</span>
          <span v-if="item.slack_notified"><i class="ti ti-brand-slack"></i>Slack通知済み</span>
        </div>
      </button>
    </div>

    <div v-if="selected" class="support-modal" @click.self="selected = null">
      <section class="support-detail">
        <header>
          <div>
            <strong>{{ kindLabels[selected.kind] }} #{{ selected.id }}</strong>
            <small>{{ selected.page_path || '画面情報なし' }}</small>
          </div>
          <button type="button" class="btn-close" @click="selected = null"></button>
        </header>
        <div class="support-thread">
          <div
            v-for="message in selected.messages"
            :key="message.id"
            class="thread-message"
            :class="message.role === 'USER' ? 'is-user' : 'is-assistant'"
          >
            <span>{{ message.role === 'USER' ? '利用者' : 'Roominkサポート' }}</span>
            <p>{{ message.content }}</p>
          </div>
        </div>
        <div v-if="selected.status !== 'RESOLVED'" class="support-reply">
          <div v-if="selected.auto_reply_scheduled_at" class="auto-reply-notice">
            <span><i class="ti ti-clock"></i>{{ formatDate(selected.auto_reply_scheduled_at) }}に自動返信予定</span>
            <button type="button" @click="cancelAutoReply">自動返信を停止</button>
          </div>
          <label for="support-reply-text">利用者への返信</label>
          <textarea id="support-reply-text" v-model="replyText" rows="5" maxlength="2000" placeholder="返信内容を入力してください"></textarea>
          <small v-if="selected.ai_reply_draft">AI返信案が入力されています。確認・修正して送信できます。</small>
        </div>
        <footer>
          <router-link v-if="selected.page_path" :to="selected.page_path" class="btn btn-outline-primary btn-sm">
            該当画面を開く
          </router-link>
          <button
            v-if="selected.status !== 'RESOLVED'"
            type="button"
            class="btn btn-primary btn-sm"
            :disabled="sendingReply || replyText.trim().length < 2"
            @click="sendReply"
          >{{ sendingReply ? '送信中…' : '返信して解決済みにする' }}</button>
          <button
            v-if="selected.status !== 'RESOLVED'"
            type="button"
            class="btn btn-outline-secondary btn-sm"
            @click="resolveSelected"
          >返信せず対応済みにする</button>
        </footer>
      </section>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.support-filter { width: 165px; }
.support-list { display: grid; gap: 10px; }
.support-card { width: 100%; padding: 14px 16px; border: 1px solid #dfe9e7; border-radius: 12px; text-align: left; background: #fff; box-shadow: 0 3px 12px rgba(30, 65, 60, .05); }
.support-card p { margin: 8px 0; color: #394d4a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.support-meta { display: flex; flex-wrap: wrap; gap: 10px; color: #71817f; font-size: 11px; }
.support-meta span { display: flex; align-items: center; gap: 3px; }
.support-modal { position: fixed; inset: 0; z-index: 1200; display: grid; place-items: center; padding: 15px; background: rgba(14, 32, 30, .46); }
.support-detail { width: min(650px, 100%); max-height: 85vh; display: flex; flex-direction: column; overflow: hidden; border-radius: 15px; background: #fff; }
.support-detail header, .support-detail footer { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 14px 16px; border-bottom: 1px solid #e5eceb; }
.support-detail header div { display: flex; flex-direction: column; }
.support-detail header small { color: #7b8987; }
.support-detail footer { justify-content: flex-end; border-top: 1px solid #e5eceb; border-bottom: 0; }
.support-thread { overflow-y: auto; padding: 15px; background: #f6f9f8; }
.support-reply { padding: 12px 16px; border-top: 1px solid #e5eceb; }
.support-reply label { display: block; margin-bottom: 5px; font-size: 12px; font-weight: 700; }
.support-reply textarea { width: 100%; resize: vertical; border: 1px solid #cad9d7; border-radius: 9px; padding: 8px 10px; font-size: 12px; }
.support-reply small { display: block; color: #748481; font-size: 10px; }
.auto-reply-notice { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; padding: 8px 10px; border-radius: 8px; color: #704b00; background: #fff4d6; font-size: 11px; }
.auto-reply-notice button { border: 1px solid #c9972f; border-radius: 7px; padding: 4px 6px; color: #704b00; background: #fff; }
.thread-message { margin-bottom: 12px; }
.thread-message span { display: block; margin-bottom: 3px; color: #758582; font-size: 10px; }
.thread-message p { width: fit-content; max-width: 88%; margin: 0; padding: 9px 11px; border-radius: 11px; background: #fff; white-space: pre-wrap; }
.thread-message.is-user { display: flex; flex-direction: column; align-items: flex-end; }
.thread-message.is-user p { color: #fff; background: var(--rk-primary, #279d91); }
</style>
