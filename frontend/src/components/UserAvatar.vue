<script setup>
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, default: '' },
  avatarUrl: { type: String, default: '' },
  size: { type: Number, default: 32 },
})

const initial = computed(() => {
  return (props.name || '?').charAt(0).toUpperCase()
})
</script>

<template>
  <div
    class="user-avatar"
    :style="{ width: size + 'px', height: size + 'px', fontSize: (size * 0.45) + 'px' }"
  >
    <img v-if="avatarUrl" :src="avatarUrl" alt="avatar" class="user-avatar__img">
    <span v-else>{{ initial }}</span>
  </div>
</template>

<style scoped>
.user-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--rk-primary);
  color: #fff;
  font-weight: 600;
  flex-shrink: 0;
  cursor: pointer;
  overflow: hidden;
}
.user-avatar__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>
