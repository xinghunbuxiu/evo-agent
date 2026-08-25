<template>
  <div
    v-if="run.summary?.worker_summary"
    class="rounded-lg border border-violet-200 bg-violet-50 px-3 py-3"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="text-sm font-medium text-violet-950">
        {{ summaryTitle }}
      </div>
      <div v-if="run.summary?.worker_summary_type" class="text-[11px] uppercase tracking-[0.14em] text-violet-500">
        {{ run.summary?.worker_summary_type }}
      </div>
    </div>

    <div v-if="workerSummaryConnector" class="mt-2 rounded-lg bg-white/80 px-3 py-2 text-xs text-violet-900">
      <div class="font-medium">连接器</div>
      <div class="mt-1">
        {{ workerSummaryConnector.status || '--' }}
        <span v-if="workerSummaryConnector.username"> / {{ workerSummaryConnector.username }}</span>
        <span v-else-if="workerSummaryConnector.account"> / {{ workerSummaryConnector.account }}</span>
      </div>
      <div v-if="workerSummaryConnector.executor_adapter || workerSummaryConnector.executor_name" class="mt-1 text-violet-700">
        {{ workerSummaryConnector.executor_name || 'executor' }}
        <span v-if="workerSummaryConnector.executor_adapter"> / {{ workerSummaryConnector.executor_adapter }}</span>
      </div>
      <div v-if="workerSummaryConnector.executor_root_dir" class="mt-1 break-all text-[11px] text-violet-600">
        {{ workerSummaryConnector.executor_root_dir }}
      </div>
      <div v-if="workerSummaryConnector.message" class="mt-1 text-violet-700">{{ workerSummaryConnector.message }}</div>
    </div>

    <div v-if="workerSummaryRoleReflection" class="mt-2 rounded-lg bg-white/80 px-3 py-2 text-xs text-violet-900">
      <div class="font-medium">岗位反思上下文</div>
      <div class="mt-1">{{ workerSummaryRoleReflection.summary || '--' }}</div>
      <div class="mt-1 text-violet-700">
        {{ workerSummaryRoleReflection.member_name || workerSummaryRoleReflection.member_id || '--' }}
        <span v-if="workerSummaryRoleReflection.primary_role"> / {{ workerSummaryRoleReflection.primary_role }}</span>
        <span v-if="workerSummaryRoleReflection.stage"> / {{ workerSummaryRoleReflection.stage }}</span>
        <span v-if="workerSummaryRoleReflection.status"> / {{ workerSummaryRoleReflection.status }}</span>
      </div>
      <div v-if="workerSummaryRoleReflection.next_experiment" class="mt-1 text-violet-700">
        next experiment {{ workerSummaryRoleReflection.next_experiment }}
      </div>
    </div>

    <div v-if="workerSummaryDraft" class="mt-2 rounded-lg bg-white/80 px-3 py-2 text-xs text-violet-900">
      <div class="font-medium">草稿产出</div>
      <div class="mt-1">{{ workerSummaryDraft.status || workerSummaryDraft.message || '--' }}</div>
      <div v-if="workerSummaryDraft.topic" class="mt-1 text-violet-700">topic {{ workerSummaryDraft.topic }}</div>
      <div v-if="workerSummaryDraft.publish_content_type" class="mt-1 text-violet-700">
        type {{ workerSummaryDraft.publish_content_type }}
        <span v-if="workerSummaryDraft.article_title"> / {{ workerSummaryDraft.article_title }}</span>
      </div>
      <div v-if="workerSummaryDraft.executor_adapter || workerSummaryDraft.executor_name" class="mt-1 text-violet-700">
        {{ workerSummaryDraft.executor_name || 'executor' }}
        <span v-if="workerSummaryDraft.executor_adapter"> / {{ workerSummaryDraft.executor_adapter }}</span>
      </div>
      <div v-if="workerSummaryDraft.article_path || workerSummaryDraft.draft_path" class="mt-1 break-all text-[11px] text-violet-600">
        {{ workerSummaryDraft.article_path || workerSummaryDraft.draft_path }}
      </div>
      <div v-if="workerSummaryDraft.preview" class="mt-1 text-violet-700">{{ workerSummaryDraft.preview }}</div>
    </div>

    <div v-if="workerSummaryAnalyze || workerSummaryReconstruct" class="mt-2 grid gap-2" :class="compact ? 'md:grid-cols-1' : 'md:grid-cols-2'">
      <div v-if="workerSummaryAnalyze" class="rounded-lg bg-white/80 px-3 py-2 text-xs text-violet-900">
        <div class="font-medium">分析结果</div>
        <div class="mt-1">{{ workerSummaryAnalyze.summary || workerSummaryAnalyze.detail || '--' }}</div>
        <div v-if="workerSummaryAnalyze.strategy_id" class="mt-1 text-violet-700">strategy {{ workerSummaryAnalyze.strategy_id }}</div>
      </div>
      <div v-if="workerSummaryReconstruct" class="rounded-lg bg-white/80 px-3 py-2 text-xs text-violet-900">
        <div class="font-medium">重建结果</div>
        <div class="mt-1">{{ workerSummaryReconstruct.summary || workerSummaryReconstruct.detail || '--' }}</div>
        <div class="mt-1 text-violet-700">
          verdict {{ workerSummaryReconstruct.evaluation_verdict || '--' }}
          <span v-if="typeof workerSummaryReconstruct.evaluation_score === 'number'"> / {{ workerSummaryReconstruct.evaluation_score.toFixed(2) }}</span>
        </div>
      </div>
    </div>

    <div v-if="workerSummaryValidation" class="mt-2 rounded-lg bg-white/80 px-3 py-2 text-xs text-violet-900">
      <div class="font-medium">验证结论</div>
      <div class="mt-1">
        verdict {{ workerSummaryValidation.verdict || '--' }}
        <span v-if="typeof workerSummaryValidation.components === 'number'"> / components {{ workerSummaryValidation.components }}</span>
        <span v-if="typeof workerSummaryValidation.has_target_dir === 'boolean'"> / target {{ workerSummaryValidation.has_target_dir ? 'yes' : 'no' }}</span>
      </div>
      <div v-if="workerSummaryValidation.framework_summary" class="mt-1 text-violet-700">{{ workerSummaryValidation.framework_summary }}</div>
    </div>

    <div v-if="workerSummaryPromotion" class="mt-2 rounded-lg bg-white/80 px-3 py-2 text-xs text-violet-900">
      <div class="font-medium">知识晋升</div>
      <div class="mt-1">{{ workerSummaryPromotion.experience_id || '--' }}</div>
      <div class="mt-1 text-violet-700">
        score {{ typeof workerSummaryPromotion.quality_score === 'number' ? workerSummaryPromotion.quality_score.toFixed(2) : '--' }}
        <span v-if="workerSummaryPromotion.platform_promotion_status?.status"> / {{ workerSummaryPromotion.platform_promotion_status?.status }}</span>
      </div>
    </div>

    <div v-if="workerSummaryAnalytics.length" class="mt-2 space-y-2">
      <div
        v-for="item in visibleAnalytics"
        :key="`${run.mission_run_id}-${item.analytics_type}-${item.experience_id || item.headline}`"
        class="rounded-lg bg-white/80 px-3 py-2 text-xs text-violet-900"
      >
        <div class="font-medium">{{ item.analytics_type || 'analytics' }}</div>
        <div class="mt-1">{{ item.headline || '--' }}</div>
        <div v-if="item.insight_summary" class="mt-1 text-violet-700">{{ item.insight_summary }}</div>
      </div>
    </div>

    <div v-if="workerSummaryFeedback" class="mt-2 rounded-lg bg-white/80 px-3 py-2 text-xs text-violet-900">
      <div class="font-medium">反馈复盘</div>
      <div class="mt-1">{{ workerSummaryFeedback.headline || '--' }}</div>
      <div v-if="workerSummaryFeedback.insight_summary" class="mt-1 text-violet-700">{{ workerSummaryFeedback.insight_summary }}</div>
      <ul v-if="feedbackSamples.length" class="mt-2 space-y-1 text-violet-700">
        <li v-for="item in feedbackSamples" :key="item">• {{ item }}</li>
      </ul>
    </div>

    <div v-if="workerSummaryGrowth.length" class="mt-2 rounded-lg bg-white/80 px-3 py-2 text-xs text-violet-900">
      <div class="font-medium">成长沉淀</div>
      <div class="mt-1 flex flex-wrap gap-2">
        <span
          v-for="item in visibleGrowth"
          :key="`${run.mission_run_id}-${item.experience_id || item.recorded_at}`"
          class="rounded-full bg-violet-100 px-2 py-1 text-[11px] text-violet-700"
        >
          {{ item.task_type || 'experience' }}
          <span v-if="typeof item.quality_score === 'number'"> / {{ item.quality_score.toFixed(2) }}</span>
        </span>
      </div>
    </div>

    <ul v-if="workerSummaryNextActions.length" class="mt-2 space-y-1 text-xs text-violet-700">
      <li v-for="item in visibleNextActions" :key="item">• {{ item }}</li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MissionRun } from '../api/missions'

