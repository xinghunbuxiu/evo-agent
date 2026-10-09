<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      eyebrow="员工空间"
      title="员工工作台"
      description="某位员工自己的岗位空间：任务执行、复盘、协作与经验沉淀。"
      hint="不是公司设置页；育成师派任务后在这里提交结果与复盘。"
      :loading="loading"
      refresh-label="刷新工作台"
      :back-to="{ path: '/dashboard' }"
      back-label="返回公司总览"
      @refresh="loadWorkspace"
    >
      <template #actions>
        <router-link
          to="/organization/parent/workspace"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          公司设置
        </router-link>
      </template>
    </WorkspacePageHeader>

    <div class="grid gap-6 xl:grid-cols-[280px_1fr]">
      <aside class="space-y-4">
        <div class="rounded-2xl border border-emerald-200 bg-[linear-gradient(135deg,#f0fdf4_0%,#ffffff_100%)] p-4 shadow-sm">
          <div class="text-sm font-semibold text-slate-900">当前员工</div>
          <div v-if="selectedMember" class="mt-3 space-y-3">
            <div>
              <div class="text-lg font-semibold text-slate-900">{{ selectedMember.name || selectedMember.member_id || '--' }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ selectedMember.primary_role || '--' }}</div>
            </div>
            <div class="rounded-xl bg-white/90 px-3 py-3 text-sm text-slate-700">
              <div class="text-slate-400">当前专注</div>
              <div class="mt-2 font-medium text-slate-900">{{ selectedMember.growth_state?.current_focus || selectedMember.training_plan?.next_action || '--' }}</div>
            </div>
            <router-link
              :to="selectedMember ? `/organization/trainer/talent_development_officer/workspace?mode=dispatch&dispatchTab=confirm&member=${encodeURIComponent(String(selectedMember.member_id || ''))}` : '/organization/trainer/talent_development_officer/workspace?mode=dispatch&dispatchTab=confirm'"
              class="inline-flex rounded-full border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
            >
              返回育成官协同
            </router-link>
            <div
              v-if="selectedMemberOrganization.departmentLabel || selectedMemberContentDirection"
              class="rounded-xl border border-slate-200 bg-white/90 px-3 py-3 text-xs text-slate-600"
            >
              <div v-if="selectedMemberOrganization.departmentLabel">
                所属部门：{{ selectedMemberOrganization.departmentLabel }}
              </div>
              <div v-if="selectedMemberContentDirection" class="mt-1">
                内容方向：{{ selectedMemberContentDirection }}
              </div>
            </div>
          </div>
          <div v-else class="mt-3 text-sm text-slate-500">
            请选择一位员工进入自己的岗位空间。
          </div>
        </div>

        <div
          v-if="canCloneSelectedMember"
          class="rounded-2xl border border-cyan-200 bg-[linear-gradient(135deg,#ecfeff_0%,#ffffff_100%)] p-4 shadow-sm"
        >
          <div class="text-sm font-semibold text-slate-900">复制同岗位 · 新账号</div>
          <p class="mt-2 text-xs leading-5 text-slate-600">
            技能与工种相同，仅换账号和内容方向。适合第二个头条号等并行产能。
          </p>
          <div class="mt-4 space-y-3">
            <label class="block text-xs text-slate-600">
              <span class="mb-1 block">新员工名称</span>
              <input
                v-model="cloneDraft.name"
                type="text"
                class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="例如 李四头条二号"
              >
            </label>
            <label class="block text-xs text-slate-600">
              <span class="mb-1 block">新账号 ID（account_id）</span>
              <input
                v-model="cloneDraft.accountId"
                type="text"
                class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="例如 toutiao_account_2"
              >
            </label>
            <label class="block text-xs text-slate-600">
              <span class="mb-1 block">内容方向</span>
              <input
                v-model="cloneDraft.contentDirection"
                type="text"
                class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="例如 本地生活 / 科技数码"
              >
            </label>
            <label class="inline-flex items-center gap-2 text-xs text-slate-600">
              <input v-model="cloneDraft.prefillFirstTask" type="checkbox">
              <span>复制后预填首轮派任务草案</span>
            </label>
            <button
              type="button"
              class="w-full rounded-full bg-cyan-700 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-800 disabled:opacity-60"
              :disabled="cloningMember"
              @click="submitAccountVariantClone"
            >
              {{ cloningMember ? '复制中...' : '复制建档' }}
            </button>
            <p v-if="cloneMessage" class="text-xs" :class="cloneSuccess ? 'text-emerald-700' : 'text-red-600'">
              {{ cloneMessage }}
            </p>
          </div>
        </div>

        <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="text-sm font-semibold text-slate-900">岗位成员</div>
              <div class="mt-1 text-xs text-slate-500">公司里每个孩子都应该有自己的一套工作空间。</div>
            </div>
            <div class="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600">
              {{ childMembers.length }}
            </div>
          </div>
          <div v-if="!childMembers.length" class="mt-4 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-sm text-slate-500">
            当前还没有可进入工作台的孩子。
          </div>
          <div v-else class="mt-4 space-y-3">
            <button
              v-for="member in childMembers"
              :key="member.member_id"
              type="button"
              @click="selectMember(member.member_id || '')"
              class="w-full rounded-2xl border px-4 py-4 text-left transition"
              :class="selectedMemberId === member.member_id ? 'border-emerald-300 bg-emerald-50 shadow-sm' : 'border-slate-200 bg-white hover:border-emerald-200 hover:bg-emerald-50/40'"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="font-medium text-slate-900">{{ member.name || member.member_id || '--' }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ member.primary_role || '--' }}</div>
                </div>
                <span class="rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-600">
                  {{ formatLifecycleStage(member.training_plan?.stage || member.onboarding?.status) }}
                </span>
              </div>
              <div class="mt-3 rounded-xl bg-white/80 px-3 py-3 text-xs text-slate-700">
                <div class="text-slate-400">当前专注</div>
                <div class="mt-1 font-medium text-slate-900">{{ member.growth_state?.current_focus || member.training_plan?.next_action || '--' }}</div>
              </div>
            </button>
          </div>
        </div>
      </aside>

      <main v-if="selectedMember" class="space-y-6">
        <div
          v-if="activeOpenTask"
          id="active-formal-task-banner"
          class="rounded-2xl border px-5 py-4 shadow-sm"
          :class="activeOpenTask.status === 'assigned' ? 'border-emerald-300 bg-emerald-50' : 'border-violet-300 bg-violet-50'"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="text-xs font-medium uppercase tracking-[0.16em]" :class="activeOpenTask.status === 'assigned' ? 'text-emerald-700' : 'text-violet-700'">
                {{ activeOpenTask.status === 'assigned' ? '当前待执行' : '当前待确认' }}
              </div>
              <div class="mt-2 text-lg font-semibold text-slate-900">{{ activeOpenTask.title || '--' }}</div>
              <div class="mt-1 text-sm leading-6 text-slate-600">{{ activeOpenTask.objective || '按任务目标推进并整理复盘材料。' }}</div>
            </div>
            <span
              class="rounded-full px-3 py-1 text-[11px] font-medium"
              :class="activeOpenTask.status === 'assigned' ? 'bg-emerald-600 text-white' : 'bg-violet-600 text-white'"
            >
              {{ formatFormalTaskStatus(activeOpenTask.status) }}
            </span>
          </div>
        </div>

        <div
          v-if="taskIntegrationPending"
          id="integration-pending-banner"
          class="rounded-2xl border px-5 py-4 shadow-sm"
          :class="integrationBannerStyle.container"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="text-xs font-medium uppercase tracking-[0.16em] text-slate-700">
                跨工种协作 · {{ integrationBannerStyle.label }}
              </div>
              <div class="mt-2 text-base font-semibold text-slate-900">
                {{ formatIntegrationPhase(taskIntegrationPending.phase) }}
              </div>
              <div class="mt-1 text-sm leading-6 text-slate-600">
                <template v-if="taskIntegrationPending.phase === 'ready_to_integrate'">
                  提供方交付已通过审核。你可以继续完成当前任务中不依赖协作的部分，然后在合适节点对接联调。
                </template>
                <template v-else-if="taskIntegrationPending.phase === 'waiting_delivery'">
                  育成师已指派提供方，对方正在交付。你无需等待，可继续推进当前任务其他工作。
                </template>
                <template v-else>
                  协作请求已提交，等待育成师指派提供方。主任务不会被阻塞。
                </template>
              </div>
            </div>
            <span class="rounded-full px-3 py-1 text-[11px] font-medium" :class="integrationBannerStyle.badge">
              {{ formatIntegrationPhase(taskIntegrationPending.phase) }}
            </span>
          </div>
          <div v-if="taskIntegrationPending.phase === 'ready_to_integrate'" class="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              class="rounded-lg bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-800 disabled:opacity-60"
              :disabled="markingIntegrated"
              @click="submitMarkIntegrated"
            >
              {{ markingIntegrated ? '提交中...' : '我已完成对接' }}
            </button>
            <span v-if="integrationMessage" class="text-sm" :class="integrationSuccess ? 'text-emerald-700' : 'text-red-600'">
              {{ integrationMessage }}
            </span>
          </div>
        </div>

        <div
          v-if="memberEvolutionThinking.primaryPlan || memberEvolutionThinking.verificationGoal || memberEvolutionThinking.escalationReason"
          class="rounded-2xl border border-violet-200 bg-violet-50 px-5 py-4 text-sm text-violet-950 shadow-sm"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="font-medium">系统自主思考</div>
            <span class="rounded-full bg-violet-100 px-2.5 py-1 text-[11px] font-medium text-violet-800">
              {{ memberEvolutionThinking.statusLabel }}
            </span>
          </div>
          <div v-if="memberEvolutionThinking.primaryPlan" class="mt-2 leading-6">
            <span class="font-medium">主方案：</span>{{ memberEvolutionThinking.primaryPlan }}
          </div>
          <div v-if="memberEvolutionThinking.fallbackPlan" class="mt-2 leading-6 text-violet-800">
            <span class="font-medium">备选：</span>{{ memberEvolutionThinking.fallbackPlan }}
          </div>
          <div v-if="memberEvolutionThinking.verificationGoal" class="mt-2 leading-6 text-violet-800">
            <span class="font-medium">验证目标：</span>{{ memberEvolutionThinking.verificationGoal }}
          </div>
          <div v-if="memberIndependenceHandoff.ready" class="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-950">
            训练进度 {{ memberIndependenceHandoff.metCount }}/{{ memberIndependenceHandoff.total }}（独立运营标准）。
            {{ memberIndependenceHandoff.notified ? '育成官已收到放手提示。' : '等待育成官收到系统放手提示。' }}
          </div>
          <div v-if="memberKnowledgeLearningTask || memberKnowledgeLearningPlan.taskId" class="mt-3 rounded-xl border border-sky-200 bg-white px-4 py-3 text-xs text-sky-900">
            <div v-if="memberKnowledgeLearningTask">
              补知识进行中：{{ memberKnowledgeLearningTask.title || memberKnowledgeLearningTask.task_id }}
              （{{ formatLearningTaskStatus(memberKnowledgeLearningTask.status) }}）
            </div>
            <div v-if="memberKnowledgeLearningPlan.summary" class="mt-1">
              回写摘要：{{ memberKnowledgeLearningPlan.summary }}
            </div>
            <div v-if="memberKnowledgeLearningPlan.nextAction" class="mt-1 text-sky-800">
              {{ memberKnowledgeLearningPlan.nextAction }}
            </div>
          </div>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
          <div class="min-w-0">
            <span class="font-semibold text-slate-900">{{ selectedMember.name || selectedMember.member_id }}</span>
            <span class="text-slate-500"> · {{ childWorkspaceMeta.title }}</span>
            <span v-if="activeOpenTask?.title" class="text-slate-500"> · {{ activeOpenTask.title }}</span>
          </div>
          <router-link
            v-if="currentTask?.task_id"
            :to="workNodeDashboardTo"
            class="shrink-0 text-xs font-medium text-teal-700 hover:underline"
          >
            查看节点流水
          </router-link>
        </div>

        <WorkspaceSubNav
          orientation="horizontal"
          :items="childWorkspaceSubNavItems"
          @select="onChildTabSelect"
        />

        <section v-if="childWorkspaceMode === 'task'" class="min-w-0 space-y-6">
            <div class="rounded-2xl border border-amber-200 bg-white p-5 shadow-sm">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-lg font-semibold text-slate-900">本轮训练闭环</div>
                  <div class="mt-1 text-sm text-slate-500">让这位员工知道自己正处在哪一环：接任务、执行提交，还是等待育成官确认。</div>
                </div>
                <span class="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-medium text-amber-800">
                  {{ formalTaskStageLabel }}
                </span>
              </div>
              <div class="mt-4 grid gap-3 md:grid-cols-3">
                <div
                  v-for="step in formalTaskSteps"
                  :key="step.key"
                  class="rounded-xl border px-4 py-4"
                  :class="step.tone"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div class="text-sm font-medium text-slate-900">{{ step.title }}</div>
                    <span class="rounded-full px-2.5 py-1 text-[11px] font-medium" :class="step.badgeClass">
                      {{ step.badge }}
                    </span>
                  </div>
                  <div class="mt-2 text-sm leading-6 text-slate-600">{{ step.summary }}</div>
                </div>
              </div>
              <div v-if="currentTask" class="mt-4 rounded-xl border border-amber-100 bg-amber-50 px-4 py-4 text-sm text-amber-950">
                <div class="font-medium">当前闭环提示</div>
                <div class="mt-2 leading-6">{{ formalTaskGuidance }}</div>
              </div>
              <div v-else class="mt-4 rounded-xl border border-dashed border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-800">
                当前还没有被分配正式训练任务，等待育成官下发第一轮任务。
              </div>
            </div>

            <div id="active-formal-task-panel" class="rounded-2xl border border-emerald-200 bg-white p-5 shadow-sm">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-lg font-semibold text-slate-900">当前任务</div>
                  <div class="mt-1 text-sm text-slate-500">这位员工此刻最应该做的事情。</div>
                </div>
                <div class="flex shrink-0 flex-col items-end gap-2">
                  <span class="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-medium text-emerald-800">
                    {{ formatFormalTaskStatus(currentTask?.status, '等待任务') }}
                  </span>
                  <router-link
                    v-if="currentTask?.task_id && selectedMember?.member_id"
                    :to="workNodeDashboardTo"
                    class="rounded-lg border border-teal-200 bg-teal-50 px-3 py-1.5 text-xs font-medium text-teal-800 hover:bg-teal-100"
                  >
                    查看节点流水
                  </router-link>
                </div>
              </div>
              <div v-if="currentTask" class="mt-4 space-y-4">
                <div>
                  <div class="text-sm font-medium text-slate-900">{{ currentTask.title || '--' }}</div>
                  <div class="mt-2 leading-6 text-slate-700">{{ currentTask.objective || '--' }}</div>
                </div>
                <div
                  v-if="currentTaskIntakeId"
                  class="rounded-xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-950"
                >
                  <div class="font-medium">来自商业接单</div>
                  <div class="mt-1 text-xs leading-5 text-teal-800">
                    接单 {{ currentTaskIntakeId }}
                    <span v-if="currentTaskFulfillmentLabel"> · 履约 {{ currentTaskFulfillmentLabel }}</span>
                    <span v-if="currentTaskCommercialLabel"> · {{ currentTaskCommercialLabel }}</span>
                  </div>
                  <div v-if="currentTaskJobIds.length" class="mt-2 text-[11px] text-teal-800">
                    关联执行队列：
                    <span v-for="(jobId, index) in currentTaskJobIds" :key="jobId">
                      {{ jobId }}<span v-if="index < currentTaskJobIds.length - 1">、</span>
                    </span>
                  </div>
                  <p v-else-if="currentTaskFulfillmentStatus" class="mt-2 text-[11px] text-teal-800">
                    履约状态：{{ currentTaskFulfillmentStatus }}（无 operation 队列时请人工按交付物完成）
                  </p>
                  <div v-if="currentTaskArtifacts.length" class="mt-3 rounded-lg border border-teal-100 bg-white/70 px-3 py-2">
                    <div class="text-[11px] font-medium text-teal-900">履约产物</div>
                    <ul class="mt-1 space-y-1">
                      <li
                        v-for="(art, index) in currentTaskArtifacts.slice(0, 5)"
                        :key="`${art.path || art.label}-${index}`"
                        class="break-all text-[11px] text-teal-800"
                      >
                        <span class="text-teal-600">{{ art.kind || 'file' }}</span>
                        · {{ String(art.path || (art.meta && typeof art.meta === 'object' && (art.meta as Record<string, unknown>).text) || art.label || '--') }}
                      </li>
                    </ul>
                  </div>
                  <router-link
                    to="/organization/intake"
                    class="mt-2 inline-block text-xs font-medium text-teal-800 underline"
                  >
                    查看接单台
                  </router-link>
                </div>
                <div v-if="currentTask.deliverables?.length" class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                  <div class="font-medium text-slate-900">交付物</div>
                  <div
                    v-for="(item, index) in currentTask.deliverables"
                    :key="`workspace-deliverable-${index}`"
                    class="mt-2"
                  >
                    {{ index + 1 }}. {{ item }}
                  </div>
                </div>
                <div v-if="currentTask.result_summary || currentTask.reflection || currentTask.review_note" class="grid gap-3 md:grid-cols-3">
                  <div class="rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-3 text-sm text-slate-700">
                    <div class="font-medium text-slate-900">结果</div>
                    <div class="mt-2 leading-6">{{ currentTask.result_summary || '--' }}</div>
                  </div>
                  <div class="rounded-xl border border-sky-100 bg-sky-50 px-3 py-3 text-sm text-slate-700">
                    <div class="font-medium text-slate-900">复盘</div>
                    <div class="mt-2 leading-6">{{ currentTask.reflection || '--' }}</div>
                  </div>
                  <div class="rounded-xl border border-violet-100 bg-violet-50 px-3 py-3 text-sm text-slate-700">
                    <div class="font-medium text-slate-900">育成点评</div>
                    <div class="mt-2 leading-6">{{ currentTask.review_note || '--' }}</div>
                  </div>
                </div>
                <div v-if="currentTask.status === 'assigned'" class="rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-4">
                  <div class="font-medium text-slate-900">由子女提交执行结果</div>
                  <div class="mt-1 text-sm text-slate-600">这一步应该由当前子女自己完成，而不是回到育成官页面代填。</div>
                  <textarea
                    v-model="taskResultDraft"
                    rows="3"
                    class="mt-3 w-full rounded-lg border border-cyan-200 bg-white px-3 py-2 text-sm text-slate-700"
                    placeholder="总结这轮产出了什么"
                  />
                  <textarea
                    v-model="taskReflectionDraft"
                    rows="4"
                    class="mt-3 w-full rounded-lg border border-cyan-200 bg-white px-3 py-2 text-sm text-slate-700"
                    placeholder="复盘卡点、有效动作、下一轮准备怎么更稳"
                  />
                  <div class="mt-3 flex items-center gap-3">
                    <button
                      @click="submitCurrentTask"
                      :disabled="submittingTask || !taskResultDraft.trim() || !taskReflectionDraft.trim()"
                      class="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-60"
                    >
                      {{ submittingTask ? '提交中...' : '提交结果与复盘' }}
                    </button>
                    <span v-if="taskMessage" class="text-sm" :class="taskSuccess ? 'text-green-600' : 'text-red-600'">
                      {{ taskMessage }}
                    </span>
                  </div>
                </div>
              </div>
              <div v-else class="mt-4 rounded-xl border border-dashed border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-800">
                当前没有挂起中的正式任务。
              </div>
            </div>

            <div
              v-if="activeOpenTask || currentTask"
              class="rounded-2xl border border-cyan-200 bg-white p-5 shadow-sm"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-lg font-semibold text-slate-900">需要其他工种配合</div>
                  <div class="mt-1 text-sm text-slate-500">
                    发起协作后你仍可继续当前任务；育成师会指派提供方，交付审核通过后这里会提示可对接。
                  </div>
                </div>
              </div>
              <div class="mt-4 grid gap-3">
                <label class="block text-xs text-slate-600">
                  <span class="mb-1 block">所需能力</span>
                  <select
                    v-model="collaborationDraft.neededCapability"
                    class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  >
                    <option value="">选择能力类型</option>
                    <option
                      v-for="option in collaborationCapabilityOptions"
                      :key="`collab-capability-${option.value}`"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label class="block text-xs text-slate-600">
                  <span class="mb-1 block">协作标题</span>
                  <input
                    v-model="collaborationDraft.title"
                    type="text"
                    class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    placeholder="例如：登录接口契约"
                  >
                </label>
                <label class="block text-xs text-slate-600">
                  <span class="mb-1 block">说明（可选）</span>
                  <textarea
                    v-model="collaborationDraft.description"
                    rows="3"
                    class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    placeholder="描述你需要对方交付什么、边界与验收标准"
                  />
                </label>
              </div>
              <div class="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  class="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-800 disabled:opacity-60"
                  :disabled="creatingCollaboration || !collaborationDraft.neededCapability || !collaborationDraft.title.trim()"
                  @click="submitCollaborationRequest"
                >
                  {{ creatingCollaboration ? '提交中...' : '发起协作请求' }}
                </button>
                <span v-if="collaborationMessage" class="text-sm" :class="collaborationSuccess ? 'text-emerald-700' : 'text-red-600'">
                  {{ collaborationMessage }}
                </span>
              </div>
            </div>

            <div class="rounded-2xl border border-violet-200 bg-white p-5 shadow-sm">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-lg font-semibold text-slate-900">下一轮建议</div>
                  <div class="mt-1 text-sm text-slate-500">不是系统配置，而是这位员工自己下一轮最该接的工作。</div>
                </div>
                <span class="rounded-full bg-violet-100 px-2.5 py-1 text-[11px] font-medium text-violet-800">
                  {{ formatRecommendationStatus(nextRecommendation?.status) }}
                </span>
              </div>
              <div v-if="nextRecommendation" class="mt-4 space-y-4">
                <div class="text-base font-medium text-slate-900">{{ nextRecommendation.title || '--' }}</div>
                <div class="leading-6 text-slate-700">{{ nextRecommendation.objective || '--' }}</div>
                <div v-if="nextRecommendation.reason" class="rounded-xl bg-violet-50 px-4 py-4 text-sm text-violet-900">
                  {{ nextRecommendation.reason }}
                </div>
                <div v-if="nextRecommendation.deliverables?.length" class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                  <div class="font-medium text-slate-900">建议交付物</div>
                  <div
                    v-for="(item, index) in nextRecommendation.deliverables"
                    :key="`workspace-next-${index}`"
                    class="mt-2"
                  >
                    {{ index + 1 }}. {{ item }}
                  </div>
                </div>
              </div>
              <div v-else class="mt-4 rounded-xl border border-dashed border-violet-200 bg-violet-50 px-4 py-4 text-sm text-violet-800">
                等当前轮闭环后，系统会在这里长出下一轮建议。
              </div>
            </div>
        </section>

        <section v-else class="min-w-0 space-y-6">
            <div v-if="childWorkspaceMode === 'decision'" class="rounded-2xl border border-cyan-200 bg-white p-5 shadow-sm">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-lg font-semibold text-slate-900">记忆检索与决策链路</div>
                  <div class="mt-1 text-sm text-slate-500">先看它这轮怎么判断，再决定要不要干预。</div>
                </div>
                <button
                  @click="runMemoryHubNow"
                  :disabled="runningMemoryHub"
                  class="rounded-full bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-60"
                >
                  {{ runningMemoryHub ? '刷新中...' : '刷新决策中枢' }}
                </button>
              </div>
              <div v-if="memoryHubMessage" class="mt-3 text-sm text-cyan-700">
                {{ memoryHubMessage }}
              </div>
              <div v-if="currentMemoryHub" class="mt-4 grid gap-4">
                <div class="grid gap-3 md:grid-cols-2">
                  <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                    <div class="text-slate-400">当前问题</div>
                    <div class="mt-2 font-medium text-slate-900">{{ currentMemoryHub.decision_intent || '--' }}</div>
                  </div>
                  <div class="rounded-xl bg-cyan-50 px-4 py-4 text-sm text-slate-700">
                    <div class="text-slate-400">当前判断</div>
                    <div class="mt-2 font-medium text-slate-900">{{ currentMemoryHub.decision_summary?.summary || '--' }}</div>
                  </div>
                </div>
                <div class="grid gap-3 md:grid-cols-2">
                  <div class="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-4 text-sm text-slate-700">
                    <div class="text-slate-400">主方案</div>
                    <div class="mt-2 font-medium text-slate-900">{{ currentMemoryHub.decision_summary?.primary_plan || '--' }}</div>
                  </div>
                  <div class="rounded-xl border border-amber-100 bg-amber-50 px-4 py-4 text-sm text-slate-700">
                    <div class="text-slate-400">备选方案</div>
                    <div class="mt-2 font-medium text-slate-900">{{ currentMemoryHub.decision_summary?.fallback_plan || currentMemoryHub.fallback_strategy || '--' }}</div>
                  </div>
                </div>
                <div class="grid gap-3 md:grid-cols-3">
                  <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                    <div class="text-slate-400">置信度</div>
                    <div class="mt-2 font-medium text-slate-900">{{ Math.round((currentMemoryHub.decision_confidence || 0) * 100) }}%</div>
                  </div>
                  <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                    <div class="text-slate-400">下一步</div>
                    <div class="mt-2 font-medium text-slate-900">{{ currentMemoryHub.next_action || '--' }}</div>
                  </div>
                  <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                    <div class="text-slate-400">升级原因</div>
                    <div class="mt-2 font-medium text-slate-900">{{ currentMemoryHub.decision_summary?.escalation_reason || currentMemoryHub.decision_summary?.stop_reason || '当前不需要升级。' }}</div>
                  </div>
                </div>
                <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
                  <div class="text-sm font-semibold text-slate-900">检索来源顺序</div>
                  <div class="mt-3 flex flex-wrap gap-2 text-xs text-slate-700">
                    <span
                      v-for="item in currentMemoryHub.retrieval_plan || []"
                      :key="`retrieval-plan-${item.source}`"
                      class="rounded-full bg-white px-3 py-1"
                    >
                      {{ item.source || '--' }} / {{ item.status || '--' }}
                    </span>
                  </div>
                </div>
                <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
                  <div class="text-sm font-semibold text-slate-900">命中结果</div>
                  <div v-if="currentMemoryHub.retrieval_hits?.length" class="mt-3 space-y-3">
                    <div
                      v-for="item in currentMemoryHub.retrieval_hits"
                      :key="`retrieval-hit-${item.source}`"
                      class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-700"
                    >
                      <div class="flex items-start justify-between gap-3">
                        <div class="font-medium text-slate-900">{{ item.source || '--' }}</div>
                        <div class="text-xs text-slate-500">{{ Math.round((item.confidence || 0) * 100) }}%</div>
                      </div>
                      <div class="mt-2 leading-6">{{ item.best_match_summary || '--' }}</div>
                      <div class="mt-2 text-xs text-slate-500">{{ item.recommended_action || '--' }}</div>
                    </div>
                  </div>
                  <div v-else class="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-500">
                    当前还没有形成明显命中，说明这轮更偏探索。
                  </div>
                </div>
              </div>
              <div v-else class="mt-4 rounded-xl border border-dashed border-cyan-200 bg-cyan-50 px-4 py-4 text-sm text-cyan-800">
                当前还没有形成决策快照，点击上方按钮刷新一次中枢。
              </div>
            </div>

            <div v-if="childWorkspaceMode === 'growth'" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div class="text-lg font-semibold text-slate-900">成长状态</div>
              <p class="mt-1 text-xs text-slate-500">训练复盘与结算后的业务实绩回写</p>
              <div class="mt-4 grid gap-3 md:grid-cols-2">
                <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                  <div class="text-slate-400">当前专注</div>
                  <div class="mt-2 font-medium text-slate-900">{{ selectedMember.growth_state?.current_focus || '--' }}</div>
                </div>
                <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                  <div class="text-slate-400">下一目标</div>
                  <div class="mt-2 font-medium text-slate-900">{{ selectedMember.growth_state?.next_goal || selectedMember.training_plan?.next_action || '--' }}</div>
                </div>
                <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                  <div class="text-slate-400">最近复盘</div>
                  <div class="mt-2 font-medium text-slate-900">{{ formatDate(selectedMember.experience_journal?.last_compiled_at) }}</div>
                </div>
                <div class="rounded-xl border border-teal-100 bg-teal-50/70 px-4 py-4 text-sm text-teal-950">
                  <div class="text-teal-700/80">商业结算实绩</div>
                  <div class="mt-2 font-medium">
                    {{ selectedMember.growth_state?.commercial_settled_count || 0 }} 单
                    <span v-if="selectedMember.growth_state?.commercial_settled_revenue != null" class="text-xs font-normal text-teal-800">
                      · 产值 {{ selectedMember.growth_state?.commercial_settled_revenue }}
                    </span>
                  </div>
                  <div class="mt-1 text-xs text-teal-800">
                    最近结算 {{ formatDate(selectedMember.growth_state?.last_commercial_settled_at) }}
                  </div>
                  <router-link
                    v-if="selectedMember.growth_state?.last_commercial_intake_id"
                    to="/organization/intake"
                    class="mt-2 inline-block text-xs font-medium underline"
                  >
                    查看接单台
                  </router-link>
                  <div
                    v-if="selectedMember.growth_state?.last_git_export_status || selectedMember.growth_state?.pending_git_export"
                    class="mt-2 text-xs text-teal-800"
                  >
                    <span v-if="selectedMember.growth_state?.pending_git_export">经验待导出</span>
                    <span v-else>
                      经验已本地导出
                      <span v-if="selectedMember.growth_state?.last_git_export_status">
                        （{{ selectedMember.growth_state.last_git_export_status }}）
                      </span>
                    </span>
                    <div
                      v-if="selectedMember.growth_state?.last_git_export_path"
                      class="mt-0.5 break-all text-[11px] text-teal-700/80"
                    >
                      {{ selectedMember.growth_state.last_git_export_path }}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="childWorkspaceMode === 'growth'" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div class="text-lg font-semibold text-slate-900">经验卡片</div>
              <p class="mt-1 text-xs text-slate-500">补知识 / 商业结算等写回的可复用经验</p>
              <div v-if="experienceCards.length" class="mt-4 space-y-3">
                <div
                  v-for="(card, cardIndex) in experienceCards.slice(0, 8)"
                  :key="String(card.card_id || card.signature || card.title || cardIndex)"
                  class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700"
                >
                  <div class="flex flex-wrap items-center gap-2">
                    <div class="font-medium text-slate-900">{{ String(card.title || '未命名经验') }}</div>
                    <span
                      v-if="card.source"
                      class="rounded-full bg-white px-2 py-0.5 text-[11px] text-slate-500"
                    >{{ String(card.source) }}</span>
                  </div>
                  <div class="mt-2 leading-6 text-slate-600">{{ String(card.summary || card.current_pattern || '--') }}</div>
                  <div class="mt-1 text-[11px] text-slate-400">{{ formatDate(String(card.created_at || card.updated_at || '')) }}</div>
                </div>
              </div>
              <div v-else class="mt-4 text-sm text-slate-500">还没有经验卡。完成补知识验证或商业结算后会出现在这里。</div>
            </div>

            <div v-if="childWorkspaceMode === 'growth'" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div class="text-lg font-semibold text-slate-900">成长轨迹</div>
              <div class="mt-4 space-y-3 text-sm text-slate-700">
                <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
                  <div class="text-xs uppercase tracking-[0.16em] text-slate-400">建档阶段</div>
                  <div class="mt-2 font-medium text-slate-900">{{ formatLifecycleStage(selectedMember.onboarding?.status || selectedMember.training_plan?.stage) }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ formatDate(selectedMember.onboarding?.created_at) }}</div>
                </div>
                <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
                  <div class="text-xs uppercase tracking-[0.16em] text-slate-400">当前闭环</div>
                  <div class="mt-2 font-medium text-slate-900">{{ formatFormalTaskStatus(currentTask?.status, '暂无任务') }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ currentTask?.title || '等待育成官分配任务' }}</div>
                </div>
                <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
                  <div class="text-xs uppercase tracking-[0.16em] text-slate-400">最近育成点评</div>
                  <div class="mt-2 font-medium leading-6 text-slate-900">{{ currentTask?.review_note || '当前还没有新的育成点评' }}</div>
                </div>
              </div>
            </div>

            <div v-if="childWorkspaceMode === 'archive'" class="rounded-2xl border border-sky-200 bg-white p-5 shadow-sm">
              <div class="text-lg font-semibold text-slate-900">经验入库</div>
              <div v-if="gitExport" class="mt-4 space-y-3 text-sm text-slate-700">
                <div class="rounded-xl bg-sky-50 px-4 py-4">
                  <div class="font-medium text-slate-900">{{ formatGitExportStatus(gitExport.status) }}</div>
                  <div class="mt-2">仓库 {{ gitExport.target_repo || '--' }}</div>
                  <div class="mt-1">分支 {{ gitExport.branch || '--' }}</div>
                  <div class="mt-1">原因 {{ gitExport.reason || '无' }}</div>
                  <div class="mt-1">下一步 {{ gitExport.next_action || '--' }}</div>
                </div>
                <div v-if="gitExport.last_export" class="rounded-xl bg-slate-50 px-4 py-4">
                  <div class="font-medium text-slate-900">最近导出</div>
                  <div class="mt-2">时间 {{ formatDate(gitExport.last_export.completed_at) }}</div>
                  <div class="mt-1">任务 {{ gitExport.last_export.task_id || '--' }}</div>
                  <div class="mt-1 break-all">文件 {{ gitExport.last_export.files?.[0] || '--' }}</div>
                </div>
              </div>
              <div v-else class="mt-4 rounded-xl border border-dashed border-sky-200 bg-sky-50 px-4 py-4 text-sm text-sky-800">
                当前还没有经验入库状态。
              </div>
            </div>

            <div v-if="childWorkspaceMode === 'message'" class="rounded-2xl border border-cyan-200 bg-white p-5 shadow-sm">
              <div class="text-lg font-semibold text-slate-900">最近沟通</div>
              <div v-if="recentMessages.length" class="mt-4 space-y-3">
                <div
                  v-for="message in recentMessages"
                  :key="message.message_id"
                  class="rounded-xl border border-cyan-100 bg-cyan-50 px-4 py-4 text-sm text-slate-700"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div class="font-medium text-slate-900">{{ message.sender_role || '--' }}</div>
                    <div class="text-xs text-slate-500">{{ formatDate(message.created_at) }}</div>
                  </div>
                  <div class="mt-2 leading-6">{{ message.content || '--' }}</div>
                </div>
              </div>
              <div v-else class="mt-4 rounded-xl border border-dashed border-cyan-200 bg-cyan-50 px-4 py-4 text-sm text-cyan-800">
                当前还没有最近沟通记录。
              </div>
            </div>
        </section>
      </main>

      <main v-else class="rounded-2xl border border-dashed border-slate-200 bg-white px-6 py-12 text-center text-slate-500">
        请选择一个孩子进入它自己的工作台。
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import WorkspaceSubNav from '../components/shell/WorkspaceSubNav.vue'
import type { WorkspaceSubNavItem } from '../components/shell/WorkspaceSubNav.vue'
import { companyConsoleKey } from '../composables/companyConsole'
import { cloneAutonomyMember, createCollaborationRequest, getAutonomyStatus, getAutonomyLearningTasks, getCollaborationPolicies, markCollaborationIntegrated, runAutonomyMemoryHub, submitAutonomyTask, type AutonomyFormalTask, type AutonomyFormalTaskRecommendation, type AutonomyStatus, type ChildMemberRuntimeProfile, type LearningTask } from '../api/plugins'
import {
  buildMemberEvolutionThinking,
  buildMemberIndependenceHandoff,
  buildMemberKnowledgeLearningPlan,
  findMemberKnowledgeLearningTask,
  formatLearningTaskStatus,
} from '../utils/memberEvolutionView'
import {
  buildCapabilityOptions,
  formatIntegrationPhase,
  integrationBannerTone,
  readTaskIntegrationPending,
} from '../utils/collaborationView'
import { resolveMemberWorkTypeId } from '../utils/formalTaskRecommendation'

