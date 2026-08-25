<template>
  <div class="rounded-xl border border-violet-200 bg-violet-50/60 px-4 py-4">
    <div class="text-sm font-semibold text-violet-950">需要新工种？</div>
    <p class="mt-1 text-xs leading-5 text-violet-800">
      派任务时发现缺审核员、测试员等协作岗，可在此一键添加（无需执行器）。
    </p>
    <div class="mt-3 flex flex-wrap gap-2">
      <button
        v-for="preset in auxiliaryPresets"
        :key="preset.preset_key"
        type="button"
        class="rounded-full border border-violet-200 bg-white px-3 py-1.5 text-xs font-medium text-violet-800 hover:bg-violet-100 disabled:opacity-60"
        :disabled="saving || exists(preset.work_type_id)"
        @click="savePreset(preset)"
      >
        + {{ preset.preset_label }}
      </button>
      <router-link
        to="/organization/parent/workspace?section=worktypes"
        class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
      >
        公司设置完整表单 →
      </router-link>
    </div>
    <p v-if="message" class="mt-3 text-xs" :class="success ? 'text-emerald-700' : 'text-red-600'">{{ message }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  AUXILIARY_WORK_TYPE_PRESETS,
  buildAuxiliaryWorkType,
  getWorkTypes,
  saveWorkTypes,
  type WorkTypePreset,
} from '../api/workTypes'

const props = defineProps<{
  existingWorkTypeIds?: string[]
}>()

const emit = defineEmits<{
  saved: [workTypeId: string]
}>()

const auxiliaryPresets = AUXILIARY_WORK_TYPE_PRESETS
const saving = ref(false)
const message = ref('')
const success = ref(false)

const exists = (workTypeId?: string | null) => {
  const id = String(workTypeId || '').trim()
  return Boolean(id && (props.existingWorkTypeIds || []).includes(id))
}

const savePreset = async (preset: WorkTypePreset) => {
  const workTypeId = String(preset.work_type_id || '').trim()
  if (!workTypeId || exists(workTypeId)) return
  saving.value = true
  message.value = ''
  try {
    const current = await getWorkTypes()
    const items = current.data?.items || []
    const version = Number(current.data?.version || 1)
    const newItem = buildAuxiliaryWorkType({
      work_type_id: workTypeId,
      title: String(preset.title || workTypeId),
      department_id: String(preset.department_id || 'quality'),
      default_goal: String(preset.goal_schema?.default_goal || ''),
      deliverables: preset.goal_schema?.deliverables,
    })
    const result = await saveWorkTypes({ version, items: [...items, newItem] })
    if (result.code !== 0 || result.success === false) throw new Error(result.message || '保存失败')
    success.value = true
    message.value = `已添加工种「${preset.preset_label}」，可立即建档或派协作任务。`
    emit('saved', workTypeId)
  } catch (error) {
    success.value = false
    message.value = error instanceof Error ? error.message : '添加工种失败'
  } finally {
    saving.value = false
  }
}
</script>