const props = withDefaults(defineProps<{
  run: MissionRun
  compact?: boolean
}>(), {
  compact: false,
})

const summaryTitle = computed(() => {
  const summaryType = props.run.summary?.worker_summary_type
  if (summaryType === 'self_media_operations') return '工种摘要 / 自媒体运营'
  if (summaryType === 'javascript_reverse') return '工种摘要 / JS 逆向'
  return '工种摘要'
})

const workerSummaryConnector = computed(() => props.run.summary?.worker_summary?.connector)
const workerSummaryRoleReflection = computed(() => props.run.summary?.worker_summary?.role_reflection)
const workerSummaryDraft = computed(() => props.run.summary?.worker_summary?.draft)
const workerSummaryAnalyze = computed(() => props.run.summary?.worker_summary?.analyze)
const workerSummaryReconstruct = computed(() => props.run.summary?.worker_summary?.reconstruct)
const workerSummaryValidation = computed(() => props.run.summary?.worker_summary?.validation)
const workerSummaryPromotion = computed(() => props.run.summary?.worker_summary?.promotion)
const workerSummaryAnalytics = computed(() => props.run.summary?.worker_summary?.analytics || [])
const workerSummaryFeedback = computed(() => props.run.summary?.worker_summary?.feedback)
const workerSummaryGrowth = computed(() => props.run.summary?.worker_summary?.growth_updates || [])
const workerSummaryNextActions = computed(() => props.run.summary?.worker_summary?.recommended_next_actions || [])

const feedbackSamples = computed(() => {
  const items = props.run.summary?.worker_summary?.feedback?.selected_feedback || []
  return items
    .slice(0, props.compact ? 2 : 4)
    .map((item) => String(item.feedback_text || '').trim())
    .filter(Boolean)
})

const visibleAnalytics = computed(() => workerSummaryAnalytics.value.slice(0, props.compact ? 2 : 4))
const visibleGrowth = computed(() => workerSummaryGrowth.value.slice(0, props.compact ? 4 : 8))
const visibleNextActions = computed(() => workerSummaryNextActions.value.slice(0, props.compact ? 4 : 8))
</script>
