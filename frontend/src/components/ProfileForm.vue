<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'
import { uploadToCloudinary } from '../cloudinary.js'
import UserAvatar from './UserAvatar.vue'

const props = defineProps({
  logoutPath: { type: String, default: '/login' },
})
const emit = defineEmits(['logout'])

const user = ref(null)
const displayName = ref('')
const avatarUrl = ref('')
const saving = ref(false)
const uploading = ref(false)
const message = ref('')
const showAvatarMenu = ref(false)

onMounted(async () => {
  try {
    user.value = await api.me()
    displayName.value = user.value.display_name || ''
    avatarUrl.value = user.value.avatar_url || ''
  } catch { /* ignore */ }
})

function onAvatarTap() {
  if (avatarUrl.value) {
    showAvatarMenu.value = true
  } else {
    document.getElementById('profile-avatar-file').click()
  }
}

function avatarChooseNew() {
  showAvatarMenu.value = false
  document.getElementById('profile-avatar-file').click()
}

function avatarRemove() {
  showAvatarMenu.value = false
  avatarUrl.value = ''
}

async function onAvatarChange(e) {
  const file = e.target.files[0]
  if (!file) return
  uploading.value = true
  message.value = ''
  try {
    avatarUrl.value = await uploadToCloudinary(file)
  } catch (err) {
    message.value = err.message
  } finally {
    uploading.value = false
  }
}

async function onSave() {
  saving.value = true
  message.value = ''
  try {
    user.value = await api.updateProfile({
      display_name: displayName.value,
      avatar_url: avatarUrl.value,
    })
    avatarUrl.value = user.value.avatar_url || ''
    message.value = '保存しました'
  } catch (e) {
    message.value = e.message || '保存に失敗しました'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="user" class="profile-page">
    <h2 class="page-title mb-4">プロフィール</h2>

    <div class="text-center mb-4 position-relative">
      <div class="avatar-tap" @click="onAvatarTap" style="cursor: pointer; display: inline-block; position: relative;">
        <UserAvatar :name="displayName || user.display_name" :avatar-url="avatarUrl" :size="96" />
        <div class="avatar-overlay">
          <i class="ti ti-camera"></i>
        </div>
      </div>
      <input
        id="profile-avatar-file"
        type="file"
        accept="image/*"
        :disabled="uploading"
        @change="onAvatarChange"
        style="display: none;"
      >
      <small v-if="uploading" class="text-muted d-block mt-1">アップロード中...</small>

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

    <div v-if="message" class="alert py-2 px-3 mb-3" :class="message === '保存しました' ? 'alert-success' : 'alert-danger'" style="font-size: 0.875rem;">
      {{ message }}
    </div>

    <form @submit.prevent="onSave">
      <div class="mb-3">
        <label class="form-label">ユーザー名</label>
        <input type="text" class="form-control" :value="user.username" disabled>
      </div>
      <div class="mb-3">
        <label class="form-label">表示名</label>
        <input v-model="displayName" type="text" class="form-control" required>
      </div>
      <button type="submit" class="btn btn-primary btn-block" :disabled="saving || uploading">
        {{ saving ? '保存中...' : '保存' }}
      </button>
    </form>

    <hr class="my-4">
    <button class="btn btn-outline-danger btn-block" @click="$emit('logout')">
      <i class="ti ti-logout"></i> ログアウト
    </button>
  </div>
</template>

<style scoped>
.profile-page {
  max-width: 480px;
  margin: 0 auto;
  padding: 1rem 0;
}
.avatar-overlay {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 28px;
  height: 28px;
  background: var(--rk-primary);
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  border: 2px solid #fff;
}
.avatar-menu-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.4);
  z-index: 1050;
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
  display: block;
  width: 100%;
  padding: 0.75rem 1rem;
  border: none;
  background: transparent;
  text-align: left;
  font-size: 0.9375rem;
  cursor: pointer;
}
.avatar-menu__item:hover {
  background: #f5f5f5;
}
</style>
