<script setup>
import { ref, onMounted } from 'vue'
import LayoutOperator from '../../components/LayoutOperator.vue'
import { api } from '../../api.js'

const loading = ref(true)
const error = ref('')
const rooms = ref([])
const areas = ref([])
const newAreaName = ref('')
const areaSaving = ref(false)

// Form
const showForm = ref(false)
const editingId = ref(null)
const form = ref(emptyForm())
const formError = ref('')
const saving = ref(false)

function emptyForm() {
  return {
    name: '', address: '', map_url: '', sms_notice: '',
    sort_order: 0, background_color: '', area: null,
  }
}

async function loadRooms() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.getRooms()
    rooms.value = Array.isArray(data) ? data : []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadAreas() {
  const data = await api.getAreas()
  areas.value = Array.isArray(data) ? data : []
}

onMounted(async () => {
  try {
    await Promise.all([loadRooms(), loadAreas()])
  } catch (e) {
    error.value = e.message
  }
})

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  formError.value = ''
  showForm.value = true
}

function openEdit(r) {
  editingId.value = r.id
  form.value = {
    name: r.name,
    address: r.address || '',
    map_url: r.map_url || '',
    sms_notice: r.sms_notice || '',
    sort_order: r.sort_order ?? 0,
    background_color: r.background_color || '',
    area: r.area || null,
  }
  formError.value = ''
  showForm.value = true
}

