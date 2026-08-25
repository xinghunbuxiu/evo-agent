<template>
  <div class="rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm lg:p-6">
    <template v-if="!compact">
      <div class="mb-3 inline-flex rounded-full bg-emerald-100 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-emerald-800">
        育成主线
      </div>
      <div class="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div class="min-w-0 flex-1">
          <h2 class="text-lg font-semibold text-slate-900">画像、编制与训练分发</h2>
          <p class="mt-1 text-sm text-slate-500">确认画像、建立编制、分发训练、观察成长，再把员工送回自己的岗位空间。</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            @click="props.loadAutonomyStatus()"
            :disabled="props.autonomyLoading"
            class="rounded-lg border border-slate-300 px-4 py-2 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            {{ props.autonomyLoading ? '刷新中...' : '刷新身份状态' }}
          </button>
          <button
            @click="props.saveAutonomyIdentity()"
            :disabled="props.autonomyIdentitySaving"
            class="rounded-lg bg-slate-900 px-4 py-2 text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {{ props.autonomyIdentitySaving ? '保存中...' : '保存身份设定' }}
          </button>
          <router-link
            to="/organization/child"
            class="inline-flex items-center rounded-lg border border-emerald-300 px-4 py-2 text-sm text-emerald-700 hover:bg-emerald-50"
          >
            打开员工工作台
          </router-link>
          <button
            @click="props.createChildPortrait()"
            :disabled="props.autonomyIdentitySaving"
            class="rounded-lg border border-emerald-300 px-4 py-2 text-emerald-700 hover:bg-emerald-50 disabled:opacity-60"
          >
            建立画像
          </button>
        </div>
      </div>
    </template>

    <p v-if="props.autonomyIdentityMessage" class="mb-4 text-sm" :class="props.autonomyIdentitySuccess ? 'text-green-600' : 'text-red-600'">
      {{ props.autonomyIdentityMessage }}
    </p>

    <div class="grid min-w-0 gap-5 xl:grid-cols-[minmax(240px,280px)_minmax(0,1fr)] xl:gap-6">
      <aside class="min-w-0 space-y-4 xl:sticky xl:top-[4.5rem] xl:max-h-[calc(100vh-5.5rem)] xl:self-start xl:overflow-y-auto">
        <div class="rounded-2xl border border-sky-200 bg-[linear-gradient(135deg,#eff6ff_0%,#ffffff_100%)] p-4 shadow-sm">
          <div class="text-sm font-semibold text-slate-900">当前育成官</div>
          <div class="mt-3">
            <div class="text-lg font-semibold text-slate-900">{{ props.trainerMemberDraft?.name || 'Talent Development Officer' }}</div>
            <div class="mt-1 text-xs text-slate-500">{{ props.trainerMemberDraft?.persona?.role_label || props.trainerMemberDraft?.primary_role || 'talent_development' }}</div>
          </div>
          <div class="mt-3 rounded-xl bg-white/90 px-3 py-3 text-sm text-slate-700">
            <div class="text-slate-400">当前工作位</div>
            <div class="mt-2 font-medium text-slate-900">{{ props.trainerMainlineModeMeta.title }}</div>
          </div>
          <div class="mt-3 rounded-xl bg-white/90 px-3 py-3 text-sm text-slate-700">
            <div class="text-slate-400">当前关注</div>
            <div class="mt-2 font-medium text-slate-900">
              {{ props.trainerMemberDraft?.growth_state?.current_focus || props.trainerMemberDraft?.self_development?.current_objective || '先确认正在带谁，再推进哪一轮带教' }}
            </div>
          </div>
        </div>

        <div class="rounded-2xl border border-amber-200 bg-[linear-gradient(135deg,#fff7ed_0%,#ffffff_100%)] p-4 shadow-sm">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="text-sm font-semibold text-slate-900">带教对象</div>
              <div class="mt-1 text-xs text-slate-500">先明确当前正在服务哪位员工。</div>
            </div>
            <div class="shrink-0 rounded-full bg-white px-2.5 py-1 text-[11px] text-amber-700">
              {{ props.managedChildMembersDraft.length }}
            </div>
          </div>
          <div v-if="props.managedChildMembersDraft.length" class="mt-4 space-y-3">
            <button
              v-for="member in props.managedChildMembersDraft"
              :key="`managed-child-${member.member_id}`"
              type="button"
              @click="props.selectChildMember(String(member.member_id || ''))"
              class="w-full rounded-2xl border px-4 py-4 text-left transition"
              :class="props.selectedChildMemberId === member.member_id ? 'border-amber-300 bg-amber-50 shadow-sm' : 'border-amber-200 bg-white hover:bg-amber-50/60'"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="truncate font-medium text-slate-900">{{ member.name || member.member_id || '--' }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ member.primary_role || '--' }}</div>
                </div>
                <span class="shrink-0 rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-600">
                  {{ props.formatLifecycleStage(member.training_plan?.stage || member.onboarding?.status) }}
                </span>
              </div>
              <div class="mt-3 rounded-xl bg-white/80 px-3 py-3 text-xs text-slate-700">
                <div class="text-slate-400">当前重点</div>
                <div class="mt-1 font-medium text-slate-900">{{ member.growth_state?.current_focus || member.training_plan?.next_action || '--' }}</div>
              </div>
            </button>
          </div>
          <div v-else class="mt-4 rounded-xl border border-dashed border-amber-200 bg-white px-3 py-4 text-sm text-amber-800">
            还没有可带教的员工，先建立第一份画像。
          </div>
        </div>
      </aside>

      <div class="min-w-0 space-y-4">
        <div
          v-if="!props.compact"
          class="rounded-[28px] border border-emerald-200 bg-[linear-gradient(135deg,#f0fdf4_0%,#ffffff_55%,#ecfeff_100%)] p-5 shadow-sm"
        >
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div class="min-w-0">
              <div class="inline-flex rounded-full bg-white px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-emerald-700">
                当前工作台
              </div>
              <div class="mt-3 text-2xl font-semibold text-slate-900">育成官当前工作台</div>
              <div class="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                育成官围绕某位员工做画像、编排、审核和复盘推动；员工则在自己的岗位空间执行任务。
              </div>
            </div>
            <div class="flex flex-wrap gap-2">
              <button
                @click="props.createChildPortrait()"
                :disabled="props.autonomyIdentitySaving"
                class="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
              >
                建立画像
              </button>
              <router-link
                v-if="props.currentChildWorkspaceRoute"
                :to="props.currentChildWorkspaceRoute"
                class="rounded-full border border-emerald-300 bg-white px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
              >
                进入这位员工的空间
              </router-link>
            </div>
          </div>

          <div class="mt-5 grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
            <div class="rounded-xl border border-white/70 bg-white/90 px-4 py-4 text-sm text-slate-700">
              <div class="text-xs uppercase tracking-[0.16em] text-slate-400">活跃员工</div>
              <div class="mt-2 text-lg font-semibold text-slate-900">{{ props.managedChildMembersDraft.length }}</div>
            </div>
            <div class="rounded-xl border border-white/70 bg-white/90 px-4 py-4 text-sm text-slate-700">
              <div class="text-xs uppercase tracking-[0.16em] text-slate-400">当前工作位</div>
              <div class="mt-2 text-lg font-semibold text-slate-900">{{ props.trainerMainlineModeMeta.title }}</div>
            </div>
            <div class="rounded-xl border border-white/70 bg-white/90 px-4 py-4 text-sm text-slate-700">
              <div class="text-xs uppercase tracking-[0.16em] text-slate-400">当前带教对象</div>
              <div class="mt-2 text-lg font-semibold text-slate-900">{{ props.trainerSelectedChildName }}</div>
            </div>
            <div class="rounded-xl border border-white/70 bg-white/90 px-4 py-4 text-sm text-slate-700">
              <div class="text-xs uppercase tracking-[0.16em] text-slate-400">当前闭环</div>
              <div class="mt-2 text-lg font-semibold text-slate-900">{{ props.trainerFormalTaskStageLabel }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ props.activeFormalTask?.title || '等待第一轮任务' }}</div>
            </div>
          </div>

          <div class="mt-5 rounded-2xl border border-cyan-200 bg-white/90 px-4 py-4">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="text-sm font-semibold text-slate-900">本轮带教闭环</div>
                <div class="mt-1 text-sm text-slate-500">把这一轮带教压成三步，避免在多个动作之间来回跳。</div>
              </div>
              <span class="rounded-full bg-cyan-100 px-2.5 py-1 text-[11px] font-medium text-cyan-800">
                {{ props.trainerFormalTaskStageLabel }}
              </span>
            </div>
            <div class="mt-4 grid gap-3 md:grid-cols-3">
              <div
                v-for="step in props.trainerFormalTaskSteps"
                :key="`trainer-step-${step.key}`"
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
            <div class="mt-4 rounded-xl border border-cyan-100 bg-cyan-50 px-4 py-4 text-sm text-cyan-950">
              <div class="font-medium">当前动作提示</div>
              <div class="mt-2 leading-6">{{ props.trainerFormalTaskGuidance }}</div>
            </div>
          </div>
        </div>

        <div v-if="!props.hideModeSwitcher" class="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
          <WorkspaceSubNav
            orientation="horizontal"
            :items="mainlineSubNavItems"
            @select="(key) => props.setTrainerMainlineMode(key, { replace: false })"
          />
          <div class="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
            <div class="font-medium text-slate-900">{{ props.trainerMainlineModeMeta.title }}</div>
            <div class="mt-2 leading-6">{{ props.trainerMainlineModeMeta.description }}</div>
          </div>
        </div>

        <section class="min-w-0 rounded-2xl border border-slate-200 bg-slate-50/70">
          <div v-if="!props.compact" class="border-b border-slate-200 px-4 py-3 lg:px-5">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div class="text-sm font-semibold text-slate-900">当前带教工作区</div>
                <div class="mt-1 text-xs text-slate-500">围绕当前对象推进当轮闭环。</div>
              </div>
              <div class="rounded-full bg-white px-3 py-1 text-[11px] text-slate-600">主工作区</div>
            </div>
          </div>
          <div class="min-w-0 px-3 py-4 lg:px-5 lg:py-5">
            <slot />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, type PropType } from 'vue'
