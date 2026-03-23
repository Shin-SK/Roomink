<script setup>
import { ref, onMounted } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { uploadToCloudinary } from '../../cloudinary.js'

const loading = ref(true)
const error = ref('')
const staffs = ref([])

// Form
const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)
const uploading = ref(false)

function emptyForm() {
  return { username: '', password: '', email: '', role: 'staff', avatar_url: '' }
}

async function loadStaffs() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getStaffs()
    staffs.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(() => loadStaffs())

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(s) {
  editingId.value = s.id
  form.value = {
    username: s.username,
    password: '',
    email: s.email || '',
    role: s.role,
    avatar_url: s.avatar_url || '',
  }
  formError.value = ''
  showForm.value = true
}

async function onAvatarChange(e) {
  const file = e.target.files[0]
  if (!file) return
  uploading.value = true
  formError.value = ''
  try {
    const url = await uploadToCloudinary(file)
    form.value.avatar_url = url
  } catch (e) {
    formError.value = e.message
  } finally {
    uploading.value = false
  }
}

const showAvatarMenu = ref(false)

function onAvatarTap() {
  if (form.value.avatar_url) {
    showAvatarMenu.value = true
  } else {
    document.getElementById('staff-avatar-file').click()
  }
}

function avatarChooseNew() {
  showAvatarMenu.value = false
  document.getElementById('staff-avatar-file').click()
}

function avatarRemove() {
  showAvatarMenu.value = false
  form.value.avatar_url = ''
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    if (editingId.value) {
      const payload = { email: form.value.email, role: form.value.role, avatar_url: form.value.avatar_url }
      if (form.value.password) payload.password = form.value.password
      await api.updateStaff(editingId.value, payload)
    } else {
      await api.createStaff({
        username: form.value.username,
        password: form.value.password,
        email: form.value.email,
        role: form.value.role,
        avatar_url: form.value.avatar_url,
      })
    }
    showForm.value = false
    await loadStaffs()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function onDelete(s) {
  if (!confirm(`「${s.username}」を削除しますか？`)) return
  error.value = ''
  try {
    await api.deleteStaff(s.id)
    await loadStaffs()
  } catch (e) {
    error.value = e.message
  }
}

const roleLabel = (role) => role === 'manager' ? 'マネージャー' : 'スタッフ'
</script>

<template>
  <LayoutOperator>
    <template #title>スタッフ管理</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-user-shield"></i> スタッフ一覧</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus text-white"></i> スタッフ追加
        </button>
      </div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!staffs.length" class="text-muted text-center py-3">
          スタッフが登録されていません
        </div>

        <table v-else class="table table-hover mb-0">
          <thead>
            <tr>
              <th style="width: 50px;"></th>
              <th>ユーザー名</th>
              <th>権限</th>
              <th style="width: 50px;"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in staffs" :key="s.id">
              <td>
                <img
                  v-if="s.avatar_url"
                  :src="s.avatar_url"
                  :alt="s.username"
                  style="width: 36px; height: 36px; border-radius: 50%; object-fit: cover;"
                >
                <div
                  v-else
                  class="d-flex align-items-center justify-content-center bg-light"
                  style="width: 36px; height: 36px; border-radius: 50%; color: var(--rk-primary);"
                >
                  <i class="ti ti-user"></i>
                </div>
              </td>
              <td>{{ s.username }}</td>
              <td><span class="badge" :class="s.role === 'manager' ? 'bg-warning text-dark' : 'bg-secondary'">{{ roleLabel(s.role) }}</span></td>
              <td>
                <button class="btn btn-link p-0" @click="openEdit(s)">
                  <i class="ti ti-edit" style="font-size: 1.25rem;"></i>
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
            <h5 class="modal-title">{{ editingId ? 'スタッフ編集' : 'スタッフ追加' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

            <div class="mb-3 text-center position-relative">
              <div class="avatar-tap" @click="onAvatarTap" style="cursor: pointer; display: inline-block; position: relative;">
                <img
                  v-if="form.avatar_url"
                  :src="form.avatar_url"
                  alt="avatar"
                  style="width: 160px; height: 160px; border-radius: 50%; object-fit: cover;"
                >
                <div
                  v-else
                  class="d-inline-flex align-items-center justify-content-center bg-light"
                  style="width: 160px; height: 160px; border-radius: 50%; font-size: 64px; color: #ccc;"
                >
                  <i class="ti ti-user"></i>
                </div>
                <div class="avatar-overlay">
                  <i class="ti ti-camera"></i>
                </div>
              </div>
              <input
                id="staff-avatar-file"
                type="file"
                accept="image/*"
                :disabled="uploading"
                @change="onAvatarChange"
                style="display: none;"
              />
              <small v-if="uploading" class="text-muted d-block mt-1">アップロード中...</small>

              <!-- アバターメニュー -->
              <div v-if="showAvatarMenu" class="avatar-menu-overlay" @click="showAvatarMenu = false">
                <div class="avatar-menu" @click.stop>
                  <button class="avatar-menu__item" @click="avatarChooseNew">
                    <i class="ti ti-photo"></i> 画像を変更する
                  </button>
                  <button class="avatar-menu__item text-danger" @click="avatarRemove">
                    <i class="ti ti-trash"></i> 画像を削除する
                  </button>
                  <button class="avatar-menu__item text-muted" @click="showAvatarMenu = false">
                    キャンセル
                  </button>
                </div>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label">ユーザー名 <span class="text-danger">*</span></label>
              <input v-model="form.username" type="text" class="form-control" placeholder="ログイン用ユーザー名" :disabled="!!editingId" />
              <small v-if="editingId" class="text-muted">ユーザー名は変更できません</small>
            </div>

            <div class="mb-3">
              <label class="form-label">パスワード <span v-if="!editingId" class="text-danger">*</span></label>
              <input v-model="form.password" type="password" class="form-control" :placeholder="editingId ? '変更する場合のみ入力' : 'パスワード'" />
            </div>

            <div class="mb-3">
              <label class="form-label">メールアドレス</label>
              <input v-model="form.email" type="email" class="form-control" placeholder="メールアドレス（任意）" />
            </div>

            <div class="mb-3">
              <label class="form-label">権限 <span class="text-danger">*</span></label>
              <select v-model="form.role" class="form-select">
                <option value="staff">スタッフ</option>
                <option value="manager">マネージャー</option>
              </select>
            </div>
          </div>
          <div class="modal-footer d-flex">
            <button v-if="editingId" class="btn btn-outline-danger me-auto" @click="onDelete({ id: editingId, username: form.username })">
              <i class="ti ti-trash"></i> 削除
            </button>
            <button class="btn btn-secondary" @click="showForm = false">キャンセル</button>
            <button
              class="btn btn-primary"
              :disabled="saving || uploading || !form.username.trim() || (!editingId && !form.password)"
              @click="onSave"
            >
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.avatar-overlay {
  position: absolute;
  bottom: 4px;
  right: 4px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--rk-primary, #2A9D8F);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.avatar-menu-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.3);
  z-index: 1060;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.avatar-menu {
  background: #fff;
  border-radius: 12px 12px 0 0;
  width: 100%;
  max-width: 400px;
  padding: 0.5rem 0;
}

.avatar-menu__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.875rem 1.25rem;
  border: none;
  background: none;
  font-size: 1rem;
  text-align: left;
  cursor: pointer;
}

.avatar-menu__item:hover {
  background: #f5f5f5;
}
</style>
