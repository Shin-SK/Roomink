<script setup>
import { ref, computed, onMounted } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'
import { getAuthRole } from '../../router.js'

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref('')

const items = ref([])
const placeholders = ref([])

const isManager = computed(() => getAuthRole() === 'manager')

const placeholderHelp = {
  customer_name: 'お客様名',
  date: '予約日（2026-07-15）',
  start_time: '開始時刻（18:00）',
  end_time: '終了時刻（23:00）',
  course_name: 'コース名',
  cast_name: '担当キャスト名',
  room_name: 'ルーム名',
  payment_method: '支払方法（現金／カード／PayPay／未設定）',
  total_price: '合計金額（カンマ区切り）',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getSmsTemplates()
    items.value = data.items
    placeholders.value = data.placeholders
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    const data = await api.updateSmsTemplates(
      items.value.map(i => ({
        payment_method: i.payment_method,
        body: i.body,
        is_active: i.is_active,
      }))
    )
    items.value = data.items
    success.value = '保存しました'
    setTimeout(() => { success.value = '' }, 3000)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

function useDefault(item) {
  item.body = item.default_body
}

function insertPlaceholder(item, name) {
  item.body = `${item.body || ''}{${name}}`
}

onMounted(load)
</script>

<template>
  <LayoutOperator>
    <template #title>SMS文面設定</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div class="alert alert-info small">
      <i class="ti ti-info-circle"></i>
      予約確定時にお客様へ送るSMSの文面を、<strong>会計（支払）方法ごと</strong>に設定できます。
      「この文面を使う」がOFF、または本文が空の場合は、従来どおりの既定文言で送信されます。
    </div>

    <div v-if="!isManager" class="alert alert-warning small">
      <i class="ti ti-lock"></i> 閲覧のみ可能です。編集はマネージャーのみ行えます。
    </div>

    <div v-if="error" class="alert alert-danger" style="white-space: pre-wrap;">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <div v-if="loading" class="text-center py-4">
      <div class="spinner-border text-primary"></div>
    </div>

    <template v-else>
      <!-- 差し込み項目 -->
      <div class="card mb-3">
        <div class="card-header"><i class="ti ti-braces"></i> 使用可能な差し込み項目</div>
        <div class="card-body">
          <table class="table table-sm mb-0">
            <tbody>
              <tr v-for="p in placeholders" :key="p">
                <td style="width: 40%;"><code>{{ '{' + p + '}' }}</code></td>
                <td class="text-muted small">{{ placeholderHelp[p] || '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 支払方法ごとの文面 -->
      <div v-for="item in items" :key="item.payment_method" class="card mb-3">
        <div class="card-header d-flex align-items-center justify-content-between">
          <span><i class="ti ti-message"></i> 予約確認SMS ／ {{ item.payment_method_label }}</span>
          <div class="form-check form-switch mb-0">
            <input
              :id="`active-${item.payment_method}`"
              v-model="item.is_active"
              class="form-check-input"
              type="checkbox"
              :disabled="!isManager"
            />
            <label class="form-check-label small" :for="`active-${item.payment_method}`">
              この文面を使う
            </label>
          </div>
        </div>
        <div class="card-body">
          <textarea
            v-model="item.body"
            class="form-control form-control-sm"
            rows="6"
            :disabled="!isManager"
            :placeholder="item.default_body"
          ></textarea>

          <div v-if="isManager" class="mt-2 d-flex flex-wrap gap-1">
            <button
              v-for="p in placeholders"
              :key="p"
              class="btn btn-outline-secondary btn-sm py-0"
              style="font-size: 0.72rem;"
              @click="insertPlaceholder(item, p)"
            >{{ '{' + p + '}' }}</button>
          </div>

          <div class="d-flex align-items-center justify-content-between mt-2">
            <small class="text-muted">
              <template v-if="item.updated_by_name">最終更新: {{ item.updated_by_name }}</template>
              <template v-else>未設定（既定文言で送信されます）</template>
            </small>
            <button
              v-if="isManager"
              class="btn btn-link btn-sm p-0"
              @click="useDefault(item)"
            >既定文言を読み込む</button>
          </div>

          <details class="mt-2">
            <summary class="small text-muted" style="cursor: pointer;">既定文言を確認する</summary>
            <pre class="default-body small mt-2 mb-0">{{ item.default_body }}</pre>
          </details>
        </div>
      </div>

      <button
        v-if="isManager"
        class="btn btn-primary w-100 mb-4"
        :disabled="saving"
        @click="onSave"
      >
        <i class="ti ti-device-floppy"></i> {{ saving ? '保存中...' : '保存' }}
      </button>
    </template>
  </LayoutOperator>
</template>

<style scoped>
.default-body {
  background: #f7f7f7;
  padding: 0.5rem;
  border-radius: 4px;
  white-space: pre-wrap;
  color: #555;
}
</style>
