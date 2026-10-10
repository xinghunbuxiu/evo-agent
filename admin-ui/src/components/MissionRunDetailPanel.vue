<template>
  <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
    <div v-show="showOverview" class="space-y-4">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="text-lg font-semibold text-slate-900">{{ run.title || run.mission_kind }}</div>
          <div class="mt-1 text-sm text-slate-500">{{ run.goal }}</div>
          <div v-if="run.summary?.session?.autonomy_session_id" class="mt-2 text-xs text-slate-400">
            autonomy session {{ run.summary?.session?.autonomy_session_id }}
          </div>
        </div>
        <div class="text-right text-xs text-slate-500">
          <div>{{ run.status }}</div>
          <div class="mt-1">{{ formatTimestamp(run.created_at) }}</div>
        </div>
      </div>

      <div class="flex flex-wrap gap-2">
      <span
        v-if="run.summary?.session?.run_count"
        class="rounded-full bg-emerald-100 px-2.5 py-1 text-xs text-emerald-700"
      >
        session {{ run.summary?.session?.run_index }}/{{ run.summary?.session?.run_count }}
      </span>
      <span
        v-if="boundMemberLabel"
        class="rounded-full bg-violet-100 px-2.5 py-1 text-xs text-violet-700"
      >
        child {{ boundMemberLabel }}
      </span>
      <span
        v-if="boundMemberRole"
        class="rounded-full bg-fuchsia-100 px-2.5 py-1 text-xs text-fuchsia-700"
      >
        role {{ boundMemberRole }}
      </span>
      <span
        v-if="boundMemberResolution"
        class="rounded-full bg-sky-100 px-2.5 py-1 text-xs text-sky-700"
      >
        via {{ boundMemberResolution }}
      </span>
      <span
        v-for="(count, key) in run.counts"
        :key="`${run.mission_run_id}-detail-${key}`"
        class="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600"
      >
        {{ key }} {{ count }}
      </span>
    </div>

    <div
      v-if="run.context?.previous_mission_run_id || run.auto_continue_source_mission_run_id || run.auto_continue_triggered_run_id"
      class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-600"
    >
      <div v-if="run.context?.previous_mission_run_id">continued from {{ run.context.previous_mission_run_id }}</div>
      <div v-if="run.auto_continue_source_mission_run_id">auto-continue source {{ run.auto_continue_source_mission_run_id }}</div>
      <div v-if="run.auto_continue_triggered_run_id">triggered next {{ run.auto_continue_triggered_run_id }}</div>
    </div>

    <MissionWorkerSummary
      v-if="run.summary?.worker_summary"
      :run="run"
    />
    </div>

    <div v-show="showActions" class="space-y-2">
      <div v-if="!run.actions.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
        暂无动作节点。
      </div>
      <div
        v-for="action in run.actions"
        :key="`${run.mission_run_id}-${action.node_id}-${action.action_type}`"
        class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="font-medium text-slate-900">{{ action.title || action.node_id }}</div>
          <div class="text-xs text-slate-500">{{ action.action_type }} / {{ action.status }}</div>
        </div>
        <div class="mt-2">{{ action.detail || '--' }}</div>
        <details v-if="action.decision_trace?.length" class="mt-2 rounded-lg border border-indigo-100 bg-white px-3 py-2">
          <summary class="cursor-pointer text-xs font-medium text-indigo-700">规划决策追踪（{{ action.decision_trace.length }}）</summary>
          <div class="mt-2 space-y-2">
            <div
              v-for="(trace, index) in action.decision_trace"
              :key="`${run.mission_run_id}-${action.node_id}-trace-${index}`"
              class="border-l-2 border-indigo-200 pl-2 text-xs"
            >
              <div class="font-medium text-slate-700">{{ trace.step || 'decision' }} <span v-if="trace.result">/ {{ trace.result }}</span></div>
              <div v-if="trace.rule_id" class="mt-0.5 break-all text-indigo-600">{{ trace.rule_id }}</div>
              <pre v-if="trace.evidence" class="mt-1 whitespace-pre-wrap break-words text-[11px] text-slate-500">{{ JSON.stringify(trace.evidence, null, 2) }}</pre>
            </div>
          </div>
        </details>
        <div v-if="action.task_id" class="mt-2 text-xs text-teal-700">task {{ action.task_id }}</div>
        <div v-if="action.task_status" class="mt-1 text-xs text-slate-500">task status {{ action.task_status }}</div>
        <div v-if="action.task_outcome" class="mt-1 text-xs text-sky-700">outcome {{ action.task_outcome }}</div>
        <div v-if="action.linked_learning_task_id" class="mt-1 text-xs text-amber-700">
          learning {{ action.linked_learning_task_id }}
        </div>
        <div v-if="action.insight_summary" class="mt-2 rounded-lg bg-sky-50 px-3 py-2 text-xs text-sky-900">
          {{ action.insight_summary }}
        </div>
        <div
          v-if="action.growth_update?.experience_id || action.task_result?.experience_id"
          class="mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-800"
        >
          growth {{ action.growth_update?.experience_id || action.task_result?.experience_id }}
        </div>
        <div v-if="action.task_error" class="mt-1 break-all text-xs text-rose-600">{{ action.task_error }}</div>
        <ul v-if="action.next_actions?.length" class="mt-2 space-y-1 text-xs text-slate-500">
          <li v-for="item in action.next_actions" :key="item">• {{ item }}</li>
        </ul>
      </div>
    </div>

    <div v-show="showPlan">
    <div
      v-if="run.summary?.next_cycle_plan?.next_steps?.length || run.summary?.next_cycle_plan?.focus_points?.length"
      class="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3"
    >
      <div class="flex items-center justify-between gap-3">
        <div class="text-sm font-medium text-emerald-900">
          {{ run.summary?.next_cycle_plan?.title || '下一轮行动计划' }}
        </div>
        <button
          v-if="showContinueButton"
          class="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
          :disabled="continueDisabled"
          @click="$emit('continue')"
        >
          {{ continueDisabled ? '推进中...' : '继续下一轮' }}
        </button>
      </div>
      <ul v-if="run.summary?.next_cycle_plan?.focus_points?.length" class="mt-2 space-y-1 text-xs text-emerald-800">
        <li v-for="item in run.summary?.next_cycle_plan?.focus_points" :key="item">• {{ item }}</li>
      </ul>
      <ul v-if="run.summary?.next_cycle_plan?.next_steps?.length" class="mt-2 space-y-1 text-xs text-emerald-700">
        <li v-for="item in run.summary?.next_cycle_plan?.next_steps" :key="item">• {{ item }}</li>
      </ul>
      <div
        v-if="run.summary?.next_cycle_plan?.role_reflection_summaries?.length || run.summary?.next_cycle_plan?.role_reflection_experiments?.length"
        class="mt-3 rounded-lg bg-white/70 px-3 py-3 text-xs text-emerald-900"
      >
        <div class="font-medium">岗位反思驱动</div>
        <ul v-if="run.summary?.next_cycle_plan?.role_reflection_summaries?.length" class="mt-2 space-y-1 text-emerald-800">
          <li v-for="item in run.summary?.next_cycle_plan?.role_reflection_summaries" :key="item">• {{ item }}</li>
        </ul>
        <ul v-if="run.summary?.next_cycle_plan?.role_reflection_experiments?.length" class="mt-2 space-y-1 text-emerald-700">
          <li v-for="item in run.summary?.next_cycle_plan?.role_reflection_experiments" :key="item">• next experiment: {{ item }}</li>
        </ul>
      </div>
      <div v-if="run.auto_continue_status" class="mt-2 text-xs text-emerald-700">
        auto continue {{ run.auto_continue_status }}
        <span v-if="run.auto_continue_triggered_run_id"> / {{ run.auto_continue_triggered_run_id }}</span>
      </div>
    </div>
    <div v-else-if="showPlan" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
      当前还没有下一轮续跑计划。
    </div>
    </div>

    <div v-show="showGrowth">
    <div v-if="run.summary?.growth_timeline?.length" class="rounded-lg border border-sky-200 bg-sky-50 px-3 py-3">
      <div class="text-sm font-medium text-sky-900">完整成长轨迹</div>
      <div class="mt-2 space-y-2">
        <div
          v-for="event in run.summary?.growth_timeline"
          :key="`${run.mission_run_id}-detail-${event.timestamp}-${event.title}`"
          class="text-xs text-sky-800"
        >
          <div class="font-medium">{{ event.title }}</div>
          <div class="mt-1">{{ event.detail || '--' }}</div>
          <div class="mt-1 text-[11px] text-sky-600">
            {{ formatTimestamp(event.timestamp) }}
            <span v-if="event.experience_id"> / {{ event.experience_id }}</span>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
      暂无成长轨迹事件。
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MissionWorkerSummary from './MissionWorkerSummary.vue'
import type { MissionRun } from '../api/missions'

export type MissionDetailSection = 'overview' | 'actions' | 'growth' | 'plan'

const props = withDefaults(defineProps<{
  run: MissionRun
  section?: MissionDetailSection
  continueDisabled?: boolean
  showContinueButton?: boolean
}>(), {
  section: 'overview',
  continueDisabled: false,
  showContinueButton: true,
})

defineEmits<{
  continue: []
}>()

const showOverview = computed(() => props.section === 'overview')
const showActions = computed(() => props.section === 'actions')
const showGrowth = computed(() => props.section === 'growth')
const showPlan = computed(() => props.section === 'plan')

const formatTimestamp = (value?: string) => {
  if (!value) return '--'
  return value.slice(0, 19).replace('T', ' ')
}

const boundMemberLabel = computed(() => {
  const name = String(props.run.context?.member_name || '').trim()
  const memberId = String(
    props.run.context?.member_id
    || props.run.member_reflection_member_id
    || ''
  ).trim()
  return name || memberId || ''
})

const boundMemberRole = computed(() => String(props.run.context?.member_primary_role || '').trim())

const boundMemberResolution = computed(() => String(props.run.context?.member_resolution_source || '').trim())
</script>
