<script setup>
import { useRouter } from 'vue-router'
import { api } from '../../api.js'
import { resetAuthCache } from '../../router.js'
import LayoutCast from '../../components/LayoutCast.vue'
import ProfileForm from '../../components/ProfileForm.vue'

const router = useRouter()

async function onLogout() {
  try { await api.logout() } catch { /* ignore */ }
  resetAuthCache()
  router.push('/login')
}
</script>

<template>
  <LayoutCast>
    <ProfileForm @logout="onLogout" />
  </LayoutCast>
</template>
