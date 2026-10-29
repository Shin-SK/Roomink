<script setup>
defineProps({ text: { type: String, default: '' } })
</script>
<template>
  <section v-if="text" class="attention-memo" aria-label="要注意メモ">
    <strong><i class="ti ti-alert-triangle" aria-hidden="true"></i> 要注意メモ</strong>
    <p>{{ text }}</p>
  </section>
</template>
<style scoped>
.attention-memo { color:#a12020; background:#fff4f3; border:1px solid #e9b8b3; border-left:4px solid #b42323; border-radius:8px; padding:12px 14px; margin-bottom:14px; overflow-wrap:anywhere; }
.attention-memo p { margin:6px 0 0; white-space:pre-wrap; line-height:1.6; font-size:14px; color:#a12020; }
</style>