type RelationshipMessage = {
  message_id?: string
  sender_role?: string
  content?: string
  created_at?: string
}

const route = useRoute()
const router = useRouter()
const consoleCtx = inject(companyConsoleKey)

const tenantId = ref(localStorage.getItem('tenant_id') || 'default')
const loading = ref(false)
const autonomyStatus = ref<AutonomyStatus | null>(null)
const selectedMemberId = ref('')
const childWorkspaceMode = ref<'task' | 'decision' | 'growth' | 'archive' | 'message'>('task')
const taskResultDraft = ref('')
const taskReflectionDraft = ref('')
const submittingTask = ref(false)
const taskMessage = ref('')
const taskSuccess = ref(false)
const runningMemoryHub = ref(false)
const memoryHubMessage = ref('')
const learningTasks = ref<LearningTask[]>([])
const cloningMember = ref(false)
const cloneMessage = ref('')
const cloneSuccess = ref(false)
const cloneDraft = ref({
  name: '',
  accountId: '',
  contentDirection: '',
  prefillFirstTask: true,
})
const collaborationDraft = ref({
  neededCapability: '',
  title: '',
  description: '',
})
const collaborationCapabilityOptions = ref<Array<{ value: string; label: string }>>([])
const creatingCollaboration = ref(false)
const collaborationMessage = ref('')
const collaborationSuccess = ref(false)
const markingIntegrated = ref(false)
const integrationMessage = ref('')
const integrationSuccess = ref(false)

