<script setup>
import { useRouter } from 'vue-router'
import { api } from '../../api.js'
import { resetAuthCache } from '../../router.js'
import LayoutCustomer from '../../components/LayoutCustomer.vue'
import ProfileForm from '../../components/ProfileForm.vue'

const router = useRouter()

async function onLogout() {
  try { await api.logout() } catch { /* ignore */ }
  resetAuthCache()
  router.push('/cu/login')
}
</script>

<template>
  <LayoutCustomer>
    <ProfileForm @logout="onLogout" />
  </LayoutCustomer>
</template>
