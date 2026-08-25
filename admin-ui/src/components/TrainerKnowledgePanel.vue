<template>
  <div class="min-w-0 space-y-4">
    <div class="rounded-xl border border-sky-200 bg-sky-50/70 px-4 py-4">
      <div class="text-sm font-semibold text-sky-950">补知识闭环</div>
      <div class="mt-1 text-xs leading-5 text-sky-800">
        当员工卡在认知缺口时，系统会自动触发调研任务。这里按顺序推进：触发调研 → 形成候选 → 验证 → 回到正式任务。
      </div>
      <div class="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="step in knowledgeSteps"
          :key="step.key"
          class="rounded-lg border px-3 py-3 text-xs"
          :class="step.done ? 'border-emerald-200 bg-emerald-50 text-emerald-900' : step.active ? 'border-sky-300 bg-white text-sky-900' : 'border-slate-200 bg-white/80 text-slate-600'"
        >
          <div class="font-medium">{{ step.done ? '✓' : step.active ? '●' : '○' }} {{ step.title }}</div>
          <div class="mt-1 leading-5">{{ step.hint }}</div>
        </div>
      </div>
    </div>

    <div v-if="!learningTask" class="rounded-xl border border-dashed border-sky-200 bg-white px-4 py-8 text-center text-sm text-slate-600">
      <p>当前员工没有进行中的补知识任务。</p>
      <p class="mt-2 text-xs text-slate-500">可在员工卡住、Memory Hub 判断需外部学习时，点击下方触发调研。</p>
      <button
        type="button"
        class="mt-4 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-60"
        :disabled="memoryHubRunning || !memberId"
        @click="runMemoryHub"
      >
        {{ memoryHubRunning ? '触发中...' : '触发 Memory Hub 调研' }}
      </button>
      <p v-if="memoryHubMessage" class="mt-3 text-xs text-sky-700">{{ memoryHubMessage }}</p>
    </div>

    <div v-else class="rounded-xl border border-sky-200 bg-white px-4 py-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <div class="font-medium text-slate-900">{{ learningTask.title || learningTask.task_id }}</div>
          <div v-if="learningTask.goal" class="mt-2 text-sm leading-6 text-slate-700">{{ learningTask.goal }}</div>
        </div>
        <span class="rounded-full bg-sky-100 px-2.5 py-1 text-[11px] font-medium text-sky-800">
          {{ formatLearningTaskStatus(learningTask.status) }}
        </span>
      </div>

      <div v-if="plan.summary" class="mt-3 rounded-lg border border-sky-100 bg-sky-50 px-3 py-3 text-xs text-sky-900">
        <div class="font-medium">训练计划回写</div>
        <div class="mt-1 leading-5">{{ plan.summary }}</div>
        <div v-if="plan.nextAction" class="mt-2 text-sky-800">{{ plan.nextAction }}</div>
      </div>

      <div v-if="learningTask.queries?.length" class="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
        <div class="font-medium text-slate-900">调研问题</div>
        <div v-for="(query, index) in learningTask.queries" :key="`kq-${index}`" class="mt-1">
          {{ index + 1 }}. {{ query }}
        </div>
      </div>

      <div class="mt-4 flex flex-wrap gap-2">
        <button
          v-if="canValidate"
          type="button"
          class="rounded-lg border border-sky-300 bg-white px-4 py-2 text-sm font-medium text-sky-800 hover:bg-sky-50 disabled:opacity-60"
          :disabled="validating"
          @click="emit('validate')"
        >
          {{ validating ? '验证中...' : '启动补知识验证' }}
        </button>
        <button
          v-if="plan.followupRecommendationId"
          type="button"
          class="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          @click="emit('go-dispatch')"
        >
          去采纳补知识后任务
        </button>
        <button
          type="button"
          class="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          :disabled="memoryHubRunning || !memberId"
          @click="runMemoryHub"
        >
          {{ memoryHubRunning ? '刷新中...' : '刷新调研状态' }}
        </button>
      </div>
      <p v-if="memoryHubMessage" class="mt-3 text-xs text-sky-700">{{ memoryHubMessage }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { LearningTask } from '../api/plugins'
import { runAutonomyMemoryHub } from '../api/plugins'
import {
  buildMemberKnowledgeLearningPlan,
  formatLearningTaskStatus,
} from '../utils/memberEvolutionView'

const props = defineProps<{
  memberId: string
  memberDraft: Record<string, any> | null
  learningTask: LearningTask | null
  tenantId?: string
  validating?: boolean
  canValidate?: boolean
}>()

const emit = defineEmits<{
  validate: []
  'go-dispatch': []
  refreshed: []
}>()

const memoryHubRunning = ref(false)
const memoryHubMessage = ref('')

const plan = computed(() => buildMemberKnowledgeLearningPlan(props.memberDraft))

const status = computed(() => String(props.learningTask?.status || plan.value.status || '').trim())

const knowledgeSteps = computed(() => {
  const current = status.value
  const order = ['needs_learning', 'researching', 'candidate_found', 'ready_for_validation', 'validating', 'validated_improved', 'validated_unchanged', 'resolved']
  const index = order.indexOf(current)
  const stepIndex = (key: string) => {
    if (key === 'trigger') return index >= 0 || Boolean(props.learningTask)
    if (key === 'candidate') return index >= order.indexOf('candidate_found')
    if (key === 'validate') return index >= order.indexOf('ready_for_validation')
    if (key === 'followup') return index >= order.indexOf('validated_improved') || Boolean(plan.value.followupRecommendationId)
    return false
  }
  const activeKey = !props.learningTask
    ? 'trigger'
    : current === 'researching' || current === 'needs_learning'
      ? 'trigger'
      : current === 'candidate_found'
        ? 'candidate'
        : current === 'ready_for_validation' || current === 'validating'
          ? 'validate'
          : 'followup'
  return [
    { key: 'trigger', title: '1. 触发调研', hint: 'Memory Hub 判断缺口并生成学习任务', done: stepIndex('trigger'), active: activeKey === 'trigger' },
    { key: 'candidate', title: '2. 形成候选', hint: '系统整理可执行方案摘要', done: stepIndex('candidate'), active: activeKey === 'candidate' },
    { key: 'validate', title: '3. 启动验证', hint: '最小验证补知识结论是否有效', done: stepIndex('validate'), active: activeKey === 'validate' },
    { key: 'followup', title: '4. 回到任务', hint: '采纳补知识后的正式任务建议', done: stepIndex('followup'), active: activeKey === 'followup' },
  ]
})

const runMemoryHub = async () => {
  if (!props.memberId) return
  memoryHubRunning.value = true
  memoryHubMessage.value = ''
  try {
    const result = await runAutonomyMemoryHub({
      tenant_id: props.tenantId || 'default',
      member_id: props.memberId,
      trigger: 'trainer_knowledge_panel',
    })
    memoryHubMessage.value = result.message || '调研状态已刷新'
    emit('refreshed')
  } catch (err) {
    memoryHubMessage.value = err instanceof Error ? err.message : '触发失败'
  } finally {
    memoryHubRunning.value = false
  }
}
</script>