const memberEvolutionThinking = computed(() => buildMemberEvolutionThinking(selectedMember.value))
const memberKnowledgeLearningTask = computed(() => findMemberKnowledgeLearningTask(selectedMember.value, learningTasks.value))
const memberKnowledgeLearningPlan = computed(() => buildMemberKnowledgeLearningPlan(selectedMember.value))
const memberIndependenceHandoff = computed(() => buildMemberIndependenceHandoff(selectedMember.value))

const formatDate = (value?: string | null) => {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const formatLifecycleStage = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return '--'
  if (normalized === 'profile_initialized') return '已建档'
  if (normalized === 'portrait_created') return '画像已创建'
  if (normalized === 'trainer_taken_over') return '育成官已接手'
  if (normalized === 'ready_for_first_case') return '待进入首轮案例'
  if (normalized === 'first_case_running') return '首轮案例进行中'
  if (normalized === 'reflection_pending') return '待补复盘'
  if (normalized === 'first_reflection_done') return '首轮复盘完成'
  if (normalized === 'commercial_delivery_done') return '商业交付已结算'
  if (normalized === 'active_training') return '持续训练中'
  if (normalized === 'completed_cycle') return '本轮已闭环'
  return normalized
}

const formatFormalTaskStatus = (value?: string | null, fallback = '--') => {
  const normalized = String(value || '').trim()
  if (!normalized) return fallback
  if (normalized === 'assigned') return '待执行'
  if (normalized === 'submitted') return '待确认'
  if (normalized === 'approved') return '已完成'
  return normalized
}

