<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'

const props = defineProps({
  date: { type: String, required: true },
  casts: { type: Array, default: () => [] },
  items: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'saved'])

const types = [
  { value: 'BREAK', label: '休憩' },
  { value: 'LATE', label: '遅刻' },
  { value: 'EARLY_LEAVE', label: '早退' },
  { value: 'OUT', label: '中抜け' },
  { value: 'CHANGEOVER', label: '入れ替え' },
  { value: 'STORE', label: '店舗都合' },
  { value: 'OTHER', label: 'その他' },
]

const editingId = ref(null)
const castId = ref('')
const unavailableType = ref('BREAK')
const startTime = ref('12:00')
const endTime = ref('13:00')
const memo = ref('')
const saving = ref(false)
const deletingId = ref(null)
const error = ref('')

function resetForm() {
  editingId.value = null
  castId.value = props.casts[0]?.id || ''
  unavailableType.value = 'BREAK'
  startTime.value = '12:00'
  endTime.value = '13:00'
  memo.value = ''
  error.value = ''
}

function editItem(item) {
  editingId.value = item.id
  castId.value = item.cast_id
  unavailableType.value = item.type
  startTime.value = item.start_time_extended
  endTime.value = item.end_time_extended
  memo.value = item.memo || ''
  error.value = ''
}

async function save() {
  if (!castId.value) {
    error.value = 'キャストを選択してください'
    return
  }
  saving.value = true
  error.value = ''
  const body = {
    cast: Number(castId.value),
    business_date: props.date,
    start_time_extended: startTime.value,
    end_time_extended: endTime.value,
    type: unavailableType.value,
    memo: memo.value,
  }
  try {
    if (editingId.value) {
      await api.updateCastUnavailableTime(editingId.value, body)
    } else {
      await api.createCastUnavailableTime(body)
    }
    resetForm()
    emit('saved')
  } catch (e) {
    error.value = e.message || '予約不可時間の保存に失敗しました'
  } finally {
    saving.value = false
  }
}

async function remove(item) {
  if (!window.confirm(`${item.cast_name}の${item.type_display}を削除しますか？`)) return
  deletingId.value = item.id
  error.value = ''
  try {
    await api.deleteCastUnavailableTime(item.id)
    if (editingId.value === item.id) resetForm()
    emit('saved')
  } catch (e) {
    error.value = e.message || '予約不可時間の削除に失敗しました'
  } finally {
    deletingId.value = null
  }
}

onMounted(resetForm)
</script>

<template>
  <div class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="emit('close')">
    <div class="modal-dialog modal-lg modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="ti ti-clock-pause me-1"></i>予約不可時間（{{ date }}）</h5>
          <button type="button" class="btn-close" @click="emit('close')"></button>
        </div>
        <div class="modal-body">
          <div class="alert alert-info py-2 px-3 small">
            休憩・遅刻・早退・中抜けなど、予約を受けられない時間を登録します。
            シフト外や既存予約と重なる時間は保存できません。
          </div>
          <div v-if="error" class="alert alert-danger py-2 px-3 small">{{ error }}</div>

          <form class="row g-2 mb-4" @submit.prevent="save">
            <div class="col-md-5">
              <label class="form-label small">キャスト</label>
              <select v-model="castId" class="form-select" required>
                <option value="" disabled>選択してください</option>
                <option v-for="cast in casts" :key="cast.id" :value="cast.id">{{ cast.name }}</option>
              </select>
            </div>
            <div class="col-md-3">
              <label class="form-label small">種別</label>
              <select v-model="unavailableType" class="form-select">
                <option v-for="item in types" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </div>
            <div class="col-6 col-md-2">
              <label class="form-label small">開始</label>
              <input v-model.trim="startTime" class="form-control" placeholder="12:00" pattern="[0-2][0-9]:[0-5][0-9]" required>
            </div>
            <div class="col-6 col-md-2">
              <label class="form-label small">終了</label>
              <input v-model.trim="endTime" class="form-control" placeholder="13:00" pattern="[0-2][0-9]:[0-5][0-9]" required>
            </div>
            <div class="col-md-9">
              <label class="form-label small">メモ（任意）</label>
              <input v-model="memo" class="form-control" maxlength="500" placeholder="例: 食事休憩">
            </div>
            <div class="col-md-3 d-flex align-items-end gap-2">
              <button type="submit" class="btn btn-primary flex-grow-1" :disabled="saving">
                {{ saving ? '保存中...' : editingId ? '更新' : '追加' }}
              </button>
              <button v-if="editingId" type="button" class="btn btn-outline-secondary" @click="resetForm">取消</button>
            </div>
          </form>

          <h6>登録済み</h6>
          <div v-if="!items.length" class="text-muted small py-3 text-center">この日の予約不可時間はありません</div>
          <div v-else class="list-group">
            <div v-for="item in items" :key="item.id" class="list-group-item d-flex align-items-center gap-2">
              <div class="flex-grow-1">
                <strong>{{ item.cast_name }}</strong>
                <span class="badge text-bg-secondary ms-2">{{ item.type_display }}</span>
                <div class="small mt-1">{{ item.start_time_extended }}〜{{ item.end_time_extended }}</div>
                <div v-if="item.memo" class="small text-muted">{{ item.memo }}</div>
              </div>
              <button class="btn btn-sm btn-outline-primary" @click="editItem(item)">編集</button>
              <button class="btn btn-sm btn-outline-danger" :disabled="deletingId === item.id" @click="remove(item)">削除</button>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline-secondary" @click="emit('close')">閉じる</button>
        </div>
      </div>
    </div>
  </div>
</template>
