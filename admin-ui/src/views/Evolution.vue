<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      eyebrow="成长 · 复盘"
      :title="sectionMeta.title"
      :description="sectionMeta.description"
      :loading="loading"
      refresh-label="刷新"
      :back-to="{ path: '/dashboard' }"
      back-label="返回公司总览"
      @refresh="refreshSection"
    >
      <template #actions>
        <router-link
          to="/organization/knowledge"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          知识库
        </router-link>
        <router-link
          to="/organization/tasks"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          任务队列
        </router-link>
      </template>
    </WorkspacePageHeader>

    <WorkspaceSubNav
      orientation="horizontal"
      :items="subNavItems"
      @select="onSectionSelect"
    />

    <div v-show="activeSection === 'overview'" class="space-y-5">
    <section
      v-if="weeklyBriefing"
      class="rounded-2xl border border-indigo-200 bg-[linear-gradient(135deg,#eef2ff_0%,#ffffff_100%)] p-5 shadow-sm"
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="text-[11px] font-medium uppercase tracking-[0.16em] text-indigo-600">{{ weeklyBriefing.period_label }}</div>
          <h2 class="mt-2 text-lg font-semibold text-slate-900">{{ weeklyBriefing.headline }}</h2>
          <p class="mt-1 text-xs text-indigo-800">{{ weeklyBriefing.readiness_stage }} · 就绪 {{ weeklyBriefing.readiness_score }}%</p>
        </div>
        <router-link
          to="/organization/finance"
          class="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs text-indigo-800 hover:bg-indigo-50"
        >
          财务决策
        </router-link>
      </div>
      <ul class="mt-4 space-y-2 text-sm text-slate-700">
        <li v-for="item in weeklyBriefing.bullets" :key="item">· {{ item }}</li>
      </ul>
      <div class="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <div class="rounded-xl bg-white/80 px-3 py-3 text-center text-xs text-slate-600">
          <div class="text-lg font-bold text-slate-900">{{ weeklyBriefing.operations.members }}</div>
          <div class="mt-1">员工</div>
        </div>
        <div class="rounded-xl bg-white/80 px-3 py-3 text-center text-xs text-slate-600">
          <div class="text-lg font-bold text-slate-900">{{ weeklyBriefing.operations.tasks_approved }}</div>
          <div class="mt-1">已确认任务</div>
        </div>
        <div class="rounded-xl bg-white/80 px-3 py-3 text-center text-xs text-slate-600">
          <div class="text-lg font-bold text-amber-700">{{ weeklyBriefing.operations.tasks_submitted }}</div>
          <div class="mt-1">待确认</div>
        </div>
        <div class="rounded-xl bg-white/80 px-3 py-3 text-center text-xs text-slate-600">
          <div class="text-lg font-bold text-sky-700">{{ weeklyBriefing.operations.knowledge_learning_active }}</div>
          <div class="mt-1">补知识中</div>
        </div>
        <div class="rounded-xl bg-white/80 px-3 py-3 text-center text-xs text-slate-600">
          <div class="text-lg font-bold text-slate-900">{{ weeklyBriefing.operations.work_types }}</div>
          <div class="mt-1">工种</div>
        </div>
        <div class="rounded-xl bg-white/80 px-3 py-3 text-center text-xs text-slate-600">
          <div class="text-lg font-bold text-slate-900">{{ weeklyBriefing.operations.training_reviews }}</div>
          <div class="mt-1">育成复盘</div>
        </div>
      </div>
      <ul v-if="weeklyBriefing.next_actions?.length" class="mt-4 space-y-1 text-xs text-indigo-900">
        <li v-for="item in weeklyBriefing.next_actions" :key="`wb-${item}`">→ {{ item }}</li>
      </ul>
    </section>
    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <article class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="text-xs uppercase tracking-[0.18em] text-slate-400">Tasks</div>
        <div class="mt-3 text-3xl font-bold text-slate-900">{{ overview?.summary.tasks_total ?? 0 }}</div>
        <p class="mt-2 text-sm text-slate-500">当前租户任务总数</p>
      </article>
      <article class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="text-xs uppercase tracking-[0.18em] text-slate-400">Decisions</div>
        <div class="mt-3 text-3xl font-bold text-slate-900">{{ overview?.summary.decision_events ?? 0 }}</div>
        <p class="mt-2 text-sm text-slate-500">可回放的自主决策事件</p>
      </article>
      <article class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="text-xs uppercase tracking-[0.18em] text-slate-400">Experiences</div>
        <div class="mt-3 text-3xl font-bold text-slate-900">{{ overview?.summary.experiences_total ?? 0 }}</div>
        <p class="mt-2 text-sm text-slate-500">沉淀到经验库的样本数</p>
      </article>
      <article class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="text-xs uppercase tracking-[0.18em] text-slate-400">Eval Score</div>
        <div class="mt-3 text-3xl font-bold text-slate-900">{{ formatMetric(overview?.summary.avg_evaluation_score) }}</div>
        <p class="mt-2 text-sm text-slate-500">平均评估分，越稳定越接近成长闭环</p>
      </article>
      <article class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="text-xs uppercase tracking-[0.18em] text-slate-400">Override Hits</div>
        <div class="mt-3 text-3xl font-bold text-slate-900">{{ overview?.summary.override_hits ?? 0 }}</div>
        <p class="mt-2 text-sm text-slate-500">
          override 命中成功率 {{ formatPercent(overview?.summary.override_success_rate) }}
        </p>
      </article>
    </section>

    <section class="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
      <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div class="flex items-center justify-between gap-4">
          <div>
            <h2 class="text-lg font-semibold text-slate-900">成长分层治理</h2>
            <p class="mt-1 text-sm text-slate-500">把“先私有成长，再项目复用，最后平台共享”明确展示出来，避免系统一开始就把所有经验混在一起。</p>
          </div>
          <div class="text-xs text-slate-400">policy {{ overview?.knowledge_policy?.share_mode || 'private_only' }}</div>
        </div>
        <div class="mt-4 grid gap-3 md:grid-cols-3">
          <div class="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
            <div class="text-xs uppercase tracking-[0.16em] text-emerald-700">Private Growth</div>
            <div class="mt-2 text-2xl font-bold text-slate-900">{{ overview?.summary.experiences_total ?? 0 }}</div>
            <div class="mt-2 text-sm text-slate-600">租户自己的经验、失败、重放结果先在私有层稳定收敛。</div>
          </div>
          <div class="rounded-2xl border border-sky-200 bg-sky-50 p-4">
            <div class="text-xs uppercase tracking-[0.16em] text-sky-700">Project Review</div>
            <div class="mt-2 text-2xl font-bold text-slate-900">{{ overview?.strategy_review_queue.length ?? 0 }}</div>
            <div class="mt-2 text-sm text-slate-600">进入复盘、实验和升级候选后，才算进入项目可复用阶段。</div>
          </div>
          <div class="rounded-2xl border border-fuchsia-200 bg-fuchsia-50 p-4">
            <div class="text-xs uppercase tracking-[0.16em] text-fuchsia-700">Platform Shared</div>
            <div class="mt-2 text-2xl font-bold text-slate-900">{{ overview?.platform_shared_promotions?.length ?? 0 }}</div>
            <div class="mt-2 text-sm text-slate-600">平台共享层只接收已经证明有效、可复用、可审计的经验和策略。</div>
          </div>
        </div>
        <div v-if="overview?.knowledge_layer_advice" class="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="text-sm font-semibold text-slate-900">经验分层建议</div>
              <div class="mt-1 text-sm text-slate-600">{{ overview.knowledge_layer_advice.headline }}</div>
            </div>
            <span class="rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-700">
              {{ overview.knowledge_layer_advice.overall_stage }}
            </span>
          </div>
          <div class="mt-3 text-sm text-slate-500">{{ overview.knowledge_layer_advice.recommendation_reason }}</div>
          <div class="mt-4 grid gap-3 md:grid-cols-3">
            <div
              v-for="layer in overview.knowledge_layer_advice.layers"
              :key="layer.key"
              class="rounded-xl bg-white px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-slate-900">{{ layer.label }}</div>
                <span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{{ layer.status }}</span>
              </div>
              <div class="mt-2 text-2xl font-bold text-slate-900">{{ layer.count }}</div>
              <div class="mt-2 text-xs text-slate-500">{{ layer.reason }}</div>
              <div class="mt-2 text-xs text-slate-400">{{ layer.next_action }}</div>
            </div>
          </div>
          <ul v-if="overview.knowledge_layer_advice.next_actions?.length" class="mt-4 space-y-1 text-sm text-slate-600">
            <li v-for="item in overview.knowledge_layer_advice.next_actions" :key="item">• {{ item }}</li>
          </ul>
        </div>
      </article>

      <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 class="text-lg font-semibold text-slate-900">当前共享策略</h2>
        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <div class="rounded-xl bg-slate-50 px-4 py-3">
            <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Share Mode</div>
            <div class="mt-2 text-lg font-semibold text-slate-900">{{ overview?.knowledge_policy?.share_mode || 'private_only' }}</div>
            <div class="mt-1 text-sm text-slate-500">
              {{ knowledgeShareDescription }}
            </div>
          </div>
          <div class="rounded-xl bg-slate-50 px-4 py-3">
            <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Promotion Gate</div>
            <div class="mt-2 text-lg font-semibold" :class="overview?.platform_promotion_status?.allowed ? 'text-emerald-700' : 'text-rose-700'">
              {{ overview?.platform_promotion_status?.allowed ? '允许上报' : '禁止上报' }}
            </div>
            <div class="mt-1 text-sm text-slate-500">
              {{ overview?.platform_promotion_status?.reason || '当前没有策略说明' }}
            </div>
          </div>
        </div>
      </article>
    </section>
    </div>

    <p v-if="error" class="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
      {{ error }}
    </p>

    <div
      v-if="compareState"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4"
    >
      <div class="w-full max-w-5xl rounded-3xl bg-white p-6 shadow-2xl">
        <div class="flex items-center justify-between gap-4">
          <div>
            <h2 class="text-xl font-semibold text-slate-900">重放对比</h2>
            <p class="mt-1 text-sm text-slate-500">对比原任务与最近一次重放的状态、能力、策略和评估变化。</p>
          </div>
          <button class="text-sm text-slate-500 hover:text-slate-700" @click="compareState = null">关闭</button>
        </div>

        <div class="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
          <span class="font-medium text-slate-700">结果：</span>
          <span :class="compareOutcomeClass(compareState.diff.outcome)">{{ compareOutcomeLabel(compareState.diff.outcome) }}</span>
          <span class="ml-4 text-slate-500">评估差值 {{ formatSigned(compareState.diff.score_delta) }}</span>
        </div>
        <div
          v-if="compareState.validation_record"
          class="mt-4 rounded-2xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800"
        >
          已沉淀为有效重放样本：{{ compareState.validation_record.id }}
        </div>

        <div class="mt-6 grid gap-4 md:grid-cols-2">
          <div class="rounded-2xl border border-slate-200 p-4">
            <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Original</div>
            <div class="mt-3 space-y-2 text-sm text-slate-600">
              <div><span class="font-medium text-slate-800">Task:</span> {{ compareState.original.task_id }}</div>
              <div><span class="font-medium text-slate-800">Status:</span> {{ compareState.original.status }}</div>
              <div><span class="font-medium text-slate-800">Capability:</span> {{ compareState.original.capability_id || '--' }}</div>
              <div><span class="font-medium text-slate-800">Strategy:</span> {{ compareState.original.strategy_id || '--' }}</div>
              <div><span class="font-medium text-slate-800">Eval:</span> {{ compareState.original.evaluation_verdict || '--' }} / {{ formatMetric(compareState.original.evaluation_score) }}</div>
              <div><span class="font-medium text-slate-800">Summary:</span> {{ compareState.original.summary || '--' }}</div>
              <div v-if="compareState.original.error" class="text-rose-700">{{ compareState.original.error }}</div>
            </div>
          </div>
          <div class="rounded-2xl border border-slate-200 p-4">
            <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Replay</div>
            <div class="mt-3 space-y-2 text-sm text-slate-600">
              <div><span class="font-medium text-slate-800">Task:</span> {{ compareState.replay.task_id }}</div>
              <div><span class="font-medium text-slate-800">Status:</span> {{ compareState.replay.status }}</div>
              <div><span class="font-medium text-slate-800">Capability:</span> {{ compareState.replay.capability_id || '--' }}</div>
              <div><span class="font-medium text-slate-800">Strategy:</span> {{ compareState.replay.strategy_id || '--' }}</div>
              <div><span class="font-medium text-slate-800">Eval:</span> {{ compareState.replay.evaluation_verdict || '--' }} / {{ formatMetric(compareState.replay.evaluation_score) }}</div>
              <div><span class="font-medium text-slate-800">Summary:</span> {{ compareState.replay.summary || '--' }}</div>
              <div v-if="compareState.replay.error" class="text-rose-700">{{ compareState.replay.error }}</div>
            </div>
          </div>
        </div>

        <div class="mt-6 grid gap-3 md:grid-cols-3">
          <div class="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
            <div class="font-medium text-slate-800">状态变化</div>
            <div class="mt-2">{{ compareState.diff.status_changed ? '已变化' : '无变化' }}</div>
          </div>
          <div class="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
            <div class="font-medium text-slate-800">能力变化</div>
            <div class="mt-2">{{ compareState.diff.capability_changed ? '已变化' : '无变化' }}</div>
          </div>
          <div class="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
            <div class="font-medium text-slate-800">策略变化</div>
            <div class="mt-2">{{ compareState.diff.strategy_changed ? '已变化' : '无变化' }}</div>
          </div>
        </div>
      </div>
    </div>

    <div v-show="activeSection === 'review'" class="space-y-6">
        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold text-slate-900">失败任务复盘</h2>
            <span class="text-sm text-slate-400">{{ overview?.review_cases.length ?? 0 }} 条</span>
          </div>
          <div v-if="!overview?.review_cases.length" class="py-10 text-center text-sm text-slate-500">
            最近没有 `failed/review` 样本，当前阶段比较稳定。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="item in overview?.review_cases"
              :key="`review-${item.task_id}-${item.created_at}`"
              class="rounded-2xl border border-rose-100 bg-rose-50/60 p-4"
            >
              <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="rounded-full bg-slate-900 px-2.5 py-1 text-xs font-medium text-white">{{ item.task_type }}</span>
                    <span class="rounded-full bg-rose-100 px-2.5 py-1 text-xs font-medium text-rose-700">{{ item.status }}</span>
                    <span
                      v-if="item.issue_category"
                      class="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-medium text-violet-700"
                    >
                      {{ categoryLabel(item.issue_category) }}
                    </span>
                    <span
                      v-if="item.evaluation_verdict"
                      class="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-700"
                    >
                      {{ item.evaluation_verdict }}
                    </span>
                  </div>
                  <div class="mt-3 text-sm font-medium text-slate-900">{{ item.strategy_id || '未命中策略' }}</div>
                  <div class="mt-1 text-sm text-slate-500">{{ item.capability_id || '未选择能力' }}</div>
                  <div
                    v-if="item.strategy_runtime_adjustments?.override_active"
                    class="mt-2 inline-flex rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700"
                  >
                    override 生效中
                  </div>
                </div>
                <div class="text-right text-xs text-slate-400">
                  <div>{{ formatDate(item.created_at) }}</div>
                  <div class="mt-2">评估 {{ formatMetric(item.evaluation_score) }}</div>
                </div>
              </div>
              <p v-if="item.error" class="mt-3 rounded-xl bg-white px-3 py-2 text-sm text-rose-700">
                {{ item.error }}
              </p>
              <p v-else-if="item.summary" class="mt-3 text-sm leading-6 text-slate-600">{{ item.summary }}</p>
              <div v-if="item.issue_hints?.length" class="mt-3 flex flex-wrap gap-2">
                <span
                  v-for="hint in item.issue_hints"
                  :key="hint"
                  class="rounded-full bg-white px-3 py-1 text-xs text-slate-500"
                >
                  {{ hint }}
                </span>
              </div>
              <div v-if="item.recommended_actions?.length" class="mt-4 rounded-2xl border border-amber-100 bg-amber-50/70 p-4">
                <h3 class="text-xs font-semibold uppercase tracking-[0.16em] text-amber-700">建议动作</h3>
                <ul class="mt-3 space-y-2 text-sm leading-6 text-amber-900">
                  <li v-for="action in item.recommended_actions" :key="action">• {{ action }}</li>
                </ul>
              </div>
              <button
                class="mt-3 mr-3 text-sm font-medium text-slate-700 hover:text-slate-900"
                @click="replayReviewTask(item.task_id)"
              >
                重放任务
              </button>
              <button
                class="mt-3 mr-3 text-sm font-medium text-teal-700 hover:text-teal-900"
                @click="openCompare(item.task_id)"
              >
                查看对比
              </button>
              <button
                class="mt-3 text-sm font-medium text-rose-700 hover:text-rose-800"
                @click="toggleDecision(`review:${item.task_id}`)"
              >
                {{ expandedDecisions.has(`review:${item.task_id}`) ? '收起复盘' : '展开复盘' }}
              </button>
              <div
                v-if="expandedDecisions.has(`review:${item.task_id}`)"
                class="mt-4 grid gap-4 rounded-2xl border border-rose-100 bg-white p-4 md:grid-cols-3"
              >
                <div>
                  <h3 class="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">候选能力</h3>
                  <ul class="mt-3 space-y-2 text-xs leading-5 text-slate-500">
                    <li v-for="candidate in item.candidate_scores || []" :key="candidate.capability_id">
                      <span class="font-medium text-slate-700">{{ candidate.capability_id }}</span>
                      <span class="ml-2">{{ formatMetric(candidate.score) }}</span>
                      <div v-for="reason in candidate.reasons" :key="reason">• {{ reason }}</div>
                    </li>
                    <li v-if="!(item.candidate_scores || []).length">• 无候选细节</li>
                  </ul>
                </div>
                <div>
                  <h3 class="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">策略原因</h3>
                  <ul class="mt-3 space-y-1 text-xs leading-5 text-slate-500">
                    <li v-for="reason in item.strategy_reasons || []" :key="reason">• {{ reason }}</li>
                    <li v-if="!(item.strategy_reasons || []).length">• 无策略解释</li>
                  </ul>
                </div>
                <div>
                  <h3 class="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">评估原因</h3>
                  <ul class="mt-3 space-y-1 text-xs leading-5 text-slate-500">
                    <li v-for="reason in item.evaluation_reasons || []" :key="reason">• {{ reason }}</li>
                    <li v-if="!(item.evaluation_reasons || []).length">• 无评估解释</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">复盘分类</h2>
          <div v-if="!reviewCategoryEntries.length" class="py-10 text-center text-sm text-slate-500">
            暂无复盘分类样本。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="[category, count] in reviewCategoryEntries"
              :key="category"
              class="rounded-xl bg-slate-50 px-4 py-3"
            >
              <div class="flex items-center justify-between text-sm font-medium text-slate-700">
                <span>{{ categoryLabel(category) }}</span>
                <span>{{ count }}</span>
              </div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">Override 风险事件</h2>
          <div v-if="!overview?.auto_rollback_events.length" class="py-10 text-center text-sm text-slate-500">
            当前没有自动回滚事件。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="event in overview?.auto_rollback_events"
              :key="`${event.strategy_id}-${event.rolled_back_at}`"
              class="rounded-xl border border-rose-100 bg-rose-50/60 px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-slate-800">{{ event.strategy_id }}</div>
                <div class="text-xs text-rose-700">{{ formatDate(event.rolled_back_at) }}</div>
              </div>
              <div class="mt-2 text-xs text-slate-500">
                {{ event.reason }} | hits {{ event.hits }} | review {{ formatPercent(event.review_ratio) }} | avg {{ formatMetric(event.avg_eval) }}
              </div>
            </div>
          </div>
        </article>
    </div>

    <div v-show="activeSection === 'trace'" class="space-y-6">
        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold text-slate-900">最近决策</h2>
            <span class="text-sm text-slate-400">{{ overview?.recent_decisions.length ?? 0 }} 条</span>
          </div>
          <div v-if="!overview?.recent_decisions.length" class="py-10 text-center text-sm text-slate-500">
            还没有形成足够的决策轨迹，先跑几次 `analyze/reconstruct` 任务。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="item in overview?.recent_decisions"
              :key="`${item.task_id}-${item.created_at}`"
              class="rounded-2xl border border-slate-100 bg-slate-50/70 p-4"
            >
              <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="rounded-full bg-slate-900 px-2.5 py-1 text-xs font-medium text-white">{{ item.task_type }}</span>
                    <span class="rounded-full bg-teal-100 px-2.5 py-1 text-xs font-medium text-teal-700">{{ item.status }}</span>
                    <span v-if="item.evaluation_verdict" class="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-700">{{ item.evaluation_verdict }}</span>
                  </div>
                  <div class="mt-3 text-sm font-medium text-slate-900">{{ item.strategy_id || '未命中策略' }}</div>
                  <div class="mt-1 text-sm text-slate-500">{{ item.capability_id || '未选择能力' }}</div>
                </div>
                <div class="text-right text-xs text-slate-400">
                  <div>{{ formatDate(item.created_at) }}</div>
                  <div class="mt-2">历史样本 {{ item.history_size ?? 0 }}</div>
                  <div>评估 {{ formatMetric(item.evaluation_score) }}</div>
                </div>
              </div>
              <p v-if="item.summary" class="mt-3 text-sm leading-6 text-slate-600">{{ item.summary }}</p>
              <button
                class="mt-3 text-sm font-medium text-teal-700 hover:text-teal-800"
                @click="toggleDecision(item.task_id)"
              >
                {{ expandedDecisions.has(item.task_id) ? '收起解释' : '查看解释' }}
              </button>
              <div
                v-if="expandedDecisions.has(item.task_id)"
                class="mt-4 grid gap-4 rounded-2xl border border-teal-100 bg-white p-4 md:grid-cols-3"
              >
                <div>
                  <h3 class="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">能力候选分</h3>
                  <div v-if="!item.candidate_scores?.length" class="mt-3 text-sm text-slate-500">无候选明细</div>
                  <div v-else class="mt-3 space-y-3">
                    <div
                      v-for="candidate in item.candidate_scores"
                      :key="`${item.task_id}-${candidate.capability_id}`"
                      class="rounded-xl bg-slate-50 p-3"
                    >
                      <div class="flex items-center justify-between gap-3">
                        <span class="text-sm font-medium text-slate-800">{{ candidate.capability_id }}</span>
                        <span class="text-sm text-slate-500">{{ formatMetric(candidate.score) }}</span>
                      </div>
                      <ul class="mt-2 space-y-1 text-xs leading-5 text-slate-500">
                        <li v-for="reason in candidate.reasons" :key="reason">• {{ reason }}</li>
                      </ul>
                    </div>
                  </div>
                </div>

                <div>
                  <h3 class="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">策略原因</h3>
                  <div class="mt-3 rounded-xl bg-slate-50 p-3">
                    <div class="text-sm font-medium text-slate-800">{{ item.strategy_id || '未命中策略' }}</div>
                    <div class="mt-1 text-xs text-slate-400">策略分 {{ formatMetric(item.strategy_score) }}</div>
                    <div
                      v-if="item.strategy_runtime_adjustments?.override_active"
                      class="mt-2 rounded-lg bg-emerald-50 px-2.5 py-2 text-xs text-emerald-800"
                    >
                      source {{ item.strategy_runtime_adjustments.source || 'manual' }}
                      | weight {{ formatSigned(item.strategy_runtime_adjustments.weight_delta ?? 0) }}
                      | preferred {{ item.strategy_runtime_adjustments.preferred ? 'yes' : 'no' }}
                    </div>
                    <div
                      v-if="typeof item.strategy_runtime_adjustments?.growth_memory_bias === 'number'"
                      class="mt-2 rounded-lg bg-sky-50 px-2.5 py-2 text-xs text-sky-800"
                    >
                      growth memory bias {{ formatSigned(item.strategy_runtime_adjustments.growth_memory_bias) }}
                    </div>
                    <div
                      v-if="typeof item.strategy_runtime_adjustments?.platform_shared_bias === 'number'"
                      class="mt-2 rounded-lg bg-indigo-50 px-2.5 py-2 text-xs text-indigo-800"
                    >
                      platform shared bias {{ formatSigned(item.strategy_runtime_adjustments.platform_shared_bias) }}
                      | hits {{ item.strategy_runtime_adjustments.platform_shared_hits || 0 }}
                    </div>
                    <div
                      v-if="item.strategy_runtime_adjustments?.platform_shared_titles?.length"
                      class="mt-2 flex flex-wrap gap-2"
                    >
                      <span
                        v-for="title in item.strategy_runtime_adjustments.platform_shared_titles"
                        :key="title"
                        class="rounded-full bg-indigo-100 px-2.5 py-1 text-xs text-indigo-700"
                      >
                        {{ title }}
                      </span>
                    </div>
                    <ul class="mt-3 space-y-1 text-xs leading-5 text-slate-500">
                      <li v-for="reason in item.strategy_reasons || []" :key="reason">• {{ reason }}</li>
                      <li v-if="!(item.strategy_reasons || []).length">• 暂无策略解释</li>
                    </ul>
                  </div>
                </div>

                <div>
                  <h3 class="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">评估反馈</h3>
                  <div class="mt-3 rounded-xl bg-slate-50 p-3">
                    <div class="flex items-center justify-between gap-3">
                      <span class="text-sm font-medium text-slate-800">{{ item.evaluation_verdict || 'none' }}</span>
                      <span class="text-sm text-slate-500">{{ formatMetric(item.evaluation_score) }}</span>
                    </div>
                    <ul class="mt-3 space-y-1 text-xs leading-5 text-slate-500">
                      <li v-for="reason in item.evaluation_reasons || []" :key="reason">• {{ reason }}</li>
                      <li v-if="!(item.evaluation_reasons || []).length">• 暂无评估解释</li>
                    </ul>
                    <div v-if="item.evaluation_metrics && Object.keys(item.evaluation_metrics).length" class="mt-3 flex flex-wrap gap-2">
                      <span
                        v-for="(value, key) in item.evaluation_metrics"
                        :key="key"
                        class="rounded-full bg-white px-2.5 py-1 text-xs text-slate-500"
                      >
                        {{ key }}: {{ value }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">经验沉淀</h2>
          <div v-if="!overview?.recent_experiences.length" class="py-10 text-center text-sm text-slate-500">
            当前租户还没有最近经验文件。
          </div>
          <div v-else class="mt-4 grid gap-3 md:grid-cols-2">
            <div
              v-for="exp in overview?.recent_experiences"
              :key="exp.id"
              class="rounded-2xl border border-slate-100 bg-white p-4 shadow-[0_8px_20px_rgba(15,23,42,0.04)]"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="flex items-center gap-2">
                  <div class="text-sm font-semibold text-slate-900">{{ exp.task_type }}</div>
                  <span
                    v-if="exp.experience_kind === 'role_reflection'"
                    class="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800"
                  >
                    岗位反思
                  </span>
                </div>
                <div class="text-sm font-semibold text-teal-600">{{ formatMetric(exp.evaluation_score ?? exp.quality_score) }}</div>
              </div>
              <div class="mt-2 text-xs uppercase tracking-[0.16em] text-slate-400">{{ exp.domain }}</div>
              <p class="mt-3 text-sm leading-6 text-slate-600">{{ exp.output_summary }}</p>
              <div v-if="exp.experience_kind === 'role_reflection'" class="mt-3 text-xs text-slate-500">
                {{ exp.member_name || exp.member_id || 'unknown member' }} / {{ exp.primary_role || 'unknown role' }}
                <span v-if="exp.stage"> / {{ exp.stage }}</span>
                <span v-if="exp.status"> / {{ exp.status }}</span>
              </div>
              <div class="mt-3 flex items-center justify-between text-xs text-slate-400">
                <span>{{ exp.strategy_id || 'strategy:none' }}</span>
                <span>{{ formatDate(exp.created_at) }}</span>
              </div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">岗位反思记忆</h2>
          <div v-if="!overview?.recent_role_reflections.length" class="py-10 text-center text-sm text-slate-500">
            当前还没有子女岗位反思进入经验层。
          </div>
          <div v-else class="mt-4 grid gap-3 md:grid-cols-2">
            <div
              v-for="item in overview?.recent_role_reflections"
              :key="item.id"
              class="rounded-2xl border border-amber-100 bg-amber-50/60 p-4"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-semibold text-slate-900">{{ item.member_name || item.member_id || 'unknown member' }}</div>
                <div class="text-xs text-slate-500">{{ formatDate(item.created_at) }}</div>
              </div>
              <div class="mt-2 text-xs uppercase tracking-[0.16em] text-amber-700">
                {{ item.primary_role || 'unknown role' }} / {{ item.domain }}
                <span v-if="item.stage"> / {{ item.stage }}</span>
                <span v-if="item.status"> / {{ item.status }}</span>
              </div>
              <div class="mt-3 text-sm leading-6 text-slate-700">{{ item.summary }}</div>
              <div v-if="item.next_experiment" class="mt-3 text-xs text-slate-500">
                next experiment: {{ item.next_experiment }}
              </div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">有效重放样本</h2>
          <div v-if="!overview?.replay_validations.length" class="py-10 text-center text-sm text-slate-500">
            还没有沉淀出有效重放样本。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="item in overview?.replay_validations"
              :key="item.id"
              class="rounded-xl bg-slate-50 px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-slate-800">{{ item.output_summary }}</div>
                <div class="text-sm text-green-700">{{ formatSigned(item.score_delta) }}</div>
              </div>
              <div class="mt-2 text-xs text-slate-500">
                {{ item.original_task_id }} -> {{ item.replay_task_id }} | {{ formatDate(item.created_at) }}
              </div>
            </div>
          </div>
        </article>
    </div>

    <div v-show="activeSection === 'strategy'" class="space-y-6">
        <article class="rounded-2xl border border-teal-200 bg-teal-50/60 p-5 shadow-sm">
          <h2 class="text-sm font-semibold text-teal-950">日常巡检</h2>
          <p class="mt-1 text-xs text-teal-800">优先完成这三步；高级策略治理在下方展开。</p>
          <div class="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              class="rounded-lg border border-teal-200 bg-white px-3 py-2 text-sm text-teal-800 hover:bg-teal-50"
              @click="onSectionSelect('review')"
            >
              查看待复盘（{{ overview?.review_cases.length ?? 0 }}）
            </button>
            <router-link
              to="/organization/finance"
              class="rounded-lg border border-teal-200 bg-white px-3 py-2 text-sm text-teal-800 hover:bg-teal-50"
            >
              记录收支决策
            </router-link>
            <button
              type="button"
              class="rounded-lg border border-teal-200 bg-white px-3 py-2 text-sm text-teal-800 hover:bg-teal-50"
              :disabled="loading"
              @click="refreshSection"
            >
              {{ loading ? '刷新中…' : '刷新成长数据' }}
            </button>
          </div>
        </article>

        <details class="rounded-2xl border border-slate-200 bg-white shadow-sm">
          <summary class="cursor-pointer px-5 py-4 text-sm font-semibold text-slate-900">
            高级策略治理（能力热度、复盘队列、平台晋升）
          </summary>
          <div class="space-y-6 border-t border-slate-100 p-5">
        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">能力与策略热度</h2>
          <div class="mt-5">
            <h3 class="text-sm font-medium text-slate-500">Top Capabilities</h3>
            <div class="mt-3 space-y-3">
              <div v-for="item in overview?.top_capabilities" :key="item.id">
                <div class="flex items-center justify-between text-sm">
                  <span class="truncate text-slate-700">{{ item.id }}</span>
                  <span class="text-slate-400">{{ item.count }}</span>
                </div>
                <div class="mt-2 h-2 rounded-full bg-slate-100">
                  <div class="h-2 rounded-full bg-teal-500" :style="{ width: `${ratio(item.count, maxCapabilityCount)}%` }" />
                </div>
              </div>
            </div>
          </div>
          <div class="mt-6">
            <h3 class="text-sm font-medium text-slate-500">Top Strategies</h3>
            <div class="mt-3 space-y-3">
              <div v-for="item in overview?.top_strategies" :key="item.id">
                <div class="flex items-center justify-between text-sm">
                  <span class="truncate text-slate-700">{{ item.id }}</span>
                  <span class="text-slate-400">{{ item.count }}</span>
                </div>
                <div class="mt-2 h-2 rounded-full bg-slate-100">
                  <div class="h-2 rounded-full bg-slate-900" :style="{ width: `${ratio(item.count, maxStrategyCount)}%` }" />
                </div>
              </div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">评估分布</h2>
          <div v-if="!verdictEntries.length" class="py-10 text-center text-sm text-slate-500">
            暂无评估结果。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div v-for="[verdict, count] in verdictEntries" :key="verdict" class="rounded-xl bg-slate-50 px-4 py-3">
              <div class="flex items-center justify-between text-sm font-medium text-slate-700">
                <span>{{ verdict }}</span>
                <span>{{ count }}</span>
              </div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">成长记忆</h2>
          <div v-if="!overview?.growth_events.length" class="py-10 text-center text-sm text-slate-500">
            当前还没有成长事件记忆。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="event in overview?.growth_events"
              :key="event.id"
              class="rounded-xl bg-slate-50 px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <div class="text-sm font-medium text-slate-800">
                    {{ event.member_name || event.strategy_id || 'system' }}
                  </div>
                  <div v-if="event.primary_role" class="mt-1 text-xs text-slate-500">
                    {{ event.primary_role }}
                  </div>
                </div>
                <div class="text-xs text-slate-500">{{ formatDate(event.created_at) }}</div>
              </div>
              <div class="mt-2 text-xs text-slate-500">
                {{ event.event_type || 'growth_event' }}
                <span v-if="event.task_type"> | task {{ event.task_type }}</span>
                <span v-if="event.domain"> | domain {{ event.domain }}</span>
                <span v-if="event.training_stage_from || event.training_stage_to">
                  | stage {{ event.training_stage_from || '--' }} -> {{ event.training_stage_to || '--' }}
                </span>
                <span v-if="event.mission_status"> | mission {{ event.mission_status }}</span>
                | score {{ formatMetric(event.quality_score) }}
              </div>
              <div class="mt-2 text-sm text-slate-600">{{ event.output_summary }}</div>
              <div v-if="event.next_action" class="mt-2 text-xs text-teal-700">
                下一步：{{ event.next_action }}
              </div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">重放增益排行</h2>
          <div v-if="!overview?.positive_strategies.length" class="py-10 text-center text-sm text-slate-500">
            还没有足够的正向重放样本来统计策略增益。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="item in overview?.positive_strategies"
              :key="item.strategy_id"
              class="rounded-xl bg-slate-50 px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-slate-800">{{ item.strategy_id }}</div>
                <div class="text-sm text-green-700">+{{ item.avg_gain.toFixed(2) }}</div>
              </div>
              <div class="mt-2 text-xs text-slate-500">
                正向样本 {{ item.count }} 次 | 总增益 {{ item.total_gain.toFixed(2) }}
              </div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">低收益策略预警</h2>
          <div v-if="!overview?.strategy_alerts.length" class="py-10 text-center text-sm text-slate-500">
            当前还没有需要重点预警的策略。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="item in overview?.strategy_alerts"
              :key="item.strategy_id"
              class="rounded-xl border border-rose-100 bg-rose-50/60 px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-slate-800">{{ item.strategy_id }}</div>
                <div class="text-sm text-rose-700">{{ item.alert_reason }}</div>
              </div>
              <div class="mt-2 text-xs text-slate-500">
                使用 {{ item.count }} 次 | review 比例 {{ (item.review_ratio * 100).toFixed(0) }}% | 平均评估 {{ item.avg_eval.toFixed(2) }} | 总增益 {{ item.total_gain.toFixed(2) }}
              </div>
              <button
                class="mt-3 text-sm font-medium text-rose-700 hover:text-rose-900"
                @click="enqueueStrategyReview(item)"
              >
                加入复盘队列
              </button>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">策略复盘队列</h2>
          <div v-if="!overview?.strategy_review_queue.length" class="py-10 text-center text-sm text-slate-500">
            当前复盘队列为空。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="item in overview?.strategy_review_queue"
              :key="item.id"
              class="rounded-xl bg-slate-50 px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-slate-800">{{ item.strategy_id }}</div>
                <div class="text-sm text-slate-500">{{ item.status }}</div>
              </div>
              <div class="mt-2 text-xs text-slate-500">
                {{ item.alert_reason || item.reason || '待复盘' }} | {{ formatDate(item.created_at) }}
              </div>
              <button
                class="mt-3 text-sm font-medium text-teal-700 hover:text-teal-900"
                @click="generateDraft(item.id)"
              >
                {{ item.draft ? '重新生成草案' : '生成优化草案' }}
              </button>
              <button
                v-if="item.draft"
                class="mt-3 ml-3 text-sm font-medium text-amber-700 hover:text-amber-900"
                @click="generateExperiment(item.id)"
              >
                {{ item.experiment_plan ? '重新生成实验计划' : '生成重放实验计划' }}
              </button>
              <button
                v-if="item.experiment_plan"
                class="mt-3 ml-3 text-sm font-medium text-rose-700 hover:text-rose-900"
                @click="runExperiment(item.id)"
              >
                执行实验计划
              </button>
              <div v-if="item.draft" class="mt-4 rounded-2xl border border-teal-100 bg-teal-50/50 p-4">
                <div class="text-sm font-medium text-slate-900">{{ item.draft.summary }}</div>
                <div class="mt-3 text-xs uppercase tracking-[0.16em] text-slate-400">目标</div>
                <ul class="mt-2 space-y-1 text-sm text-slate-600">
                  <li v-for="goal in item.draft.goals" :key="goal">• {{ goal }}</li>
                </ul>
                <div class="mt-3 text-xs uppercase tracking-[0.16em] text-slate-400">假设</div>
                <ul class="mt-2 space-y-1 text-sm text-slate-600">
                  <li v-for="hypothesis in item.draft.hypotheses" :key="hypothesis">• {{ hypothesis }}</li>
                </ul>
                <div class="mt-3 text-xs uppercase tracking-[0.16em] text-slate-400">拟议改动</div>
                <ul class="mt-2 space-y-1 text-sm text-slate-600">
                  <li v-for="change in item.draft.proposed_changes" :key="change">• {{ change }}</li>
                </ul>
                <div class="mt-3 text-xs uppercase tracking-[0.16em] text-slate-400">验证计划</div>
                <ul class="mt-2 space-y-1 text-sm text-slate-600">
                  <li v-for="plan in item.draft.validation_plan" :key="plan">• {{ plan }}</li>
                </ul>
              </div>
              <div v-if="item.experiment_plan" class="mt-4 rounded-2xl border border-amber-100 bg-amber-50/50 p-4">
                <div class="text-sm font-medium text-slate-900">{{ item.experiment_plan.title }}</div>
                <div class="mt-2 text-xs text-slate-500">
                  样本数 {{ item.experiment_plan.sample_count }} | {{ item.experiment_plan.next_action }}
                </div>
                <div class="mt-3 text-xs uppercase tracking-[0.16em] text-slate-400">实验步骤</div>
                <ul class="mt-2 space-y-1 text-sm text-slate-600">
                  <li v-for="step in item.experiment_plan.steps" :key="step">• {{ step }}</li>
                </ul>
                <div class="mt-3 text-xs uppercase tracking-[0.16em] text-slate-400">验收标准</div>
                <ul class="mt-2 space-y-1 text-sm text-slate-600">
                  <li v-for="rule in item.experiment_plan.acceptance_criteria" :key="rule">• {{ rule }}</li>
                </ul>
              </div>
              <div v-if="item.experiment_runs?.length" class="mt-4 rounded-2xl border border-rose-100 bg-rose-50/40 p-4">
                <div class="flex items-center justify-between gap-3">
                  <div class="text-sm font-medium text-slate-900">实验执行批次</div>
                  <div class="text-xs text-slate-500">最近执行 {{ formatDate(item.last_run_at || item.experiment_runs[0]?.created_at) }}</div>
                </div>
                <div class="mt-3 space-y-3">
                  <div
                    v-for="run in item.experiment_runs"
                    :key="`${item.id}-${run.created_at}`"
                    class="rounded-xl bg-white px-3 py-3"
                  >
                    <div class="text-sm font-medium text-slate-800">{{ run.plan_title || '重放实验' }}</div>
                    <div class="mt-1 text-xs text-slate-500">
                      请求 {{ run.sample_count_requested }} 个样本，已创建 {{ run.sample_count_actual }} 个回放任务
                    </div>
                    <div
                      v-if="run.summary"
                      class="mt-2 text-xs font-medium"
                      :class="runStatusClass(run.summary.status)"
                    >
                      {{ runStatusLabel(run.summary.status) }}
                    </div>
                    <div v-if="run.summary" class="mt-2 grid gap-2 md:grid-cols-2">
                      <div class="rounded-lg bg-slate-50 px-2.5 py-2 text-xs text-slate-600">
                        完成 {{ run.summary.completed }} / {{ run.sample_count_actual }}
                        | 待完成 {{ run.summary.pending }}
                      </div>
                      <div class="rounded-lg bg-slate-50 px-2.5 py-2 text-xs text-slate-600">
                        success {{ run.summary.success }} | review {{ run.summary.review }} | failed {{ run.summary.failed }}
                      </div>
                      <div class="rounded-lg bg-slate-50 px-2.5 py-2 text-xs text-slate-600">
                        基线 {{ formatMetric(run.summary.baseline_avg_score) }}
                        -> 实验 {{ formatMetric(run.summary.avg_score) }}
                        ({{ formatSigned(run.summary.score_delta) }})
                      </div>
                      <div class="rounded-lg bg-slate-50 px-2.5 py-2 text-xs text-slate-600">
                        improved {{ run.summary.improved_count }} | regressed {{ run.summary.regressed_count }} | unchanged {{ run.summary.unchanged_count }}
                      </div>
                    </div>
                    <div class="mt-2 text-xs text-slate-500">
                      Source: {{ run.source_task_ids.join(', ') || '--' }}
                    </div>
                    <div class="mt-1 text-xs text-teal-700">
                      Replay: {{ run.task_ids.join(', ') || '--' }}
                    </div>
                    <div v-if="run.summary?.recommended_action" class="mt-2 rounded-lg bg-amber-50 px-2.5 py-2 text-xs text-amber-800">
                      {{ run.summary.recommended_action }}
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="item.upgrade_candidate" class="mt-4 rounded-2xl border border-green-100 bg-green-50/50 p-4">
                <div class="flex items-center justify-between gap-3">
                  <div class="text-sm font-medium text-slate-900">{{ item.upgrade_candidate.title }}</div>
                  <div
                    class="text-xs font-medium"
                    :class="upgradeDecisionClass(item.upgrade_candidate.decision)"
                  >
                    {{ upgradeDecisionLabel(item.upgrade_candidate.decision) }}
                  </div>
                </div>
                <div class="mt-2 text-sm text-slate-600">{{ item.upgrade_candidate.summary }}</div>
                <div
                  v-if="item.platform_promotion"
                  class="mt-3 inline-flex rounded-full px-2.5 py-1 text-xs font-medium"
                  :class="platformPromotionClass(item.platform_promotion.status)"
                >
                  {{ platformPromotionLabel(item.platform_promotion.status) }}
                </div>
                <div class="mt-3 text-xs uppercase tracking-[0.16em] text-slate-400">候选依据</div>
                <ul class="mt-2 space-y-1 text-sm text-slate-600">
                  <li v-for="reason in item.upgrade_candidate.rationale" :key="reason">• {{ reason }}</li>
                </ul>
                <div class="mt-3 text-xs uppercase tracking-[0.16em] text-slate-400">建议动作</div>
                <ul class="mt-2 space-y-1 text-sm text-slate-600">
                  <li v-for="action in item.upgrade_candidate.proposed_actions" :key="action">• {{ action }}</li>
                </ul>
                <div class="mt-3 text-xs uppercase tracking-[0.16em] text-slate-400">风险检查</div>
                <ul class="mt-2 space-y-1 text-sm text-slate-600">
                  <li v-for="check in item.upgrade_candidate.risk_checks" :key="check">• {{ check }}</li>
                </ul>
                <div class="mt-3 rounded-xl bg-white px-3 py-2 text-xs text-slate-500">
                  {{ item.upgrade_candidate.decision_note || '等待决策' }}
                  <span v-if="item.upgrade_candidate.decided_at"> | {{ formatDate(item.upgrade_candidate.decided_at) }}</span>
                </div>
                <div class="mt-3 flex flex-wrap gap-3">
                  <button
                    class="text-sm font-medium text-green-700 hover:text-green-900"
                    @click="decideUpgrade(item.id, 'accept')"
                  >
                    采纳升级
                  </button>
                  <button
                    class="text-sm font-medium text-amber-700 hover:text-amber-900"
                    @click="decideUpgrade(item.id, 'observe')"
                  >
                    继续观察
                  </button>
                  <button
                    class="text-sm font-medium text-rose-700 hover:text-rose-900"
                    @click="decideUpgrade(item.id, 'reject')"
                  >
                    拒绝升级
                  </button>
                  <button
                    v-if="!item.platform_promotion"
                    class="text-sm font-medium text-sky-700 hover:text-sky-900 disabled:cursor-not-allowed disabled:text-slate-400"
                    :disabled="!overview?.platform_promotion_status?.allowed"
                    @click="promoteToPlatform(item.id)"
                  >
                    上报平台共享层
                  </button>
                </div>
                <div v-if="overview?.platform_promotion_status" class="mt-3 rounded-xl bg-white px-3 py-2 text-xs text-slate-500">
                  平台共享策略：{{ overview.platform_promotion_status.allowed ? '允许' : '禁止' }}
                  | {{ overview.platform_promotion_status.reason }}
                </div>
                <div v-if="item.platform_promotion" class="mt-3 rounded-xl bg-sky-50 px-3 py-2 text-xs text-sky-800">
                  已上报平台共享层
                  <span v-if="item.platform_promotion.promoted_at"> | {{ formatDate(item.platform_promotion.promoted_at) }}</span>
                  <span v-if="item.platform_promotion.path"> | {{ item.platform_promotion.path }}</span>
                </div>
              </div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">平台共享层</h2>
          <div
            v-if="overview?.platform_promotion_status"
            class="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600"
          >
            当前租户共享策略：{{ overview.platform_promotion_status.allowed ? '可上报' : '不可上报' }}
            | 模式 {{ overview.platform_promotion_status.share_mode }}
            | {{ overview.platform_promotion_status.reason }}
          </div>
          <div v-if="!overview?.platform_shared_promotions?.length" class="py-10 text-center text-sm text-slate-500">
            目前还没有平台共享层样本。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="item in overview?.platform_shared_promotions"
              :key="item.id"
              class="rounded-xl border border-sky-100 bg-sky-50/50 px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-slate-800">{{ item.title || item.strategy_id || 'unknown strategy' }}</div>
                <div class="text-xs text-slate-500">{{ formatDate(item.promoted_at) }}</div>
              </div>
              <div class="mt-2 text-xs text-slate-500">
                tenant {{ item.tenant_id || '--' }} | strategy {{ item.strategy_id || '--' }} | mode {{ item.share_mode || '--' }}
              </div>
              <div v-if="item.summary" class="mt-2 text-sm text-slate-600">{{ item.summary }}</div>
              <div class="mt-2 text-xs text-sky-800">
                {{ upgradeDecisionLabel(item.decision) }}
                <span v-if="item.path"> | {{ item.path }}</span>
              </div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">成长时间线</h2>
          <div v-if="!overview?.growth_timeline.length" class="py-10 text-center text-sm text-slate-500">
            当前还没有可展示的成长事件。
          </div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="event in overview?.growth_timeline"
              :key="`${event.event_type}-${event.strategy_id}-${event.timestamp}`"
              class="rounded-xl border border-slate-100 bg-slate-50/70 px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="flex items-center gap-2">
                  <span
                    class="rounded-full px-2.5 py-1 text-xs font-medium"
                    :class="timelineEventClass(event.event_type)"
                  >
                    {{ event.title }}
                  </span>
                  <span class="text-sm font-medium text-slate-800">{{ event.strategy_id || 'system' }}</span>
                </div>
                <div class="text-xs text-slate-500">{{ formatDate(event.timestamp) }}</div>
              </div>
              <div v-if="event.detail" class="mt-2 text-sm text-slate-600">{{ event.detail }}</div>
            </div>
          </div>
        </article>

        <article class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">插件与域</h2>
          <div class="mt-4 grid gap-4">
            <div class="rounded-xl bg-slate-50 p-4">
              <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Loaded Plugins</div>
              <div class="mt-3 flex flex-wrap gap-2">
                <span
                  v-for="name in overview?.plugin_policy.loaded"
                  :key="name"
                  class="rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white"
                >
                  {{ name }}
                </span>
                <span v-if="!overview?.plugin_policy.loaded?.length" class="text-sm text-slate-500">无插件</span>
              </div>
            </div>
            <div class="rounded-xl bg-slate-50 p-4">
              <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Enabled Policy</div>
              <div class="mt-3 flex flex-wrap gap-2">
                <span
                  v-for="name in overview?.plugin_policy.enabled"
                  :key="name"
                  class="rounded-full bg-teal-100 px-3 py-1 text-xs font-medium text-teal-700"
                >
                  {{ name }}
                </span>
                <span v-if="!overview?.plugin_policy.enabled?.length" class="text-sm text-slate-500">未设置白名单</span>
              </div>
            </div>
            <div class="rounded-xl bg-slate-50 p-4">
              <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Observed Domains</div>
              <div class="mt-3 flex flex-wrap gap-2">
                <span
                  v-for="domain in overview?.domains"
                  :key="domain"
                  class="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-700"
                >
                  {{ domain }}
                </span>
                <span v-if="!overview?.domains?.length" class="text-sm text-slate-500">暂无经验域</span>
              </div>
            </div>
            <div class="rounded-xl bg-slate-50 p-4">
              <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Strategy Overrides</div>
              <div v-if="!strategyOverrideEntries.length" class="mt-3 text-sm text-slate-500">当前没有生效中的运行时策略覆盖。</div>
              <div v-else class="mt-3 space-y-3">
                <div
                  v-for="[strategyId, override] in strategyOverrideEntries"
                  :key="strategyId"
                  class="rounded-lg bg-white px-3 py-3"
                >
                  <div class="text-sm font-medium text-slate-800">{{ strategyId }}</div>
                  <div class="mt-1 text-xs text-slate-500">
                    weight {{ formatSigned(override.weight_delta ?? 0) }}
                    | preferred {{ override.preferred ? 'yes' : 'no' }}
                    | blocked {{ override.blocked ? 'yes' : 'no' }}
                  </div>
                  <div class="mt-1 text-xs text-slate-500">
                    {{ override.source || 'manual' }}<span v-if="override.updated_at"> | {{ formatDate(override.updated_at) }}</span>
                    <span v-if="override.expires_at"> | expires {{ formatDate(override.expires_at) }}</span>
                  </div>
                  <div
                    v-if="overview?.override_stats?.[strategyId]"
                    class="mt-2 rounded-lg bg-slate-50 px-2.5 py-2 text-xs text-slate-600"
                  >
                    hits {{ overview.override_stats[strategyId].hits }}
                    | success {{ overview.override_stats[strategyId].success }}
                    | review {{ overview.override_stats[strategyId].review }}
                    | failed {{ overview.override_stats[strategyId].failed }}
                    | avg {{ formatMetric(overview.override_stats[strategyId].avg_eval) }}
                    | {{ overview.override_stats[strategyId].status === 'risky' ? '风险偏高' : '运行正常' }}
                  </div>
                  <button
                    class="mt-2 text-xs font-medium text-rose-700 hover:text-rose-900"
                    @click="rollbackOverride(strategyId)"
                  >
                    回滚 override
                  </button>
                </div>
              </div>
            </div>
          </div>
        </article>
          </div>
        </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import WorkspaceSubNav, { type WorkspaceSubNavItem } from '../components/shell/WorkspaceSubNav.vue'
import {
  addStrategyReviewQueue,
  decideStrategyUpgradeCandidate,
  generateStrategyReviewDraft,
  generateStrategyReviewExperiment,
  getEvolutionOverview,
  promoteStrategyReviewToPlatform,
  rollbackStrategyOverride,
  runStrategyReviewExperiment,
  type EvolutionOverview,
} from '../api/evolution'
import { getTaskCompare, replayTask, type TaskCompareResult } from '../api/tasks'
import { getWeeklyBriefing, type WeeklyBriefing } from '../api/finance'

type EvolutionSection = 'overview' | 'review' | 'trace' | 'strategy'

const route = useRoute()
const router = useRouter()
const activeSection = ref<EvolutionSection>('overview')

const tenantId = ref(localStorage.getItem('tenant_id') || 'default')
const loading = ref(false)
const error = ref('')
const overview = ref<EvolutionOverview | null>(null)
const weeklyBriefing = ref<WeeklyBriefing | null>(null)
const expandedDecisions = ref<Set<string>>(new Set())
const compareState = ref<TaskCompareResult | null>(null)

const maxCapabilityCount = computed(() =>
  Math.max(1, ...(overview.value?.top_capabilities.map((item) => item.count) || [1]))
)
const maxStrategyCount = computed(() =>
  Math.max(1, ...(overview.value?.top_strategies.map((item) => item.count) || [1]))
)
const verdictEntries = computed(() =>
  Object.entries(overview.value?.evaluation_verdicts || {}).sort((a, b) => b[1] - a[1])
)
const reviewCategoryEntries = computed(() =>
  Object.entries(overview.value?.review_category_counts || {}).sort((a, b) => b[1] - a[1])
)
const strategyOverrideEntries = computed(() =>
  Object.entries(overview.value?.strategy_overrides || {}).sort((a, b) => a[0].localeCompare(b[0]))
)
const knowledgeShareDescription = computed(() => {
  const shareMode = overview.value?.knowledge_policy?.share_mode
  if (shareMode === 'platform_share') return '允许在满足门禁后进入平台共享层。'
  if (shareMode === 'reviewed_share') return '先走 review，再决定是否共享。'
  return '当前只在租户私有层内生长。'
})

const sectionMeta = computed(() => {
  const map: Record<EvolutionSection, { title: string; description: string }> = {
    overview: { title: '成长总览', description: '任务、决策、经验与评估分摘要；判断系统是否在真正收敛。' },
    review: { title: '失败复盘', description: 'failed/review 样本、复盘分类与 override 风险事件。' },
    trace: { title: '决策轨迹', description: '最近决策、经验沉淀、岗位反思与有效重放样本。' },
    strategy: { title: '策略治理', description: '能力/策略热度、复盘队列、平台共享与插件域状态。' },
  }
  return map[activeSection.value]
})

const subNavItems = computed<WorkspaceSubNavItem[]>(() => ([
  { key: 'overview', title: '总览', badge: String(overview.value?.summary.tasks_total ?? 0), active: activeSection.value === 'overview' },
  { key: 'review', title: '复盘', badge: String(overview.value?.review_cases.length ?? 0), active: activeSection.value === 'review' },
  { key: 'trace', title: '轨迹', badge: String(overview.value?.recent_decisions.length ?? 0), active: activeSection.value === 'trace' },
  { key: 'strategy', title: '策略', badge: String(overview.value?.strategy_review_queue.length ?? 0), active: activeSection.value === 'strategy' },
]))

const normalizeSection = (value: unknown): EvolutionSection => {
  const section = String(value || '').trim()
  if (section === 'review' || section === 'trace' || section === 'strategy') return section
  return 'overview'
}

const onSectionSelect = (key: string) => {
  const section = normalizeSection(key)
  activeSection.value = section
  router.replace({
    path: route.path,
    query: section === 'overview' ? {} : { section },
  })
}

const refreshSection = async () => {
  await loadOverview()
}

watch(() => route.query.section, (value) => {
  activeSection.value = normalizeSection(value)
}, { immediate: true })

const timelineEventClass = (eventType?: string) => {
  if (eventType === 'auto_rollback') return 'bg-rose-100 text-rose-700'
  if (eventType === 'upgrade_decision') return 'bg-emerald-100 text-emerald-700'
  if (eventType === 'experiment_run') return 'bg-amber-100 text-amber-700'
  if (eventType === 'upgrade_candidate') return 'bg-teal-100 text-teal-700'
  return 'bg-slate-100 text-slate-700'
}

const formatMetric = (value?: number | null) =>
  typeof value === 'number' ? value.toFixed(2) : '--'

const formatPercent = (value?: number | null) =>
  typeof value === 'number' ? `${(value * 100).toFixed(0)}%` : '--'

const formatDate = (value?: string) => {
  if (!value) return '--'
  return value.replace('T', ' ').slice(0, 19)
}

const ratio = (value: number, max: number) => Math.max(6, Math.round((value / max) * 100))

const categoryLabel = (category?: string) => {
  switch (category) {
    case 'input_gap':
      return '输入不足'
    case 'plugin_policy_gap':
      return '插件策略限制'
    case 'capability_gap':
      return '能力空间不足'
    case 'strategy_gap':
      return '策略覆盖不足'
    case 'execution_error':
      return '执行链路错误'
    case 'evaluator_strict':
      return '评估未放行'
    default:
      return category || '未分类'
  }
}

const compareOutcomeLabel = (outcome?: string) => {
  if (outcome === 'improved') return '较原任务更好'
  if (outcome === 'regressed') return '较原任务退化'
  return '变化不明显'
}

const compareOutcomeClass = (outcome?: string) => {
  if (outcome === 'improved') return 'text-green-700'
  if (outcome === 'regressed') return 'text-rose-700'
  return 'text-slate-600'
}

const runStatusLabel = (status?: string) => {
  if (status === 'running') return '实验进行中'
  if (status === 'improved') return '实验验证正向'
  if (status === 'regressed') return '实验出现退化'
  if (status === 'mixed') return '实验结果混合'
  return status || '待汇总'
}

const runStatusClass = (status?: string) => {
  if (status === 'running') return 'text-amber-700'
  if (status === 'improved') return 'text-green-700'
  if (status === 'regressed') return 'text-rose-700'
  return 'text-slate-600'
}

const upgradeDecisionLabel = (decision?: string) => {
  if (decision === 'accept') return '已采纳'
  if (decision === 'auto_accept') return '自动采纳'
  if (decision === 'observe') return '继续观察'
  if (decision === 'reject') return '已拒绝'
  return '待决策'
}

const upgradeDecisionClass = (decision?: string) => {
  if (decision === 'accept') return 'text-green-700'
  if (decision === 'auto_accept') return 'text-emerald-700'
  if (decision === 'observe') return 'text-amber-700'
  if (decision === 'reject') return 'text-rose-700'
  return 'text-slate-600'
}

const platformPromotionLabel = (status?: string) => {
  if (status === 'promoted') return '已进入平台共享层'
  return status || '共享状态未知'
}

const platformPromotionClass = (status?: string) => {
  if (status === 'promoted') return 'bg-sky-100 text-sky-700'
  return 'bg-slate-100 text-slate-700'
}

const formatSigned = (value?: number | null) => {
  if (typeof value !== 'number') return '--'
  return value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2)
}