const formatRecommendationStatus = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return '暂无建议'
  if (normalized === 'suggested') return '待采用'
  if (normalized === 'adopted') return '已采用'
  if (normalized === 'assigned') return '已转任务'
  return normalized
}

const formatGitExportStatus = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return '--'
  if (normalized === 'ready') return '待入库'
  if (normalized === 'queued') return '排队中'
  if (normalized === 'exporting') return '入库中'
  if (normalized === 'completed') return '已入库'
  if (normalized === 'failed') return '入库失败'
  return normalized
}

const setChildWorkspaceMode = (value: 'task' | 'decision' | 'growth' | 'archive' | 'message') => {
  if (childWorkspaceMode.value === value) return
  childWorkspaceMode.value = value
  router.replace({
    path: route.path,
    query: { ...route.query, tab: value },
  })
}

const normalizeChildTab = (value: unknown): 'task' | 'decision' | 'growth' | 'archive' | 'message' => {
  const tab = String(value || '').trim()
  if (tab === 'decision' || tab === 'growth' || tab === 'archive' || tab === 'message') return tab
  return 'task'
}

const childMembers = computed<ChildMemberRuntimeProfile[]>(() => (
  (autonomyStatus.value?.child_members?.items || [])
    .filter((item) => String(item.primary_role || '') !== 'talent_development')
))

