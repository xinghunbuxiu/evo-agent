<template>
  <div class="space-y-3">
    <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
      <div class="font-medium text-slate-900">技能库</div>
      <p class="mt-2 leading-6">
        从 ExperienceStore 按当前工种/员工范围拉取已验证经验条目，供节点流水右侧「技能」Tab 查阅。
      </p>
    </div>

    <div v-if="loading" class="text-sm text-slate-500">加载技能中...</div>
    <div v-else-if="errorMessage" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      {{ errorMessage }}
    </div>

    <article
      v-for="skill in skills"
      :key="skill.skill_id"
      class="rounded-xl border border-slate-200 bg-white px-4 py-4"
    >
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div class="font-medium text-slate-900">{{ skill.title }}</div>
        <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">
          {{ skill.domain }}
        </span>
      </div>
      <p class="mt-2 text-sm leading-6 text-slate-600">{{ skill.summary || '暂无摘要' }}</p>
      <div class="mt-2 flex flex-wrap gap-2 text-[10px] text-slate-500">
        <span v-if="skill.member_id">员工 {{ skill.member_id }}</span>
        <span v-if="skill.task_id">任务 {{ skill.task_id }}</span>
        <span v-if="skill.quality_score != null">质量 {{ skill.quality_score }}</span>
      </div>
    </article>

    <div v-if="!loading && !skills.length && !errorMessage" class="text-sm text-slate-500">
      当前范围暂无技能条目；任务确认并沉淀经验后会逐步出现。
    </div>
  </div>
</template>

<script setup lang="ts">
import { inject, ref, watch } from 'vue'
import { getWorkNodeSkills, type WorkNodeSkill } from '../../api/workNodes'
import { companyConsoleKey } from '../../composables/companyConsole'

const props = defineProps<{
  workTypeId?: string
  memberId?: string
}>()

const consoleCtx = inject(companyConsoleKey)
const loading = ref(false)
const errorMessage = ref('')
const skills = ref<WorkNodeSkill[]>([])

const loadSkills = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await getWorkNodeSkills({
      tenant_id: consoleCtx?.tenantId.value || 'default',
      work_type_id: props.workTypeId || undefined,
      member_id: props.memberId || undefined,
      limit: 40,
    })
    skills.value = result.data?.items || []
  } catch (error) {
    skills.value = []
    errorMessage.value = error instanceof Error ? error.message : '技能加载失败'
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.workTypeId, props.memberId, consoleCtx?.tenantId.value],
  () => { void loadSkills() },
  { immediate: true },
)
</script>
