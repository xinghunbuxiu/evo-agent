<template>
  <div class="rounded-2xl border border-violet-200 bg-violet-50/50 p-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="max-w-2xl">
        <div class="text-sm font-semibold text-violet-950">岗位工种</div>
        <p class="mt-1 text-sm leading-6 text-violet-900">
          业务部门下的工种由你定义。需要自动化能力时绑定 openSpec 执行器；审核员、测试员等协作岗可不绑执行器。
        </p>
      </div>
      <button
        type="button"
        @click="loadWorkTypesLocal"
        :disabled="workTypesLoading"
        class="rounded-full border border-violet-300 bg-white px-3 py-1.5 text-xs font-medium text-violet-800 hover:bg-violet-100 disabled:opacity-60"
      >
        {{ workTypesLoading ? '刷新中...' : '刷新列表' }}
      </button>
    </div>

    <div v-if="workTypeItems.length" class="mt-4 space-y-3">
      <article
        v-for="item in workTypeItems"
        :key="item.work_type_id"
        class="rounded-xl border border-violet-200 bg-white px-4 py-4"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="font-medium text-slate-900">{{ item.title || item.work_type_id }}</div>
            <div class="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
              <span>ID {{ item.work_type_id }}</span>
              <span v-if="item.department_label || item.department_id">· {{ item.department_label || item.department_id }}</span>
              <span v-if="item.worker_id">· 执行器 {{ item.worker_id }}</span>
              <span v-else>· 人工协作岗</span>
            </div>
            <p v-if="item.goal_schema?.default_goal" class="mt-2 text-sm text-slate-600">{{ item.goal_schema.default_goal }}</p>
            <div class="mt-2 flex flex-wrap gap-2 text-[11px]">
              <span
                v-if="item.worker_id"
                class="rounded-full px-2 py-0.5"
                :class="workerEnabled(item.worker_id) ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'"
              >
                执行器 {{ workerEnabled(item.worker_id) ? '已启用' : '未启用' }}
              </span>
              <span v-else class="rounded-full bg-sky-100 px-2 py-0.5 text-sky-800">无需执行器</span>
            </div>
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              @click="goToPortraitBootstrap(item.work_type_id)"
              class="rounded-lg border border-violet-300 bg-white px-3 py-1.5 text-xs font-medium text-violet-800 hover:bg-violet-50"
            >
              去建档
            </button>
            <button
              type="button"
              @click="removeWorkType(item.work_type_id)"
              :disabled="workTypesSaving"
              class="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-60"
            >
              删除
            </button>
          </div>
        </div>
      </article>
    </div>
    <div v-else class="mt-4 rounded-xl border border-dashed border-violet-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
      还没有岗位工种。先用下方表单添加，或让育成师在派任务时快速创建辅助工种。
    </div>

    <div class="mt-5 rounded-xl border border-violet-300 bg-white p-5">
      <div class="text-sm font-semibold text-slate-900">添加工种</div>
      <p class="mt-1 text-xs text-slate-500">执行器列表来自平台已注册的 openSpec 插件，非页面写死。</p>

      <div class="mt-4 flex flex-wrap gap-2">
        <button
          v-for="preset in auxiliaryPresets"
          :key="preset.preset_key"
          type="button"
          class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-800 hover:bg-sky-100"
          @click="fillAuxiliaryPreset(preset)"
        >
          + {{ preset.preset_label }}
        </button>
      </div>

      <div class="mt-4 grid gap-4 md:grid-cols-2">
        <label class="block text-sm text-slate-700">
          <span class="mb-1 block text-xs text-slate-500">工种 ID</span>
          <input v-model="draft.work_type_id" type="text" placeholder="例如 quality_reviewer" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
        </label>
        <label class="block text-sm text-slate-700">
          <span class="mb-1 block text-xs text-slate-500">显示名称</span>
          <input v-model="draft.title" type="text" placeholder="例如 审核员" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
        </label>
        <label class="block text-sm text-slate-700">
          <span class="mb-1 block text-xs text-slate-500">所属部门</span>
          <select v-model="draft.department_id" class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
            <option v-for="item in departmentOptions" :key="item.id" :value="item.id">{{ item.label }}</option>
          </select>
        </label>
        <label class="block text-sm text-slate-700 md:col-span-2">
          <span class="mb-1 block text-xs text-slate-500">默认目标</span>
          <textarea v-model="draft.default_goal" rows="2" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="这名岗位成员首要要达成什么" />
        </label>
      </div>

      <label class="mt-4 inline-flex items-center gap-2 text-sm text-slate-700">
        <input v-model="draft.requires_worker" type="checkbox">
        <span>本工种需要自动化执行器（取消勾选则为纯协作岗，如审核员/测试员）</span>
      </label>

      <div v-if="draft.requires_worker" class="mt-4 space-y-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
        <label class="block text-sm text-slate-700">
          <span class="mb-1 block text-xs text-slate-500">执行器插件（来自注册表）</span>
          <select v-model="draft.worker_id" class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm" @change="onWorkerSelect">
            <option value="">请选择</option>
            <option v-for="item in workerOptions" :key="item.worker_id" :value="item.worker_id">
              {{ item.title || item.worker_id }}（{{ item.capability_type || 'plugin' }}）
            </option>
          </select>
        </label>
        <label class="inline-flex items-center gap-2 text-sm text-slate-700">
          <input v-model="draft.enable_worker" type="checkbox">
          <span>保存后启用该执行器（需重启 Admin）</span>
        </label>
        <button
          v-if="examplePresetForWorker"
          type="button"
          class="rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-800 hover:bg-emerald-100"
          @click="fillExamplePreset"
        >
          填入「{{ examplePresetForWorker.preset_label }}」示例
        </button>
      </div>

      <div class="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          @click="submitWorkType"
          :disabled="workTypesSaving"
          class="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-60"
        >
          {{ workTypesSaving ? '保存中...' : '保存工种' }}
        </button>
        <button
          type="button"
          @click="fillFromSelectedWorker"
          :disabled="!draft.worker_id || !draft.requires_worker"
          class="rounded-lg border border-violet-300 bg-white px-4 py-2 text-sm font-medium text-violet-800 hover:bg-violet-50 disabled:opacity-60"
        >
          从执行器填充
        </button>
      </div>
      <p v-if="workTypesMessage" class="mt-3 text-sm" :class="workTypesSuccess ? 'text-green-600' : 'text-red-600'">
        {{ workTypesMessage }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  AUXILIARY_WORK_TYPE_PRESETS,
  buildAuxiliaryWorkType,
  buildWorkTypeFromWorker,
  findWorkTypeExamplePreset,
  getWorkTypes,
  RESERVED_WORK_TYPE_IDS,
  resolveDepartmentLabel,
  saveWorkTypes,
  type WorkTypeItem,
  type WorkTypePreset,
} from '../api/workTypes'
import { updateWorkerRegistry, type WorkerManifest, type WorkerRegistryPayload } from '../api/plugins'