const selectedMember = computed<ChildMemberRuntimeProfile | null>(() => (
  childMembers.value.find((item) => String(item.member_id || '') === String(selectedMemberId.value || '')) || null
))

const experienceCards = computed(() => {
  const cards = selectedMember.value?.experience_journal?.cards
  if (!Array.isArray(cards)) return [] as Array<Record<string, unknown>>
  return cards.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
})

const workNodeDashboardTo = computed(() => {
  const taskId = String(currentTask.value?.task_id || activeOpenTask.value?.task_id || '').trim()
  const memberId = String(selectedMember.value?.member_id || '').trim()
  const wt = resolveMemberWorkTypeId(selectedMember.value)
  return {
    path: '/dashboard',
    query: {
      scope: 'node',
      node: taskId ? `node:${taskId}` : undefined,
      member: memberId || undefined,
      wt: wt || undefined,
    },
  }
})

const selectedMemberOrganization = computed(() => ({
  departmentId: String(selectedMember.value?.organization?.department_id || '').trim(),
  departmentLabel: String(selectedMember.value?.organization?.department_label || '').trim(),
}))

const selectedMemberContentDirection = computed(() => (
  String(selectedMember.value?.content_profile?.content_direction || '').trim()
))

const canCloneSelectedMember = computed(() => {
  const member = selectedMember.value
  if (!member) return false
  const role = String(member.primary_role || '').trim()
  if (!role || role === 'talent_development') return false
  const jobs = member.current_jobs || []
  return jobs.length > 0 || Boolean(role)
})

