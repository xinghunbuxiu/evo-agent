<template>
  <details v-if="selectedChildMemberDraft?.primary_role === 'talent_development'" class="mt-4 rounded-xl border border-sky-200 bg-sky-50/60 text-sm text-sky-950">
    <summary class="cursor-pointer list-none px-4 py-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="font-medium">巡检策略工作面</div>
          <div class="mt-1 text-xs text-sky-700">只有当前选中的是育成官本人时，才需要展开这些自检与工作台内容。</div>
        </div>
        <div class="rounded-full bg-white px-3 py-1 text-[11px] text-sky-700">
          育成官自检
        </div>
      </div>
    </summary>
    <div class="border-t border-sky-200 px-4 py-4">
      <div class="mb-4 grid gap-3 md:grid-cols-3">
        <div class="rounded-xl border border-sky-200 bg-white/90 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前对象</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedChildMemberDraft?.name || '育成官' }}</div>
        </div>
        <div class="rounded-xl border border-sky-200 bg-white/90 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前模式</div>
          <div class="mt-2 font-medium text-slate-900">{{ exclusiveWorkspaceMeta.title }}</div>
        </div>
        <div class="rounded-xl border border-sky-200 bg-white/90 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前重点</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedChildMemberRuntime?.derived_state?.next_action || selectedChildMemberDraft?.training_plan?.next_action || '继续观察育成节奏' }}</div>
        </div>
      </div>
      <div class="mb-4 rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-sm font-semibold text-slate-900">当前工作位</div>
            <div class="mt-1 text-xs text-slate-500">这里只有育成官本人会进入。先决定是在做巡检、看队列、调自动策略还是处理自我发展。</div>
          </div>
          <div class="rounded-full bg-slate-100 px-3 py-1 text-[11px] text-slate-600">
            当前 {{ exclusiveWorkspaceMeta.title }}
          </div>
        </div>
        <div class="mt-4 grid gap-3 lg:grid-cols-2 xl:grid-cols-4">
          <button
            v-for="item in exclusiveWorkspaceCards"
            :key="`exclusive-card-${item.key}`"
            type="button"
            @click="setExclusiveWorkspaceMode(item.key)"
            class="rounded-2xl border px-4 py-4 text-left transition"
            :class="item.active ? item.activeClass : item.idleClass"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-sm font-semibold text-slate-900">{{ item.title }}</div>
                <div class="mt-2 text-xs leading-5 text-slate-500">{{ item.description }}</div>
              </div>
              <span class="rounded-full px-2.5 py-1 text-[11px] font-medium" :class="item.badgeClass">
                {{ item.badge }}
              </span>
            </div>
          </button>
        </div>
        <div class="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
          <div class="font-medium text-slate-900">{{ exclusiveWorkspaceMeta.title }}</div>
          <div class="mt-2 leading-6">{{ exclusiveWorkspaceMeta.description }}</div>
        </div>
      </div>

      <div v-show="exclusiveWorkspaceMode === 'overview'">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="font-medium">育成官训练巡检</div>
          <div class="mt-1 text-xs text-sky-700">手动触发一次巡检后，系统会按当前运行态自动改写子女训练计划并落盘。</div>
        </div>
        <button
          @click="runTrainingReview"
          :disabled="trainingReviewRunning"
          class="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-60"
        >
          {{ trainingReviewRunning ? '巡检中...' : '立即巡检' }}
        </button>
      </div>
      <p v-if="trainingReviewMessage" class="mb-4 text-sm" :class="trainingReviewSuccess ? 'text-green-600' : 'text-red-600'">
        {{ trainingReviewMessage }}
      </p>
      <div class="mb-4 rounded-lg bg-white px-3 py-3 text-xs text-slate-700">
        <div class="font-medium text-slate-900">最近巡检结果</div>
        <div class="mt-2">时间 {{ formatDate(autonomyStatus?.training_review?.last_review_at) }}</div>
        <div class="mt-1">触发方式 {{ autonomyStatus?.training_review?.last_trigger || '--' }}</div>
        <div class="mt-1">变更数量 {{ autonomyStatus?.training_review?.changed_count ?? 0 }}</div>
        <div class="mt-1">{{ autonomyStatus?.training_review?.last_message || '尚未产生巡检记录' }}</div>
        <div v-if="autonomyStatus?.training_review?.changed_members?.length" class="mt-3 grid gap-2 md:grid-cols-2">
          <div
            v-for="member in autonomyStatus.training_review.changed_members"
            :key="`training-review-member-${member.member_id}`"
            class="rounded border border-slate-200 bg-slate-50 px-3 py-3"
          >
            <div class="font-medium text-slate-900">{{ member.name || member.member_id || '--' }}</div>
            <div class="mt-1">{{ member.primary_role || '--' }} / {{ member.training_stage || '--' }}</div>
            <div class="mt-1 text-sky-800">{{ member.next_action || '--' }}</div>
          </div>
        </div>
      </div>
      <div class="mb-4 grid gap-3 md:grid-cols-3">
        <div class="rounded-lg bg-white px-3 py-3 text-xs text-slate-700">
          <div class="text-sky-700">当前带教子女</div>
          <div class="mt-2 text-lg font-semibold text-slate-900">{{ selectedChildMemberRuntime?.training_overview?.assigned_children_count || 0 }}</div>
        </div>
        <div class="rounded-lg bg-white px-3 py-3 text-xs text-slate-700">
          <div class="text-sky-700">发展阶段</div>
          <div class="mt-2 text-lg font-semibold text-slate-900">{{ selectedChildMemberRuntime?.training_plan?.stage || selectedChildMemberDraft?.training_plan?.stage || '--' }}</div>
        </div>
        <div class="rounded-lg bg-white px-3 py-3 text-xs text-slate-700">
          <div class="text-sky-700">当前下一步</div>
          <div class="mt-2 leading-5 text-slate-900">{{ selectedChildMemberRuntime?.derived_state?.next_action || selectedChildMemberDraft?.training_plan?.next_action || '--' }}</div>
        </div>
      </div>
      <div v-if="trainerIntentSummary" class="mb-4 rounded-lg border border-sky-200 bg-white px-3 py-3 text-xs text-slate-700">
        <div class="font-medium text-slate-900">育成官当前意图</div>
        <div class="mt-2 grid gap-3 md:grid-cols-3">
          <div class="rounded border border-sky-100 bg-sky-50 px-3 py-3">
            <div class="text-sky-700">当前意图</div>
            <div class="mt-2 leading-5 text-slate-900">{{ trainerIntentSummary.intent }}</div>
          </div>
          <div class="rounded border border-sky-100 bg-sky-50 px-3 py-3">
            <div class="text-sky-700">原因</div>
            <div class="mt-2 leading-5 text-slate-900">{{ trainerIntentSummary.reason }}</div>
          </div>
          <div class="rounded border border-sky-100 bg-sky-50 px-3 py-3">
            <div class="text-sky-700">风险控制</div>
            <div class="mt-2 leading-5 text-slate-900">{{ trainerIntentSummary.risk }}</div>
          </div>
        </div>
        <div v-if="trainerIntentSummary.next_moves.length" class="mt-3 rounded border border-sky-100 bg-slate-50 px-3 py-3">
          <div class="font-medium text-slate-900">下一轮育成动作</div>
          <div class="mt-2 grid gap-2">
            <div v-for="(item, index) in trainerIntentSummary.next_moves" :key="`trainer-intent-${index}`" class="leading-5 text-slate-700">
              {{ index + 1 }}. {{ item }}
            </div>
          </div>
        </div>
      </div>
      </div>

      <div v-show="exclusiveWorkspaceMode === 'queue' || exclusiveWorkspaceMode === 'automation'">
      <div class="mb-4 rounded-lg bg-white px-3 py-3 text-xs text-slate-700">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="font-medium text-slate-900">育成官工作台</div>
            <div class="mt-1 text-sky-700">这里是父节点最近交办给育成官的任务，育成官需要围绕这些交办去安排子女训练。</div>
          </div>
          <div class="text-sky-700">任务 {{ trainerDirectiveQueue.length }}</div>
        </div>
        <div v-show="exclusiveWorkspaceMode === 'automation'" class="mt-3 rounded-lg border border-violet-200 bg-violet-50/70 px-3 py-3">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <label class="inline-flex items-center gap-2 text-[11px] text-violet-900">
              <input :checked="trainerAutoAssistEnabled" type="checkbox" @change="emit('update:trainerAutoAssistEnabled', ($event.target as HTMLInputElement).checked)">
              <span>开启低风险半自动执行</span>
            </label>
            <button
              type="button"
              @click="runTrainerLowRiskSuggestionBatch"
              :disabled="!trainerAutoAssistEnabled || trainerBatchRunning || !trainerLowRiskSuggestionQueue.length"
              class="rounded-lg bg-violet-600 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-violet-700 disabled:opacity-60"
            >
              {{ trainerBatchRunning ? '批处理中...' : `执行低风险建议 (${trainerLowRiskSuggestionQueue.length})` }}
            </button>
          </div>
          <div class="mt-2 text-[11px] text-violet-800">
            当前仅自动执行低风险建议：`标记已接手`、`要求补复盘`。`重排训练` 和 `立即巡检` 仍保留人工判断。
          </div>
          <div class="mt-3 grid gap-3 md:grid-cols-2">
            <div class="rounded-lg border border-violet-200 bg-white/80 px-3 py-3">
              <div class="text-[11px] font-medium text-violet-900">自动动作白名单</div>
              <label class="mt-2 inline-flex items-center gap-2 text-[11px] text-slate-700">
                <input :checked="trainerAutoAssistAllowedTakeOver" type="checkbox" @change="emit('update:trainerAutoAssistAllowedTakeOver', ($event.target as HTMLInputElement).checked)">
                <span>允许自动接手</span>
              </label>
              <label class="mt-2 inline-flex items-center gap-2 text-[11px] text-slate-700">
                <input :checked="trainerAutoAssistAllowedReflection" type="checkbox" @change="emit('update:trainerAutoAssistAllowedReflection', ($event.target as HTMLInputElement).checked)">
                <span>允许自动要求补复盘</span>
              </label>
            </div>
            <div class="rounded-lg border border-violet-200 bg-white/80 px-3 py-3">
              <div class="text-[11px] font-medium text-violet-900">自动阶段白名单</div>
              <input
                :value="trainerAutoAssistAllowedStages.join(', ')"
                @change="emit('update:trainerAutoAssistAllowedStages', String(($event.target as HTMLInputElement).value || '').split(',').map((item) => item.trim()).filter(Boolean))"
                type="text"
                class="mt-2 w-full rounded-lg border border-violet-200 bg-white px-3 py-2 text-[11px] text-slate-700"
                placeholder="profile_initialized, active_training"
              >
              <div class="mt-2 text-[11px] text-violet-800">只有这些训练阶段的子女，才允许进入半自动执行。</div>
            </div>
          </div>
        </div>
        <div v-if="!trainerDirectiveQueue.length && exclusiveWorkspaceMode === 'queue'" class="mt-3 rounded border border-dashed border-sky-200 bg-sky-50 px-3 py-4 text-sky-700">
          当前还没有新的父节点交办任务。
        </div>
        <div v-else-if="exclusiveWorkspaceMode === 'queue'" class="mt-3 grid gap-3 md:grid-cols-2">
          <button
            v-for="item in trainerDirectiveQueue"
            :key="`trainer-directive-${item.message_id}`"
            type="button"
            @click="item.managed_child_member_id ? selectChildMember(item.managed_child_member_id) : undefined"
            class="rounded-lg border border-sky-200 bg-sky-50/60 px-3 py-3 text-left hover:bg-sky-100/60"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="font-medium text-slate-900">{{ item.title }}</div>
                <div class="mt-1 text-slate-500">{{ item.managed_child_name }} / {{ item.managed_child_role }}</div>
              </div>
              <div class="text-right">
                <div class="text-slate-500">{{ formatDate(item.created_at) }}</div>
                <span
                  class="mt-2 inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium"
                  :class="trainerQueueStatusBadgeClass(item.queue_status)"
                >
                  {{ item.queue_status_label }}
                </span>
              </div>
            </div>
            <div class="mt-2 line-clamp-3 leading-6 text-slate-700">{{ item.content }}</div>
            <div class="mt-2 text-[11px] text-sky-800">最近动作 {{ item.latest_action_label }}</div>
            <div class="mt-2 rounded-lg border border-sky-100 bg-white/80 px-3 py-3 text-[11px] leading-5 text-sky-950">
              <div class="font-medium">育成官管理判断</div>
              <div class="mt-1">{{ item.management_summary }}</div>
              <div class="mt-2 rounded bg-sky-100 px-2 py-2 text-sky-800">
                {{ item.suggested_action_label }}
              </div>
            </div>
            <div class="mt-3 grid gap-2 md:grid-cols-3">
              <div class="rounded border border-white bg-white px-2 py-2">
                <div class="text-slate-400">阶段</div>
                <div class="mt-1 text-slate-900">{{ item.training_stage || '--' }}</div>
              </div>
              <div class="rounded border border-white bg-white px-2 py-2">
                <div class="text-slate-400">当前专注</div>
                <div class="mt-1 text-slate-900">{{ item.current_focus || '--' }}</div>
              </div>
              <div class="rounded border border-white bg-white px-2 py-2">
                <div class="text-slate-400">下一步</div>
                <div class="mt-1 text-slate-900">{{ item.next_action || '--' }}</div>
              </div>
            </div>
            <div class="mt-2 flex flex-wrap gap-2">
              <span class="rounded-full bg-white px-2.5 py-1 text-[11px] text-sky-800">
                {{ item.directive_type || 'parent_guidance' }}
              </span>
              <span class="rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-600">
                点击打开子女
              </span>
            </div>
            <div v-if="item.timeline.length" class="mt-3 rounded-lg border border-sky-100 bg-white/80 px-3 py-3">
              <div class="text-[11px] font-medium text-sky-900">培养流水</div>
              <div class="mt-2 grid gap-2">
                <div
                  v-for="entry in item.timeline"
                  :key="`${item.message_id}-${entry.key}`"
                  class="flex items-center justify-between gap-3 text-[11px] text-slate-600"
                >
                  <span>{{ entry.label }}</span>
                  <span>{{ formatDate(entry.at) }}</span>
                </div>
              </div>
            </div>
            <div class="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                @click.stop="handleTrainerSuggestedAction(item)"
                :disabled="item.suggested_action === 'observe' || trainerActionRunningId === `${item.message_id}:suggested` || trainingReviewRunning"
                class="rounded-lg bg-violet-600 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-violet-700 disabled:opacity-60"
              >
                {{ trainerActionRunningId === `${item.message_id}:suggested` ? '执行中...' : (item.suggested_action === 'observe' ? '建议观察' : '执行建议') }}
              </button>
              <button
                type="button"
                @click.stop="handleTrainerDirectiveAction(item, 'take_over')"
                :disabled="trainerActionRunningId === `${item.message_id}:take_over`"
                class="rounded-lg px-3 py-1.5 text-[11px] font-medium disabled:opacity-60"
                :class="item.suggested_action === 'take_over' ? 'bg-sky-700 text-white ring-2 ring-sky-200 hover:bg-sky-800' : 'bg-sky-600 text-white hover:bg-sky-700'"
              >
                {{ trainerActionRunningId === `${item.message_id}:take_over` ? '处理中...' : '标记已接手' }}
              </button>
              <button
                type="button"
                @click.stop="handleTrainerDirectiveAction(item, 'request_reflection')"
                :disabled="trainerActionRunningId === `${item.message_id}:request_reflection`"
                class="rounded-lg border px-3 py-1.5 text-[11px] font-medium disabled:opacity-60"
                :class="item.suggested_action === 'request_reflection' ? 'border-emerald-400 bg-emerald-50 text-emerald-800 ring-2 ring-emerald-100 hover:bg-emerald-100' : 'border-emerald-300 bg-white text-emerald-700 hover:bg-emerald-50'"
              >
                {{ trainerActionRunningId === `${item.message_id}:request_reflection` ? '处理中...' : '要求补复盘' }}
              </button>
              <button
                type="button"
                @click.stop="handleTrainerDirectiveAction(item, 'replan_training')"
                :disabled="trainerActionRunningId === `${item.message_id}:replan_training`"
                class="rounded-lg border px-3 py-1.5 text-[11px] font-medium disabled:opacity-60"
                :class="item.suggested_action === 'replan_training' ? 'border-amber-400 bg-amber-50 text-amber-800 ring-2 ring-amber-100 hover:bg-amber-100' : 'border-amber-300 bg-white text-amber-700 hover:bg-amber-50'"
              >
                {{ trainerActionRunningId === `${item.message_id}:replan_training` ? '处理中...' : '重排训练' }}
              </button>
              <button
                type="button"
                @click.stop="handleTrainerDirectiveReview(item)"
                :disabled="trainingReviewRunning"
                class="rounded-lg border px-3 py-1.5 text-[11px] font-medium disabled:opacity-60"
                :class="item.suggested_action === 'run_review' ? 'border-slate-400 bg-slate-100 text-slate-900 ring-2 ring-slate-200 hover:bg-slate-200' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'"
              >
                {{ trainingReviewRunning ? '巡检中...' : '立即巡检' }}
              </button>
            </div>
          </button>
        </div>
      </div>
      </div>

      <div v-show="exclusiveWorkspaceMode === 'growth'">
      <div class="mb-4 rounded-lg bg-white px-3 py-3 text-xs text-slate-700">
        <div class="font-medium text-slate-900">育成官自我发展</div>
        <div class="mt-2">成长等级 {{ selectedChildMemberRuntime?.self_development?.level || '基础阶段' }}</div>
        <div class="mt-2">长期目标 {{ selectedChildMemberDraft?.role_memory?.long_term_goal || '--' }}</div>
        <div class="mt-1">当前专注 {{ selectedChildMemberRuntime?.self_development?.current_objective || selectedChildMemberDraft?.growth_state?.current_focus || '--' }}</div>
        <div class="mt-1">培养策略 {{ selectedChildMemberDraft?.operating_contract?.learning_strategy || '--' }}</div>
        <div class="mt-1">下一里程碑 {{ selectedChildMemberRuntime?.self_development?.next_milestone || '--' }}</div>
        <div v-if="selectedChildMemberRuntime?.self_development?.focus?.length" class="mt-2 flex flex-wrap gap-2">
          <span
            v-for="item in selectedChildMemberRuntime.self_development.focus"
            :key="`trainer-focus-${item}`"
            class="rounded-full bg-violet-100 px-2.5 py-1 text-[11px] text-violet-800"
          >
            {{ item }}
          </span>
        </div>
        <div class="mt-2 flex flex-wrap gap-2" v-if="selectedChildMemberRuntime?.training_overview?.stage_counts">
          <span
            v-for="(count, stage) in selectedChildMemberRuntime.training_overview.stage_counts"
            :key="`training-stage-${stage}`"
            class="rounded-full bg-sky-100 px-2.5 py-1 text-[11px] text-sky-800"
          >
            {{ stage }} · {{ count }}
          </span>
        </div>
        <div v-if="selectedChildMemberRuntime?.coaching_stats?.total_records" class="mt-2 rounded border border-violet-100 bg-violet-50 px-3 py-2 text-[11px] text-violet-900">
          已累计 {{ selectedChildMemberRuntime.coaching_stats.total_records }} 条带教履历
        </div>
        <div v-if="selectedChildMemberRuntime?.self_development?.growth_signals?.length" class="mt-2 flex flex-wrap gap-2">
          <span
            v-for="signal in selectedChildMemberRuntime.self_development.growth_signals"
            :key="`trainer-growth-${signal}`"
            class="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] text-emerald-800"
          >
            {{ signal }}
          </span>
        </div>
        <div v-if="selectedChildMemberRuntime?.self_development?.missing_capabilities?.length" class="mt-3 rounded border border-amber-100 bg-amber-50 px-3 py-3">
          <div class="font-medium text-amber-900">仍需补齐</div>
          <div
            v-for="item in selectedChildMemberRuntime.self_development.missing_capabilities"
            :key="`trainer-gap-${item}`"
            class="mt-1 text-amber-800"
          >
            {{ item }}
          </div>
        </div>
        <div v-if="selectedChildMemberRuntime?.training_overview?.next_target" class="mt-3 rounded border border-sky-100 bg-sky-50 px-3 py-3">
          <div class="font-medium text-slate-900">优先跟进对象</div>
          <div class="mt-1">{{ selectedChildMemberRuntime.training_overview.next_target.name || selectedChildMemberRuntime.training_overview.next_target.member_id || '--' }}</div>
          <div class="mt-1">{{ selectedChildMemberRuntime.training_overview.next_target.primary_role || '--' }} / {{ selectedChildMemberRuntime.training_overview.next_target.stage || '--' }}</div>
          <div class="mt-1 text-sky-800">{{ selectedChildMemberRuntime.training_overview.next_target.next_action || '--' }}</div>
        </div>
      </div>
      <div class="mb-4 rounded-lg border border-violet-200 bg-violet-50/50 px-3 py-3 text-xs text-slate-700">
        <div class="font-medium text-violet-950">带教履历</div>
        <div class="mt-1 text-violet-800">任务确认、复制建档、放手提示等关键动作会自动记录在此。</div>
        <div v-if="!trainerCoachingLogCards.length" class="mt-3 rounded border border-dashed border-violet-200 bg-white px-3 py-4 text-violet-700">
          还没有带教记录。完成一次任务确认或「复制同岗位」建档后会自动生成。
        </div>
        <div v-else class="mt-3 space-y-3 max-h-[420px] overflow-y-auto">
          <article
            v-for="card in trainerCoachingLogCards"
            :key="`coaching-log-${card.card_id}`"
            class="rounded-lg border border-violet-200 bg-white px-3 py-3"
          >
            <div class="font-medium text-slate-900">{{ card.title || '带教记录' }}</div>
            <div class="mt-1 text-[11px] text-slate-500">{{ formatDate(card.created_at) }}</div>
            <div class="mt-2 leading-5 text-slate-700">{{ card.summary || card.current_pattern || '--' }}</div>
            <div v-if="card.next_experiment" class="mt-2 text-violet-800">
              下一步：{{ card.next_experiment }}
            </div>
          </article>
        </div>
      </div>
      <div class="font-medium">育成官最近培养的子女</div>
      <div v-if="!talentDevelopmentAssignments.length" class="mt-2 text-xs text-sky-700">当前还没有接管中的培养对象</div>
      <div v-else class="mt-3 grid gap-3 md:grid-cols-2">
        <div
          v-for="member in talentDevelopmentAssignments"
          :key="`training-${member.member_id}`"
          class="rounded-lg bg-white px-3 py-3 text-xs text-slate-700"
        >
          <div class="font-medium text-slate-900">{{ member.name || member.member_id }}</div>
          <div class="mt-1">{{ member.primary_role || '--' }}</div>
          <div class="mt-1">状态 {{ member.onboarding?.status || '--' }}</div>
          <div class="mt-1">训练阶段 {{ member.training_plan?.stage || '--' }}</div>
          <div class="mt-1">目标 {{ member.growth_state?.next_goal || '--' }}</div>
          <div class="mt-1">下一步 {{ member.training_plan?.next_action || '--' }}</div>
          <div class="mt-1">建档时间 {{ formatDate(member.onboarding?.created_at) }}</div>
        </div>
      </div>
      </div>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

