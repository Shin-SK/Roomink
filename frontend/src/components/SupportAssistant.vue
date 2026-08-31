<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'

const route = useRoute()
const currentUser = ref(null)
const open = ref(false)
const loading = ref(false)
const error = ref('')
const input = ref('')
const conversationId = ref(null)
const conversationKind = ref('SUPPORT')
const messages = ref([])
const feedbackSent = ref(false)
const scrollArea = ref(null)
const panelView = ref('chat')
const showUnresolvedForm = ref(false)
const unresolvedReason = ref('')
const hasRetryAnswer = ref(false)
const sendingInquiry = ref(false)
const featureRequest = ref('')
const sendingFeatureRequest = ref(false)
const historyLoading = ref(false)
const historyItems = ref([])

const isSupportedRoute = computed(() => {
  if (!currentUser.value || route.meta.public) return false
  return route.path.startsWith('/op/') ||
    route.path.startsWith('/cast/') ||
    route.path.startsWith('/cu/') ||
    (route.path.startsWith('/s/') && route.path.includes('/mypage'))
})

const suggestions = computed(() => {
  const role = currentUser.value?.role
  if (role === 'cast') return ['今日の予約はどこで確認できますか？', 'シフト申請の方法を教えて']
  if (role === 'customer') return ['予約内容はどこで確認できますか？', '予約の申し込み方法を教えて']
  if (route.path.startsWith('/op/orders/')) return ['カード決済後のSMSはどこから送れますか？', '予約内容はどこで編集できますか？']
  if (route.path === '/op/cast-notes') return ['ノートへ画像を入れる方法は？', '記事の並び替え方法は？']
  return ['この画面の使い方を教えて', '探している設定画面を案内して']
})

function resetConversation() {
  conversationId.value = null
  conversationKind.value = 'SUPPORT'
  messages.value = []
  feedbackSent.value = false
  showUnresolvedForm.value = false
  unresolvedReason.value = ''
  hasRetryAnswer.value = false
  featureRequest.value = ''
  panelView.value = 'chat'
  error.value = ''
}

async function refreshAuth() {
  try {
    currentUser.value = await api.me()
  } catch {
    currentUser.value = null
    open.value = false
  }
}

watch(
  () => route.fullPath,
  async () => {
    await refreshAuth()
    resetConversation()
  },
  { immediate: true },
)

async function scrollToBottom() {
  await nextTick()
  if (scrollArea.value) scrollArea.value.scrollTop = scrollArea.value.scrollHeight
}