async function onSave() {
  saving.value = true
  formError.value = ''
  try {
    const payload = {
      name: form.value.name,
      address: form.value.address || '',
      map_url: form.value.map_url || '',
      sms_notice: form.value.sms_notice || '',
      sort_order: form.value.sort_order,
      background_color: form.value.background_color || '',
      area: form.value.area || null,
    }
    if (editingId.value) {
      await api.updateRoom(editingId.value, payload)
    } else {
      await api.createRoom(payload)
    }
    showForm.value = false
    await loadRooms()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function addArea() {
  if (!newAreaName.value.trim()) return
  areaSaving.value = true
  error.value = ''
  try {
    await api.createArea({ name: newAreaName.value.trim() })
    newAreaName.value = ''
    await loadAreas()
  } catch (e) {
    error.value = e.message
  } finally {
    areaSaving.value = false
  }
}

async function renameArea(area) {
  const name = window.prompt('エリア名を変更', area.name)
  if (name === null || name.trim() === area.name) return
  error.value = ''
  try {
    await api.updateArea(area.id, { name: name.trim() })
    await Promise.all([loadAreas(), loadRooms()])
  } catch (e) {
    error.value = e.message
  }
}

async function deleteArea(area) {
  if (!confirm(`エリア「${area.name}」を削除しますか？\n部屋・希望エリア・シフトで使用中の場合は削除できません。`)) return
  error.value = ''
  try {
    await api.deleteArea(area.id)
    await loadAreas()
  } catch (e) {
    error.value = e.message
  }
}

async function onDelete(r) {
  if (!confirm(`「${r.name}」を削除しますか？`)) return
  error.value = ''
  try {
    await api.deleteRoom(r.id)
    await loadRooms()
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <LayoutOperator>
    <template #title>ルーム管理</template>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <div class="card mb-4">
      <div class="card-header"><i class="ti ti-map-pin"></i> エリア管理</div>
      <div class="card-body">
        <p class="small text-muted">先にエリアを作成し、各ルーム・キャスト希望・シフトで選択します。表記ゆれを防ぐため、直接入力はできません。</p>
        <div class="input-group mb-3">
          <input v-model="newAreaName" class="form-control" maxlength="50" placeholder="例: 高田馬場" @keyup.enter="addArea">
          <button class="btn btn-outline-primary" :disabled="areaSaving || !newAreaName.trim()" @click="addArea">追加</button>
        </div>
        <div v-if="!areas.length" class="text-muted small">エリアが未登録です。先に追加してください。</div>
        <div v-else class="d-flex flex-wrap gap-2">
          <span v-for="area in areas" :key="area.id" class="badge bg-light text-dark border py-2">
            {{ area.name }}
            <button class="btn btn-link btn-sm p-0 ms-2" @click="renameArea(area)">変更</button>
            <button class="btn btn-link btn-sm p-0 ms-1 text-danger" @click="deleteArea(area)">削除</button>
          </span>
        </div>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-header d-flex align-items-center justify-content-between">
        <span><i class="ti ti-door"></i> ルーム一覧</span>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="ti ti-plus text-white"></i> ルーム追加
        </button>
      </div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-3">
          <div class="spinner-border text-primary"></div>
        </div>

        <div v-else-if="!rooms.length" class="text-muted text-center py-3">
          ルームが登録されていません
        </div>

        <div v-else class="table-responsive">
          <table class="table table-hover mb-0 rooms-table">
            <thead>
              <tr>
                <th>名前</th>
                <th style="width: 120px;">エリア</th>
                <th style="width: 100px;">表示順</th>
                <th style="width: 50px;"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rooms" :key="r.id">
                <td>
                  <div>{{ r.name }}</div>
                  <div v-if="r.address" class="room-address small text-muted">{{ r.address }}</div>
                  <a
                    v-if="r.map_url"
                    :href="r.map_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="small"
                  ><i class="ti ti-map-pin"></i> 地図を確認</a>
                  <div v-if="r.sms_notice" class="small text-warning-emphasis">
                    <i class="ti ti-alert-triangle"></i> {{ r.sms_notice }}
                  </div>
                </td>
                <td>
                  <span v-if="r.area_name" class="badge bg-light text-dark border">{{ r.area_name }}</span>
                  <span v-else class="text-muted small">未設定</span>
                </td>
                <td>{{ r.sort_order }}</td>
                <td>
                  <button class="btn btn-link p-0" @click="openEdit(r)">
                    <i class="ti ti-edit" style="font-size: 1.25rem;"></i>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Form modal -->
    <div v-if="showForm" class="modal d-block" style="background: rgba(0,0,0,0.3);" @click.self="showForm = false">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editingId ? 'ルーム編集' : 'ルーム追加' }}</h5>
            <button type="button" class="btn-close" @click="showForm = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

            <div class="mb-3">
              <label class="form-label">名前 <span class="text-danger">*</span></label>
              <input v-model="form.name" type="text" class="form-control" placeholder="ルーム名" />
            </div>
            <div class="mb-3">
              <label class="form-label">表示順</label>
              <input v-model.number="form.sort_order" type="number" class="form-control" min="0" />
            </div>
            <div class="mb-3">
              <label class="form-label">住所（任意）</label>
              <input v-model="form.address" type="text" class="form-control" placeholder="例: 東京都新宿区○○1-2-3 ○○ビル101" maxlength="255" />
              <div class="form-text">予約確定後、お客様の予約詳細とマイページに表示されます。</div>
            </div>
            <div class="mb-3">
              <label class="form-label">地図URL（任意）</label>
              <input
                v-model="form.map_url"
                type="url"
                class="form-control"
                placeholder="例: https://maps.app.goo.gl/..."
                maxlength="500"
              />
              <div class="form-text">予約確認SMSの地図案内に使用します。</div>
            </div>
            <div class="mb-3">
              <label class="form-label">SMS注意事項（任意）</label>
              <textarea
                v-model="form.sms_notice"
                class="form-control"
                rows="3"
                placeholder="例: 似た建物が多いため、建物名で検索してください。"
              ></textarea>
              <div class="form-text">このルームが予約に割り当てられた場合だけSMSへ差し込めます。</div>
            </div>
            <div class="mb-3">
              <label class="form-label">エリア（任意）</label>
              <select v-model="form.area" class="form-select">
                <option :value="null">未設定</option>
                <option v-for="area in areas.filter(a => a.is_active)" :key="area.id" :value="area.id">{{ area.name }}</option>
              </select>
              <div class="form-text">エリア管理で作成済みのエリアから選択します。空欄の場合は「未設定」として集計されます。</div>
            </div>
            <div class="mb-3">
              <label class="form-label">背景色</label>
              <div class="d-flex align-items-center gap-2">
                <input v-model="form.background_color" type="color"
                  class="form-control form-control-color" style="width: 64px;" />
                <input v-model="form.background_color" type="text" class="form-control"
                  placeholder="#RRGGBB (空欄なら自動配色)" />
                <button v-if="form.background_color" type="button"
                  class="btn btn-sm btn-outline-secondary" @click="form.background_color = ''">クリア</button>
              </div>
            </div>
          </div>
          <div class="modal-footer d-flex">
            <button v-if="editingId" class="btn btn-outline-danger me-auto" @click="onDelete({ id: editingId, name: form.name })">
              <i class="ti ti-trash"></i> 削除
            </button>
            <button class="btn btn-secondary" @click="showForm = false">キャンセル</button>
            <button class="btn btn-primary" :disabled="saving || !form.name.trim()" @click="onSave">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </LayoutOperator>
</template>

<style scoped>
.rooms-table {
  min-width: 620px;
}

@media (max-width: 575.98px) {
  .rooms-table {
    min-width: 0;
    table-layout: fixed;
  }

  .rooms-table th:nth-child(1),
  .rooms-table td:nth-child(1) {
    width: 47%;
  }

  .rooms-table th:nth-child(2),
  .rooms-table td:nth-child(2) {
    width: 27% !important;
  }

  .rooms-table th:nth-child(3),
  .rooms-table td:nth-child(3) {
    width: 14% !important;
  }

  .rooms-table th:nth-child(4),
  .rooms-table td:nth-child(4) {
    width: 12% !important;
  }

  .room-address {
    display: none;
  }
}
</style>
