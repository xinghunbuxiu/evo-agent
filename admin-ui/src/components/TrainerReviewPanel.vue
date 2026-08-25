<template>
  <div
    v-if="selectedChildMemberId"
    id="review-zone"
    class="min-w-0 scroll-mt-24 rounded-xl border border-cyan-200 bg-cyan-50/60 px-4 py-4 text-sm text-cyan-950"
  >
    <div class="mb-4 rounded-xl border border-cyan-100 bg-white px-4 py-4">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-sm font-semibold text-cyan-950">复盘沟通工作面</div>
          <div class="mt-1 text-xs text-cyan-700">这里处理育成官与子女的关系层沟通、状态回话和必要的带教反馈，不再和公司级配置混放。</div>
        </div>
        <div class="rounded-full bg-cyan-100 px-3 py-1 text-[11px] text-cyan-800">
          {{ reviewWorkspaceMode === 'conversation' ? '沟通记录' : reviewWorkspaceMode === 'professional' ? '专业视角' : reviewWorkspaceMode === 'knowledge' ? '补知识' : '成长诊断' }}
        </div>
      </div>
      <div class="mt-4 grid gap-3 md:grid-cols-3">
        <div class="rounded-xl border border-cyan-100 bg-cyan-50/60 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前对象</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedChildMemberDraft?.name || selectedChildMemberId || '--' }}</div>
        </div>
        <div class="rounded-xl border border-cyan-100 bg-cyan-50/60 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前阶段</div>
          <div class="mt-2 font-medium text-slate-900">{{ formatLifecycleStage(selectedChildMemberDraft?.training_plan?.stage || selectedChildMemberDraft?.onboarding?.status) }}</div>
        </div>
        <div class="rounded-xl border border-cyan-100 bg-cyan-50/60 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前重点</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedChildMemberRuntime?.professional_view?.next_professional_focus || selectedChildMemberDraft?.growth_state?.current_focus || '--' }}</div>
        </div>
      </div>
    </div>
    <div class="mb-4 rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="text-sm font-semibold text-slate-900">当前工作位</div>
          <div class="mt-1 text-xs text-slate-500">围绕同一个孩子切换沟通、专业判断和成长诊断，不把不同层次的内容混看。</div>
        </div>
        <div class="rounded-full bg-slate-100 px-3 py-1 text-[11px] text-slate-600">
          当前 {{ reviewWorkspaceMeta.title }}
        </div>
      </div>
      <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <button
          v-for="item in reviewWorkspaceCards"
          :key="`review-card-${item.key}`"
          type="button"
          @click="onSelectReviewWorkspace(item.key)"
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
        <div class="font-medium text-slate-900">{{ reviewWorkspaceMeta.title }}</div>
        <div class="mt-2 leading-6">{{ reviewWorkspaceMeta.description }}</div>
      </div>
    </div>
    <div v-if="reviewWorkspaceMode === 'conversation'" class="min-w-0 space-y-4">
        <div class="min-w-0 rounded-xl border border-cyan-100 bg-white px-4 py-4">
          <div class="font-medium text-slate-900">当前沟通窗口</div>
          <div class="mt-1 text-xs leading-5 text-cyan-700">聚焦当前员工的反馈与回复，不混入其他成员消息。</div>
          <div class="mt-4 space-y-3">
            <textarea
              :value="childReplyDraft"
              rows="4"
              class="block w-full min-h-[5.5rem] min-w-0 resize-y rounded-lg border border-cyan-200 bg-white px-3 py-2.5 text-sm leading-6 text-slate-700"
              placeholder="让这位员工用自己的身份反馈：比如我卡住了、我完成了、我觉得这轮建议需要调整..."
              @input="emit('update:childReplyDraft', ($event.target as HTMLTextAreaElement).value)"
            ></textarea>
            <div class="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                @click="sendChildReply"
                :disabled="childReplySending || !selectedChildMemberId || !childReplyDraft.trim()"
                class="shrink-0 rounded-lg bg-cyan-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-60"
              >
                {{ childReplySending ? '发送中...' : '发送这条反馈' }}
              </button>
            </div>
          </div>
          <div v-if="!(selectedChildConversation?.messages?.length)" class="mt-4 text-xs text-cyan-700">当前还没有历史沟通，你可以先发第一条内部消息。</div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="message in (selectedChildConversation.messages || []).slice().reverse().slice(0, 6)"
              :key="message.message_id"
              class="min-w-0 rounded-lg px-3 py-3 text-xs"
              :class="relationshipMessageCardClass(message)"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="font-medium text-slate-900">{{ relationshipSenderLabel(message) }}</div>
                  <div class="mt-1 flex flex-wrap gap-2">
                    <span
                      class="rounded-full px-2.5 py-1 text-[11px] font-medium"
                      :class="relationshipMessageBadgeClass(message)"
                    >
                      {{ relationshipMessageTypeLabel(message) }}
                    </span>
                    <span
                      v-if="message.metadata?.reply_policy"
                      class="rounded-full bg-white/80 px-2.5 py-1 text-[11px] text-slate-600"
                    >
                      {{ String(message.metadata.reply_policy) }}
                    </span>
                    <span
                      v-if="message.metadata?.auto_followup"
                      class="rounded-full bg-white/80 px-2.5 py-1 text-[11px] text-violet-700"
                    >
                      自动成长跟进
                    </span>
                  </div>
                </div>
                <div class="text-slate-500">{{ formatDate(message.created_at) }}</div>
              </div>
              <div class="mt-2 leading-6">{{ message.content || '--' }}</div>
              <div
                v-if="message.message_type === 'trainer_growth_comment' && (message.metadata?.training_stage_from || message.metadata?.training_stage_to || message.metadata?.mission_status)"
                class="mt-2 text-[11px] text-slate-600"
              >
                <span v-if="message.metadata?.training_stage_from || message.metadata?.training_stage_to">
                  阶段 {{ formatLifecycleStage(String(message.metadata?.training_stage_from || ''), '--') }} -> {{ formatLifecycleStage(String(message.metadata?.training_stage_to || ''), '--') }}
                </span>
                <span v-if="message.metadata?.mission_status">
                  / 任务 {{ formatFormalTaskStatus(String(message.metadata?.mission_status || ''), '--') }}
                </span>
              </div>
              <div v-if="Array.isArray(message.metadata?.applied_rules) && message.metadata?.applied_rules.length" class="mt-2 flex flex-wrap gap-2">
                <span
                  v-for="rule in message.metadata?.applied_rules as string[]"
                  :key="`${message.message_id}-${rule}`"
                  class="rounded-full bg-cyan-100 px-2.5 py-1 text-[11px] text-cyan-800"
                >
                  {{ rule }}
                </span>
              </div>
            </div>
          </div>
        </div>
    </div>

    <TrainerKnowledgePanel
      v-else-if="reviewWorkspaceMode === 'knowledge'"
      :member-id="selectedChildMemberId"
      :member-draft="selectedChildMemberDraft"
      :learning-task="resolvedLearningTask"
      :tenant-id="tenantId"
      :validating="validatingKnowledgeLearning"
      :can-validate="canValidateKnowledgeLearning"
      @validate="emit('validate-knowledge')"
      @go-dispatch="emit('go-dispatch')"
      @refreshed="emit('knowledge-refreshed')"
    />

    <div v-else-if="reviewWorkspaceMode === 'professional' || reviewWorkspaceMode === 'diagnosis'" class="min-w-0 space-y-4">
        <div v-if="selectedChildMemberDraft?.training_plan" class="rounded-xl border border-violet-200 bg-violet-50/60 px-4 py-4 text-sm text-violet-950">
          <div v-if="selectedChildMemberRuntime?.professional_view && reviewWorkspaceMode === 'professional'" class="mb-4 rounded-lg border border-emerald-100 bg-white px-3 py-3 text-xs text-slate-700">
            <div class="font-medium text-slate-900">这位员工当前的专业判断</div>
            <div class="mt-2">视角来源 {{ selectedChildMemberRuntime.professional_view.owner || '--' }}</div>
            <div class="mt-1 leading-5">{{ selectedChildMemberRuntime.professional_view.summary || '--' }}</div>
            <div class="mt-3 grid gap-3 md:grid-cols-2">
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-3">
                <div class="font-medium text-slate-900">现在怎么判断</div>
                <div class="mt-2 leading-5">{{ selectedChildMemberRuntime.professional_view.current_judgement || '--' }}</div>
              </div>
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-3">
                <div class="font-medium text-slate-900">下一轮重点</div>
                <div class="mt-2 leading-5">{{ selectedChildMemberRuntime.professional_view.next_professional_focus || '--' }}</div>
              </div>
            </div>
            <div class="mt-3 grid gap-3 md:grid-cols-2">
              <div class="rounded border border-emerald-100 bg-emerald-50 px-3 py-3">
                <div class="font-medium text-slate-900">复盘归纳</div>
                <div class="mt-2 leading-5">{{ selectedChildMemberRuntime.professional_view.reflection_summary || '--' }}</div>
              </div>
              <div class="rounded border border-amber-100 bg-amber-50 px-3 py-3">
                <div class="font-medium text-slate-900">当前做事方式</div>
                <div class="mt-2 leading-5">{{ selectedChildMemberRuntime.professional_view.current_pattern || '--' }}</div>
              </div>
            </div>
            <div class="mt-3 grid gap-3 md:grid-cols-2">
              <div class="rounded border border-rose-100 bg-rose-50 px-3 py-3">
                <div class="font-medium text-slate-900">当前风险</div>
                <div class="mt-2 leading-5">{{ selectedChildMemberRuntime.professional_view.professional_risk || '--' }}</div>
              </div>
              <div class="rounded border border-sky-100 bg-sky-50 px-3 py-3">
                <div class="font-medium text-slate-900">下一步实验</div>
                <div class="mt-2 leading-5">{{ selectedChildMemberRuntime.professional_view.next_experiment || '--' }}</div>
              </div>
            </div>
            <details class="mt-3 rounded border border-emerald-100 bg-emerald-50/50">
              <summary class="cursor-pointer list-none px-3 py-3">
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div class="font-medium text-slate-900">更多专业证据</div>
                  <div class="rounded-full bg-white px-3 py-1 text-[11px] text-emerald-700">按需展开</div>
                </div>
              </summary>
              <div class="border-t border-emerald-100 px-3 py-3">
                <div v-if="selectedChildMemberRuntime.professional_view.evidence?.length" class="flex flex-wrap gap-2">
                  <span
                    v-for="item in selectedChildMemberRuntime.professional_view.evidence"
                    :key="`professional-evidence-${item}`"
                    class="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] text-emerald-800"
                  >
                    {{ item }}
                  </span>
                </div>
                <div v-if="selectedChildMemberRuntime.professional_view.recent_reflections?.length" class="mt-3 rounded border border-emerald-100 bg-white px-3 py-3">
                  <div class="font-medium text-slate-900">最近三次岗位反馈</div>
                  <div
                    v-for="(item, index) in selectedChildMemberRuntime.professional_view.recent_reflections"
                    :key="`professional-reflection-${index}`"
                    class="mt-2 leading-5 text-slate-700"
                  >
                    {{ index + 1 }}. {{ item }}
                  </div>
                </div>
              </div>
            </details>
            <div v-if="selectedChildMemberDraft?.experience_journal?.cards?.length" class="mt-3 rounded border border-slate-200 bg-slate-50 px-3 py-3">
              <div class="flex items-start justify-between gap-3">
                <div class="font-medium text-slate-900">岗位经验卡片</div>
                <div class="text-[11px] text-slate-500">
                  汇总于 {{ formatDate(selectedChildMemberDraft.experience_journal.last_compiled_at) }}
                </div>
              </div>
              <div
                v-for="item in (selectedChildMemberDraft.experience_journal.cards || []).slice(0, 3)"
                :key="String(item.card_id || item.signature || item.title || 'experience-card')"
                class="mt-3 rounded-lg border border-white bg-white px-3 py-3 shadow-sm"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <div class="font-medium text-slate-900">{{ item.title || '--' }}</div>
                    <div class="mt-1 text-[11px] text-slate-500">
                      {{ item.job_id || '--' }} / {{ formatLifecycleStage(item.stage, '--') }} / {{ formatExperienceCardStatus(item.status) }}
                    </div>
                  </div>
                  <div class="text-[11px] text-slate-500">{{ formatDate(item.updated_at || item.created_at) }}</div>
                </div>
                <div class="mt-2 leading-5 text-slate-700">{{ item.summary || '--' }}</div>
                <div class="mt-3 grid gap-3 md:grid-cols-3">
                  <div class="rounded border border-slate-100 bg-slate-50 px-3 py-2">
                    <div class="text-[11px] font-medium text-slate-900">工作模式</div>
                    <div class="mt-1 leading-5 text-slate-600">{{ item.current_pattern || '--' }}</div>
                  </div>
                  <div class="rounded border border-slate-100 bg-rose-50 px-3 py-2">
                    <div class="text-[11px] font-medium text-slate-900">风险</div>
                    <div class="mt-1 leading-5 text-slate-600">{{ item.professional_risk || '--' }}</div>
                  </div>
                  <div class="rounded border border-slate-100 bg-sky-50 px-3 py-2">
                    <div class="text-[11px] font-medium text-slate-900">实验</div>
                    <div class="mt-1 leading-5 text-slate-600">{{ item.next_experiment || '--' }}</div>
                  </div>
                </div>
                <div v-if="item.evidence?.length" class="mt-3 flex flex-wrap gap-2">
                  <span
                    v-for="evidence in item.evidence"
                    :key="`${item.card_id || item.signature}-evidence-${evidence}`"
                    class="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600"
                  >
                    {{ evidence }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div v-show="reviewWorkspaceMode === 'diagnosis'" class="flex items-start justify-between gap-4">
            <div>
              <div class="font-medium">育成计划</div>
              <div class="mt-1 text-xs text-violet-800">阶段 {{ formatLifecycleStage(selectedChildMemberDraft.training_plan.stage) }} / 负责人 {{ selectedChildMemberDraft.training_plan.owner_member_id || '--' }}</div>
            </div>
            <div class="text-right text-xs text-violet-800">
              <div>下一步 {{ selectedChildMemberDraft.training_plan.next_action || '--' }}</div>
              <div class="mt-1">复查时间 {{ formatDate(selectedChildMemberDraft.training_plan.review_after) }}</div>
            </div>
          </div>
          <div v-show="reviewWorkspaceMode === 'diagnosis'" class="mt-4 grid gap-3 md:grid-cols-3">
            <div class="rounded-lg bg-white px-3 py-3">
              <div class="text-xs font-semibold uppercase tracking-[0.14em] text-violet-700">成长目标</div>
              <div v-if="!(selectedChildMemberDraft.training_plan.goals || []).length" class="mt-2 text-xs text-slate-500">暂无</div>
              <div v-else class="mt-2 space-y-2">
                <div
                  v-for="(goal, index) in selectedChildMemberDraft.training_plan.goals || []"
                  :key="`goal-${index}`"
                  class="text-xs text-slate-700"
                >
                  {{ index + 1 }}. {{ goal }}
                </div>
              </div>
            </div>
            <div class="rounded-lg bg-white px-3 py-3">
              <div class="text-xs font-semibold uppercase tracking-[0.14em] text-violet-700">训练课程</div>
              <div v-if="!(selectedChildMemberDraft.training_plan.curriculum || []).length" class="mt-2 text-xs text-slate-500">暂无</div>
              <div v-else class="mt-2 space-y-2">
                <div
                  v-for="(item, index) in selectedChildMemberDraft.training_plan.curriculum || []"
                  :key="`curriculum-${index}`"
                  class="text-xs text-slate-700"
                >
                  {{ index + 1 }}. {{ item }}
                </div>
              </div>
            </div>
            <div class="rounded-lg bg-white px-3 py-3">
              <div class="text-xs font-semibold uppercase tracking-[0.14em] text-violet-700">里程碑</div>
              <div v-if="!(selectedChildMemberDraft.training_plan.milestones || []).length" class="mt-2 text-xs text-slate-500">暂无</div>
              <div v-else class="mt-2 space-y-2">
                <div
                  v-for="(item, index) in selectedChildMemberDraft.training_plan.milestones || []"
                  :key="`milestone-${index}`"
                  class="text-xs text-slate-700"
                >
                  {{ index + 1 }}. {{ item }}
                </div>
              </div>
            </div>
          </div>
          <div v-if="selectedChildMemberRuntime?.training_autopilot && reviewWorkspaceMode === 'diagnosis'" class="mt-4 rounded-lg border border-violet-100 bg-white px-3 py-3 text-xs text-slate-700">
            <div class="font-medium text-slate-900">育成官自动改写记录</div>
            <div class="mt-2">自动改写 {{ selectedChildMemberRuntime.training_autopilot.auto_updated ? '是' : '否' }}</div>
            <div class="mt-1">原因 {{ selectedChildMemberRuntime.training_autopilot.reason || '--' }}</div>
            <div v-if="selectedChildMemberRuntime.training_autopilot.coaching_view" class="mt-3 grid gap-3 md:grid-cols-3">
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-3">
                <div class="font-medium text-slate-900">成长诊断</div>
                <div class="mt-2 leading-5">{{ selectedChildMemberRuntime.training_autopilot.coaching_view.growth_diagnosis || '--' }}</div>
              </div>
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-3">
                <div class="font-medium text-slate-900">训练建议</div>
                <div class="mt-2 leading-5">{{ selectedChildMemberRuntime.training_autopilot.coaching_view.training_suggestion || '--' }}</div>
              </div>
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-3">
                <div class="font-medium text-slate-900">外部趋势提醒</div>
                <div class="mt-2 leading-5">{{ selectedChildMemberRuntime.training_autopilot.coaching_view.trend_watch || '--' }}</div>
              </div>
            </div>
            <div v-if="selectedChildMemberRuntime.training_autopilot.applied_rules?.length" class="mt-2 flex flex-wrap gap-2">
              <span
                v-for="rule in selectedChildMemberRuntime.training_autopilot.applied_rules"
                :key="`training-rule-${rule}`"
                class="rounded-full bg-violet-100 px-2.5 py-1 text-[11px] text-violet-800"
              >
                {{ rule }}
              </span>
            </div>
            <div v-if="selectedChildMemberRuntime.training_autopilot.observations?.length" class="mt-2 flex flex-wrap gap-2">
              <span
                v-for="item in selectedChildMemberRuntime.training_autopilot.observations"
                :key="`training-observation-${item}`"
                class="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] text-emerald-800"
              >
                {{ item }}
              </span>
            </div>
          </div>
        </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { LearningTask } from '../api/plugins'
import TrainerKnowledgePanel from './TrainerKnowledgePanel.vue'

type GenericRecord = Record<string, any>

const props = defineProps<{
  selectedChildMemberId: string
  selectedChildMemberDraft: GenericRecord | null
  selectedChildMemberRuntime: GenericRecord | null
  selectedChildConversation: GenericRecord | null
  childReplyDraft: string
  childReplySending: boolean
  formatDate: (value?: string | null) => string
  sendChildReply: () => void | Promise<void>
  relationshipMessageCardClass: (message?: GenericRecord) => string
  relationshipSenderLabel: (message?: GenericRecord) => string
  relationshipMessageBadgeClass: (message?: GenericRecord) => string
  relationshipMessageTypeLabel: (message?: GenericRecord) => string
  workspaceMode?: 'conversation' | 'professional' | 'diagnosis' | 'knowledge'
  learningTask?: LearningTask | null
  tenantId?: string
  validatingKnowledgeLearning?: boolean
  canValidateKnowledgeLearning?: boolean
}>()

const reviewWorkspaceMode = ref<'conversation' | 'professional' | 'diagnosis' | 'knowledge'>('conversation')

const isReviewWorkspaceMode = (value: unknown): value is 'conversation' | 'professional' | 'diagnosis' | 'knowledge' => (
  value === 'conversation' || value === 'professional' || value === 'diagnosis' || value === 'knowledge'
)

const setReviewWorkspaceMode = (value: 'conversation' | 'professional' | 'diagnosis' | 'knowledge') => {
  if (reviewWorkspaceMode.value === value) return
  reviewWorkspaceMode.value = value
}

const onSelectReviewWorkspace = (key: 'conversation' | 'professional' | 'diagnosis' | 'knowledge') => {
  setReviewWorkspaceMode(key)
}

const resolvedLearningTask = computed(() => props.learningTask ?? null)

const reviewWorkspaceMeta = computed(() => {
  if (reviewWorkspaceMode.value === 'professional') {
    return {
      title: '专业视角视图',
      description: '这里专门查看当前子女的专业判断、反思归纳、最近经验卡和下一轮实验方向。',
    }
  }
  if (reviewWorkspaceMode.value === 'knowledge') {
    return {
      title: '补知识工作位',
      description: '处理调研、候选方案、验证与回到正式任务的闭环，不让认知缺口拖住岗位训练。',
    }
  }
  if (reviewWorkspaceMode.value === 'diagnosis') {
    return {
      title: '成长诊断视图',
      description: '这里专门查看育成计划、课程里程碑、自动改写记录和训练诊断。',
    }
  }
  return {
    title: '沟通记录视图',
    description: '这里专门处理育成官与当前子女之间的消息来回、反馈和规则痕迹。',
  }
})

const reviewWorkspaceCards = computed(() => ([
  {
    key: 'conversation',
    title: '沟通记录',
    description: '集中看这一个孩子的来回消息、反馈和规则痕迹。',
    badge: reviewWorkspaceMode.value === 'conversation' ? '当前' : '沟通',
    badgeClass: reviewWorkspaceMode.value === 'conversation' ? 'bg-cyan-600 text-white' : 'bg-cyan-100 text-cyan-700',
    active: reviewWorkspaceMode.value === 'conversation',
    activeClass: 'border-cyan-300 bg-cyan-50 shadow-sm',
    idleClass: 'border-cyan-200 bg-white hover:bg-cyan-50/60',
  },
  {
    key: 'professional',
    title: '专业视角',
    description: '查看这位员工现在怎么判断、怎么做，以及下一轮实验方向。',
    badge: reviewWorkspaceMode.value === 'professional' ? '当前' : (props.selectedChildMemberRuntime?.professional_view ? '已有判断' : '待形成'),
    badgeClass: reviewWorkspaceMode.value === 'professional' ? 'bg-emerald-600 text-white' : (props.selectedChildMemberRuntime?.professional_view ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'),
    active: reviewWorkspaceMode.value === 'professional',
    activeClass: 'border-emerald-300 bg-emerald-50 shadow-sm',
    idleClass: 'border-emerald-200 bg-white hover:bg-emerald-50/60',
  },
  {
    key: 'knowledge',
    title: '补知识',
    description: '调研缺口、验证认知、回到正式任务。',
    badge: props.learningTask ? '进行中' : (reviewWorkspaceMode.value === 'knowledge' ? '当前' : '待进入'),
    badgeClass: props.learningTask ? 'bg-sky-600 text-white' : (reviewWorkspaceMode.value === 'knowledge' ? 'bg-sky-600 text-white' : 'bg-sky-100 text-sky-700'),
    active: reviewWorkspaceMode.value === 'knowledge',
    activeClass: 'border-sky-300 bg-sky-50 shadow-sm',
    idleClass: 'border-sky-200 bg-white hover:bg-sky-50/60',
  },
  {
    key: 'diagnosis',
    title: '成长诊断',
    description: '查看训练计划、课程里程碑和自动改写痕迹。',
    badge: reviewWorkspaceMode.value === 'diagnosis' ? '当前' : '诊断',
    badgeClass: reviewWorkspaceMode.value === 'diagnosis' ? 'bg-violet-600 text-white' : 'bg-violet-100 text-violet-700',
    active: reviewWorkspaceMode.value === 'diagnosis',
    activeClass: 'border-violet-300 bg-violet-50 shadow-sm',
    idleClass: 'border-violet-200 bg-white hover:bg-violet-50/60',
  },
]) as Array<{
  key: 'conversation' | 'professional' | 'diagnosis' | 'knowledge'
  title: string
  description: string
  badge: string
  badgeClass: string
  active: boolean
  activeClass: string
  idleClass: string
}>)

const formatLifecycleStage = (value?: string | null, fallback = '--') => {
  const normalized = String(value || '').trim()
  if (!normalized) return fallback
  if (normalized === 'profile_initialized') return '已建档'
  if (normalized === 'portrait_created') return '画像已创建'
  if (normalized === 'trainer_taken_over') return '育成官已接手'
  if (normalized === 'ready_for_first_case') return '待进入首轮案例'
  if (normalized === 'first_case_running') return '首轮案例进行中'
  if (normalized === 'reflection_pending') return '待补复盘'
  if (normalized === 'first_reflection_done') return '首轮复盘完成'
  if (normalized === 'active_training') return '持续训练中'
  if (normalized === 'completed_cycle') return '本轮已闭环'
  if (normalized === 'archived') return '已归档'
  return normalized
}

const formatFormalTaskStatus = (value?: string | null, fallback = '--') => {
  const normalized = String(value || '').trim()
  if (!normalized) return fallback
  if (normalized === 'queued') return '待执行'
  if (normalized === 'in_progress') return '执行中'
  if (normalized === 'awaiting_review') return '待复盘'
  if (normalized === 'approved') return '已通过'
  if (normalized === 'rejected') return '需重做'
  if (normalized === 'completed') return '已完成'
  return normalized
}

const formatExperienceCardStatus = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return '--'
  if (normalized === 'draft') return '草稿中'
  if (normalized === 'active') return '生效中'
  if (normalized === 'stabilizing') return '沉淀中'
  if (normalized === 'validated') return '已验证'
  if (normalized === 'archived') return '已归档'
  return normalized
}

const inferReviewWorkspaceMode = () => (
  props.selectedChildMemberRuntime?.professional_view ? 'professional' : 'conversation'
)

watch(() => props.selectedChildMemberId, () => {
  if (isReviewWorkspaceMode(props.workspaceMode)) return
  setReviewWorkspaceMode(inferReviewWorkspaceMode())
}, { immediate: true })

watch(() => props.workspaceMode, (value) => {
  if (!isReviewWorkspaceMode(value) || value === reviewWorkspaceMode.value) return
  reviewWorkspaceMode.value = value
}, { immediate: true })

watch(reviewWorkspaceMode, (value) => {
  if (value === props.workspaceMode) return
  emit('update:workspaceMode', value)
})

const emit = defineEmits<{
  'update:childReplyDraft': [value: string]
  'update:workspaceMode': [value: 'conversation' | 'professional' | 'diagnosis' | 'knowledge']
  'validate-knowledge': []
  'go-dispatch': []
  'knowledge-refreshed': []
}>()
</script>
