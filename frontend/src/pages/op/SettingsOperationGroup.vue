<script setup>
import { computed, onMounted, ref } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { generateTemporaryPassword } from '../../password.js'

const loading = ref(true)
const error = ref('')
const message = ref('')
const data = ref({ stores: [], people: [] })
const saving = ref(false)
const showCreate = ref(false)
const showInvite = ref(false)
const createForm = ref(emptyCreateForm())
const inviteForm = ref(emptyInviteForm())

function emptyCreateForm() {
  return {
    username: '', password: '', email: '', role: 'staff', store_ids: [],
    is_operation_group_manager: false,
  }
}

function emptyInviteForm() {
  return { username: '', role: 'staff', store_ids: [] }
}

const storesById = computed(() => Object.fromEntries(data.value.stores.map(store => [store.id, store.name])))
const managerCandidates = computed(() => data.value.people.filter(person =>
  person.memberships.some(membership => membership.role === 'manager')
))
const roleLabel = role => role === 'manager' ? 'マネージャー' : 'スタッフ'

async function load() {
  loading.value = true
  error.value = ''
  try { data.value = await api.getOperationGroup() }
  catch (e) { error.value = e.message }
  finally { loading.value = false }
}

function selectedAll(form) {
  return form.store_ids.length === data.value.stores.length
}

function toggleAll(form) {
  form.store_ids = selectedAll(form) ? [] : data.value.stores.map(store => store.id)
}

function openCreate() {
  createForm.value = emptyCreateForm()
  showCreate.value = true
  message.value = ''
}

function openInvite() {
  inviteForm.value = emptyInviteForm()
  showInvite.value = true
  message.value = ''
}

function generatePassword() {
  createForm.value.password = generateTemporaryPassword(14)
}

async function createStaff() {
  saving.value = true
  error.value = ''
  try {
    data.value = await api.createOperationGroupStaff(createForm.value)
    showCreate.value = false
    message.value = 'スタッフを追加しました。選択した店舗だけを利用できます。'
  } catch (e) { error.value = e.message }
  finally { saving.value = false }
}

async function inviteStaff() {
  saving.value = true
  error.value = ''
  try {
    const result = await api.inviteToOperationGroup(inviteForm.value)
    showInvite.value = false
    message.value = result.detail
  } catch (e) { error.value = e.message }
  finally { saving.value = false }
}