const toggleDecision = (taskId: string) => {
  const next = new Set(expandedDecisions.value)
  if (next.has(taskId)) {
    next.delete(taskId)
  } else {
    next.add(taskId)
  }
  expandedDecisions.value = next
}

const loadOverview = async () => {
  loading.value = true
  error.value = ''
  expandedDecisions.value = new Set()
  localStorage.setItem('tenant_id', tenantId.value || 'default')

  try {
    const [response, briefingResult] = await Promise.all([
      getEvolutionOverview(tenantId.value || 'default'),
      getWeeklyBriefing(tenantId.value || 'default').catch(() => null),
    ])
    overview.value = response.data || null
    weeklyBriefing.value = briefingResult?.data || null
  } catch (err) {
    console.error('Failed to load evolution overview', err)
    error.value = '成长控制台加载失败，请确认后端服务和租户数据已准备好'
  } finally {
    loading.value = false
  }
}

const replayReviewTask = async (taskId: string) => {
  try {
    await replayTask(taskId)
    await loadOverview()
  } catch (err) {
    console.error('Failed to replay task', err)
    error.value = '任务重放失败，请检查后端服务是否正常'
  }
}

const openCompare = async (taskId: string) => {
  try {
    const response = await getTaskCompare(taskId)
    if (response.success && response.data) {
      compareState.value = response.data
      return
    }
    error.value = response.message || '暂无可对比的重放任务'
  } catch (err) {
    console.error('Failed to load comparison', err)
    error.value = '对比加载失败，请先至少重放一次任务'
  }
}