const currentTask = computed<AutonomyFormalTask | null>(() => {
  const memberId = String(selectedMemberId.value || '').trim()
  if (!memberId) return null
  const items = (autonomyStatus.value?.task_center?.items || [])
    .filter((item) => String(item.member_id || '').trim() === memberId)
    .slice()
    .sort((left, right) => String(right.assigned_at || '').localeCompare(String(left.assigned_at || '')))
  return items[0] || null
})

const currentTaskIntakeId = computed(() => {
  const task = activeOpenTask.value || currentTask.value
  const metadata = task?.metadata && typeof task.metadata === 'object' ? task.metadata : {}
  return String((metadata as Record<string, unknown>).intake_id || '').trim()
})

const currentTaskFulfillment = computed(() => {
  const task = activeOpenTask.value || currentTask.value
  const metadata = task?.metadata && typeof task.metadata === 'object' ? task.metadata as Record<string, unknown> : {}
  return metadata.fulfillment && typeof metadata.fulfillment === 'object'
    ? metadata.fulfillment as Record<string, unknown>
    : {}
})

const currentTaskFulfillmentLabel = computed(() => (
  String(currentTaskFulfillment.value.primary_operation_type || currentTaskFulfillment.value.status || '').trim()
))

const currentTaskFulfillmentStatus = computed(() => (
  String(currentTaskFulfillment.value.status || '').trim()
))

const currentTaskJobIds = computed(() => {
  const task = activeOpenTask.value || currentTask.value
  const metadata = task?.metadata && typeof task.metadata === 'object' ? task.metadata as Record<string, unknown> : {}
  const fromMeta = Array.isArray(metadata.job_ids) ? metadata.job_ids : []
  const fromFulfillment = Array.isArray(currentTaskFulfillment.value.job_ids)
    ? currentTaskFulfillment.value.job_ids
    : []
  const merged = [...fromMeta, ...fromFulfillment]
    .map((item) => String(item || '').trim())
    .filter(Boolean)
  return Array.from(new Set(merged))
})

const currentTaskArtifacts = computed(() => {
  const raw = currentTaskFulfillment.value.artifacts
  if (!Array.isArray(raw)) return [] as Array<Record<string, unknown>>
  return raw.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
})

const currentTaskCommercialLabel = computed(() => {
  const task = activeOpenTask.value || currentTask.value
  const metadata = task?.metadata && typeof task.metadata === 'object' ? task.metadata as Record<string, unknown> : {}
  const commercial = metadata.commercial && typeof metadata.commercial === 'object'
    ? metadata.commercial as Record<string, unknown>
    : {}
  const amount = commercial.quoted_amount ?? commercial.budget
  if (amount == null || amount === '') return ''
  const currency = String(commercial.currency || 'CNY')
  return `报价 ${amount} ${currency}`
})

const activeOpenTask = computed<AutonomyFormalTask | null>(() => {
  const memberId = String(selectedMemberId.value || '').trim()
  if (!memberId) return null
  const items = (autonomyStatus.value?.task_center?.items || [])
    .filter((item) => String(item.member_id || '').trim() === memberId)
    .slice()
    .sort((left, right) => String(right.assigned_at || '').localeCompare(String(left.assigned_at || '')))
  return items.find((item) => {
    const status = String(item.status || '').trim()
    return status === 'assigned' || status === 'submitted'
  }) || null
})

const taskIntegrationPending = computed(() => (
  readTaskIntegrationPending(activeOpenTask.value || currentTask.value)
))

const integrationBannerStyle = computed(() => integrationBannerTone(taskIntegrationPending.value?.phase))

const formalTaskStageLabel = computed(() => {
  const status = String(activeOpenTask.value?.status || currentTask.value?.status || '').trim()
  if (status === 'assigned') return '待执行'
  if (status === 'submitted') return '待确认'
  if (status === 'approved') return '已完成'
  return '等待任务'
})

