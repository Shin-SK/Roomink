<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import OrderForm from '../../components/OrderForm.vue'

const router = useRouter()
const route = useRoute()

const initialPhone = ref(route.query.phone || '')

function onCreated({ order, startDate }) {
  router.push(`/op/schedule?date=${startDate}&highlight=${order.id}`)
}

function onCancel() {
  router.push('/op/schedule')
}
</script>

<template>
  <LayoutOperator>
    <template #title>予約フロー</template>
    <OrderForm
      :initial-phone="initialPhone"
      @created="onCreated"
      @cancel="onCancel"
    />
  </LayoutOperator>
</template>
