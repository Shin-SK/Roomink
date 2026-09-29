<script setup>
import { computed, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import LayoutOperator from '../../components/LayoutOperator.vue'
import OrderForm from '../../components/OrderForm.vue'

const router = useRouter()
const route = useRoute()

const initialPhone = ref(route.query.phone || '')
const initialDate = ref(route.query.date || '')
const initialStartTime = ref(route.query.start || '15:00')
const initialCast = ref(route.query.cast || '')
const initialCustomerId = ref(route.query.customer || '')
const isPopup = computed(() => route.query.popup === '1')

function onCreated({ order, startDate }) {
  if (isPopup.value && window.opener) {
    window.opener.postMessage({
      type: 'roomink-order-created',
      order,
      startDate,
    }, window.location.origin)
    window.close()
    return
  }
  router.push(`/op/schedule?date=${startDate}&highlight=${order.id}`)
}

function onCancel() {
  if (isPopup.value && window.opener) {
    window.close()
    return
  }
  router.push('/op/schedule')
}
</script>

<template>
  <div v-if="isPopup" class="order-entry-popup">
    <header class="order-entry-popup__header">
      <div>
        <div class="order-entry-popup__eyebrow">予約タイムラインから入力中</div>
        <h1>予約作成</h1>
      </div>
      <button type="button" class="btn btn-outline-secondary btn-sm" @click="onCancel">
        閉じる
      </button>
    </header>
    <main class="order-entry-popup__body">
      <OrderForm
        :initial-phone="initialPhone"
        :initial-date="initialDate"
        :initial-start-time="initialStartTime"
        :initial-cast="initialCast"
        :initial-customer-id="initialCustomerId"
        :embedded="true"
        :show-flow-hint="false"
        @created="onCreated"
        @cancel="onCancel"
      />
    </main>
  </div>
  <LayoutOperator v-else>
    <template #title>予約フロー</template>
    <OrderForm
      :initial-phone="initialPhone"
      :initial-date="initialDate"
      :initial-start-time="initialStartTime"
      :initial-cast="initialCast"
      :initial-customer-id="initialCustomerId"
      @created="onCreated"
      @cancel="onCancel"
    />
  </LayoutOperator>
</template>

<style scoped>
.order-entry-popup {
  min-height: 100vh;
  background: #f8fafc;
}

.order-entry-popup__header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px;
  background: rgba(255, 255, 255, 0.96);
  border-bottom: 1px solid #e2e8f0;
  backdrop-filter: blur(10px);
}

.order-entry-popup__header h1 {
  margin: 1px 0 0;
  font-size: 20px;
}

.order-entry-popup__eyebrow {
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
}

.order-entry-popup__body {
  max-width: 720px;
  margin: 0 auto;
  padding: 18px;
}
</style>
