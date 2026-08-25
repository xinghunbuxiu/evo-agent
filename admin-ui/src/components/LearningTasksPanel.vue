<template>
  <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
    <div class="flex items-start justify-between gap-4 mb-4">
      <div>
        <h2 class="text-lg font-semibold">后台学习任务</h2>
        <p class="text-slate-500 text-sm mt-1">这里展示系统已经真正发起的学习任务，而不是停留在“应该去学什么”的计划阶段。</p>
      </div>
      <button
        @click="loadLearningTasks"
        :disabled="learningTasksLoading"
        class="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
      >
        {{ learningTasksLoading ? '刷新中...' : '刷新学习任务' }}
      </button>
    </div>

    <div class="mb-4 rounded-2xl border border-teal-200 bg-teal-50/60 px-4 py-4 text-sm text-teal-950">
      <div class="font-medium">这块看什么</div>
      <div class="mt-2 leading-6">
        先看系统有没有真的把“不会的东西”变成学习任务，再看这些任务有没有进入验证、比较和稳定晋升，而不是一直卡在计划里。
      </div>
    </div>

    <div v-if="!learningTasks.length" class="rounded-xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
      当前没有需要外部学习的任务，说明现有样本暂时都处在稳定或本地可处理状态。
    </div>
    <div v-else class="space-y-4">
      <div
        v-for="task in learningTasks"
        :key="task.task_id"
        class="rounded-xl border border-slate-200 bg-white px-4 py-4"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-sm font-medium text-slate-900">{{ task.tenant_id }}</div>
            <div class="mt-1 text-xs text-slate-500 break-all">{{ task.source_dir || task.bundle_path || '--' }}</div>
          </div>
          <div class="text-right text-xs text-slate-500">
            <div>{{ task.status || '--' }}</div>
            <div class="mt-1">{{ task.updated_at?.replace('T', ' ').slice(0, 19) || '--' }}</div>
          </div>
        </div>

        <div class="mt-3 grid gap-3 md:grid-cols-2">
          <div class="rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-600">
            <div>问题分类：{{ task.issue_category || '--' }}</div>
            <div class="mt-1">学习来源：{{ (task.preferred_sources || []).join(' -> ') || '--' }}</div>
            <div class="mt-1">验证门禁：{{ task.validation_gate || '--' }}</div>
            <div v-if="typeof task.stable_cycle_count === 'number'" class="mt-1">
              连续稳定轮次：{{ task.stable_cycle_count }}
              <span
                v-if="task.stable_cycle_count >= 2"
                class="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700"
              >
                已达稳定经验门槛
              </span>
            </div>
          </div>
          <div class="rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-600">
            <div>下一步：{{ task.next_validation_action || '--' }}</div>
            <div v-if="task.last_comparison" class="mt-1">
              最近比较：
              <span
                class="rounded-full px-2 py-0.5 text-[11px] font-medium"
                :class="comparisonBadgeClass(task.last_comparison.result || task.last_comparison.outcome)"
              >
                {{ task.last_comparison.result || task.last_comparison.outcome || '--' }}
              </span>
              <span v-if="typeof task.last_comparison.score_delta === 'number'">
                / delta {{ formatDelta(task.last_comparison.score_delta) }}
              </span>
            </div>
            <div v-if="task.source_runs?.length" class="mt-2 flex flex-wrap gap-2">
              <span
                v-for="run in task.source_runs"
                :key="`${task.task_id}-${run.source}`"
                class="rounded-full bg-white px-2.5 py-1 text-xs text-slate-500"
              >
                {{ run.source }} / {{ run.status }} / {{ run.candidate_count }}
              </span>
            </div>
          </div>
        </div>

        <div
          v-if="task.last_comparison || task.comparison_history?.length || task.stable_promoted_at"
          class="mt-3 grid gap-3 md:grid-cols-2"
        >
          <div class="rounded-lg border border-emerald-100 bg-emerald-50/60 px-3 py-3 text-sm text-slate-700">
            <div class="font-medium text-slate-900">观察比较</div>
            <div class="mt-2">
              当前结果：
              <span
                class="rounded-full px-2 py-0.5 text-[11px] font-medium"
                :class="comparisonBadgeClass(task.last_comparison?.result || task.last_comparison?.outcome)"
              >
                {{ task.last_comparison?.result || task.last_comparison?.outcome || '--' }}
              </span>
            </div>
            <div class="mt-1">最新重放：{{ task.last_comparison?.replay_task_id || '--' }}</div>
            <div class="mt-1">对照源任务：{{ task.last_comparison?.original_task_id || '--' }}</div>
            <div class="mt-1">
              分数变化：
              {{ typeof task.last_comparison?.score_delta === 'number' ? formatDelta(task.last_comparison?.score_delta) : '--' }}
            </div>
          </div>
          <div class="rounded-lg border border-emerald-100 bg-emerald-50/60 px-3 py-3 text-sm text-slate-700">
            <div class="font-medium text-slate-900">观察轨迹</div>
            <div class="mt-2">比较次数：{{ task.comparison_history?.length || 0 }}</div>
            <div class="mt-1">稳定晋升：{{ task.stable_promoted_at ? formatDate(task.stable_promoted_at) : '--' }}</div>
            <ul v-if="task.comparison_history?.length" class="mt-2 space-y-1 text-xs text-slate-500">
              <li
                v-for="(history, index) in task.comparison_history.slice(0, 3)"
                :key="`${task.task_id}-history-${index}`"
              >
                • {{ formatDate(history.at) }} /
                <span
                  class="rounded-full px-2 py-0.5 text-[11px] font-medium"
                  :class="comparisonBadgeClass(history.result)"
                >
                  {{ history.result || '--' }}
                </span>
              </li>
            </ul>
          </div>
        </div>

        <ul v-if="task.queries?.length" class="mt-3 space-y-1 text-sm text-slate-600">
          <li v-for="query in task.queries" :key="query">• {{ query }}</li>
        </ul>

        <details v-if="task.candidate_approaches?.length" class="mt-3 rounded-lg border border-teal-100 bg-teal-50/40">
          <summary class="cursor-pointer list-none px-3 py-3">
            <div class="flex items-center justify-between gap-3">
              <div class="font-medium text-slate-900">候选解决方案</div>
              <div class="rounded-full bg-white px-3 py-1 text-[11px] text-teal-700">{{ task.candidate_approaches.length }} 条</div>
            </div>
          </summary>
          <div class="border-t border-teal-100 px-3 py-3 grid gap-3 md:grid-cols-2">
            <div
              v-for="candidate in task.candidate_approaches"
              :key="`${task.task_id}-${candidate.source}-${candidate.title}`"
              class="rounded-lg border border-teal-100 bg-white px-3 py-3 text-sm text-slate-700"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="font-medium text-slate-900">{{ candidate.title }}</div>
                <div class="text-xs text-teal-700">{{ candidate.source }} / {{ formatScore(candidate.confidence) }}</div>
              </div>
              <div class="mt-2">{{ candidate.summary }}</div>
              <ul v-if="candidate.evidence?.length" class="mt-2 space-y-1 text-xs text-slate-500">
                <li v-for="evidence in candidate.evidence" :key="evidence">• {{ evidence }}</li>
              </ul>
              <div v-if="candidate.metadata?.signature_score" class="mt-2 text-xs text-teal-700">
                相似度签名：{{ formatScore(Number(candidate.metadata.signature_score)) }}
              </div>
            </div>
          </div>
        </details>

        <div class="mt-3 flex items-center gap-3">
          <button
            @click="triggerLearningTaskValidation(task.task_id)"
            :disabled="validatingLearningTaskId === task.task_id"
            class="px-3 py-2 rounded-lg bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-60"
          >
            {{ validatingLearningTaskId === task.task_id ? '验证中...' : '发起验证' }}
          </button>
          <div class="text-xs text-slate-500">
            {{ task.archived ? '历史档案将重跑实验' : '当前任务将重放最近源任务' }}
          </div>
        </div>
        <div v-if="task.auto_validation?.status" class="mt-2 text-xs text-teal-700">
          自动验证：{{ task.auto_validation.status }} / {{ task.auto_validation.source || '--' }}
          <span v-if="task.auto_validation.created_task_ids?.length">
            / 任务 {{ task.auto_validation.created_task_ids.join(', ') }}
          </span>
          <span v-if="task.auto_validation.validation_ids?.length">
            / 验证 {{ task.auto_validation.validation_ids.join(', ') }}
          </span>
          <span
            v-if="task.auto_validation.source === 'observation_loop'"
            class="ml-2 rounded-full bg-teal-100 px-2 py-0.5 text-[11px] font-medium text-teal-700"
          >
            后台自动观察
          </span>
        </div>
      </div>
    </div>
    <p v-if="learningTaskMessage" class="mt-4 text-sm text-teal-700">{{ learningTaskMessage }}</p>
  </div>
</template>

<script setup lang="ts">
type GenericRecord = Record<string, any>

defineProps<{
  learningTasksLoading: boolean
  learningTasks: GenericRecord[]
  validatingLearningTaskId: string
  learningTaskMessage: string
  formatDate: (value?: string | null) => string
  formatScore: (value?: number | null) => string
  formatDelta: (value?: number | null) => string
  comparisonBadgeClass: (value?: string | null) => string
  loadLearningTasks: () => void | Promise<void>
  triggerLearningTaskValidation: (taskId: string) => void | Promise<void>
}>()
</script>
