<template>
  <div
    v-if="selectedChildMemberId && selectedChildMemberDraft?.primary_role !== 'talent_development'"
    id="dispatch-zone"
    class="scroll-mt-24 mt-4 rounded-xl border border-amber-200 bg-amber-50/70 px-4 py-4 text-sm text-amber-950"
  >
    <div class="mb-4 rounded-xl border border-amber-100 bg-white px-4 py-4">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-sm font-semibold text-amber-950">任务编排工作面</div>
          <div class="mt-1 text-xs text-amber-700">
            对内训练任务与接单后正式任务跟踪。商业外包请优先走
            <router-link to="/organization/intake" class="font-medium text-amber-900 underline">接单台</router-link>
            （智脑路由 + 育成确认）。
          </div>
        </div>
        <div class="rounded-full bg-amber-100 px-3 py-1 text-[11px] text-amber-800">
          {{ trainerFormalTaskStageLabel }}
        </div>
      </div>
      <div class="mt-4 grid gap-3 md:grid-cols-3">
        <div class="rounded-xl border border-amber-100 bg-amber-50/60 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前对象</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedChildMemberDraft?.name || selectedChildMemberId || '--' }}</div>
        </div>
        <div class="rounded-xl border border-amber-100 bg-amber-50/60 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前任务</div>
          <div class="mt-2 font-medium text-slate-900">{{ activeFormalTask?.title || '等待分配' }}</div>
        </div>
        <div class="rounded-xl border border-amber-100 bg-amber-50/60 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前动作</div>
          <div class="mt-2 font-medium text-slate-900">{{ trainerFormalTaskGuidance }}</div>
        </div>
      </div>
    </div>
    <WorkspaceSubNav
      class="mb-4"
      orientation="horizontal"
      :items="dispatchSubNavItems"
      @select="onDispatchSubNavSelect"
    />
    <div class="mb-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
      <div class="font-medium text-slate-900">{{ dispatchWorkspaceMeta.title }}</div>
      <div class="mt-1 text-xs leading-5">{{ dispatchWorkspaceMeta.description }}</div>
    </div>

    <div v-show="dispatchWorkspaceMode === 'collaboration'" class="mb-4 space-y-4">
      <div class="rounded-xl border border-cyan-200 bg-white px-4 py-4 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="text-sm font-semibold text-slate-900">跨工种协作队列</div>
            <div class="mt-1 text-xs text-slate-500">
              员工发起协作后不会阻塞主任务；育成师在此指派提供方，提供方交付并审核通过后，请求方会收到「可对接」提示。
            </div>
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="rounded-lg border border-cyan-200 bg-white px-3 py-1.5 text-xs font-medium text-cyan-800 hover:bg-cyan-50 disabled:opacity-60"
              :disabled="collaborationLoading"
              @click="loadCollaborationQueue"
            >
              {{ collaborationLoading ? '刷新中...' : '刷新队列' }}
            </button>
            <span class="rounded-full bg-cyan-100 px-3 py-1 text-[11px] font-medium text-cyan-800">
              进行中 {{ pipelineCollaborations.length }}
            </span>
          </div>
        </div>
        <p v-if="collaborationMessage" class="mt-3 text-sm" :class="collaborationSuccess ? 'text-emerald-700' : 'text-red-600'">
          {{ collaborationMessage }}
        </p>
        <div v-if="!pipelineCollaborations.length" class="mt-4 rounded-xl border border-dashed border-cyan-200 bg-cyan-50 px-4 py-5 text-sm text-cyan-900">
          当前没有进行中的协作请求。员工可在自己的任务页发起「需要其他工种配合」。
        </div>
        <div v-else class="mt-4 space-y-4">
          <div
            v-for="request in pipelineCollaborations"
            :key="request.request_id"
            class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="text-sm font-semibold text-slate-900">{{ request.title || '--' }}</div>
                <div class="mt-1 text-xs text-slate-500">
                  能力 {{ formatCapabilityLabel(request.needed_capability) }}
                  · 请求方 {{ memberNameById(request.requester_member_id) }}
                  <span v-if="request.requester_task_id"> · 关联任务 {{ request.requester_task_id }}</span>
                </div>
                <div v-if="request.description" class="mt-2 text-sm leading-6 text-slate-600">{{ request.description }}</div>
              </div>
              <span class="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700">
                {{ formatCollaborationStatus(request.status) }}
              </span>
            </div>
            <div
              v-if="summarizeCollaborationRequest(request).providerMemberId"
              class="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900"
            >
              提供方：{{ memberNameById(summarizeCollaborationRequest(request).providerMemberId) }}
              <span v-if="summarizeCollaborationRequest(request).providerTaskId">
                · 任务 {{ summarizeCollaborationRequest(request).providerTaskId }}
              </span>
            </div>
            <div
              v-if="['open', 'assigned'].includes(String(request.status || ''))"
              class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-[1fr_1fr_auto_auto]"
            >
              <label class="block text-xs text-slate-600">
                <span class="mb-1 block">指派提供方</span>
                <select
                  v-model="collaborationAssignDraft(request).providerMemberId"
                  class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                >
                  <option value="">选择员工</option>
                  <option
                    v-for="member in providerCandidatesForRequest(request)"
                    :key="`collab-provider-${request.request_id}-${member.member_id}`"
                    :value="member.member_id"
                  >
                    {{ member.name || member.member_id }}
                  </option>
                </select>
              </label>
              <label class="block text-xs text-slate-600">
                <span class="mb-1 block">提供方任务 ID（可选）</span>
                <input
                  v-model="collaborationAssignDraft(request).providerTaskId"
                  type="text"
                  class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                  placeholder="派任务后可回填"
                >
              </label>
              <div class="flex flex-wrap items-center gap-2 md:col-span-2 xl:col-span-1 xl:col-start-3 xl:self-end">
                <button
                  type="button"
                  class="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-800 disabled:opacity-60"
                  :disabled="collaborationActionRunning === String(request.request_id) || !collaborationAssignDraft(request).providerMemberId"
                  @click="submitCollaborationAssign(request)"
                >
                  {{ collaborationActionRunning === String(request.request_id) ? '指派中...' : '确认指派' }}
                </button>
                <button
                  v-if="collaborationAssignDraft(request).providerMemberId"
                  type="button"
                  class="rounded-lg border border-violet-300 bg-white px-4 py-2 text-sm font-medium text-violet-800 hover:bg-violet-50"
                  @click="goToProviderDispatch(collaborationAssignDraft(request).providerMemberId)"
                >
                  去派任务
                </button>
              </div>
            </div>
            <div
              v-else-if="String(request.status || '') === 'provider_submitted'"
              class="mt-3 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-xs text-violet-900"
            >
              提供方已提交，请在「结果确认」工作位审核其任务后，请求方会自动收到可对接通知。
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="dispatchWorkspaceMode === 'summary'" class="min-w-0 space-y-4">
      <div class="space-y-4">
        <div class="rounded-xl border border-amber-100 bg-white px-4 py-4">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="font-medium text-slate-900">当前子女闭环摘要</div>
              <div class="mt-1 text-xs text-slate-500">先判断这位员工现在卡在闭环的哪一步，再决定是分配、催提交，还是做确认。</div>
            </div>
            <span class="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-medium text-amber-800">
              {{ trainerFormalTaskStageLabel }}
            </span>
          </div>
          <div class="mt-4 grid gap-3 md:grid-cols-3">
            <div
              v-for="step in trainerFormalTaskSteps"
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
          <div class="mt-4 rounded-xl border border-amber-100 bg-amber-50 px-4 py-4 text-sm text-amber-950">
            <div class="font-medium">育成官下一步</div>
            <div class="mt-2 leading-6">{{ trainerFormalTaskGuidance }}</div>
          </div>
          <div
            v-if="memberEvolutionThinking.primaryPlan || memberEvolutionThinking.verificationGoal || memberEvolutionThinking.escalationReason"
            class="mt-4 rounded-xl border border-violet-200 bg-violet-50 px-4 py-4 text-sm text-violet-950"
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
          </div>
          <div
            v-if="memberIndependenceReadiness.criteria.length"
            class="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-950"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="font-medium">可独立运营判定</div>
              <span class="rounded-full px-2.5 py-1 text-[11px] font-medium" :class="memberIndependenceReadiness.ready ? 'bg-emerald-600 text-white' : 'bg-emerald-100 text-emerald-800'">
                {{ memberIndependenceReadiness.ready ? '已达标' : `${memberIndependenceReadiness.metCount}/${memberIndependenceReadiness.total}` }}
              </span>
            </div>
            <div class="mt-3 grid gap-2 md:grid-cols-2">
              <div
                v-for="item in memberIndependenceReadiness.criteria"
                :key="item.id"
                class="rounded-lg border px-3 py-2 text-xs"
                :class="item.met ? 'border-emerald-200 bg-white text-emerald-900' : 'border-emerald-100 bg-emerald-50/60 text-emerald-700'"
              >
                {{ item.met ? '✓' : '○' }} {{ item.label }}
              </div>
            </div>
          </div>
          <div
            v-if="memberIndependenceHandoff.ready"
            class="mt-4 rounded-xl border px-4 py-4 text-sm"
            :class="memberIndependenceHandoff.notified ? 'border-amber-300 bg-amber-50 text-amber-950' : 'border-emerald-300 bg-emerald-50 text-emerald-950'"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="font-medium">可独立运营 · 放手提示</div>
              <span class="rounded-full px-2.5 py-1 text-[11px] font-medium" :class="memberIndependenceHandoff.notified ? 'bg-amber-600 text-white' : 'bg-emerald-600 text-white'">
                {{ memberIndependenceHandoff.notified ? '已通知育成官' : '待通知' }}
              </span>
            </div>
            <div class="mt-2 leading-6">
              系统判定该员工训练进度 {{ memberIndependenceHandoff.metCount }}/{{ memberIndependenceHandoff.total }}（独立运营标准）。
              建议开始收缩带教频率，把更多真实决策交给岗位成员。
            </div>
            <div v-if="memberIndependenceHandoff.nextAction" class="mt-2 text-xs opacity-80">
              {{ memberIndependenceHandoff.nextAction }}
            </div>
          </div>
          <div
            v-if="memberKnowledgeLearningTask"
            class="mt-4 rounded-xl border border-sky-200 bg-sky-50 px-4 py-4 text-sm text-sky-950"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="font-medium">补知识任务（自动触发）</div>
              <span class="rounded-full bg-sky-100 px-2.5 py-1 text-[11px] font-medium text-sky-800">
                {{ formatLearningTaskStatus(memberKnowledgeLearningTask.status) }}
              </span>
            </div>
            <div class="mt-2 text-base font-medium text-slate-900">{{ memberKnowledgeLearningTask.title || memberKnowledgeLearningTask.task_id }}</div>
            <div v-if="memberKnowledgeLearningTask.goal" class="mt-2 leading-6 text-sky-900">{{ memberKnowledgeLearningTask.goal }}</div>
            <div v-if="memberKnowledgeLearningPlan.summary" class="mt-2 rounded-lg border border-sky-100 bg-white px-3 py-2 text-xs leading-5 text-sky-900">
              回写摘要：{{ memberKnowledgeLearningPlan.summary }}
            </div>
            <div v-if="memberKnowledgeLearningPlan.nextAction" class="mt-2 text-xs text-sky-800">
              训练计划：{{ memberKnowledgeLearningPlan.nextAction }}
            </div>
            <div v-if="memberKnowledgeLearningPlan.followupRecommendationId" class="mt-2 text-xs text-sky-800">
              系统已生成补知识后正式任务建议，请到「任务分配」页采纳。
            </div>
            <div v-if="memberKnowledgeLearningTask.queries?.length" class="mt-3 rounded-lg border border-sky-100 bg-white px-3 py-3 text-xs text-slate-700">
              <div class="font-medium text-slate-900">调研问题</div>
              <div v-for="(query, index) in memberKnowledgeLearningTask.queries" :key="`kq-${index}`" class="mt-1">
                {{ index + 1 }}. {{ query }}
              </div>
            </div>
            <div v-if="memberKnowledgeLearningTask.next_validation_action" class="mt-2 text-xs text-sky-800">
              下一步：{{ memberKnowledgeLearningTask.next_validation_action }}
            </div>
            <button
              v-if="canValidateKnowledgeLearning"
              type="button"
              class="mt-3 rounded-lg border border-sky-300 bg-white px-3 py-1.5 text-[11px] font-medium text-sky-800 hover:bg-sky-100 disabled:opacity-60"
              :disabled="validatingKnowledgeLearningTaskId === memberKnowledgeLearningTask.task_id"
              @click="validateMemberKnowledgeLearning?.()"
            >
              {{ validatingKnowledgeLearningTaskId === memberKnowledgeLearningTask.task_id ? '验证中...' : '启动补知识验证' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="dispatchWorkspaceMode === 'assign' || dispatchWorkspaceMode === 'confirm'" class="min-w-0 space-y-4">
      <TrainerQuickWorkTypePanel
        v-if="dispatchWorkspaceMode === 'assign'"
        :existing-work-type-ids="companyWorkTypeIds"
        @saved="emit('work-type-saved', $event)"
      />
      <div class="space-y-4">
        <div class="rounded-xl border border-amber-100 bg-white px-4 py-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="font-medium">当前编排任务</div>
              <div class="mt-1 text-xs text-amber-800">这里专门围绕这一轮任务闭环工作，不再把其他观察信息混进来。</div>
            </div>
            <div class="rounded-full bg-white/80 px-3 py-1 text-xs text-amber-800">
              {{ selectedChildFormalTasks.length ? `任务 ${selectedChildFormalTasks.length}` : '暂无任务' }}
            </div>
          </div>
          <p v-if="formalTaskMessage" class="mt-3 text-sm" :class="formalTaskSuccess ? 'text-green-600' : 'text-red-600'">
            {{ formalTaskMessage }}
          </p>
          <div class="mt-4" :class="dispatchWorkspaceMode === 'assign' ? 'grid gap-4 xl:grid-cols-2' : 'space-y-4'">
            <div v-if="dispatchWorkspaceMode === 'assign'" class="min-w-0 rounded-xl border border-amber-100 bg-white px-4 py-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="font-medium text-slate-900">1. 编辑本轮任务</div>
                  <div class="mt-1 text-xs text-slate-500">先把这轮目标、结果标准和交付物写清楚，再正式下发给当前子女。</div>
                  <div v-if="formalTaskRecommendationHint" class="mt-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] leading-5 text-emerald-900">
                    {{ formalTaskRecommendationHint }}
                  </div>
                  <div v-if="formalTaskAssignWorkTypeId || formalTaskAssignMissionKind" class="mt-2 flex flex-wrap gap-2 text-[11px]">
                    <span v-if="formalTaskAssignWorkTypeId" class="rounded-full bg-emerald-100 px-2.5 py-1 text-emerald-800">
                      工种 {{ formalTaskAssignWorkTypeId }}
                    </span>
                    <span v-if="formalTaskAssignMissionKind" class="rounded-full bg-sky-100 px-2.5 py-1 text-sky-800">
                      Mission {{ formalTaskAssignMissionKind }}
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  @click="selectedChildMemberDraft ? applyRecommendedFormalTaskDraft(selectedChildMemberDraft, { force: true }) : undefined"
                  :disabled="!selectedChildMemberDraft"
                  class="rounded-lg border border-amber-200 px-3 py-1.5 text-[11px] text-amber-700 hover:bg-amber-50 disabled:opacity-60"
                >
                  重生成草案
                </button>
              </div>
              <div class="mt-3 grid gap-3">
                <div>
                  <div class="text-xs uppercase tracking-[0.16em] text-amber-700">任务标题</div>
                  <input
                    :value="formalTaskAssignTitleDraft"
                    type="text"
                    class="mt-2 w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm text-slate-700"
                    placeholder="例如：产出第一篇头条可发布内容"
                    @input="emit('update:formalTaskAssignTitleDraft', ($event.target as HTMLInputElement).value)"
                  >
                </div>
                <div>
                  <div class="text-xs uppercase tracking-[0.16em] text-amber-700">任务目标</div>
                  <textarea
                    :value="formalTaskAssignObjectiveDraft"
                    rows="3"
                    class="mt-2 w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm text-slate-700"
                    placeholder="说明这轮为什么做、做到什么算过关"
                    @input="emit('update:formalTaskAssignObjectiveDraft', ($event.target as HTMLTextAreaElement).value)"
                  ></textarea>
                </div>
                <div>
                  <div class="text-xs uppercase tracking-[0.16em] text-amber-700">交付物</div>
                  <textarea
                    :value="formalTaskAssignDeliverablesDraft"
                    rows="4"
                    class="mt-2 w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm text-slate-700"
                    placeholder="每行一个交付物"
                    @input="emit('update:formalTaskAssignDeliverablesDraft', ($event.target as HTMLTextAreaElement).value)"
                  ></textarea>
                </div>
              </div>
              <button
                @click="assignFormalTaskToSelectedChild"
                :disabled="formalTaskActionRunning === 'assign' || !selectedChildMemberId || !formalTaskAssignTitleDraft.trim() || !formalTaskAssignObjectiveDraft.trim()"
                class="mt-4 rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-60"
              >
                {{ formalTaskActionRunning === 'assign' ? '分配中...' : '分配正式任务' }}
              </button>
              <button
                v-if="selectedChildMemberId"
                type="button"
                @click="goToChildWorkspaceForMember?.(selectedChildMemberId)"
                class="mt-3 rounded-lg border border-cyan-300 bg-white px-4 py-2 text-sm font-medium text-cyan-800 hover:bg-cyan-50"
              >
                打开员工工作台
              </button>
            </div>

            <div class="min-w-0 rounded-xl border border-amber-100 bg-white px-4 py-4">
              <div class="flex items-start justify-between gap-3">
                <div class="font-medium text-slate-900">2. 当前任务状态</div>
                <span v-if="activeFormalTask" class="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-medium text-amber-800">
                  {{ formatFormalTaskStatus(activeFormalTask.status, '待执行') }}
                </span>
              </div>
              <div v-if="!activeFormalTask" class="mt-3 rounded-lg border border-dashed border-amber-200 bg-amber-50 px-3 py-4 text-sm text-amber-800">
                还没有正式任务。先由育成师下达第一轮任务。
              </div>
              <div v-else class="mt-3 space-y-3">
                <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                  <div class="flex items-start justify-between gap-3">
                    <div>
                      <div class="font-medium text-slate-900">{{ activeFormalTask.title || '--' }}</div>
                      <div class="mt-1 text-xs text-slate-500">{{ formatDate(activeFormalTask.assigned_at) }}</div>
                    </div>
                    <router-link
                      v-if="activeFormalTask.task_id && selectedChildMemberId"
                      :to="workNodeDashboardTo"
                      class="shrink-0 rounded-lg border border-teal-200 bg-teal-50 px-3 py-1.5 text-xs font-medium text-teal-800 hover:bg-teal-100"
                    >
                      查看节点流水
                    </router-link>
                  </div>
                  <div class="mt-3">
                    <div class="text-xs uppercase tracking-[0.16em] text-slate-400">任务目标</div>
                    <div class="mt-2 leading-6 text-slate-800">{{ activeFormalTask.objective || '--' }}</div>
                  </div>
                  <div class="mt-3">
                    <div class="text-xs uppercase tracking-[0.16em] text-slate-400">交付物</div>
                    <div v-if="activeFormalTask.deliverables?.length" class="mt-2 space-y-2 text-slate-800">
                      <div v-for="(item, index) in activeFormalTask.deliverables" :key="`formal-task-deliverable-${index}`">
                        {{ index + 1 }}. {{ item }}
                      </div>
                    </div>
                    <div v-else class="mt-2 text-slate-500">暂无</div>
                  </div>
                  <div v-if="activeFormalTask.result_summary || activeFormalTask.reflection || activeFormalTask.review_note" class="mt-3 grid gap-3">
                    <div v-if="activeFormalTask.result_summary" class="rounded border border-emerald-100 bg-emerald-50 px-3 py-3">
                      <div class="text-xs uppercase tracking-[0.16em] text-emerald-700">执行结果</div>
                      <div class="mt-2 leading-6 text-slate-800">{{ activeFormalTask.result_summary }}</div>
                    </div>
                    <div v-if="activeFormalTask.reflection" class="rounded border border-sky-100 bg-sky-50 px-3 py-3">
                      <div class="text-xs uppercase tracking-[0.16em] text-sky-700">执行复盘</div>
                      <div class="mt-2 leading-6 text-slate-800">{{ activeFormalTask.reflection }}</div>
                    </div>
                    <div v-if="activeFormalTask.review_note" class="rounded border border-violet-100 bg-violet-50 px-3 py-3">
                      <div class="text-xs uppercase tracking-[0.16em] text-violet-700">育成点评</div>
                      <div class="mt-2 leading-6 text-slate-800">{{ activeFormalTask.review_note }}</div>
                    </div>
                  </div>
                </div>

                <div v-if="activeFormalTask.status === 'assigned'" class="rounded-lg border border-cyan-100 bg-cyan-50 px-3 py-3">
                  <div class="font-medium text-slate-900">3. 等待子女在自己的空间提交结果</div>
                  <div class="mt-2 text-sm leading-6 text-slate-700">
                    这一步已经从育成官页面移出。请让当前子女回到自己的岗位空间提交结果与复盘，育成官只在这里观察状态并等待确认。
                  </div>
                  <router-link
                    :to="`/organization/child/${encodeURIComponent(String(selectedChildMemberId || ''))}/workspace`"
                    class="mt-3 inline-flex rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700"
                  >
                    打开这位员工的工作台
                  </router-link>
                </div>

                <div v-else-if="activeFormalTask.status === 'submitted'" class="rounded-lg border border-violet-100 bg-violet-50 px-3 py-3">
                  <div class="font-medium text-slate-900">4. 育成师确认完成</div>
                  <textarea
                    :value="formalTaskApproveNoteDraft"
                    rows="3"
                    class="mt-3 w-full rounded-lg border border-violet-200 bg-white px-3 py-2 text-sm text-slate-700"
                    placeholder="点评这轮表现，并明确是否进入下一轮"
                    @input="emit('update:formalTaskApproveNoteDraft', ($event.target as HTMLTextAreaElement).value)"
                  ></textarea>
                  <button
                    @click="approveSelectedFormalTask"
                    :disabled="formalTaskActionRunning === 'approve'"
                    class="mt-3 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-60"
                  >
                    {{ formalTaskActionRunning === 'approve' ? '确认中...' : '确认本轮完成' }}
                  </button>
                </div>

                <div v-else class="rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-3 text-sm text-emerald-900">
                  <div>这轮任务已经完成，可以开始准备下一轮更正式的训练任务。</div>
                  <div class="mt-2 text-xs text-emerald-700">建议顺手把这轮经验导出到 Gitee，这样这位员工的成长就不只是显示在页面上，而是真的被入库了。</div>
                  <div
                    v-if="activeFormalTaskRecommendation"
                    class="mt-3 rounded-lg border border-violet-200 bg-violet-50 px-3 py-3 text-xs text-violet-950"
                  >
                    <div class="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div class="font-medium">系统生成的下一轮任务建议</div>
                        <div class="mt-1">{{ activeFormalTaskRecommendation.title || '--' }}</div>
                      </div>
                      <div class="flex flex-wrap gap-2">
                        <button
                          type="button"
                          @click="adoptRecommendedFormalTask"
                          class="rounded-lg border border-violet-200 bg-white px-3 py-1.5 text-[11px] font-medium text-violet-700 hover:bg-violet-100"
                        >
                          采用这条建议
                        </button>
                        <button
                          type="button"
                          @click="adoptAndAssignRecommendedFormalTask"
                          :disabled="formalTaskActionRunning === 'assign'"
                          class="rounded-lg bg-violet-600 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-violet-700 disabled:opacity-60"
                        >
                          {{ formalTaskActionRunning === 'assign' ? '进入中...' : '直接进入下一轮' }}
                        </button>
                      </div>
                    </div>
                    <div class="mt-2 leading-5 text-slate-700">{{ activeFormalTaskRecommendation.objective || '--' }}</div>
                    <div v-if="activeFormalTaskRecommendation.reason" class="mt-2 text-violet-800">
                      原因 {{ activeFormalTaskRecommendation.reason }}
                    </div>
                    <div v-if="activeFormalTaskRecommendation.deliverables?.length" class="mt-2 space-y-1 text-slate-700">
                      <div
                        v-for="(item, index) in activeFormalTaskRecommendation.deliverables"
                        :key="`next-recommendation-deliverable-${index}`"
                      >
                        {{ index + 1 }}. {{ item }}
                      </div>
                    </div>
                  </div>
                  <div
                    v-if="formalTaskGitExportRuntime"
                    class="mt-3 rounded-lg border px-3 py-3 text-xs"
                    :class="formalTaskGitExportStatusClass"
                  >
                    <div class="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div class="font-medium">自动经验入库状态</div>
                        <div class="mt-1">{{ formalTaskGitExportStatusLabel }}</div>
                      </div>
                      <span
                        class="rounded-full px-2.5 py-1 text-[11px] font-medium"
                        :class="formalTaskGitExportMatchesActiveTask ? 'bg-white/80 text-slate-800' : 'bg-white/60 text-slate-600'"
                      >
                        {{ formalTaskGitExportMatchesActiveTask ? '当前任务' : '最近一次导出' }}
                      </span>
                    </div>
                    <div class="mt-2">仓库 {{ formalTaskGitExportRuntime.target_repo || '--' }}</div>
                    <div class="mt-1">分支 {{ formalTaskGitExportRuntime.branch || '--' }}</div>
                    <div class="mt-1">令牌 {{ formalTaskGitExportRuntime.token_available ? '已就绪' : '缺失' }}</div>
                    <div class="mt-1">原因 {{ formalTaskGitExportRuntime.reason || '无' }}</div>
                    <div class="mt-1">下一步 {{ formalTaskGitExportRuntime.next_action || '--' }}</div>
                    <div v-if="formalTaskGitExportRuntime.last_export" class="mt-2 rounded bg-white/70 px-3 py-3 text-slate-700">
                      <div>时间 {{ formatDate(formalTaskGitExportRuntime.last_export.completed_at) }}</div>
                      <div class="mt-1">状态 {{ formatGitExportStatus(formalTaskGitExportRuntime.last_export.status) }}</div>
                      <div class="mt-1">任务 {{ formalTaskGitExportRuntime.last_export.task_type || '--' }} / {{ formalTaskGitExportRuntime.last_export.task_id || '--' }}</div>
                      <div class="mt-1 break-all">链接 {{ formalTaskGitExportRuntime.last_export.repo_url || '--' }}</div>
                      <div v-if="formalTaskGitExportRuntime.last_export.files?.length" class="mt-1 break-all">
                        文件 {{ formalTaskGitExportRuntime.last_export.files[0] }}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    @click="exportCurrentTenantExperiencesToGit"
                    :disabled="formalTaskExperienceExporting"
                    class="mt-3 rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-60"
                  >
                    {{ formalTaskExperienceExporting ? '导出中...' : '导出本轮经验到 Gitee' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import TrainerQuickWorkTypePanel from './TrainerQuickWorkTypePanel.vue'
import type { WorkspaceSubNavItem } from './shell/WorkspaceSubNav.vue'
import type { AutonomyStatus, CollaborationRequest, LearningTask } from '../api/plugins'
import {
  assignCollaborationRequest,
  getCollaborationPolicies,
  listCollaborations,
} from '../api/plugins'
import {
  buildMemberEvolutionThinking,
  buildMemberIndependenceHandoff,
  buildMemberIndependenceReadiness,
  buildMemberKnowledgeLearningPlan,
  formatLearningTaskStatus,
} from '../utils/memberEvolutionView'
import {
  buildCapabilityOptions,
  formatCapabilityLabel,
  formatCollaborationStatus,
  isCollaborationPipelineStatus,
  summarizeCollaborationRequest,
} from '../utils/collaborationView'
import { resolveMemberWorkTypeId } from '../utils/formalTaskRecommendation'

type GenericRecord = Record<string, any>

const props = defineProps<{
  selectedChildMemberId: string
  selectedChildMemberDraft: GenericRecord | null
  memberKnowledgeLearningTask?: LearningTask | null
  validatingKnowledgeLearningTaskId?: string
  selectedChildFormalTasks: GenericRecord[]
  trainerFormalTaskStageLabel: string
  trainerFormalTaskSteps: Array<{ key: string; title: string; badge: string; summary: string; tone: string; badgeClass: string }>
  trainerFormalTaskGuidance: string
  formalTaskMessage: string
  formalTaskSuccess: boolean
  formalTaskAssignTitleDraft: string
  formalTaskAssignObjectiveDraft: string
  formalTaskAssignDeliverablesDraft: string
  formalTaskRecommendationHint: string
  formalTaskAssignWorkTypeId: string
  formalTaskAssignMissionKind: string
  formalTaskApproveNoteDraft: string
  formalTaskActionRunning: string
  activeFormalTask: GenericRecord | null
  activeFormalTaskRecommendation: GenericRecord | null
  formalTaskGitExportRuntime: GenericRecord | null
  formalTaskGitExportStatusClass: string
  formalTaskGitExportStatusLabel: string
  formalTaskGitExportMatchesActiveTask: boolean
  formalTaskExperienceExporting: boolean
  formatDate: (value?: string | null) => string
  applyRecommendedFormalTaskDraft: (member: GenericRecord, options?: GenericRecord) => void
  assignFormalTaskToSelectedChild: () => void | Promise<void>
  goToChildWorkspaceForMember?: (memberId?: string) => void
  approveSelectedFormalTask: () => void | Promise<void>
  adoptRecommendedFormalTask: () => void | Promise<void>
  adoptAndAssignRecommendedFormalTask: () => void | Promise<void>
  exportCurrentTenantExperiencesToGit: () => void | Promise<void>
  validateMemberKnowledgeLearning?: () => void | Promise<void>
  workspaceMode?: 'summary' | 'assign' | 'confirm' | 'collaboration'
  tenantId?: string
  childMembersForCollaboration?: GenericRecord[]
  goToTrainerDispatchForMember?: (memberId?: string, dispatchTab?: 'summary' | 'assign' | 'confirm' | 'collaboration') => void
  companyWorkTypes?: Array<{ work_type_id?: string }>
}>()

const companyWorkTypeIds = computed(() => (
  (props.companyWorkTypes || []).map((item) => String(item.work_type_id || '').trim()).filter(Boolean)
))

const dispatchWorkspaceMode = ref<'summary' | 'assign' | 'confirm' | 'collaboration'>('summary')

const workNodeDashboardTo = computed(() => {
  const taskId = String(props.activeFormalTask?.task_id || '').trim()
  const memberId = String(props.selectedChildMemberId || '').trim()
  const wt = resolveMemberWorkTypeId(props.selectedChildMemberDraft as any)
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

const collaborationLoading = ref(false)
const collaborationActionRunning = ref('')
const collaborationMessage = ref('')
const collaborationSuccess = ref(false)
const orchestratorCollaborations = ref<CollaborationRequest[]>([])
const capabilityOptions = ref<Array<{ value: string; label: string }>>([])
const assignDrafts = ref<Record<string, { providerMemberId: string; providerTaskId: string }>>({})

const ensureAssignDraft = (requestId: string) => {
  if (!assignDrafts.value[requestId]) {
    assignDrafts.value[requestId] = { providerMemberId: '', providerTaskId: '' }
  }
  return assignDrafts.value[requestId]
}

const memberNameById = (memberId?: string | null) => {
  const normalized = String(memberId || '').trim()
  if (!normalized) return '--'
  const member = (props.childMembersForCollaboration || []).find((item) => String(item.member_id || '') === normalized)
  return String(member?.name || normalized)
}

const memberWorkTypeIds = (member: GenericRecord) => {
  const jobs = Array.isArray(member.current_jobs) ? member.current_jobs : []
  return jobs
    .map((job) => String(job?.work_type_id || '').trim())
    .filter(Boolean)
}

const providerCandidatesForRequest = (request: CollaborationRequest) => {
  const requesterId = String(request.requester_member_id || '').trim()
  const targetWorkTypeId = String(request.target_work_type_id || '').trim()
  const targetDepartmentId = String(request.target_department_id || '').trim()
  return (props.childMembersForCollaboration || []).filter((member) => {
    const memberId = String(member.member_id || '').trim()
    if (!memberId || memberId === requesterId) return false
    if (String(member.primary_role || '') === 'talent_development') return false
    if (targetWorkTypeId) {
      const workTypeIds = memberWorkTypeIds(member)
      if (workTypeIds.length && !workTypeIds.includes(targetWorkTypeId)) return false
    }
    if (targetDepartmentId) {
      const departmentId = String(member.organization?.department_id || '').trim()
      if (departmentId && departmentId !== targetDepartmentId) return false
    }
    return true
  })
}

const pipelineCollaborations = computed(() => (
  orchestratorCollaborations.value.filter((item) => isCollaborationPipelineStatus(item.status))
))

const loadCollaborationQueue = async () => {
  collaborationLoading.value = true
  collaborationMessage.value = ''
  try {
    const [listResult, policyResult] = await Promise.all([
      listCollaborations({
        tenant_id: props.tenantId || 'default',
        role: 'orchestrator',
      }),
      getCollaborationPolicies(),
    ])
    orchestratorCollaborations.value = listResult.data?.items || []
    capabilityOptions.value = buildCapabilityOptions(
      Array.isArray(policyResult.data?.deliverable_templates) ? policyResult.data.deliverable_templates : [],
    )
    for (const request of orchestratorCollaborations.value) {
      const requestId = String(request.request_id || '').trim()
      if (!requestId) continue
      const draft = ensureAssignDraft(requestId)
      const summary = summarizeCollaborationRequest(request)
      if (summary.providerMemberId && !draft.providerMemberId) {
        draft.providerMemberId = summary.providerMemberId
      }
      if (summary.providerTaskId && !draft.providerTaskId) {
        draft.providerTaskId = summary.providerTaskId
      }
    }
  } catch {
    collaborationSuccess.value = false
    collaborationMessage.value = '协作队列加载失败'
  } finally {
    collaborationLoading.value = false
  }
}

const submitCollaborationAssign = async (request: CollaborationRequest) => {
  const requestId = String(request.request_id || '').trim()
  const draft = assignDrafts.value[requestId]
  const providerMemberId = String(draft?.providerMemberId || '').trim()
  if (!requestId || !providerMemberId) return
  collaborationActionRunning.value = requestId
  collaborationMessage.value = ''
  try {
    const result = await assignCollaborationRequest(requestId, {
      tenant_id: props.tenantId || 'default',
      provider_member_id: providerMemberId,
      provider_task_id: String(draft?.providerTaskId || '').trim() || undefined,
      assigned_by: 'talent_development_officer',
    })
    orchestratorCollaborations.value = orchestratorCollaborations.value.map((item) => (
      String(item.request_id || '') === requestId ? (result.data?.request || item) : item
    ))
    collaborationSuccess.value = true
    collaborationMessage.value = result.message || '协作已指派，提供方可并行执行'
    emit('autonomyUpdated', result.data?.autonomy || null)
    await loadCollaborationQueue()
  } catch {
    collaborationSuccess.value = false
    collaborationMessage.value = '协作指派失败'
  } finally {
    collaborationActionRunning.value = ''
  }
}

const goToProviderDispatch = (memberId?: string) => {
  const normalized = String(memberId || '').trim()
  if (!normalized) return
  props.goToTrainerDispatchForMember?.(normalized, 'assign')
}

const collaborationAssignDraft = (request: CollaborationRequest) => (
  ensureAssignDraft(String(request.request_id || ''))
)

const emit = defineEmits<{
  'update:formalTaskAssignTitleDraft': [value: string]
  'update:formalTaskAssignObjectiveDraft': [value: string]
  'update:formalTaskAssignDeliverablesDraft': [value: string]
  'update:formalTaskApproveNoteDraft': [value: string]
  'update:workspaceMode': [value: 'summary' | 'assign' | 'confirm' | 'collaboration']
  autonomyUpdated: [value: AutonomyStatus | null]
  'work-type-saved': [workTypeId: string]
}>()

onMounted(() => {
  void loadCollaborationQueue()
})

watch(() => props.workspaceMode, (value) => {
  if (value === 'collaboration') {
    void loadCollaborationQueue()
  }
}, { immediate: true })

const memberEvolutionThinking = computed(() => buildMemberEvolutionThinking(props.selectedChildMemberDraft))

const memberIndependenceReadiness = computed(() => buildMemberIndependenceReadiness(props.selectedChildMemberDraft))

const memberKnowledgeLearningTask = computed(() => props.memberKnowledgeLearningTask || null)

const memberIndependenceHandoff = computed(() => buildMemberIndependenceHandoff(props.selectedChildMemberDraft))

const memberKnowledgeLearningPlan = computed(() => buildMemberKnowledgeLearningPlan(props.selectedChildMemberDraft))

const canValidateKnowledgeLearning = computed(() => {
  const status = String(memberKnowledgeLearningTask.value?.status || '').trim()
  return ['needs_learning', 'researching', 'candidate_found', 'ready_for_validation'].includes(status)
})

const isDispatchWorkspaceMode = (value: unknown): value is 'summary' | 'assign' | 'confirm' | 'collaboration' => (
  value === 'summary' || value === 'assign' || value === 'confirm' || value === 'collaboration'
)

const setDispatchWorkspaceMode = (value: 'summary' | 'assign' | 'confirm' | 'collaboration') => {
  if (dispatchWorkspaceMode.value === value) return
  dispatchWorkspaceMode.value = value
  emit('update:workspaceMode', value)
}

const onDispatchSubNavSelect = (key: string) => {
  setDispatchWorkspaceMode(key as 'summary' | 'assign' | 'confirm' | 'collaboration')
}

const dispatchWorkspaceMeta = computed(() => {
  if (dispatchWorkspaceMode.value === 'collaboration') {
    return {
      title: '协作队列视图',
      description: '查看员工发起的跨工种协作，指派提供方并跟踪交付与审核进度。',
    }
  }
  if (dispatchWorkspaceMode.value === 'assign') {
    return {
      title: '任务分配视图',
      description: '这里专门编辑正式任务草案、重生成建议并把任务下发给当前子女。',
    }
  }
  if (dispatchWorkspaceMode.value === 'confirm') {
    return {
      title: '结果确认视图',
      description: '这里专门看当前任务状态、子女提交结果、育成复盘确认和下一轮建议接续。',
    }
  }
  return {
    title: '闭环总览视图',
    description: '这里专门看当前子女处于任务闭环的哪一步，以及育成官此刻最该采取的动作。',
  }
})

const formatFormalTaskStatus = (value?: string | null, fallback = '--') => {
  const normalized = String(value || '').trim()
  if (!normalized) return fallback
  if (normalized === 'assigned') return '待执行'
  if (normalized === 'submitted') return '待确认'
  if (normalized === 'approved') return '已完成'
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

const dispatchWorkspaceCards = computed(() => ([
  {
    key: 'summary',
    title: '闭环总览',
    description: '先看当前卡在哪一步，再决定是分配、等待还是确认。',
    badge: dispatchWorkspaceMode.value === 'summary' ? '当前' : '总览',
    badgeClass: dispatchWorkspaceMode.value === 'summary' ? 'bg-amber-600 text-white' : 'bg-amber-100 text-amber-700',
    active: dispatchWorkspaceMode.value === 'summary',
    activeClass: 'border-amber-300 bg-amber-50 shadow-sm',
    idleClass: 'border-amber-200 bg-white hover:bg-amber-50/60',
  },
  {
    key: 'assign',
    title: '任务分配',
    description: '整理这轮目标、交付物和任务草案后正式下发。',
    badge: dispatchWorkspaceMode.value === 'assign' ? '当前' : '编排',
    badgeClass: dispatchWorkspaceMode.value === 'assign' ? 'bg-violet-600 text-white' : 'bg-violet-100 text-violet-700',
    active: dispatchWorkspaceMode.value === 'assign',
    activeClass: 'border-violet-300 bg-violet-50 shadow-sm',
    idleClass: 'border-violet-200 bg-white hover:bg-violet-50/60',
  },
  {
    key: 'confirm',
    title: '结果确认',
    description: '查看子女提交内容，确认这一轮是否正式完成。',
    badge: dispatchWorkspaceMode.value === 'confirm' ? '当前' : (props.activeFormalTask ? '处理中' : '待进入'),
    badgeClass: dispatchWorkspaceMode.value === 'confirm' ? 'bg-emerald-600 text-white' : (props.activeFormalTask ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'),
    active: dispatchWorkspaceMode.value === 'confirm',
    activeClass: 'border-emerald-300 bg-emerald-50 shadow-sm',
    idleClass: 'border-emerald-200 bg-white hover:bg-emerald-50/60',
  },
  {
    key: 'collaboration',
    title: '协作队列',
    description: '处理跨工种协作请求，指派提供方并跟踪交付审核。',
    badge: dispatchWorkspaceMode.value === 'collaboration' ? '当前' : (pipelineCollaborations.value.length ? `${pipelineCollaborations.value.length} 进行中` : '空闲'),
    badgeClass: dispatchWorkspaceMode.value === 'collaboration' ? 'bg-cyan-600 text-white' : (pipelineCollaborations.value.length ? 'bg-cyan-100 text-cyan-800' : 'bg-slate-100 text-slate-600'),
    active: dispatchWorkspaceMode.value === 'collaboration',
    activeClass: 'border-cyan-300 bg-cyan-50 shadow-sm',
    idleClass: 'border-cyan-200 bg-white hover:bg-cyan-50/60',
  },
]) as Array<{
  key: 'summary' | 'assign' | 'confirm' | 'collaboration'
  title: string
  description: string
  badge: string
  badgeClass: string
  active: boolean
  activeClass: string
  idleClass: string
}>)

const dispatchSubNavItems = computed<WorkspaceSubNavItem[]>(() => (
  dispatchWorkspaceCards.value.map((item) => ({
    key: item.key,
    title: item.title,
    badge: item.badge,
    badgeClass: item.badgeClass,
    active: item.active,
  }))
))

const inferDispatchWorkspaceMode = () => {
  const status = String(props.activeFormalTask?.status || '').trim()
  if (status === 'submitted' || status === 'approved') return 'confirm'
  if (status === 'assigned') return 'confirm'
  return 'assign'
}

watch(() => props.activeFormalTask?.status, () => {
  if (isDispatchWorkspaceMode(props.workspaceMode)) return
  setDispatchWorkspaceMode(inferDispatchWorkspaceMode())
}, { immediate: true })

watch(() => props.workspaceMode, (value) => {
  if (!isDispatchWorkspaceMode(value) || value === dispatchWorkspaceMode.value) return
  dispatchWorkspaceMode.value = value
}, { immediate: true })

watch(dispatchWorkspaceMode, (value) => {
  if (value === props.workspaceMode) return
  emit('update:workspaceMode', value)
  if (value === 'collaboration') {
    void loadCollaborationQueue()
  }
})
</script>