const formalTaskSteps = computed(() => {
  const task = activeOpenTask.value || currentTask.value
  const status = String(task?.status || '').trim()
  const isAssigned = status === 'assigned'
  const isSubmitted = status === 'submitted'
  const isApproved = status === 'approved'
  return [
    {
      key: 'assigned',
      title: '1. 育成官分配',
      badge: task ? 'ready' : 'waiting',
      badgeClass: task ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600',
      summary: task ? `已收到任务：${task.title || '--'}` : '等待第一轮正式训练任务',
      tone: task ? 'border-emerald-200 bg-emerald-50/70' : 'border-slate-200 bg-slate-50',
    },
    {
      key: 'submitted',
      title: '2. 子女执行提交',
      badge: isSubmitted || isApproved ? 'done' : (isAssigned ? 'now' : 'waiting'),
      badgeClass: isSubmitted || isApproved ? 'bg-emerald-100 text-emerald-700' : (isAssigned ? 'bg-cyan-100 text-cyan-700' : 'bg-slate-100 text-slate-600'),
      summary: isSubmitted || isApproved ? '这轮结果与复盘已经提交' : (isAssigned ? '当前应该围绕任务目标推进并整理复盘' : '等待任务后进入执行'),
      tone: isSubmitted || isApproved ? 'border-emerald-200 bg-emerald-50/70' : (isAssigned ? 'border-cyan-200 bg-cyan-50/70' : 'border-slate-200 bg-slate-50'),
    },
    {
      key: 'approved',
      title: '3. 育成官确认',
      badge: isApproved ? 'done' : (isSubmitted ? 'now' : 'waiting'),
      badgeClass: isApproved ? 'bg-emerald-100 text-emerald-700' : (isSubmitted ? 'bg-violet-100 text-violet-700' : 'bg-slate-100 text-slate-600'),
      summary: isApproved ? '这轮已经确认完成，可准备进入下一轮' : (isSubmitted ? '等待育成官点评并确认本轮完成' : '执行提交后才会进入确认环节'),
      tone: isApproved ? 'border-emerald-200 bg-emerald-50/70' : (isSubmitted ? 'border-violet-200 bg-violet-50/70' : 'border-slate-200 bg-slate-50'),
    },
  ]
})

const formalTaskGuidance = computed(() => {
  const task = activeOpenTask.value || currentTask.value
  const status = String(task?.status || '').trim()
  if (!task) return '等待育成官根据你的岗位画像，下发第一轮正式训练任务。'
  if (status === 'assigned') {
    return '先围绕当前任务完成最小可验证交付，再把结果、卡点和下一轮想法整理出来，提交给育成官。'
  }
  if (status === 'submitted') {
    return '你已经完成这轮执行并提交了结果，接下来等待育成官点评与确认，不需要再盲目扩任务。'
  }
  if (status === 'approved') {
    return '这轮已经完成确认，可以整理经验入库，并等待系统或育成官推动下一轮训练。'
  }
  return '按照当前任务推进，并保持复盘材料可读、可验证。'
})

const nextRecommendation = computed<AutonomyFormalTaskRecommendation | null>(() => {
  const memberId = String(selectedMemberId.value || '').trim()
  if (!memberId) return null
  const items = (autonomyStatus.value?.task_center?.recommendations || [])
    .filter((item) => String(item.member_id || '').trim() === memberId)
    .slice()
    .sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')))
  return items.find((item) => String(item.status || '').trim() === 'suggested') || items[0] || null
})

const gitExport = computed(() => (
  selectedMember.value?.current_jobs?.find((job) => job?.runtime_state?.tenant_state?.git_export)?.runtime_state?.tenant_state?.git_export
  || null
))

const currentMemoryHub = computed(() => selectedMember.value?.memory_hub || null)

const recentMessages = computed<RelationshipMessage[]>(() => {
  const memberId = String(selectedMemberId.value || '').trim()
  if (!memberId) return []
  const thread = (autonomyStatus.value?.relationship_center?.conversation_threads || []).find((item) => (
    String(item.thread_id || '') === `trainer:${memberId}`
  ))
  return (thread?.messages || [])
    .slice()
    .sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')))
    .slice(0, 4)
})

const childWorkspaceMeta = computed(() => {
  if (childWorkspaceMode.value === 'decision') {
    return {
      title: '决策中枢',
      summary: '聚焦检索、判断与升级',
      description: '这里专门看这位员工这轮先查了什么、命中了什么、主方案是什么，以及何时需要升级到外部学习。',
    }
  }
  if (childWorkspaceMode.value === 'growth') {
    return {
      title: '成长状态',
      summary: '聚焦成长轨迹与当前专注',
      description: '这里专门看这位员工当前专注什么、下一步准备往哪长，以及最近这一轮带教留下了什么痕迹。',
    }
  }
  if (childWorkspaceMode.value === 'archive') {
    return {
      title: '经验入库',
      summary: '聚焦经验沉淀与知识入库',
      description: '这里专门看这轮经验有没有成功写入仓库、最近一次导出写了什么，以及当前卡在什么环节。',
    }
  }
  if (childWorkspaceMode.value === 'message') {
    return {
      title: '最近沟通',
      summary: '聚焦和育成官的来回沟通',
      description: '这里专门看这位员工最近收到了什么带教反馈、回复了什么内容，不和任务内容混在一起读。',
    }
  }
  return {
    title: '任务闭环',
    summary: '聚焦当前轮的接单、执行与提交',
    description: '这里专门看这位员工这轮任务走到哪一步、现在最该做什么，以及什么时候该把结果交回给育成官。',
  }
})

const childWorkspaceCards = computed(() => ([
  {
    key: 'task',
    title: '任务闭环',
    description: '查看当前任务、执行提示和下一轮建议。',
    badge: activeOpenTask.value ? formatFormalTaskStatus(activeOpenTask.value.status, '待执行') : (currentTask.value ? '已完成' : '等待任务'),
    badgeClass: currentTask.value ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600',
    active: childWorkspaceMode.value === 'task',
    activeClass: 'border-amber-300 bg-amber-50 shadow-sm',
    idleClass: 'border-amber-200 bg-white hover:bg-amber-50/60',
  },
  {
    key: 'decision',
    title: '决策中枢',
    description: '查看本轮检索来源、命中结果和主备方案。',
    badge: currentMemoryHub.value?.decision_summary?.external_learning_required ? '需升级' : '已成形',
    badgeClass: currentMemoryHub.value?.decision_summary?.external_learning_required ? 'bg-amber-100 text-amber-700' : 'bg-cyan-100 text-cyan-700',
    active: childWorkspaceMode.value === 'decision',
    activeClass: 'border-cyan-300 bg-cyan-50 shadow-sm',
    idleClass: 'border-cyan-200 bg-white hover:bg-cyan-50/60',
  },
  {
    key: 'growth',
    title: '成长状态',
    description: '查看当前专注、成长轨迹和最近带教痕迹。',
    badge: formatLifecycleStage(selectedMember.value?.training_plan?.stage || selectedMember.value?.onboarding?.status),
    badgeClass: 'bg-slate-100 text-slate-700',
    active: childWorkspaceMode.value === 'growth',
    activeClass: 'border-slate-300 bg-slate-50 shadow-sm',
    idleClass: 'border-slate-200 bg-white hover:bg-slate-50',
  },
  {
    key: 'archive',
    title: '经验入库',
    description: '查看经验是否入库、最近一次导出和下一步。',
    badge: formatGitExportStatus(gitExport.value?.status),
    badgeClass: 'bg-sky-100 text-sky-700',
    active: childWorkspaceMode.value === 'archive',
    activeClass: 'border-sky-300 bg-sky-50 shadow-sm',
    idleClass: 'border-sky-200 bg-white hover:bg-sky-50/60',
  },
  {
    key: 'message',
    title: '最近沟通',
    description: '查看最近收到和发出的带教沟通。',
    badge: recentMessages.value.length ? `${recentMessages.value.length} 条` : '暂无',
    badgeClass: 'bg-cyan-100 text-cyan-700',
    active: childWorkspaceMode.value === 'message',
    activeClass: 'border-cyan-300 bg-cyan-50 shadow-sm',
    idleClass: 'border-cyan-200 bg-white hover:bg-cyan-50/60',
  },
]) as Array<{
  key: 'task' | 'decision' | 'growth' | 'archive' | 'message'
  title: string
  description: string
  badge: string
  badgeClass: string
  active: boolean
  activeClass: string
  idleClass: string
}>)

const childWorkspaceSubNavItems = computed<WorkspaceSubNavItem[]>(() => (
  childWorkspaceCards.value.map((item) => ({
    key: item.key,
    title: item.title,
    description: item.description,
    badge: item.badge,
    badgeClass: item.badgeClass,
    active: item.active,
  }))
))