type GenericRecord = Record<string, any>

const props = defineProps<{
  selectedChildMemberDraft: GenericRecord | null
  selectedChildMemberRuntime: GenericRecord | null
  autonomyStatus: GenericRecord | null
  trainingReviewRunning: boolean
  trainingReviewMessage: string
  trainingReviewSuccess: boolean
  trainerIntentSummary: GenericRecord | null
  trainerDirectiveQueue: GenericRecord[]
  trainerAutoAssistEnabled: boolean
  trainerBatchRunning: boolean
  trainerLowRiskSuggestionQueue: GenericRecord[]
  trainerAutoAssistAllowedTakeOver: boolean
  trainerAutoAssistAllowedReflection: boolean
  trainerAutoAssistAllowedStages: string[]
  trainerActionRunningId: string
  talentDevelopmentAssignments: GenericRecord[]
  formatDate: (value?: string | null) => string
  runTrainingReview: () => void | Promise<void>
  runTrainerLowRiskSuggestionBatch: () => void | Promise<void>
  selectChildMember: (memberId: string) => void
  handleTrainerSuggestedAction: (item: any) => void | Promise<void>
  handleTrainerDirectiveAction: (item: any, actionType: 'take_over' | 'request_reflection' | 'replan_training') => void | Promise<void>
  handleTrainerDirectiveReview: (item: any) => void | Promise<void>
  trainerQueueStatusBadgeClass: (status: string) => string
  workspaceMode?: 'overview' | 'queue' | 'automation' | 'growth'
}>()