async function sendMessage(value = input.value) {
  const text = String(value || '').trim()
  if (!text || loading.value) return
  error.value = ''
  input.value = ''
  feedbackSent.value = false
  showUnresolvedForm.value = false
  messages.value.push({ role: 'USER', content: text, sources: [] })
  await scrollToBottom()
  loading.value = true
  try {
    const data = await api.supportChat({
      conversation_id: conversationId.value,
      message: text,
      page_path: route.path,
      page_title: String(route.name || ''),
      store_slug: route.params.storeSlug || '',
    })
    conversationId.value = data.conversation_id
    conversationKind.value = 'SUPPORT'
    messages.value.push({
      role: 'ASSISTANT',
      content: data.answer,
      sources: data.sources || [],
    })
  } catch (e) {
    error.value = e.message || '案内を取得できませんでした。'
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

function sourcePath(path) {
  if (!path) return ''
  if (!path.includes('{')) return path
  const base = path.split('/{')[0]
  return route.path.startsWith(base) ? route.path : ''
}

async function resolveConversation() {
  if (!conversationId.value || feedbackSent.value) return
  try {
    await api.resolveSupportConversation(conversationId.value)
    feedbackSent.value = true
    messages.value.push({ role: 'ASSISTANT', content: '解決済みとして記録しました。ありがとうございます。', sources: [] })
  } catch (e) {
    error.value = e.message
  }
}

function markUnresolved() {
  if (!conversationId.value || feedbackSent.value) return
  showUnresolvedForm.value = true
}

async function submitUnresolvedReason() {
  const reason = unresolvedReason.value.trim()
  if (!conversationId.value || reason.length < 5 || sendingInquiry.value) return
  sendingInquiry.value = true
  error.value = ''
  try {
    const data = await api.markSupportConversationUnresolved(conversationId.value, reason)
    messages.value.push({ role: 'USER', content: `解決しなかった点: ${reason}`, sources: [] })
    messages.value.push({ role: 'ASSISTANT', content: data.answer, sources: data.sources || [] })
    hasRetryAnswer.value = true
    showUnresolvedForm.value = false
    unresolvedReason.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    sendingInquiry.value = false
    await scrollToBottom()
  }
}

async function requestOperator() {
  if (!conversationId.value || !hasRetryAnswer.value || sendingInquiry.value) return
  sendingInquiry.value = true
  error.value = ''
  try {
    await api.escalateSupportConversation(conversationId.value)
    feedbackSent.value = true
    messages.value.push({
      role: 'ASSISTANT',
      content: '運営への問い合わせを受け付けました。返信は「問い合わせ履歴」から確認できます。',
      sources: [],
    })
  } catch (e) {
    error.value = e.message
  } finally {
    sendingInquiry.value = false
    await scrollToBottom()
  }
}

function openFeatureRequest() {
  panelView.value = 'feature'
  error.value = ''
}

async function submitFeatureRequest() {
  const details = featureRequest.value.trim()
  if (details.length < 5 || sendingFeatureRequest.value) return
  sendingFeatureRequest.value = true
  error.value = ''
  try {
    const data = await api.submitSupportFeatureRequest({
      details,
      page_path: route.path,
      page_title: String(route.name || ''),
      store_slug: route.params.storeSlug || '',
    })
    conversationId.value = data.conversation_id
    conversationKind.value = 'FEATURE'
    messages.value = [
      { role: 'USER', content: details, sources: [] },
      { role: 'ASSISTANT', content: data.acknowledgement, sources: [] },
    ]
    feedbackSent.value = true
    featureRequest.value = ''
    panelView.value = 'chat'
  } catch (e) {
    error.value = e.message
  } finally {
    sendingFeatureRequest.value = false
    await scrollToBottom()
  }
}

async function loadHistory() {
  panelView.value = 'history'
  historyLoading.value = true
  error.value = ''
  try {
    const data = await api.getMySupportConversations()
    historyItems.value = data.results || []
  } catch (e) {
    error.value = e.message
  } finally {
    historyLoading.value = false
  }
}

async function openHistoryConversation(id) {
  try {
    const data = await api.getMySupportConversation(id)
    conversationId.value = data.id
    conversationKind.value = data.kind || 'SUPPORT'
    messages.value = data.messages || []
    feedbackSent.value = data.status !== 'OPEN'
    showUnresolvedForm.value = false
    hasRetryAnswer.value = Boolean(data.unresolved_reason && data.status === 'OPEN')
    panelView.value = 'chat'
    await scrollToBottom()
  } catch (e) {
    error.value = e.message
  }
}

function startNewConversation() {
  resetConversation()
  open.value = true
}

function formatHistoryDate(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('ja-JP', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}
</script>

<template>
  <div v-if="isSupportedRoute" class="support-assistant">
    <button
      v-if="!open"
      class="support-launcher"
      type="button"
      aria-label="Roominkサポートを開く"
      @click="open = true"
    >
      <i class="ti ti-message-chatbot"></i>
      <span>お困りですか？</span>
    </button>

    <section v-else class="support-panel" aria-label="Roomink操作サポート">
      <header class="support-header">
        <div>
          <strong>Roominkサポート</strong>
          <small>現在の画面に合わせてご案内します</small>
        </div>
        <div class="support-header-actions">
          <button type="button" :aria-label="panelView === 'chat' ? '問い合わせ履歴' : '質問へ戻る'" @click="panelView === 'chat' ? loadHistory() : startNewConversation()">
            <i :class="panelView === 'chat' ? 'ti ti-history' : 'ti ti-message-plus'"></i>
          </button>
          <button class="support-close" type="button" aria-label="閉じる" @click="open = false">
            <i class="ti ti-x"></i>
          </button>
        </div>
      </header>

      <div v-if="panelView === 'history'" class="support-history">
        <div class="support-history-title">
          <strong>問い合わせ履歴</strong>
          <button type="button" @click="startNewConversation"><i class="ti ti-plus"></i> 新しく質問</button>
        </div>
        <p v-if="historyLoading" class="support-empty">読み込み中…</p>
        <p v-else-if="historyItems.length === 0" class="support-empty">問い合わせ履歴はありません。</p>
        <button
          v-for="item in historyItems"
          v-else
          :key="item.id"
          type="button"
          class="support-history-item"
          @click="openHistoryConversation(item.id)"
        >
          <span><strong>#{{ item.id }}</strong> {{ item.latest_message || '問い合わせ' }}</span>
          <small>{{ item.store_name }}・{{ formatHistoryDate(item.updated_at) }}</small>
          <em v-if="item.has_unread_reply">新しい返信</em>
        </button>
      </div>

      <form v-else-if="panelView === 'feature'" class="support-feature" @submit.prevent="submitFeatureRequest">
        <i class="ti ti-bulb"></i>
        <strong>ご意見・機能要望</strong>
        <p>Roominkをより使いやすくするためのご意見をお寄せください。現在困っている操作は、質問画面からお問い合わせください。</p>
        <label for="support-feature-request">ご意見・機能要望</label>
        <textarea id="support-feature-request" v-model="featureRequest" rows="7" maxlength="2000" placeholder="例：予約一覧を条件ごとに保存できるようにしてほしい"></textarea>
        <small>受付後に検討しますが、個別の実装時期をお約束するものではありません。</small>
        <button type="submit" :disabled="sendingFeatureRequest || featureRequest.trim().length < 5">
          {{ sendingFeatureRequest ? '送信中…' : '機能要望を送る' }}
        </button>
      </form>

      <div v-else ref="scrollArea" class="support-messages">
        <div v-if="messages.length === 0" class="support-welcome">
          <i class="ti ti-sparkles"></i>
          <strong>何にお困りですか？</strong>
          <p>操作方法をご案内します。電話番号・お客様名・パスワードは入力しないでください。</p>
          <button
            v-for="suggestion in suggestions"
            :key="suggestion"
            type="button"
            @click="sendMessage(suggestion)"
          >{{ suggestion }}</button>
          <button type="button" class="support-feature-link" @click="openFeatureRequest">
            <i class="ti ti-bulb"></i> ご意見・機能要望を送る
          </button>
        </div>

        <div
          v-for="(message, index) in messages"
          :key="index"
          class="support-message"
          :class="message.role === 'USER' ? 'is-user' : 'is-assistant'"
        >
          <p>{{ message.content }}</p>
          <div v-if="message.sources?.length" class="support-sources">
            <span>関連画面</span>
            <template v-for="source in message.sources" :key="source.title + source.path">
              <router-link v-if="sourcePath(source.path)" :to="sourcePath(source.path)" @click="open = false">
                {{ source.title }}
              </router-link>
              <span v-else class="support-source-label">{{ source.title }}</span>
            </template>
          </div>
        </div>
        <div v-if="loading" class="support-message is-assistant"><p>確認しています…</p></div>
        <p v-if="error" class="support-error">{{ error }}</p>
      </div>

      <div v-if="conversationId && !feedbackSent && !loading && !showUnresolvedForm" class="support-feedback">
        <span>{{ hasRetryAnswer ? '追加の案内で解決しましたか？' : '解決しましたか？' }}</span>
        <button type="button" @click="resolveConversation"><i class="ti ti-check"></i> 解決した</button>
        <button v-if="!hasRetryAnswer" type="button" @click="markUnresolved"><i class="ti ti-x"></i> 解決しなかった</button>
        <button v-else type="button" @click="requestOperator"><i class="ti ti-user-question"></i> 運営へ問い合わせる</button>
      </div>

      <form v-if="showUnresolvedForm && !feedbackSent" class="support-unresolved" @submit.prevent="submitUnresolvedReason">
        <label for="support-unresolved-reason">どこが解決しませんでしたか？</label>
        <textarea id="support-unresolved-reason" v-model="unresolvedReason" rows="3" maxlength="2000" placeholder="例：案内されたボタンが画面に見つかりません"></textarea>
        <div>
          <small>入力内容をもとに、別の方法をもう一度ご案内します。</small>
          <button type="submit" :disabled="sendingInquiry || unresolvedReason.trim().length < 5">
            {{ sendingInquiry ? '確認中…' : 'もう一度案内を受ける' }}
          </button>
        </div>
      </form>

      <form v-if="panelView === 'chat' && conversationKind === 'SUPPORT'" class="support-input" @submit.prevent="sendMessage()">
        <textarea v-model="input" rows="2" maxlength="2000" placeholder="操作方法を質問してください"></textarea>
        <button type="submit" :disabled="loading || !input.trim()" aria-label="送信">
          <i class="ti ti-send"></i>
        </button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.support-assistant { position: fixed; right: 18px; bottom: 86px; z-index: 1080; }
.support-launcher { display: flex; align-items: center; gap: 8px; border: 0; border-radius: 999px; padding: 12px 17px; color: white; background: var(--rk-primary, #279d91); box-shadow: 0 8px 28px rgba(25, 75, 70, .25); font-weight: 700; }
.support-launcher i { font-size: 21px; }
.support-panel { width: min(390px, calc(100vw - 24px)); height: min(620px, calc(100vh - 115px)); display: flex; flex-direction: column; overflow: hidden; background: #fff; border: 1px solid #dce8e6; border-radius: 18px; box-shadow: 0 18px 55px rgba(20, 50, 48, .24); }
.support-header { display: flex; justify-content: space-between; align-items: center; padding: 15px 16px; color: #fff; background: var(--rk-primary, #279d91); }
.support-header div { display: flex; flex-direction: column; }
.support-header .support-header-actions { flex-direction: row; align-items: center; gap: 2px; }
.support-header-actions button { border: 0; color: #fff; background: transparent; font-size: 20px; }
.support-header small { opacity: .88; font-size: 11px; }
.support-close { border: 0; color: #fff; background: transparent; font-size: 21px; }
.support-messages { flex: 1; overflow-y: auto; padding: 15px; background: #f5f9f8; }
.support-welcome { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; padding: 5px; color: #2f4744; }
.support-welcome > i { font-size: 26px; color: var(--rk-primary, #279d91); }
.support-welcome p { margin: 0 0 3px; color: #667a77; font-size: 12px; line-height: 1.6; }
.support-welcome button { width: 100%; border: 1px solid #bcd8d4; border-radius: 10px; padding: 9px 11px; text-align: left; color: #276b64; background: #fff; font-size: 13px; }
.support-welcome .support-feature-link { margin-top: 5px; border-style: dashed; color: #705400; background: #fffaf0; }
.support-message { display: flex; flex-direction: column; align-items: flex-start; margin-bottom: 11px; }
.support-message p { max-width: 88%; margin: 0; padding: 10px 12px; border-radius: 14px 14px 14px 3px; white-space: pre-wrap; line-height: 1.55; background: #fff; color: #2c3e3b; font-size: 13px; box-shadow: 0 2px 8px rgba(0, 0, 0, .05); }
.support-message.is-user { align-items: flex-end; }
.support-message.is-user p { color: #fff; background: var(--rk-primary, #279d91); border-radius: 14px 14px 3px 14px; }
.support-sources { max-width: 88%; display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px; font-size: 11px; }
.support-sources > span:first-child { color: #7a8e8b; }
.support-sources a, .support-source-label { color: #257b72; background: #e3f2f0; border-radius: 999px; padding: 2px 7px; text-decoration: none; }
.support-error { margin: 6px 0; color: #b42318; font-size: 12px; }
.support-feedback { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; padding: 8px 12px; border-top: 1px solid #e4ecea; background: #fff; font-size: 11px; }
.support-feedback button { border: 1px solid #cddedb; border-radius: 8px; padding: 5px 7px; color: #365c57; background: #fff; }
.support-unresolved { padding: 10px 12px; border-top: 1px solid #e4ecea; background: #fff7ed; }
.support-unresolved label { display: block; margin-bottom: 5px; color: #5d4330; font-size: 12px; font-weight: 700; }
.support-unresolved textarea { width: 100%; resize: none; border: 1px solid #d9c3ae; border-radius: 9px; padding: 8px; font-size: 12px; }
.support-unresolved div { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 6px; }
.support-unresolved small { color: #826852; font-size: 10px; }
.support-unresolved button { flex: 0 0 auto; border: 0; border-radius: 8px; padding: 7px 10px; color: #fff; background: var(--rk-primary, #279d91); font-size: 11px; font-weight: 700; }
.support-unresolved button:disabled { opacity: .45; }
.support-history { flex: 1; overflow-y: auto; padding: 13px; background: #f5f9f8; }
.support-history-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.support-history-title button { border: 1px solid #bcd8d4; border-radius: 8px; padding: 6px 8px; color: #276b64; background: #fff; font-size: 11px; }
.support-history-item { position: relative; width: 100%; display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; padding: 10px; border: 1px solid #dce8e6; border-radius: 10px; text-align: left; background: #fff; }
.support-history-item span { overflow: hidden; color: #344b47; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.support-history-item small { color: #7a8e8b; font-size: 10px; }
.support-history-item em { position: absolute; right: 8px; bottom: 8px; border-radius: 999px; padding: 2px 6px; color: #fff; background: #d97706; font-size: 9px; font-style: normal; }
.support-empty { padding: 35px 0; text-align: center; color: #758582; font-size: 12px; }
.support-feature { flex: 1; display: flex; flex-direction: column; align-items: flex-start; gap: 8px; overflow-y: auto; padding: 18px; background: #f5f9f8; }
.support-feature > i { color: #b8860b; font-size: 28px; }
.support-feature p { margin: 0 0 6px; color: #667a77; font-size: 12px; line-height: 1.6; }
.support-feature label { color: #344b47; font-size: 12px; font-weight: 700; }
.support-feature textarea { width: 100%; resize: vertical; border: 1px solid #c8d9d6; border-radius: 10px; padding: 9px 10px; font-size: 13px; }
.support-feature small { color: #7a6d4d; font-size: 10px; line-height: 1.5; }
.support-feature button { align-self: flex-end; border: 0; border-radius: 9px; padding: 8px 12px; color: #fff; background: var(--rk-primary, #279d91); font-size: 12px; font-weight: 700; }
.support-feature button:disabled { opacity: .45; }
.support-input { display: flex; gap: 8px; align-items: flex-end; padding: 10px; border-top: 1px solid #dce8e6; background: #fff; }
.support-input textarea { flex: 1; resize: none; border: 1px solid #c8d9d6; border-radius: 10px; padding: 8px 10px; font-size: 13px; }
.support-input button { width: 39px; height: 39px; border: 0; border-radius: 10px; color: #fff; background: var(--rk-primary, #279d91); }
.support-input button:disabled { opacity: .45; }
@media (max-width: 575px) {
  .support-assistant { right: 10px; bottom: 78px; }
  .support-launcher span { display: none; }
  .support-launcher { width: 49px; height: 49px; justify-content: center; padding: 0; }
  .support-panel { width: calc(100vw - 20px); height: calc(100vh - 100px); }
}
</style>