const props = defineProps<{
  workerRegistry: WorkerRegistryPayload | null
  workerEnabledDraft: Record<string, boolean>
}>()

const emit = defineEmits<{
  (event: 'work-types-updated'): void
  (event: 'request-enable-worker', workerId: string, enabled: boolean): void
}>()

const router = useRouter()
const portraitBootstrapPath = '/organization/trainer/talent_development_officer/workspace'
const auxiliaryPresets = AUXILIARY_WORK_TYPE_PRESETS

const departmentOptions = [
  { id: 'operations', label: '运营' },
  { id: 'rnd', label: '研发' },
  { id: 'quality', label: '质量' },
]

const goToPortraitBootstrap = (workTypeId: string) => {
  const normalized = String(workTypeId || '').trim()
  if (!normalized) return
  router.push({
    path: portraitBootstrapPath,
    query: { mode: 'portrait', portraitTab: 'summary', work_type_id: normalized },
  })
}

const workTypesLoading = ref(false)
const workTypesSaving = ref(false)
const workTypesMessage = ref('')
const workTypesSuccess = ref(false)
const workTypeItems = ref<WorkTypeItem[]>([])
const version = ref(1)

const emptyDraft = () => ({
  work_type_id: '',
  title: '',
  department_id: 'operations',
  worker_id: '',
  default_goal: '',
  requires_worker: true,
  enable_worker: true,
})

