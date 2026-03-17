<script setup>
import { ref } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const models = [
  { key: 'cast', label: 'キャスト', hint: '必須: name / 任意: avatar_url' },
  { key: 'room', label: 'ルーム', hint: '必須: name / 任意: sort_order' },
  { key: 'course', label: 'コース', hint: '必須: name, duration, price' },
  { key: 'option', label: 'オプション', hint: '必須: name, price' },
  { key: 'customer', label: '顧客', hint: '必須: phone / 任意: display_name, flag, memo' },
]

const selectedModel = ref('cast')
const file = ref(null)
const preview = ref(null)
const result = ref(null)
const error = ref('')
const loading = ref(false)

function onFileChange(e) {
  file.value = e.target.files[0] || null
  preview.value = null
  result.value = null
  error.value = ''
}

async function onPreview() {
  if (!file.value) return
  loading.value = true
  error.value = ''
  preview.value = null
  try {
    preview.value = await api.csvPreview(selectedModel.value, file.value)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function onImport() {
  if (!file.value) return
  loading.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await api.csvImport(selectedModel.value, file.value)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function reset() {
  file.value = null
  preview.value = null
  result.value = null
  error.value = ''
  const input = document.getElementById('csv-file')
  if (input) input.value = ''
}
</script>

<template>
  <LayoutOperator>
    <template #title>CSVインポート</template>

    <div class="mb-3">
      <router-link to="/op/settings" class="btn btn-outline-secondary btn-sm">
        <i class="ti ti-arrow-left"></i> 設定に戻る
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div v-if="result" class="alert alert-success">
      インポート完了: {{ result.created }}件 作成 / {{ result.updated }}件 更新 (全{{ result.total_rows }}行)
      <button class="btn btn-sm btn-outline-success ms-2" @click="reset">続けてインポート</button>
    </div>

    <div class="card mb-4">
      <div class="card-header">
        <i class="ti ti-file-import"></i> CSVファイルを選択
      </div>
      <div class="card-body">
        <div class="mb-3">
          <label class="form-label">対象データ</label>
          <select v-model="selectedModel" class="form-select" :disabled="!!result">
            <option v-for="m in models" :key="m.key" :value="m.key">{{ m.label }}</option>
          </select>
          <small class="text-muted">{{ models.find(m => m.key === selectedModel)?.hint }}</small>
        </div>

        <div class="mb-3">
          <label class="form-label">CSVファイル</label>
          <input id="csv-file" type="file" class="form-control" accept=".csv" @change="onFileChange" :disabled="!!result" />
        </div>

        <div class="d-flex gap-2">
          <button class="btn btn-outline-primary" :disabled="!file || loading || !!result" @click="onPreview">
            <i class="ti ti-eye"></i> プレビュー
          </button>
          <button class="btn btn-primary" :disabled="!file || loading || !!result" @click="onImport">
            <i class="ti ti-upload"></i> {{ loading ? 'インポート中...' : 'インポート実行' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Preview -->
    <div v-if="preview" class="card">
      <div class="card-header">
        <i class="ti ti-table"></i> プレビュー (先頭{{ preview.preview.length }}行 / 全{{ preview.total_rows }}行)
      </div>
      <div class="card-body table-responsive">
        <table class="table table-sm table-bordered mb-0">
          <thead>
            <tr>
              <th v-for="h in preview.headers" :key="h">{{ h }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in preview.preview" :key="i">
              <td v-for="h in preview.headers" :key="h">{{ row[h] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </LayoutOperator>
</template>
