<script setup>
import { useRouter } from 'vue-router'
import { api } from '../../api.js'
import { resetAuthCache } from '../../router.js'
import LayoutOperator from '../../components/LayoutOperator.vue'
import ProfileForm from '../../components/ProfileForm.vue'

const router = useRouter()

async function onLogout() {
  try { await api.logout() } catch { /* ignore */ }
  resetAuthCache()
  router.push('/op/login')
}
</script>

<template>
  <LayoutOperator>
    <ProfileForm @logout="onLogout" />
  </LayoutOperator>
</template>