const exclusiveWorkspaceMode = ref<'overview' | 'queue' | 'automation' | 'growth'>('overview')

const COACHING_EVENT_STAGES = new Set([
  'task_approved_round',
  'account_variant_clone',
  'independence_handoff',
  'knowledge_followup_closed',
])

const trainerCoachingLogCards = computed(() => {
  const journal = props.selectedChildMemberRuntime?.experience_journal
  const cards = Array.isArray(journal?.cards) ? journal.cards : []
  return cards
    .filter((card: GenericRecord) => {
      const stage = String(card?.stage || '').trim()
      const title = String(card?.title || '').trim()
      return COACHING_EVENT_STAGES.has(stage) || title.includes('【带教】')
    })
    .slice(0, 16)
})

const isExclusiveWorkspaceMode = (value: unknown): value is 'overview' | 'queue' | 'automation' | 'growth' => (
  value === 'overview' || value === 'queue' || value === 'automation' || value === 'growth'
)

const setExclusiveWorkspaceMode = (value: 'overview' | 'queue' | 'automation' | 'growth') => {
  if (exclusiveWorkspaceMode.value === value) return
  exclusiveWorkspaceMode.value = value
}

const exclusiveWorkspaceMeta = computed(() => {
  if (exclusiveWorkspaceMode.value === 'queue') {
    return {
      title: '带教队列视图',
      description: '这里专门看父节点交办给育成官的培养任务、建议动作、当前聚焦对象和培养流水。',
    }
  }
  if (exclusiveWorkspaceMode.value === 'automation') {
    return {
      title: '自动策略视图',
      description: '这里专门管理低风险半自动执行、白名单阶段和批处理动作，不和带教队列混排。',
    }
  }
  if (exclusiveWorkspaceMode.value === 'growth') {
    return {
      title: '自我发展视图',
      description: '这里专门看育成官自己的发展等级、缺口、下一里程碑和最近培养对象。',
    }
  }
  return {
    title: '巡检总览视图',
    description: '这里专门看训练巡检结果、当前带教规模、当前意图和下一轮育成动作。',
  }
})