const draft = ref(emptyDraft())

const workerOptions = computed<WorkerManifest[]>(() => (
  Object.values(props.workerRegistry?.manifests || {})
    .filter((item) => item.worker_id && item.worker_id !== 'talent_development_officer')
    .sort((left, right) => String(left.title || left.worker_id).localeCompare(String(right.title || right.worker_id), 'zh-CN'))
))

const examplePresetForWorker = computed(() => findWorkTypeExamplePreset(draft.value.worker_id))

const workerEnabled = (workerId?: string) => {
  const id = String(workerId || '').trim()
  if (!id) return false
  return Boolean(props.workerEnabledDraft[id])
}

const normalizeWorkTypeId = (value: string) => (
  String(value || '').trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '')
)

const loadWorkTypesLocal = async () => {
  workTypesLoading.value = true
  workTypesMessage.value = ''
  try {
    const result = await getWorkTypes()
    workTypeItems.value = result.data?.items || []
    version.value = Number(result.data?.version || 1)
  } catch {
    workTypesSuccess.value = false
    workTypesMessage.value = '工种列表加载失败'
  } finally {
    workTypesLoading.value = false
  }
}

const onWorkerSelect = () => {
  const manifest = workerOptions.value.find((item) => item.worker_id === draft.value.worker_id)
  if (!manifest) return
  const filled = buildWorkTypeFromWorker(manifest, {
    work_type_id: draft.value.work_type_id || undefined,
    title: draft.value.title || undefined,
    goal_schema: { default_goal: draft.value.default_goal || '' },
  })
  if (!draft.value.work_type_id) draft.value.work_type_id = filled.work_type_id
  if (!draft.value.title) draft.value.title = filled.title || filled.work_type_id
}

const fillAuxiliaryPreset = (preset: WorkTypePreset) => {
  draft.value.work_type_id = String(preset.work_type_id || '')
  draft.value.title = String(preset.title || '')
  draft.value.department_id = String(preset.department_id || 'quality')
  draft.value.default_goal = String(preset.goal_schema?.default_goal || '')
  draft.value.requires_worker = false
  draft.value.worker_id = ''
  draft.value.enable_worker = false
  workTypesSuccess.value = true
  workTypesMessage.value = `已填入「${preset.preset_label}」模板，确认后保存即可。`
}

const fillExamplePreset = () => {
  const preset = examplePresetForWorker.value
  const manifest = workerOptions.value.find((item) => item.worker_id === draft.value.worker_id)
  if (!preset || !manifest) return
  const filled = buildWorkTypeFromWorker(manifest, preset)
  draft.value.work_type_id = filled.work_type_id
  draft.value.title = filled.title || filled.work_type_id
  draft.value.department_id = String(preset.department_id || draft.value.department_id)
  draft.value.default_goal = String(preset.goal_schema?.default_goal || '')
  draft.value.requires_worker = true
  draft.value.enable_worker = true
  workTypesSuccess.value = true
  workTypesMessage.value = `已填入「${preset.preset_label}」示例，确认后保存。`
}

const fillFromSelectedWorker = () => {
  const manifest = workerOptions.value.find((item) => item.worker_id === draft.value.worker_id)
  if (!manifest) return
  const filled = buildWorkTypeFromWorker(manifest, { goal_schema: { default_goal: draft.value.default_goal || '' } })
  draft.value.work_type_id = draft.value.work_type_id || filled.work_type_id
  draft.value.title = draft.value.title || filled.title || filled.work_type_id
}

const stripRuntimeFields = (items: WorkTypeItem[]): WorkTypeItem[] => (
  items.map(({ runtime_route: _route, ...rest }) => rest)
)

const persistWorkTypes = async (items: WorkTypeItem[]) => {
  const result = await saveWorkTypes({ version: version.value, items: stripRuntimeFields(items) })
  if (result.code !== 0 || result.success === false) throw new Error(result.message || '工种保存失败')
  workTypeItems.value = result.data?.items || items
  version.value = Number(result.data?.version || version.value)
  emit('work-types-updated')
}

