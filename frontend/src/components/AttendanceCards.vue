<script setup>
import { computed, ref } from 'vue'

const props = defineProps({ cards: { type: Array, default: () => [] } })
const failedAvatars = ref(new Set())
const lateCount = computed(() => props.cards.filter(card => card.late).length)
const shortStatus = card => card.label.includes('未出勤') ? '未出勤' : '未確認'
function avatarFailed(url) {
  failedAvatars.value = new Set([...failedAvatars.value, url])
}
</script>

<template>
  <section v-if="cards.length" class="attendance" aria-label="出勤の確認">
    <header class="attendance__header">
      <div class="attendance__title"><i class="ti ti-users" aria-hidden="true"></i><h2>出勤の確認</h2><span>{{ cards.length }}名</span></div>
      <div class="attendance__legend"><span v-if="lateCount" class="attendance__late-count">開始超過 {{ lateCount }}</span><span v-if="cards.length > lateCount">開始前 {{ cards.length - lateCount }}</span></div>
    </header>
    <ul class="attendance__grid">
      <li v-for="card in cards" :key="card.id" class="attendance__person" :class="{ 'is-late': card.late }" :aria-label="`${card.name} ${card.time} ${card.room} ${card.label}`">
        <div class="attendance__avatar" aria-hidden="true">
          <img v-if="card.avatar && !failedAvatars.has(card.avatar)" :src="card.avatar" alt="" loading="lazy" @error="avatarFailed(card.avatar)">
          <i v-else class="ti ti-user"></i>
        </div>
        <div class="attendance__body">
          <strong>{{ card.name }}</strong>
          <div class="attendance__meta"><time>{{ card.time }}</time><span>{{ shortStatus(card) }}</span></div>
          <span class="attendance__room" :title="card.room">{{ card.room }}</span>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.attendance__header, .attendance__title, .attendance__legend { display: flex; align-items: center; flex-wrap: wrap; }
.attendance__header { justify-content: space-between; gap: 6px 12px; margin-bottom: 10px; }
.attendance__title { gap: 7px; color: #394b49; }
.attendance__title > i { color: #78908a; font-size: 17px; }
.attendance__title h2 { margin: 0; font-size: .86rem; font-weight: 700; }
.attendance__title > span { border-radius: 20px; padding: 1px 7px; color: #677873; background: #eef3f1; font-size: .7rem; }
.attendance__legend { gap: 12px; color: #946617; font-size: .7rem; }
.attendance__late-count { color: #b03b4d; }
.attendance__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 7px; list-style: none; margin: 0; padding: 0; }
.attendance__person { display: flex; align-items: center; gap: 9px; padding: 9px 10px; min-width: 0; border-radius: 7px; background: #fff6df; color: #825b12; }
.attendance__person.is-late { background: #fff0f0; color: #a73548; }
.attendance__avatar { width: 34px; height: 34px; flex: 0 0 34px; border-radius: 50%; background: #f0deb9; display: grid; place-items: center; overflow: hidden; font-size: 21px; }
.is-late .attendance__avatar { background: #f5dadd; }
.attendance__avatar img { width: 100%; height: 100%; object-fit: cover; }
.attendance__body { min-width: 0; flex: 1; }
.attendance__body > strong { display: block; color: #3f3934; font-size: .79rem; line-height: 1.4; overflow-wrap: anywhere; }
.attendance__meta { display: flex; gap: 5px; align-items: baseline; flex-wrap: wrap; margin-top: 2px; font-size: .69rem; line-height: 1.5; }
.attendance__meta time { font-weight: 700; font-size: .75rem; font-variant-numeric: tabular-nums; }
.attendance__room { display: block; color: #7e7468; font-size: .69rem; line-height: 1.4; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
@media (max-width: 575px) {
  .attendance__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
  .attendance__person { gap: 7px; padding: 8px; align-items: flex-start; }
  .attendance__avatar { width: 27px; height: 27px; flex-basis: 27px; font-size: 18px; }
  .attendance__meta > span { font-size: .69rem; }
}
</style>
