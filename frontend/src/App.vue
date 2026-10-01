<script setup>
import SupportAssistant from './components/SupportAssistant.vue'

const isStaging = import.meta.env.VITE_ROOMINK_ENV === 'staging'
</script>

<template>
  <div v-if="isStaging" class="staging-banner" role="status">
    STAGING｜検証環境・実データではありません
  </div>
  <router-view />
  <SupportAssistant />
</template>

<style scoped>
.staging-banner {
  position: fixed;
  inset: 0 0 auto 0;
  z-index: 10000;
  padding: 5px 12px;
  background: #7c3aed;
  color: #fff;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .04em;
  text-align: center;
  box-shadow: 0 2px 8px rgb(31 20 61 / 22%);
}

.staging-banner + :deep(*) {
  margin-top: 28px;
}
</style>