const submitWorkType = async () => {
  const workTypeId = normalizeWorkTypeId(draft.value.work_type_id)
  const title = String(draft.value.title || '').trim()
  const workerId = String(draft.value.worker_id || '').trim()
  if (!workTypeId) {
    workTypesMessage.value = '请填写工种 ID'
    workTypesSuccess.value = false
    return
  }
  if (RESERVED_WORK_TYPE_IDS.has(workTypeId)) {
    workTypesMessage.value = '该 ID 为系统内置职能保留'
    workTypesSuccess.value = false
    return
  }
  if (!title) {
    workTypesMessage.value = '请填写显示名称'
    workTypesSuccess.value = false
    return
  }
  if (draft.value.requires_worker && !workerId) {
    workTypesMessage.value = '需要执行器的工种请选择插件，或取消「需要自动化执行器」'
    workTypesSuccess.value = false
    return
  }
  if (workTypeItems.value.some((item) => item.work_type_id === workTypeId)) {
    workTypesMessage.value = `工种 ${workTypeId} 已存在`
    workTypesSuccess.value = false
    return
  }

  workTypesSaving.value = true
  workTypesMessage.value = ''
  try {
    const departmentId = String(draft.value.department_id || '').trim() || 'operations'
    let newItem: WorkTypeItem
    if (draft.value.requires_worker) {
      const manifest = workerOptions.value.find((item) => item.worker_id === workerId)
      if (!manifest) throw new Error('执行器不存在')
      const example = findWorkTypeExamplePreset(workerId)
      newItem = buildWorkTypeFromWorker(manifest, {
        work_type_id: workTypeId,
        title,
        worker_id: workerId,
        department_id: departmentId,
        department_label: resolveDepartmentLabel(departmentId),
        goal_schema: {
          default_goal: String(draft.value.default_goal || example?.goal_schema?.default_goal || '').trim(),
          deliverables: example?.goal_schema?.deliverables || [],
        },
        input_schema: example?.input_schema,
        closure_loop: example?.closure_loop,
      })
    } else {
      newItem = buildAuxiliaryWorkType({
        work_type_id: workTypeId,
        title,
        department_id: departmentId,
        default_goal: String(draft.value.default_goal || '').trim(),
      })
    }

    const usedWorker = draft.value.requires_worker && workerId
    await persistWorkTypes([...workTypeItems.value, newItem])

    if (usedWorker && draft.value.enable_worker) {
      emit('request-enable-worker', workerId, true)
      try {
        await updateWorkerRegistry({ [workerId]: { enabled: true } })
      } catch {
        workTypesMessage.value = '工种已保存，但执行器启用失败，请手动启用'
        workTypesSuccess.value = false
        return
      }
    }

    const savedTitle = title
    const hadWorker = usedWorker
    draft.value = emptyDraft()
    workTypesSuccess.value = true
    workTypesMessage.value = hadWorker
      ? `已添加工种「${savedTitle}」。如启用了执行器，请重启 Admin。`
      : `已添加工种「${savedTitle}」（协作岗，无需执行器）。`
    goToPortraitBootstrap(workTypeId)
  } catch {
    workTypesSuccess.value = false
    workTypesMessage.value = '工种保存失败'
  } finally {
    workTypesSaving.value = false
  }
}

const removeWorkType = async (workTypeId: string) => {
  const target = String(workTypeId || '').trim()
  if (!target || !window.confirm(`确定删除工种 ${target}？`)) return
  workTypesSaving.value = true
  try {
    await persistWorkTypes(workTypeItems.value.filter((item) => item.work_type_id !== target))
    workTypesSuccess.value = true
    workTypesMessage.value = `已删除工种 ${target}`
  } catch {
    workTypesSuccess.value = false
    workTypesMessage.value = '删除失败'
  } finally {
    workTypesSaving.value = false
  }
}

defineExpose({ loadWorkTypesLocal })
</script>
