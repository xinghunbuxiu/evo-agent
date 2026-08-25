<template>
  <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
    <div class="flex items-start justify-between gap-4 mb-4">
      <div>
        <h2 class="text-lg font-semibold">自主研究状态</h2>
        <p class="text-slate-500 text-sm mt-1">当前先围绕第一个自媒体孩子观察自主研究、任务推进和复盘沉淀是否真正跑通。</p>
      </div>
      <button
        @click="loadAutonomyStatus"
        :disabled="autonomyLoading"
        class="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
      >
        {{ autonomyLoading ? '刷新中...' : '刷新状态' }}
      </button>
    </div>

    <div class="mb-4 rounded-2xl border border-sky-200 bg-sky-50/60 px-4 py-4 text-sm text-sky-950">
      <div class="font-medium">这块看什么</div>
      <div class="mt-2 leading-6">
        先看系统是不是在持续观察、最近有没有报错、下一步准备研究什么。只有需要判断研究质量时，再展开下面的分析与重构细项。
      </div>
    </div>

    <div class="grid gap-3 md:grid-cols-4">
      <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">研究开关</div>
        <div class="mt-2 font-medium text-slate-900">{{ autonomyStatus?.enabled ? '开启' : '关闭' }}</div>
      </div>
      <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">当前工种</div>
        <div class="mt-2 font-medium text-slate-900">{{ autonomyStatus?.domain || '--' }}</div>
      </div>
      <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">当前状态</div>
        <div class="mt-2 font-medium text-slate-900">{{ formatResearchState(autonomyStatus?.status) }}</div>
      </div>
      <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">观察周期</div>
        <div class="mt-2 font-medium text-slate-900">{{ autonomyStatus?.loop_interval_seconds || '--' }}s</div>
      </div>
    </div>

    <div class="mt-4 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
      <div>最近运行：{{ autonomyStatus?.last_run_at || '--' }}</div>
      <div class="mt-1">最近错误：{{ autonomyStatus?.last_error || '无' }}</div>
    </div>

    <div v-if="autonomyEntries.length" class="mt-4 space-y-3">
      <div
        v-for="entry in autonomyEntries"
        :key="`${entry.tenantId}-${entry.sourceDir}`"
        class="rounded-xl border border-slate-200 bg-white px-4 py-4"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-sm font-medium text-slate-900">{{ entry.tenantId }}</div>
            <div class="mt-1 text-xs text-slate-500 break-all">{{ entry.sourceDir }}</div>
          </div>
          <div class="text-right text-xs text-slate-500">
            <div>{{ formatResearchState(entry.diagnosis?.research_state, '待观察') }}</div>
            <div class="mt-1">{{ entry.diagnosis?.stable ? '稳定' : '研究中' }}</div>
          </div>
        </div>
        <div class="mt-3 text-sm text-slate-600">
          下一步：{{ entry.diagnosis?.next_action || '继续观察' }}
        </div>
        <details class="mt-3 rounded-lg border border-slate-200 bg-slate-50/80">
          <summary class="cursor-pointer list-none px-3 py-3">
            <div class="flex items-center justify-between gap-3">
              <div class="font-medium text-slate-900">研究细项</div>
              <div class="rounded-full bg-white px-3 py-1 text-[11px] text-slate-600">按需展开</div>
            </div>
          </summary>
          <div class="border-t border-slate-200 px-3 py-3">
            <div class="grid gap-3 md:grid-cols-2">
              <div class="rounded-lg bg-white px-3 py-3 text-sm text-slate-600">
                <div class="font-medium text-slate-800">分析阶段</div>
                <div class="mt-2">状态 {{ formatResearchStepStatus(entry.diagnosis?.analyze?.status) }}</div>
                <div class="mt-1">评估 {{ entry.diagnosis?.analyze?.evaluation_verdict || '--' }} / {{ formatScore(entry.diagnosis?.analyze?.evaluation_score) }}</div>
                <div v-if="entry.diagnosis?.analyze?.strategy_reasons?.length" class="mt-2 text-xs text-slate-500">
                  {{ entry.diagnosis.analyze.strategy_reasons.join(' / ') }}
                </div>
              </div>
              <div class="rounded-lg bg-white px-3 py-3 text-sm text-slate-600">
                <div class="font-medium text-slate-800">重构阶段</div>
                <div class="mt-2">状态 {{ formatResearchStepStatus(entry.diagnosis?.reconstruct?.status) }}</div>
                <div class="mt-1">评估 {{ entry.diagnosis?.reconstruct?.evaluation_verdict || '--' }} / {{ formatScore(entry.diagnosis?.reconstruct?.evaluation_score) }}</div>
                <div class="mt-1">问题 {{ entry.diagnosis?.reconstruct?.issue_category || '--' }}</div>
                <div v-if="entry.diagnosis?.reconstruct?.strategy_reasons?.length" class="mt-2 text-xs text-slate-500">
                  {{ entry.diagnosis.reconstruct.strategy_reasons.join(' / ') }}
                </div>
                <div v-if="entry.diagnosis?.reconstruct?.strategy_runtime_adjustments" class="mt-2 text-xs text-teal-700">
                  <span v-if="Number(entry.diagnosis.reconstruct.strategy_runtime_adjustments.growth_memory_bias || 0)">
                    成长 {{ formatSigned(entry.diagnosis.reconstruct.strategy_runtime_adjustments.growth_memory_bias) }}
                  </span>
                  <span v-if="Number(entry.diagnosis.reconstruct.strategy_runtime_adjustments.platform_shared_bias || 0)" class="ml-2">
                    共享 {{ formatSigned(entry.diagnosis.reconstruct.strategy_runtime_adjustments.platform_shared_bias) }}
                  </span>
                  <span v-if="Number(entry.diagnosis.reconstruct.strategy_runtime_adjustments.signature_memory_bias || 0)" class="ml-2">
                    签名 {{ formatSigned(entry.diagnosis.reconstruct.strategy_runtime_adjustments.signature_memory_bias) }}
                  </span>
                </div>
              </div>
            </div>
            <ul
              v-if="entry.diagnosis?.reconstruct?.recommended_actions?.length"
              class="mt-3 space-y-1 text-sm text-slate-600"
            >
              <li
                v-for="action in entry.diagnosis?.reconstruct?.recommended_actions"
                :key="action"
              >
                • {{ action }}
              </li>
            </ul>
          </div>
        </details>
        <div v-if="entry.diagnosis?.learning_plan" class="mt-3 rounded-lg bg-amber-50 px-3 py-3 text-sm text-amber-900">
          <div class="font-medium">外部学习计划</div>
          <div class="mt-2">需要外部学习：{{ entry.diagnosis.learning_plan.needs_external_learning ? '是' : '否' }}</div>
          <div class="mt-1">优先来源：{{ (entry.diagnosis.learning_plan.preferred_sources || []).join(' -> ') || '--' }}</div>
          <div class="mt-1">验证门禁：{{ entry.diagnosis.learning_plan.validation_gate || '--' }}</div>
          <ul v-if="entry.diagnosis.learning_plan.queries?.length" class="mt-2 space-y-1">
            <li v-for="query in entry.diagnosis.learning_plan.queries" :key="query">• {{ query }}</li>
          </ul>
        </div>
        <div v-if="entry.diagnosis?.learning_task" class="mt-3 rounded-lg bg-teal-50 px-3 py-3 text-sm text-teal-950">
          <div class="font-medium">学习任务执行</div>
          <div class="mt-2">状态：{{ formatLearningTaskStatus(entry.diagnosis.learning_task.status) }}</div>
          <div class="mt-1">来源：{{ (entry.diagnosis.learning_task.preferred_sources || []).join(' -> ') || '--' }}</div>
          <div class="mt-1">验证动作：{{ entry.diagnosis.learning_task.next_validation_action || '--' }}</div>
          <div v-if="entry.diagnosis.learning_task.source_runs?.length" class="mt-2 flex flex-wrap gap-2">
            <span
              v-for="run in entry.diagnosis.learning_task.source_runs"
              :key="`${entry.tenantId}-${entry.sourceDir}-${run.source}`"
              class="rounded-full bg-white px-2.5 py-1 text-xs text-teal-700"
            >
              {{ run.source }} / {{ formatSourceRunStatus(run.status) }} / {{ run.candidate_count }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
type GenericRecord = Record<string, any>

defineProps<{
  autonomyLoading: boolean
  autonomyStatus: GenericRecord | null
  autonomyEntries: GenericRecord[]
  formatScore: (value?: number | null) => string
  formatSigned: (value: unknown) => string
  loadAutonomyStatus: () => void | Promise<void>
}>()

const formatResearchState = (value?: string | null, fallback = '--') => {
  const normalized = String(value || '').trim()
  if (!normalized) return fallback
  if (normalized === 'idle') return '待观察'
  if (normalized === 'monitoring') return '持续观察中'
  if (normalized === 'researching') return '研究中'
  if (normalized === 'learning') return '外部学习中'
  if (normalized === 'reconstructing') return '重构中'
  if (normalized === 'validating') return '验证中'
  if (normalized === 'stable') return '已稳定'
  if (normalized === 'blocked') return '已阻塞'
  if (normalized === 'failed') return '研究失败'
  return normalized
}

const formatResearchStepStatus = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return '--'
  if (normalized === 'pending') return '待开始'
  if (normalized === 'running') return '进行中'
  if (normalized === 'needs_learning') return '需补学习'
  if (normalized === 'ready_for_validation') return '待验证'
  if (normalized === 'validated') return '已验证'
  if (normalized === 'completed') return '已完成'
  if (normalized === 'failed') return '失败'
  return normalized
}

const formatLearningTaskStatus = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return '--'
  if (normalized === 'queued') return '待执行'
  if (normalized === 'running') return '执行中'
  if (normalized === 'collecting') return '资料收集中'
  if (normalized === 'validating') return '验证中'
  if (normalized === 'completed') return '已完成'
  if (normalized === 'failed') return '失败'
  return normalized
}

const formatSourceRunStatus = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return '--'
  if (normalized === 'pending') return '待拉取'
  if (normalized === 'running') return '拉取中'
  if (normalized === 'completed') return '已完成'
  if (normalized === 'failed') return '失败'
  return normalized
}
</script>
