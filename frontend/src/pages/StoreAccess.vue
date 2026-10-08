<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
import { openStore } from '../storeSelection.js'

const data = ref({ memberships: [], invitations: [] })
const error = ref('')
const loading = ref(true)
const busy = ref(false)
const roleLabel = role => role === 'manager' ? 'マネージャー' : 'スタッフ'

async function load() {
  error.value = ''
  try { data.value = await api.getStoreAccess() }
  catch (e) { error.value = e.message }
  finally { loading.value = false }
}

async function respond(invite, action) {
  if (!window.confirm(action === 'accept'
    ? `「${invite.store_name}」へ${roleLabel(invite.role)}として参加しますか？`
    : `「${invite.store_name}」からの招待を辞退しますか？`)) return
  busy.value = true
  error.value = ''
  try {
    await api.respondStoreInvitation(invite.id, action)
    await load()
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}

async function logout() {
  try { await api.logout(); window.location.assign('/login') }
  catch (e) { error.value = e.message }
}
onMounted(load)
</script>

<template>
  <main class="container py-4" style="max-width: 760px">
    <div class="d-flex align-items-center justify-content-between mb-4">
      <img src="/logo.svg" alt="Roomink" style="height: 32px">
      <button class="btn btn-outline-secondary btn-sm" @click="logout">ログアウト</button>
    </div>
    <h1 class="h4">所属店舗・招待</h1>
    <p class="text-muted">店舗ごとに利用できる権限が異なります。招待は承認するまで所属に追加されません。</p>
    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <p v-if="loading">読み込み中...</p>
    <template v-else>
      <section class="card mb-4">
        <div class="card-body">
          <h2 class="h5">所属している店舗</h2>
          <p v-if="!data.memberships.length" class="text-muted mb-0">現在、利用できる店舗はありません。店舗の管理者に招待を依頼してください。</p>
          <div v-for="member in data.memberships" :key="member.store_id" class="d-flex flex-wrap align-items-center justify-content-between gap-2 py-3 border-bottom">
            <div><strong>{{ member.store_name }}</strong><div class="small text-muted">{{ roleLabel(member.role) }}</div></div>
            <button class="btn btn-primary btn-sm" @click="openStore(member.store_id)">この店舗を開く</button>
          </div>
        </div>
      </section>
      <section class="card">
        <div class="card-body">
          <h2 class="h5">届いている招待</h2>
          <p v-if="!data.invitations.length" class="text-muted mb-0">承認待ちの招待はありません。</p>
          <article v-for="invite in data.invitations" :key="invite.id" class="py-3 border-bottom">
            <h3 class="h6">{{ invite.store_name }}</h3>
            <p class="small mb-2">招待者：{{ invite.invited_by_name }} ／ 権限：{{ roleLabel(invite.role) }}<br>
              有効期限：{{ new Date(invite.expires_at).toLocaleString('ja-JP') }}</p>
            <div class="d-flex gap-2">
              <button class="btn btn-primary btn-sm" :disabled="busy" @click="respond(invite, 'accept')">承認して参加</button>
              <button class="btn btn-outline-secondary btn-sm" :disabled="busy" @click="respond(invite, 'decline')">辞退</button>
            </div>
          </article>
        </div>
      </section>
    </template>
  </main>
</template>