const exclusiveWorkspaceCards = computed(() => ([
  {
    key: 'overview',
    title: '巡检总览',
    description: '先看最近巡检结果、当前带教规模和本轮育成意图。',
    badge: exclusiveWorkspaceMode.value === 'overview' ? '当前' : '总览',
    badgeClass: exclusiveWorkspaceMode.value === 'overview' ? 'bg-sky-600 text-white' : 'bg-sky-100 text-sky-700',
    active: exclusiveWorkspaceMode.value === 'overview',
    activeClass: 'border-sky-300 bg-sky-50 shadow-sm',
    idleClass: 'border-sky-200 bg-white hover:bg-sky-50/60',
  },
  {
    key: 'queue',
    title: '带教队列',
    description: '查看父节点交办、建议动作和当前最该接手的对象。',
    badge: exclusiveWorkspaceMode.value === 'queue' ? '当前' : (props.trainerDirectiveQueue.length ? `${props.trainerDirectiveQueue.length} 项` : '空队列'),
    badgeClass: exclusiveWorkspaceMode.value === 'queue' ? 'bg-violet-600 text-white' : (props.trainerDirectiveQueue.length ? 'bg-violet-100 text-violet-700' : 'bg-slate-100 text-slate-600'),
    active: exclusiveWorkspaceMode.value === 'queue',
    activeClass: 'border-violet-300 bg-violet-50 shadow-sm',
    idleClass: 'border-violet-200 bg-white hover:bg-violet-50/60',
  },
  {
    key: 'automation',
    title: '自动策略',
    description: '管理低风险自动执行和可放开的阶段边界。',
    badge: exclusiveWorkspaceMode.value === 'automation' ? '当前' : (props.trainerAutoAssistEnabled ? '已开启' : '未开启'),
    badgeClass: exclusiveWorkspaceMode.value === 'automation' ? 'bg-amber-600 text-white' : (props.trainerAutoAssistEnabled ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'),
    active: exclusiveWorkspaceMode.value === 'automation',
    activeClass: 'border-amber-300 bg-amber-50 shadow-sm',
    idleClass: 'border-amber-200 bg-white hover:bg-amber-50/60',
  },
  {
    key: 'growth',
    title: '自我发展',
    description: '查看育成官自己的等级、缺口和最近培养对象。',
    badge: exclusiveWorkspaceMode.value === 'growth' ? '当前' : '成长',
    badgeClass: exclusiveWorkspaceMode.value === 'growth' ? 'bg-emerald-600 text-white' : 'bg-emerald-100 text-emerald-700',
    active: exclusiveWorkspaceMode.value === 'growth',
    activeClass: 'border-emerald-300 bg-emerald-50 shadow-sm',
    idleClass: 'border-emerald-200 bg-white hover:bg-emerald-50/60',
  },
]) as Array<{
  key: 'overview' | 'queue' | 'automation' | 'growth'
  title: string
  description: string
  badge: string
  badgeClass: string
  active: boolean
  activeClass: string
  idleClass: string
}>)

watch(() => props.selectedChildMemberDraft?.primary_role, (value) => {
  if (String(value || '') === 'talent_development') {
    if (isExclusiveWorkspaceMode(props.workspaceMode)) return
    setExclusiveWorkspaceMode('overview')
  }
}, { immediate: true })

watch(() => props.workspaceMode, (value) => {
  if (!isExclusiveWorkspaceMode(value) || value === exclusiveWorkspaceMode.value) return
  exclusiveWorkspaceMode.value = value
}, { immediate: true })

watch(exclusiveWorkspaceMode, (value) => {
  if (value === props.workspaceMode) return
  emit('update:workspaceMode', value)
})

const emit = defineEmits<{
  'update:trainerAutoAssistEnabled': [value: boolean]
  'update:trainerAutoAssistAllowedTakeOver': [value: boolean]
  'update:trainerAutoAssistAllowedReflection': [value: boolean]
  'update:trainerAutoAssistAllowedStages': [value: string[]]
  'update:workspaceMode': [value: 'overview' | 'queue' | 'automation' | 'growth']
}>()
</script>