const enqueueStrategyReview = async (item: {
  strategy_id: string
  count: number
  review_ratio: number
  avg_eval: number
  total_gain: number
  alert_reason: string
}) => {
  try {
    await addStrategyReviewQueue(tenantId.value || 'default', {
      strategy_id: item.strategy_id,
      reason: 'strategy_alert',
      alert_reason: item.alert_reason,
      count: item.count,
      review_ratio: item.review_ratio,
      avg_eval: item.avg_eval,
      total_gain: item.total_gain,
    })
    await loadOverview()
  } catch (err) {
    console.error('Failed to enqueue strategy review', err)
    error.value = '加入复盘队列失败'
  }
}

const generateDraft = async (reviewId: string) => {
  try {
    await generateStrategyReviewDraft(tenantId.value || 'default', reviewId)
    await loadOverview()
  } catch (err) {
    console.error('Failed to generate review draft', err)
    error.value = '生成优化草案失败'
  }
}

const generateExperiment = async (reviewId: string) => {
  try {
    await generateStrategyReviewExperiment(tenantId.value || 'default', reviewId)
    await loadOverview()
  } catch (err) {
    console.error('Failed to generate experiment plan', err)
    error.value = '生成重放实验计划失败'
  }
}

const runExperiment = async (reviewId: string) => {
  try {
    await runStrategyReviewExperiment(tenantId.value || 'default', reviewId)
    await loadOverview()
  } catch (err) {
    console.error('Failed to run experiment plan', err)
    error.value = '执行实验计划失败，请确认该策略已有可重放历史样本'
  }
}

const decideUpgrade = async (
  reviewId: string,
  decision: 'accept' | 'observe' | 'reject'
) => {
  try {
    await decideStrategyUpgradeCandidate(tenantId.value || 'default', reviewId, decision)
    await loadOverview()
  } catch (err) {
    console.error('Failed to decide upgrade candidate', err)
    error.value = '更新升级候选决策失败'
  }
}

const promoteToPlatform = async (reviewId: string) => {
  try {
    await promoteStrategyReviewToPlatform(tenantId.value || 'default', reviewId)
    await loadOverview()
  } catch (err) {
    console.error('Failed to promote review entry to platform', err)
    error.value = '上报平台共享层失败，请先检查租户共享策略和升级候选状态'
  }
}

const rollbackOverride = async (strategyId: string) => {
  try {
    await rollbackStrategyOverride(tenantId.value || 'default', strategyId)
    await loadOverview()
  } catch (err) {
    console.error('Failed to rollback strategy override', err)
    error.value = '回滚策略 override 失败'
  }
}

onMounted(loadOverview)
</script>
