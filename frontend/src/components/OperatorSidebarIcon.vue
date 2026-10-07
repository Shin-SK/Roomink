<script setup>
import { computed } from 'vue'
import buildingCommunity from '@tabler/icons/outline/building-community.svg?raw'
import calculator from '@tabler/icons/outline/calculator.svg?raw'
import calendar from '@tabler/icons/outline/calendar.svg?raw'
import calendarCheck from '@tabler/icons/outline/calendar-check.svg?raw'
import cashBanknote from '@tabler/icons/outline/cash-banknote.svg?raw'
import chartBar from '@tabler/icons/outline/chart-bar.svg?raw'
import chevronLeft from '@tabler/icons/outline/chevron-left.svg?raw'
import chevronRight from '@tabler/icons/outline/chevron-right.svg?raw'
import clipboardPlus from '@tabler/icons/outline/clipboard-plus.svg?raw'
import clock from '@tabler/icons/outline/clock.svg?raw'
import door from '@tabler/icons/outline/door.svg?raw'
import doorExit from '@tabler/icons/outline/door-exit.svg?raw'
import helpCircle from '@tabler/icons/outline/help-circle.svg?raw'
import home from '@tabler/icons/outline/home.svg?raw'
import lifebuoy from '@tabler/icons/outline/lifebuoy.svg?raw'
import logout from '@tabler/icons/outline/logout.svg?raw'
import notebook from '@tabler/icons/outline/notebook.svg?raw'
import receipt from '@tabler/icons/outline/receipt.svg?raw'
import reportMoney from '@tabler/icons/outline/report-money.svg?raw'
import settings from '@tabler/icons/outline/settings.svg?raw'
import star from '@tabler/icons/outline/star.svg?raw'
import users from '@tabler/icons/outline/users.svg?raw'

const props = defineProps({
  name: { type: String, required: true },
})

const icons = {
  'building-community': buildingCommunity,
  calculator,
  calendar,
  'calendar-check': calendarCheck,
  'cash-banknote': cashBanknote,
  'chart-bar': chartBar,
  'chevron-left': chevronLeft,
  'chevron-right': chevronRight,
  'clipboard-plus': clipboardPlus,
  clock,
  door,
  'door-exit': doorExit,
  'help-circle': helpCircle,
  home,
  lifebuoy,
  logout,
  notebook,
  receipt,
  'report-money': reportMoney,
  settings,
  star,
  users,
}

const markup = computed(() => icons[props.name] || helpCircle)
</script>

<template>
  <span class="operator-sidebar-icon" aria-hidden="true" v-html="markup"></span>
</template>

<style scoped>
.operator-sidebar-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 20px;
  width: 20px;
  height: 20px;
}

.operator-sidebar-icon :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