import WorkspaceSubNav from './shell/WorkspaceSubNav.vue'
import type { WorkspaceSubNavItem } from './shell/WorkspaceSubNav.vue'

type TrainerMeta = { title: string, description?: string }
type TrainerStep = { key: string, title: string, summary?: string, badge?: string, badgeClass?: string, tone?: string }
type TrainerCard = { key: string, title: string, description?: string, badge?: string, badgeClass?: string, active?: boolean, activeClass?: string, idleClass?: string }

const props = defineProps({
  autonomyIdentityMessage: { type: String, default: '' },
  autonomyIdentitySuccess: { type: Boolean, default: false },
  autonomyLoading: { type: Boolean, default: false },
  autonomyIdentitySaving: { type: Boolean, default: false },
  managedChildMembersDraft: { type: Array as PropType<any[]>, default: () => [] },
  selectedChildMemberId: { type: String, default: '' },
  trainerMemberDraft: { type: Object as PropType<any | null>, default: null },
  trainerMainlineModeMeta: { type: Object as PropType<TrainerMeta>, required: true },
  trainerSelectedChildName: { type: String, default: '--' },
  trainerSelectedChildMeta: { type: String, default: '--' },
  trainerFormalTaskStageLabel: { type: String, default: '--' },
  trainerFormalTaskGuidance: { type: String, default: '--' },
  trainerFormalTaskSteps: { type: Array as PropType<TrainerStep[]>, default: () => [] },
  trainerMainlineCards: { type: Array as PropType<TrainerCard[]>, default: () => [] },
  activeFormalTask: { type: Object as PropType<any | null>, default: null },
  currentChildWorkspaceRoute: { type: String, default: '' },
  formatLifecycleStage: { type: Function as PropType<(value?: string) => string>, required: true },
  selectChildMember: { type: Function as PropType<(memberId: string) => void>, required: true },
  createChildPortrait: { type: Function as PropType<() => void>, required: true },
  loadAutonomyStatus: { type: Function as PropType<() => void>, required: true },
  saveAutonomyIdentity: { type: Function as PropType<() => void>, required: true },
  setTrainerMainlineMode: { type: Function as PropType<(key: any, options?: { replace?: boolean }) => void>, required: true },
  compact: { type: Boolean, default: false },
  hideModeSwitcher: { type: Boolean, default: false },
})

const mainlineSubNavItems = computed<WorkspaceSubNavItem[]>(() => (
  props.trainerMainlineCards.map((item) => ({
    key: item.key,
    title: item.title.replace(/^\d+\.\s*/, ''),
    badge: item.badge,
    badgeClass: item.badgeClass,
    active: item.active,
  }))
))
</script>