const onChildTabSelect = (key: string) => {
  const allowed = ['task', 'decision', 'growth', 'archive', 'message'] as const
  if ((allowed as readonly string[]).includes(key)) {
    setChildWorkspaceMode(key as typeof allowed[number])
  }
}

const runMemoryHubNow = async () => {
  const memberId = String(selectedMember.value?.member_id || '').trim()
  if (!memberId) return
  runningMemoryHub.value = true
  memoryHubMessage.value = ''
  try {
    const result = await runAutonomyMemoryHub({
      tenant_id: tenantId.value || 'default',
      member_id: memberId,
      trigger: 'workspace_manual_refresh',
    })
    autonomyStatus.value = result.data?.autonomy || autonomyStatus.value
    const learningResult = await getAutonomyLearningTasks(tenantId.value || 'default')
    learningTasks.value = learningResult.data?.items || learningTasks.value
    memoryHubMessage.value = result.message || '决策中枢已刷新'
  } catch {
    memoryHubMessage.value = '刷新失败'
  } finally {
    runningMemoryHub.value = false
  }
}

const selectMember = (memberId: string) => {
  selectedMemberId.value = memberId
  childWorkspaceMode.value = 'task'
  taskResultDraft.value = ''
  taskReflectionDraft.value = ''
  taskMessage.value = ''
  cloneMessage.value = ''
  collaborationMessage.value = ''
  integrationMessage.value = ''
  router.replace({
    path: `/organization/child/${encodeURIComponent(memberId)}/workspace`,
    query: { tab: 'task' },
  })
}

const submitAccountVariantClone = async () => {
  const sourceMemberId = String(selectedMember.value?.member_id || '').trim()
  if (!sourceMemberId) return
  cloningMember.value = true
  cloneMessage.value = ''
  cloneSuccess.value = false
  try {
    const result = await cloneAutonomyMember({
      tenant_id: tenantId.value || 'default',
      source_member_id: sourceMemberId,
      name: String(cloneDraft.value.name || '').trim(),
      account_id: String(cloneDraft.value.accountId || '').trim(),
      content_direction: String(cloneDraft.value.contentDirection || '').trim(),
      clone_mode: 'account_variant',
      prefill_first_task: cloneDraft.value.prefillFirstTask,
      trainer_member_id: 'talent_development_officer',
    })
    autonomyStatus.value = result.data?.autonomy || autonomyStatus.value
    const createdMemberId = String(result.data?.member?.member_id || result.data?.employee?.member_id || '').trim()
    cloneSuccess.value = true
    cloneMessage.value = result.message || '复制建档成功'
    cloneDraft.value = {
      name: '',
      accountId: '',
      contentDirection: '',
      prefillFirstTask: true,
    }
    if (createdMemberId) {
      router.push({
        path: '/organization/trainer/talent_development_officer/workspace',
        query: {
          mode: 'dispatch',
          dispatchTab: 'assign',
          member: createdMemberId,
        },
      })
    }
  } catch {
    cloneSuccess.value = false
    cloneMessage.value = '复制建档失败，请检查名称、账号与内容方向'
  } finally {
    cloningMember.value = false
  }
}

const submitCollaborationRequest = async () => {
  const memberId = String(selectedMember.value?.member_id || '').trim()
  const taskId = String(activeOpenTask.value?.task_id || currentTask.value?.task_id || '').trim()
  const neededCapability = String(collaborationDraft.value.neededCapability || '').trim()
  const title = String(collaborationDraft.value.title || '').trim()
  if (!memberId || !neededCapability || !title) return
  creatingCollaboration.value = true
  collaborationMessage.value = ''
  try {
    const result = await createCollaborationRequest({
      tenant_id: tenantId.value || 'default',
      requester_member_id: memberId,
      needed_capability: neededCapability,
      title,
      description: String(collaborationDraft.value.description || '').trim(),
      requester_task_id: taskId || undefined,
      requester_continues: true,
    })
    autonomyStatus.value = result.data?.autonomy || autonomyStatus.value
    collaborationSuccess.value = true
    collaborationMessage.value = result.message || '协作请求已提交，可继续当前任务'
    collaborationDraft.value = {
      neededCapability: collaborationDraft.value.neededCapability,
      title: '',
      description: '',
    }
  } catch {
    collaborationSuccess.value = false
    collaborationMessage.value = '协作请求提交失败'
  } finally {
    creatingCollaboration.value = false
  }
}

const submitMarkIntegrated = async () => {
  const memberId = String(selectedMember.value?.member_id || '').trim()
  const requestId = String(taskIntegrationPending.value?.collaboration_request_id || '').trim()
  if (!memberId || !requestId) return
  markingIntegrated.value = true
  integrationMessage.value = ''
  try {
    const result = await markCollaborationIntegrated(requestId, {
      tenant_id: tenantId.value || 'default',
      member_id: memberId,
    })
    autonomyStatus.value = result.data?.autonomy || autonomyStatus.value
    integrationSuccess.value = true
    integrationMessage.value = result.message || '已标记对接完成'
  } catch {
    integrationSuccess.value = false
    integrationMessage.value = '标记对接失败'
  } finally {
    markingIntegrated.value = false
  }
}

const submitCurrentTask = async () => {
  const taskId = String(activeOpenTask.value?.task_id || currentTask.value?.task_id || '').trim()
  if (!taskId) return
  submittingTask.value = true
  taskMessage.value = ''
  try {
    const result = await submitAutonomyTask({
      tenant_id: tenantId.value || 'default',
      task_id: taskId,
      result_summary: String(taskResultDraft.value || '').trim(),
      reflection: String(taskReflectionDraft.value || '').trim(),
    })
    autonomyStatus.value = result.data?.autonomy || autonomyStatus.value
    const learningResult = await getAutonomyLearningTasks(tenantId.value || 'default')
    learningTasks.value = learningResult.data?.items || learningTasks.value
    taskSuccess.value = true
    taskMessage.value = result.message || '结果与复盘已提交'
    taskResultDraft.value = ''
    taskReflectionDraft.value = ''
    await consoleCtx?.refreshOverview?.()
  } catch {
    taskSuccess.value = false
    taskMessage.value = '提交失败'
  } finally {
    submittingTask.value = false
  }
}

const loadWorkspace = async () => {
  loading.value = true
  try {
    const [statusResult, learningResult, policyResult] = await Promise.all([
      getAutonomyStatus(tenantId.value || 'default'),
      getAutonomyLearningTasks(tenantId.value || 'default'),
      getCollaborationPolicies(),
    ])
    autonomyStatus.value = statusResult.data || null
    learningTasks.value = learningResult.data?.items || []
    collaborationCapabilityOptions.value = buildCapabilityOptions(
      Array.isArray(policyResult.data?.deliverable_templates) ? policyResult.data.deliverable_templates : [],
    )
    const routeMemberId = String(route.params.memberId || '').trim()
    const availableIds = childMembers.value.map((item) => String(item.member_id || ''))
    if (routeMemberId && availableIds.includes(routeMemberId)) {
      selectedMemberId.value = routeMemberId
    } else if (!selectedMemberId.value || !availableIds.includes(selectedMemberId.value)) {
      selectedMemberId.value = String(childMembers.value[0]?.member_id || '')
    }
    // Preserve deep-link tab (e.g. ?tab=growth for experience cards)
    childWorkspaceMode.value = normalizeChildTab(route.query.tab)
  } finally {
    loading.value = false
  }
}

watch(() => route.query.tab, (tab) => {
  childWorkspaceMode.value = normalizeChildTab(tab)
}, { immediate: true })

watch(() => route.params.memberId, () => {
  const routeMemberId = String(route.params.memberId || '').trim()
  if (routeMemberId) {
    selectedMemberId.value = routeMemberId
  }
})

onMounted(loadWorkspace)
</script>