async function setGroupManager(person, isActive) {
  const action = isActive ? '運営管理者に設定' : '運営管理者を解除'
  if (!window.confirm(`「${person.username}」を${action}しますか？`)) return
  saving.value = true
  error.value = ''
  try {
    data.value = await api.setOperationGroupManager({ username: person.username, is_active: isActive })
    message.value = isActive ? '運営管理者を追加しました。' : '運営管理者を解除しました。'
  } catch (e) { error.value = e.message }
  finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <LayoutOperator>
    <template #title>運営管理</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger" role="alert">{{ error }}</div>
    <div v-if="message" class="alert alert-info" role="status">{{ message }}</div>
    <div v-if="loading" class="text-center py-5"><div class="spinner-border text-primary"></div></div>

    <template v-else>
      <section class="card mb-4">
        <div class="card-body">
          <h2 class="h5">管理できる店舗</h2>
          <p class="text-muted small">ここには、同じ契約内で運営管理を任された店舗だけが表示されます。他のRoomink利用店舗は表示されません。</p>
          <div class="d-flex flex-wrap gap-2">
            <span v-for="store in data.stores" :key="store.id" class="badge text-bg-light border text-dark py-2 px-3">{{ store.name }}</span>
          </div>
        </div>
      </section>

      <section class="card mb-4">
        <div class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
          <span><i class="ti ti-users-group"></i> スタッフの追加・招待</span>
          <div class="d-flex gap-2">
            <button class="btn btn-outline-primary btn-sm" @click="openInvite"><i class="ti ti-send"></i> 既存アカウントを招待</button>
            <button class="btn btn-primary btn-sm" @click="openCreate"><i class="ti ti-user-plus text-white"></i> 新しいスタッフを追加</button>
          </div>
        </div>
        <div class="card-body">
          <p class="mb-0 small text-muted">追加時に所属店舗を選びます。選ばなかった店舗の顧客・設定・着信は利用できません。既存アカウントは、本人の承認後に追加されます。</p>
        </div>
      </section>

      <section class="card mb-4">
        <div class="card-header"><i class="ti ti-shield-check"></i> 運営管理者</div>
        <div class="card-body">
          <p class="small text-muted">運営管理者は、この画面に表示される契約内の店舗とスタッフ所属を管理できます。店舗マネージャーであるスタッフだけを設定できます。</p>
          <p v-if="!managerCandidates.length" class="text-muted mb-0">設定できる店舗マネージャーがいません。</p>
          <div v-for="person in managerCandidates" :key="person.username" class="d-flex flex-wrap align-items-center gap-2 border-bottom py-2">
            <strong class="text-break">{{ person.username }}</strong>
            <span v-if="person.is_operation_group_manager" class="badge text-bg-primary">運営管理者</span>
            <button
              class="btn btn-outline-secondary btn-sm ms-auto"
              :disabled="saving"
              @click="setGroupManager(person, !person.is_operation_group_manager)"
            >{{ person.is_operation_group_manager ? '解除' : '運営管理者にする' }}</button>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-header"><i class="ti ti-list-details"></i> 契約内のスタッフ所属</div>
        <div class="card-body p-0">
          <p v-if="!data.people.length" class="text-muted text-center py-4 mb-0">スタッフはいません。</p>
          <div v-for="person in data.people" :key="person.username" class="person-row px-3 py-3 border-bottom">
            <div class="d-flex flex-wrap gap-2 align-items-center">
              <strong class="text-break">{{ person.username }}</strong>
              <span v-if="person.is_operation_group_manager" class="badge text-bg-primary">運営管理者</span>
            </div>
            <div class="d-flex flex-wrap gap-2 mt-2">
              <span v-for="membership in person.memberships" :key="membership.store_id" class="badge text-bg-light border text-dark">
                {{ storesById[membership.store_id] }}・{{ roleLabel(membership.role) }}
              </span>
            </div>
          </div>
        </div>
      </section>
    </template>

    <div v-if="showCreate" class="modal d-block" style="background: rgba(0,0,0,0.3)" @click.self="showCreate = false">
      <div class="modal-dialog modal-dialog-scrollable"><div class="modal-content">
        <div class="modal-header"><h2 class="modal-title h5">新しいスタッフを追加</h2><button class="btn-close" @click="showCreate = false"></button></div>
        <form @submit.prevent="createStaff"><div class="modal-body">
          <div class="mb-3"><label class="form-label">ユーザー名</label><input v-model="createForm.username" class="form-control" maxlength="150" required></div>
          <div class="mb-3"><label class="form-label">初期パスワード</label><div class="input-group"><input v-model="createForm.password" class="form-control" type="text" required><button type="button" class="btn btn-outline-secondary" @click="generatePassword">生成</button></div></div>
          <div class="mb-3"><label class="form-label">メールアドレス（任意）</label><input v-model="createForm.email" class="form-control" type="email"></div>
          <div class="mb-3"><label class="form-label">店舗内の権限</label><select v-model="createForm.role" class="form-select"><option value="staff">スタッフ</option><option value="manager">マネージャー</option></select></div>
          <div class="mb-3"><label class="form-label d-block">所属店舗</label><button type="button" class="btn btn-link btn-sm p-0 mb-2" @click="toggleAll(createForm)">{{ selectedAll(createForm) ? 'すべて解除' : 'すべて選択' }}</button><label v-for="store in data.stores" :key="store.id" class="form-check d-block"><input v-model="createForm.store_ids" class="form-check-input" type="checkbox" :value="store.id"><span class="form-check-label">{{ store.name }}</span></label></div>
          <label v-if="createForm.role === 'manager'" class="form-check"><input v-model="createForm.is_operation_group_manager" class="form-check-input" type="checkbox"><span class="form-check-label">このスタッフを運営管理者にもする</span></label>
        </div><div class="modal-footer"><button type="button" class="btn btn-outline-secondary" @click="showCreate = false">キャンセル</button><button class="btn btn-primary" :disabled="saving || !createForm.store_ids.length">{{ saving ? '保存中...' : '追加する' }}</button></div></form>
      </div></div>
    </div>

    <div v-if="showInvite" class="modal d-block" style="background: rgba(0,0,0,0.3)" @click.self="showInvite = false">
      <div class="modal-dialog modal-dialog-scrollable"><div class="modal-content">
        <div class="modal-header"><h2 class="modal-title h5">既存アカウントを招待</h2><button class="btn-close" @click="showInvite = false"></button></div>
        <form @submit.prevent="inviteStaff"><div class="modal-body">
          <p class="small text-muted">相手が現在使っているユーザー名を入力してください。本人の承認が必要です。</p>
          <div class="mb-3"><label class="form-label">ユーザー名</label><input v-model="inviteForm.username" class="form-control" maxlength="150" required></div>
          <div class="mb-3"><label class="form-label">店舗内の権限</label><select v-model="inviteForm.role" class="form-select"><option value="staff">スタッフ</option><option value="manager">マネージャー</option></select></div>
          <div><label class="form-label d-block">招待する店舗</label><button type="button" class="btn btn-link btn-sm p-0 mb-2" @click="toggleAll(inviteForm)">{{ selectedAll(inviteForm) ? 'すべて解除' : 'すべて選択' }}</button><label v-for="store in data.stores" :key="store.id" class="form-check d-block"><input v-model="inviteForm.store_ids" class="form-check-input" type="checkbox" :value="store.id"><span class="form-check-label">{{ store.name }}</span></label></div>
        </div><div class="modal-footer"><button type="button" class="btn btn-outline-secondary" @click="showInvite = false">キャンセル</button><button class="btn btn-primary" :disabled="saving || !inviteForm.store_ids.length">{{ saving ? '送信中...' : '招待する' }}</button></div></form>
      </div></div>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.person-row:last-child { border-bottom: 0 !important; }
</style>
