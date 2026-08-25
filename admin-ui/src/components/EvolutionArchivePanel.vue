<template>
  <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
    <div class="flex items-start justify-between gap-4 mb-4">
      <div>
        <h2 class="text-lg font-semibold">成长档案</h2>
        <p class="text-slate-500 text-sm mt-1">展示系统过去如何从 review/failed 样本进入实验，再形成升级候选和平台共享。</p>
      </div>
      <button
        @click="loadEvolutionOverview"
        :disabled="evolutionLoading"
        class="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
      >
        {{ evolutionLoading ? '刷新中...' : '刷新成长档案' }}
      </button>
    </div>

    <div class="mb-4 rounded-2xl border border-violet-200 bg-violet-50/60 px-4 py-4 text-sm text-violet-950">
      <div class="font-medium">这块看什么</div>
      <div class="mt-2 leading-6">
        这里不是看即时任务，而是看系统过去怎样从失败样本里长出经验。重点看有没有形成可复盘案例、有没有进入升级候选、有没有真正被沉淀下来。
      </div>
    </div>

    <div class="grid gap-3 md:grid-cols-4">
      <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">样本总数</div>
        <div class="mt-2 font-medium text-slate-900">{{ evolutionOverview?.summary?.total_tasks ?? '--' }}</div>
      </div>
      <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">平均评分</div>
        <div class="mt-2 font-medium text-slate-900">{{ formatScore(evolutionOverview?.summary?.avg_score) }}</div>
      </div>
      <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">待复盘</div>
        <div class="mt-2 font-medium text-slate-900">{{ evolutionOverview?.summary?.review_count ?? '--' }}</div>
      </div>
      <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">已晋升</div>
        <div class="mt-2 font-medium text-slate-900">{{ evolutionOverview?.summary?.promoted_count ?? '--' }}</div>
      </div>
    </div>

    <details v-if="growthTimeline.length" class="mt-4 rounded-xl border border-slate-200 bg-slate-50/70">
      <summary class="cursor-pointer list-none px-4 py-4">
        <div class="flex items-center justify-between gap-3">
          <div class="text-sm font-medium text-slate-900">成长时间线</div>
          <div class="rounded-full bg-white px-3 py-1 text-[11px] text-slate-600">{{ growthTimeline.length }} 条</div>
        </div>
      </summary>
      <div class="space-y-3 border-t border-slate-200 px-4 py-4">
        <div
          v-for="item in growthTimeline"
          :key="`${item.timestamp}-${item.strategy_id}-${item.event_type}`"
          class="rounded-xl border border-slate-200 bg-white px-4 py-3"
        >
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="text-sm font-medium text-slate-900">{{ item.title || item.event_type || '--' }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ item.strategy_id || '--' }}</div>
            </div>
            <div class="text-xs text-slate-500">{{ formatDate(item.timestamp) }}</div>
          </div>
          <div class="mt-2 text-sm text-slate-600">{{ item.detail || '--' }}</div>
        </div>
      </div>
    </details>

    <div v-if="reviewQueueTop.length" class="mt-4">
      <div class="text-sm font-medium text-slate-900 mb-3">关键复盘案例</div>
      <div class="space-y-4">
        <div
          v-for="item in reviewQueueTop"
          :key="item.id"
          class="rounded-xl border border-indigo-100 bg-indigo-50/40 px-4 py-4"
        >
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="text-sm font-medium text-slate-900">{{ item.strategy_id || item.id }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ item.alert_reason || '--' }} / {{ item.status || '--' }}</div>
            </div>
            <div class="text-right text-xs text-slate-500">
              <div>{{ formatDate(item.created_at) }}</div>
              <div class="mt-1">avg {{ formatScore(item.avg_eval) }}</div>
            </div>
          </div>
          <div class="mt-3 text-sm text-slate-600">{{ item.notes || item.draft?.summary || '--' }}</div>

          <div v-if="item.experiment_runs?.[0]?.summary" class="mt-3 rounded-lg bg-white px-3 py-3 text-sm text-slate-600">
            <div>实验状态：{{ item.experiment_runs[0].summary?.status || '--' }}</div>
            <div class="mt-1">分数变化：{{ formatDelta(item.experiment_runs[0].summary?.score_delta) }}</div>
            <div class="mt-1">建议动作：{{ item.experiment_runs[0].summary?.recommended_action || '--' }}</div>
          </div>

          <div v-if="item.upgrade_candidate" class="mt-3 rounded-lg bg-white px-3 py-3 text-sm text-slate-600">
            <div>升级候选：{{ item.upgrade_candidate.title || '--' }}</div>
            <div class="mt-1">决策：{{ item.upgrade_candidate.decision || '--' }}</div>
            <div class="mt-1">{{ item.upgrade_candidate.summary || '--' }}</div>
          </div>

          <div v-if="item.platform_promotion?.status" class="mt-3 text-sm text-indigo-700">
            平台共享：{{ item.platform_promotion.status }} / {{ formatDate(item.platform_promotion.promoted_at) }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
type GenericRecord = Record<string, any>

defineProps<{
  evolutionLoading: boolean
  evolutionOverview: GenericRecord | null
  growthTimeline: GenericRecord[]
  reviewQueueTop: GenericRecord[]
  formatDate: (value?: string | null) => string
  formatScore: (value?: number | null) => string
  formatDelta: (value?: number | null) => string
  loadEvolutionOverview: () => void | Promise<void>
}>()
</script>
