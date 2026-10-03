<script setup>
import { computed, onMounted, ref } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const starting = ref(false)
const error = ref('')
const activation = ref({ status: 'preparing', can_start: false, started_at: null })

const startedAtLabel = computed(() => {
  if (!activation.value.started_at) return ''
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(activation.value.started_at))
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    activation.value = await api.getLineActivation()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function startLine() {
  if (!window.confirm('LINE連携を開始します。開始後は自動通知とセラピストのLINE連携案内が有効になります。よろしいですか？')) return
  starting.value = true
  error.value = ''
  try {
    activation.value = await api.startLineActivation()
  } catch (e) {
    error.value = e.message
  } finally {
    starting.value = false
  }
}

onMounted(load)
</script>

<template>
  <LayoutOperator>
    <template #title>LINE連携開始</template>

    <router-link to="/op/settings" class="btn btn-sm btn-outline-secondary mb-3">
      <i class="ti ti-arrow-left"></i> 設定に戻る
    </router-link>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div v-if="loading" class="text-center py-5">
      <div class="spinner-border text-secondary"></div>
    </div>

    <div v-else class="activation-wrap">
      <div v-if="activation.status === 'preparing'" class="card activation-card">
        <div class="card-body text-center py-5">
          <div class="status-icon status-icon--preparing mb-3">
            <i class="ti ti-tool"></i>
          </div>
          <h5 class="mb-2">Roomink運営が接続準備中です</h5>
          <p class="text-muted mb-0">
            接続テストが完了すると、こちらからLINE連携を開始できるようになります。
          </p>
        </div>
      </div>

      <div v-else-if="activation.status === 'ready'" class="card activation-card border-primary">
        <div class="card-body text-center py-5">
          <div class="status-icon status-icon--ready mb-3">
            <i class="ti ti-circle-check"></i>
          </div>
          <div class="badge text-bg-primary mb-3">接続準備完了</div>
          <h5 class="mb-2">お好きなタイミングで開始できます</h5>
          <p class="text-muted mb-4">
            ボタンを押すまでは自動通知は始まりません。店舗内の準備が整ってから開始してください。
          </p>
          <button
            class="btn btn-primary btn-lg w-100"
            type="button"
            :disabled="starting || !activation.can_start"
            @click="startLine"
          >
            <span v-if="starting" class="spinner-border spinner-border-sm me-1"></span>
            LINE連携を開始する
          </button>
        </div>
      </div>

      <div v-else class="card activation-card border-success">
        <div class="card-body text-center py-5">
          <div class="status-icon status-icon--active mb-3">
            <i class="ti ti-check"></i>
          </div>
          <div class="badge text-bg-success mb-3">利用中</div>
          <h5 class="mb-2">LINE連携は開始済みです</h5>
          <p class="text-muted mb-0">
            <template v-if="startedAtLabel">{{ startedAtLabel }}から利用しています。</template>
            <template v-else>自動通知とセラピストのLINE連携をご利用いただけます。</template>
          </p>
        </div>
      </div>

      <p class="small text-muted text-center mt-3 mb-0">
        停止や設定変更が必要な場合はRoomink運営へご連絡ください。
      </p>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.activation-wrap {
  max-width: 560px;
  margin: 0 auto;
}
.activation-card {
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}
.status-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 2rem;
}
.status-icon--preparing {
  color: #64748b;
  background: #f1f5f9;
}
.status-icon--ready {
  color: #2563eb;
  background: #dbeafe;
}
.status-icon--active {
  color: #15803d;
  background: #dcfce7;
}

@media (max-width: 576px) {
  .activation-card .card-body {
    padding-left: 1.25rem;
    padding-right: 1.25rem;
  }
}
</style>
