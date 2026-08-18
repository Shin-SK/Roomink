<script setup>
import { useRoute, useRouter } from 'vue-router'
import { api } from '../../api.js'
import { resetAuthCache } from '../../router.js'
import LayoutCustomer from '../../components/LayoutCustomer.vue'
import ProfileForm from '../../components/ProfileForm.vue'
import { customerPath } from '../../customerStore.js'

const router = useRouter()
const route = useRoute()

async function onLogout() {
  try { await api.logout() } catch { /* ignore */ }
  resetAuthCache()
  router.push(customerPath(route, 'login'))
}
</script>

<template>
  <LayoutCustomer>
    <ProfileForm @logout="onLogout" />
  </LayoutCustomer>
</template>
