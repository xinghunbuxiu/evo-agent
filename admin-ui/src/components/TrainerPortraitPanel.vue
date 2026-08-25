<template>
  <div>
    <div id="portrait-zone" class="scroll-mt-24 mb-4 rounded-2xl border border-emerald-200 bg-emerald-50/50 px-4 py-4">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-sm font-semibold text-emerald-950">画像建档工作面</div>
          <div class="mt-1 text-xs text-emerald-700">这里先完成建档、岗位确认、人格画像和成长起点，确保新子女不是裸奔进入任务面。</div>
        </div>
        <div class="rounded-full bg-white px-3 py-1 text-[11px] text-emerald-700">
          {{ portraitWorkspaceMode === 'members' ? '成员视图' : portraitWorkspaceMode === 'identity' ? '画像编辑' : portraitWorkspaceMode === 'state' ? '状态视图' : '总览视图' }}
        </div>
      </div>
      <div class="mt-4 grid gap-3 md:grid-cols-3">
        <div class="rounded-xl border border-emerald-200 bg-white/90 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前对象</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedChildMemberDraft?.name || newChildPortraitName || '新子女画像' }}</div>
        </div>
        <div class="rounded-xl border border-emerald-200 bg-white/90 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前岗位</div>
          <div class="mt-2 font-medium text-slate-900">{{ selectedChildMemberDraft?.primary_role || childPrimaryRole || 'pending_role' }}</div>
        </div>
        <div class="rounded-xl border border-emerald-200 bg-white/90 px-4 py-3 text-sm text-slate-700">
          <div class="text-slate-400">当前重点</div>
          <div class="mt-2 font-medium text-slate-900">{{ childDerivedState?.next_action || selectedChildMemberDraft?.training_plan?.next_action || '先建立画像并确认成长起点' }}</div>
        </div>
      </div>
    </div>

    <div class="mb-4 rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          @click="setPortraitWorkspaceMode('summary')"
          class="rounded-full px-3 py-1.5 text-xs font-medium"
          :class="portraitWorkspaceMode === 'summary' ? 'bg-emerald-600 text-white' : 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200'"
        >
          总览
        </button>
        <button
          type="button"
          @click="setPortraitWorkspaceMode('members')"
          class="rounded-full px-3 py-1.5 text-xs font-medium"
          :class="portraitWorkspaceMode === 'members' ? 'bg-amber-600 text-white' : 'bg-amber-100 text-amber-800 hover:bg-amber-200'"
        >
          成员
        </button>
        <button
          type="button"
          @click="setPortraitWorkspaceMode('identity')"
          class="rounded-full px-3 py-1.5 text-xs font-medium"
          :class="portraitWorkspaceMode === 'identity' ? 'bg-violet-600 text-white' : 'bg-violet-100 text-violet-800 hover:bg-violet-200'"
        >
          画像编辑
        </button>
        <button
          type="button"
          @click="setPortraitWorkspaceMode('state')"
          class="rounded-full px-3 py-1.5 text-xs font-medium"
          :class="portraitWorkspaceMode === 'state' ? 'bg-sky-600 text-white' : 'bg-sky-100 text-sky-800 hover:bg-sky-200'"
        >
          状态
        </button>
      </div>
      <div class="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
        <div class="font-medium text-slate-900">{{ portraitWorkspaceMeta.title }}</div>
        <div class="mt-2 leading-6">{{ portraitWorkspaceMeta.description }}</div>
      </div>
    </div>

    <div
      class="min-w-0"
      :class="portraitWorkspaceMode === 'identity' ? 'grid gap-6 xl:grid-cols-2' : 'space-y-4'"
    >
      <div v-if="portraitWorkspaceMode === 'identity'" class="min-w-0 rounded-2xl border border-amber-200 bg-amber-50/70 p-5">
        <div class="text-sm font-semibold text-amber-950">父节点画像</div>
        <div class="mt-1 text-xs text-amber-700">这里只保留父节点对新子女的命名、角色和边界说明，不和当前子女建档混在一起。</div>
        <div class="mt-4 grid gap-3">
          <div>
            <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-amber-700">称呼</label>
            <input :value="parentDisplayName" type="text" class="w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="父节点" @input="emit('update:parentDisplayName', ($event.target as HTMLInputElement).value)">
          </div>
          <div>
            <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-amber-700">身份</label>
            <input :value="parentRoleLabel" type="text" class="w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="父节点" @input="emit('update:parentRoleLabel', ($event.target as HTMLInputElement).value)">
          </div>
          <div>
            <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-amber-700">说明</label>
            <textarea :value="parentDescription" rows="4" class="w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="负责提供方向、资源与边界，陪伴岗位成员成长" @input="emit('update:parentDescription', ($event.target as HTMLTextAreaElement).value)"></textarea>
          </div>
        </div>
      </div>

      <div
        v-if="portraitWorkspaceMode === 'summary' || portraitWorkspaceMode === 'members' || portraitWorkspaceMode === 'identity' || portraitWorkspaceMode === 'state'"
        class="min-w-0 rounded-2xl border border-emerald-200 bg-emerald-50/70 p-5"
      >
        <div v-show="portraitWorkspaceMode === 'summary'" class="rounded-xl border border-emerald-200 bg-white/70 p-4">
          <div class="text-sm font-semibold text-emerald-950">创建新员工</div>
          <div class="mt-1 text-xs text-emerald-700">必须选择已登记的岗位工种，创建后在此完成画像并派首个正式任务。</div>
          <div class="mt-1 text-xs text-emerald-600">当前归属空间 {{ tenantId || 'default' }}。这个子女只属于当前空间。</div>
          <div class="mt-3 grid gap-3 md:grid-cols-2">
            <div>
              <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-emerald-700">岗位工种</label>
              <select
                v-if="companyWorkTypes.length"
                :value="newChildPortraitWorkTypeId"
                required
                class="w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm text-slate-700"
                @change="onNewPortraitWorkTypeChange"
              >
                <option value="" disabled>请选择岗位工种</option>
                <option
                  v-for="item in companyWorkTypes"
                  :key="item.work_type_id"
                  :value="item.work_type_id"
                >
                  {{ item.title || item.work_type_id }}
                </option>
              </select>
              <div v-else class="rounded-lg border border-dashed border-emerald-200 bg-white px-3 py-3 text-xs text-emerald-800">
                <p>{{ companyWorkTypesLoading ? '工种列表加载中...' : '还没有岗位工种。' }}</p>
                <router-link to="/organization/parent/workspace?section=worktypes" class="mt-2 inline-block font-medium text-emerald-700 underline">
                  去公司设置添加工种 →
                </router-link>
              </div>
            </div>
            <div>
              <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-emerald-700">子女称呼</label>
              <input
                :value="newChildPortraitName"
                type="text"
                class="w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm text-slate-700"
                placeholder="小B"
                @input="emit('update:newChildPortraitName', ($event.target as HTMLInputElement).value)"
              >
            </div>
          </div>
        </div>
        <div
          class="mt-4"
          :class="portraitWorkspaceMode === 'summary' ? 'grid min-w-0 gap-5 xl:grid-cols-2' : 'space-y-4'"
        >
          <div v-if="portraitWorkspaceMode === 'summary' || portraitWorkspaceMode === 'members'" class="min-w-0 space-y-4">
            <div class="flex items-center justify-between gap-3">
              <div class="text-sm font-semibold text-emerald-950">当前编制</div>
              <div class="rounded-full bg-white px-3 py-1 text-[11px] text-emerald-700">tenant {{ tenantId || 'default' }}</div>
            </div>
            <div v-if="childMembersDraft.length" class="mt-4 space-y-3">
              <button
                v-for="member in childMembersDraft"
                :key="member.member_id"
                @click="selectChildMember(member.member_id)"
                class="w-full rounded-2xl border px-4 py-4 text-left transition"
                :class="selectedChildMemberId === member.member_id ? 'border-emerald-300 bg-emerald-50 shadow-sm' : (member.status === 'archived' ? 'border-slate-300 bg-slate-100 text-slate-500' : 'border-emerald-200 bg-white hover:bg-emerald-50/60')"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <div class="font-medium text-slate-900">{{ member.name || member.member_id }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ member.primary_role || '--' }}<span v-if="member.system_managed"> · 系统</span><span v-if="member.status === 'archived'"> · 已归档</span></div>
                  </div>
                  <span class="rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-600">
                    {{ formatLifecycleStage(member.training_plan?.stage || member.onboarding?.status) }}
                  </span>
                </div>
                <div class="mt-3 rounded-xl bg-white/80 px-3 py-3 text-xs text-slate-700">
                  <div class="text-slate-400">当前重点</div>
                  <div class="mt-1 font-medium text-slate-900">{{ member.growth_state?.current_focus || member.training_plan?.next_action || '--' }}</div>
                </div>
              </button>
            </div>
            <div class="mt-3 flex flex-wrap gap-3">
              <button
                @click="archiveSelectedChildMember"
                :disabled="!selectedChildMemberId || !!selectedChildMemberDraft?.system_managed"
                class="rounded-lg border border-amber-300 px-3 py-2 text-sm text-amber-700 hover:bg-amber-50 disabled:opacity-60"
              >
                归档当前子女
              </button>
              <button
                @click="deleteSelectedChildMember"
                :disabled="activeChildMembersDraft.length <= 1 || !selectedChildMemberId || !!selectedChildMemberDraft?.system_managed"
                class="rounded-lg border border-rose-300 px-3 py-2 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-60"
              >
                删除当前子女
              </button>
            </div>
            <div class="mt-4 rounded-xl border border-emerald-200 bg-white/80 p-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-sm font-semibold text-emerald-950">带教成长摘要</div>
                  <div class="mt-1 text-xs text-emerald-700">把每个子女最近的岗位复盘、育成官点评、阶段和下一步收束成一眼能读懂的状态卡。</div>
                </div>
                <div class="text-xs text-emerald-700">active {{ childGrowthDigestCards.length }}</div>
              </div>
              <div v-if="childGrowthNarrative" class="mt-4 rounded-xl border border-sky-200 bg-sky-50/70 p-4">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <div class="text-sm font-semibold text-sky-950">育成官今日播报</div>
                    <div class="mt-1 text-xs text-sky-700">系统把今天最关键的成长情况压成一段播报，方便你先读结论再决定介入谁。</div>
                  </div>
                  <div class="text-xs text-sky-700">{{ childGrowthNarrative.updated_label }}</div>
                </div>
                <div class="mt-3 rounded-lg border border-sky-200 bg-white px-4 py-4 text-sm leading-7 text-slate-700">
                  {{ childGrowthNarrative.summary }}
                </div>
                <div v-if="childGrowthNarrative.highlights.length" class="mt-3 grid gap-2">
                  <div
                    v-for="item in childGrowthNarrative.highlights"
                    :key="`broadcast-${item}`"
                    class="rounded-lg border border-sky-100 bg-white/80 px-3 py-3 text-xs text-sky-900"
                  >
                    {{ item }}
                  </div>
                </div>
              </div>
              <div v-if="childGrowthPriorityQueue.length" class="mt-4 rounded-xl border border-amber-200 bg-amber-50/70 p-4">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <div class="text-sm font-semibold text-amber-950">优先介入列表</div>
                    <div class="mt-1 text-xs text-amber-700">系统根据阻塞、阶段成熟度、复盘缺口和带教缺口，自动给出当前最值得先带教的子女。</div>
                  </div>
                  <div class="text-xs text-amber-700">top {{ childGrowthPriorityQueue.length }}</div>
                </div>
                <div class="mt-3 grid gap-3">
                  <button
                    v-for="item in childGrowthPriorityQueue"
                    :key="`priority-${item.member_id}`"
                    type="button"
                    @click="selectChildMember(item.member_id)"
                    class="w-full rounded-lg border border-amber-200 bg-white px-4 py-4 text-left hover:bg-amber-50/50"
                  >
                    <div class="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div class="font-medium text-slate-900">{{ item.name || item.member_id }}</div>
                        <div class="mt-1 text-xs text-slate-500">{{ item.primary_role || '--' }} / {{ item.training_stage || '--' }}</div>
                      </div>
                      <div class="flex items-center gap-2 text-[11px]">
                        <span class="rounded-full bg-amber-100 px-2.5 py-1 font-medium text-amber-800">P{{ item.priority_score }}</span>
                        <span class="rounded-full px-2.5 py-1 font-medium" :class="growthDigestStatusBadgeClass(item.derived_status)">
                          {{ formatDerivedStatus(item.derived_status) }}
                        </span>
                      </div>
                    </div>
                    <div class="mt-3 text-xs text-slate-700">系统判断：{{ item.priority_summary }}</div>
                    <div class="mt-2 flex flex-wrap gap-2">
                      <span
                        v-for="reason in item.priority_reasons"
                        :key="`${item.member_id}-${reason}`"
                        class="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] text-amber-800"
                      >
                        {{ reason }}
                      </span>
                    </div>
                    <div class="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
                      <div class="text-slate-500">建议你现在看这个点</div>
                      <div class="mt-2 font-medium text-slate-900">{{ item.next_action || item.current_focus || '--' }}</div>
                    </div>
                  </button>
                </div>
              </div>
              <div v-if="!childGrowthDigestCards.length" class="mt-3 rounded-lg border border-dashed border-emerald-200 bg-emerald-50/60 px-3 py-4 text-xs text-emerald-700">
                还没有可展示的子女成长摘要，先建立画像并保存身份设定。
              </div>
              <div v-else class="mt-4 grid gap-3">
                <button
                  v-for="card in childGrowthDigestCards"
                  :key="`growth-digest-${card.member_id}`"
                  type="button"
                  @click="selectChildMember(card.member_id)"
                  class="w-full rounded-xl border px-4 py-4 text-left transition"
                  :class="selectedChildMemberId === card.member_id ? 'border-emerald-400 bg-emerald-50 shadow-sm' : 'border-slate-200 bg-white hover:border-emerald-300 hover:bg-emerald-50/40'"
                >
                  <div class="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div class="font-medium text-slate-900">{{ card.name || card.member_id }}</div>
                      <div class="mt-1 text-xs text-slate-500">{{ card.primary_role || '--' }}</div>
                    </div>
                    <div class="flex flex-wrap items-center justify-end gap-2 text-[11px]">
                      <span class="rounded-full px-2.5 py-1 font-medium" :class="growthDigestStatusBadgeClass(card.derived_status)">
                        {{ formatDerivedStatus(card.derived_status) }}
                      </span>
                      <span class="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600">
                        {{ card.training_stage || '--' }}
                      </span>
                    </div>
                  </div>
                  <div class="mt-3 grid gap-3 md:grid-cols-2">
                    <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
                      <div class="text-slate-500">当前专注</div>
                      <div class="mt-2 font-medium text-slate-900">{{ card.current_focus || '--' }}</div>
                    </div>
                    <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
                      <div class="text-slate-500">下一步</div>
                      <div class="mt-2 font-medium text-slate-900">{{ card.next_action || '--' }}</div>
                    </div>
                  </div>
                  <div v-if="card.blocked_reason" class="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-3 text-xs text-rose-700">
                    阻塞原因：{{ card.blocked_reason }}
                  </div>
                  <div class="mt-3 grid gap-3 md:grid-cols-2">
                    <div class="rounded-lg border border-emerald-200 bg-emerald-50/70 px-3 py-3 text-xs text-emerald-950">
                      <div class="font-medium">子女岗位复盘</div>
                      <div class="mt-2 leading-5">{{ card.reflection_summary || '还没有形成岗位复盘。' }}</div>
                      <div v-if="card.next_experiment" class="mt-2 text-emerald-700">下一实验：{{ card.next_experiment }}</div>
                    </div>
                    <div class="rounded-lg border border-violet-200 bg-violet-50/70 px-3 py-3 text-xs text-violet-950">
                      <div class="font-medium">育成官点评</div>
                      <div class="mt-2 leading-5">{{ card.trainer_comment || '育成官暂时还没有新的点评。' }}</div>
                      <div v-if="card.mission_status || card.training_stage_from || card.training_stage_to" class="mt-2 text-violet-700">
                        <span v-if="card.training_stage_from || card.training_stage_to">
                          阶段 {{ formatLifecycleStage(card.training_stage_from, '--') }} -> {{ formatLifecycleStage(card.training_stage_to, '--') }}
                        </span>
                        <span v-if="card.mission_status">
                          / 任务 {{ formatJobStatus(card.mission_status) }}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div class="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                    <span class="rounded-full bg-slate-100 px-2.5 py-1">策略 {{ card.learning_strategy || '--' }}</span>
                    <span class="rounded-full bg-slate-100 px-2.5 py-1">更新于 {{ formatDate(card.latest_activity_at) }}</span>
                  </div>
                </button>
              </div>
            </div>
          </div>
          <div
            v-if="portraitWorkspaceMode === 'summary' || portraitWorkspaceMode === 'identity' || portraitWorkspaceMode === 'state'"
            class="min-w-0 space-y-4"
          >
            <div class="rounded-xl border border-emerald-200 bg-white/90 p-4">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div class="text-sm font-semibold text-emerald-950">当前建档对象</div>
                  <div class="mt-1 text-xs text-emerald-700">右侧只处理当前选中的孩子，集中完成身份、岗位和成长方向设定。</div>
                </div>
                <div class="rounded-full bg-emerald-100 px-3 py-1 text-[11px] text-emerald-800">
                  {{ formatLifecycleStage(selectedChildMemberDraft?.training_plan?.stage || selectedChildMemberDraft?.onboarding?.status, '草稿中') }}
                </div>
                <button
                  v-if="canGoToDispatchForSelectedChild"
                  type="button"
                  @click="goToDispatchForSelectedChild"
                  class="rounded-lg bg-amber-600 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-amber-700"
                >
                  去派任务
                </button>
              </div>
              <div class="mt-4 grid gap-3 md:grid-cols-3">
                <div class="rounded-xl bg-emerald-50/70 px-4 py-3 text-sm text-slate-700">
                  <div class="text-slate-400">名称</div>
                  <div class="mt-2 font-medium text-slate-900">{{ childName || selectedChildMemberDraft?.name || '未命名子女' }}</div>
                </div>
                <div class="rounded-xl bg-emerald-50/70 px-4 py-3 text-sm text-slate-700">
                  <div class="text-slate-400">岗位</div>
                  <div class="mt-2 font-medium text-slate-900">{{ childPrimaryRole || selectedChildMemberDraft?.primary_role || 'pending_role' }}</div>
                </div>
                <div class="rounded-xl bg-emerald-50/70 px-4 py-3 text-sm text-slate-700">
                  <div class="text-slate-400">当前重点</div>
                  <div class="mt-2 font-medium text-slate-900">{{ childCurrentFocus || selectedChildMemberDraft?.growth_state?.current_focus || '先完成画像并确认起点' }}</div>
                </div>
              </div>
            </div>

            <div v-show="portraitWorkspaceMode === 'summary' || portraitWorkspaceMode === 'identity'" class="rounded-xl border border-emerald-200 bg-white/80 p-4">
              <div class="text-sm font-semibold text-emerald-950">身份设定</div>
              <div class="mt-1 text-xs text-emerald-700">先把这位员工是谁、叫什么、将以什么岗位身份成长，表达清楚。</div>
              <div class="mt-4 grid gap-3">
                <div>
                  <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-emerald-700">内部编号</label>
                  <input :value="childMemberId" type="text" class="w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="employee_xiaob" @input="emit('update:childMemberId', ($event.target as HTMLInputElement).value)">
                </div>
                <div>
                  <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-emerald-700">对外名称</label>
                  <input :value="childName" type="text" class="w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="小B" @input="emit('update:childName', ($event.target as HTMLInputElement).value)">
                </div>
                <div>
                  <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-emerald-700">岗位工种</label>
                  <select
                    v-if="companyWorkTypes.length"
                    :value="childPrimaryRole"
                    class="w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm text-slate-700"
                    @change="onEditPortraitWorkTypeChange"
                  >
                    <option value="" disabled>请选择工种</option>
                    <option
                      v-for="item in companyWorkTypes"
                      :key="`edit-${item.work_type_id}`"
                      :value="item.work_type_id"
                    >
                      {{ item.title || item.work_type_id }}
                    </option>
                  </select>
                  <div v-else class="rounded-lg border border-dashed border-emerald-200 bg-white px-3 py-2 text-xs text-emerald-800">
                    请先在<router-link to="/organization/parent/workspace?section=worktypes" class="underline">公司设置</router-link>添加工种
                  </div>
                  <div class="mt-1 text-xs text-emerald-700">从公司已添加工种中选择；对应 job_id 用于任务路由。</div>
                </div>
                <div>
                  <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-emerald-700">岗位称呼</label>
                  <input :value="childRoleLabel" type="text" class="w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="待育成员工" @input="emit('update:childRoleLabel', ($event.target as HTMLInputElement).value)">
                </div>
                <div>
                  <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-emerald-700">自我介绍</label>
                  <textarea :value="childSelfDescription" rows="4" class="w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="我是正在成长中的岗位成员..." @input="emit('update:childSelfDescription', ($event.target as HTMLTextAreaElement).value)"></textarea>
                </div>
                <div>
                  <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-emerald-700">长期目标</label>
                  <textarea :value="childLongTermGoal" rows="3" class="w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="持续成长为能独立理解目标、执行任务、复盘经验的岗位执行者" @input="emit('update:childLongTermGoal', ($event.target as HTMLTextAreaElement).value)"></textarea>
                </div>
              </div>
            </div>

            <details v-show="portraitWorkspaceMode === 'summary' || portraitWorkspaceMode === 'identity'" class="rounded-xl border border-slate-200 bg-white/80" :open="portraitWorkspaceMode === 'identity'">
              <summary class="cursor-pointer list-none px-4 py-4">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div class="text-sm font-semibold text-slate-900">表达与互动方式</div>
                    <div class="mt-1 text-xs text-slate-500">这些设置决定这位员工以后怎么说话、怎么和外界交流。</div>
                  </div>
                  <div class="rounded-full bg-slate-100 px-3 py-1 text-[11px] text-slate-600">
                    可选展开
                  </div>
                </div>
              </summary>
              <div class="border-t border-slate-200 px-4 py-4">
                <div class="grid gap-3 md:grid-cols-2">
                  <div>
                    <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-slate-500">说话风格</label>
                    <input :value="childSpeakingStyle" type="text" class="w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="clear_supportive" @input="emit('update:childSpeakingStyle', ($event.target as HTMLInputElement).value)">
                  </div>
                  <div>
                    <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-slate-500">互动方式</label>
                    <input :value="childInteractionStyle" type="text" class="w-full rounded-lg border border-emerald-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="friendly_observant" @input="emit('update:childInteractionStyle', ($event.target as HTMLInputElement).value)">
                  </div>
                </div>
              </div>
            </details>

            <div v-show="portraitWorkspaceMode === 'summary' || portraitWorkspaceMode === 'identity'" class="rounded-xl border border-slate-200 bg-white/80 p-4">
              <div class="text-sm font-semibold text-slate-900">能力与成长方向</div>
              <div class="mt-1 text-xs text-slate-500">先确认当下最关键的成长方向，更多细项按需补充。</div>
              <div class="mt-4 grid gap-3 md:grid-cols-2">
                <div>
                  <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-slate-500">当前专注</label>
                  <input :value="childCurrentFocus" type="text" class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="pending_role" @input="emit('update:childCurrentFocus', ($event.target as HTMLInputElement).value)">
                </div>
                <div>
                  <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-slate-500">下一目标</label>
                  <input :value="childNextGoal" type="text" class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="跑通真实案例并形成可复用经验" @input="emit('update:childNextGoal', ($event.target as HTMLInputElement).value)">
                </div>
              </div>
              <details class="mt-4 rounded-xl border border-slate-200 bg-slate-50/70" :open="portraitWorkspaceMode === 'identity'">
                <summary class="cursor-pointer list-none px-4 py-3">
                  <div class="flex flex-wrap items-center justify-between gap-3">
                    <div class="text-sm font-medium text-slate-900">更多成长细项</div>
                    <div class="rounded-full bg-white px-3 py-1 text-[11px] text-slate-600">按需展开</div>
                  </div>
                </summary>
                <div class="border-t border-slate-200 px-4 py-4">
                  <div class="grid gap-3 md:grid-cols-2">
                    <div>
                      <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-slate-500">当前优势</label>
                      <input :value="childStrengthsText" type="text" class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="自主研究, 智能分析, 复盘成长" @input="emit('update:childStrengthsText', ($event.target as HTMLInputElement).value)">
                    </div>
                    <div>
                      <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-slate-500">当前短板</label>
                      <input :value="childShortcomingsText" type="text" class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="真实经验不足, 需要更多案例训练" @input="emit('update:childShortcomingsText', ($event.target as HTMLInputElement).value)">
                    </div>
                    <div>
                      <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-slate-500">适合方向</label>
                      <input :value="childPreferredDomainsText" type="text" class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="pending_role" @input="emit('update:childPreferredDomainsText', ($event.target as HTMLInputElement).value)">
                    </div>
                    <div class="md:col-span-2">
                      <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-slate-500">成长策略</label>
                      <input :value="childLearningStrategy" type="text" class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700" placeholder="case_first_iterative_growth" @input="emit('update:childLearningStrategy', ($event.target as HTMLInputElement).value)">
                    </div>
                  </div>
                </div>
              </details>
            </div>

            <div v-show="portraitWorkspaceMode === 'summary' || portraitWorkspaceMode === 'state'" class="rounded-xl border border-emerald-200 bg-white/80 p-4">
              <div class="text-sm font-semibold text-emerald-950">当前状态</div>
              <div class="mt-4 grid gap-3 md:grid-cols-3">
                <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                  <div class="text-xs uppercase tracking-[0.16em] text-slate-400">当前状态</div>
                  <div class="mt-2 font-medium text-slate-900">{{ formatDerivedStatus(childDerivedState?.status || autonomyStatus?.child_agent?.growth_state?.phase) }}</div>
                </div>
                <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                  <div class="text-xs uppercase tracking-[0.16em] text-slate-400">阻塞原因</div>
                  <div class="mt-2 font-medium text-slate-900">{{ childDerivedState?.blocked_reason || autonomyStatus?.child_agent?.growth_state?.blocked_reason || '无' }}</div>
                </div>
                <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                  <div class="text-xs uppercase tracking-[0.16em] text-slate-400">下一动作</div>
                  <div class="mt-2 font-medium text-slate-900">{{ childDerivedState?.next_action || '--' }}</div>
                </div>
              </div>
            </div>

            <details v-if="childAutonomousPlan && (portraitWorkspaceMode === 'summary' || portraitWorkspaceMode === 'state')" class="mt-4 rounded-xl border border-emerald-200 bg-emerald-50/60 text-sm text-emerald-950">
              <summary class="cursor-pointer list-none px-4 py-4">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div class="font-medium">子女自主计划</div>
                    <div class="mt-1 text-xs text-emerald-700">这块不代表父节点替它决定，而是展示它此刻正在自己理解、推进和准备复盘的主线。</div>
                  </div>
                  <div class="rounded-full bg-white px-3 py-1 text-[11px] text-emerald-700">按需展开</div>
                </div>
              </summary>
              <div class="border-t border-emerald-200 px-4 py-4">
                <div class="grid gap-3 md:grid-cols-2">
                  <div class="rounded-lg border border-emerald-100 bg-white px-3 py-3">
                    <div class="text-xs uppercase tracking-[0.16em] text-emerald-700">当前目标</div>
                    <div class="mt-2 leading-6 text-slate-800">{{ childAutonomousPlan.objective }}</div>
                  </div>
                  <div class="rounded-lg border border-emerald-100 bg-white px-3 py-3">
                    <div class="text-xs uppercase tracking-[0.16em] text-emerald-700">为什么现在做</div>
                    <div class="mt-2 leading-6 text-slate-800">{{ childAutonomousPlan.why_now }}</div>
                  </div>
                </div>
                <div class="mt-3 grid gap-3 md:grid-cols-2">
                  <div class="rounded-lg border border-emerald-100 bg-white px-3 py-3">
                    <div class="text-xs uppercase tracking-[0.16em] text-emerald-700">下一步计划</div>
                    <div v-if="childAutonomousPlan.steps.length" class="mt-2 space-y-2 text-slate-800">
                      <div v-for="(step, index) in childAutonomousPlan.steps" :key="`child-plan-step-${index}`" class="leading-6">
                        {{ index + 1 }}. {{ step }}
                      </div>
                    </div>
                    <div v-else class="mt-2 text-slate-500">暂无</div>
                  </div>
                  <div class="rounded-lg border border-emerald-100 bg-white px-3 py-3">
                    <div class="text-xs uppercase tracking-[0.16em] text-emerald-700">证据与重排条件</div>
                    <div class="mt-2 leading-6 text-slate-800">{{ childAutonomousPlan.evidence }}</div>
                    <div class="mt-2 leading-6 text-amber-800">replan {{ childAutonomousPlan.replan_trigger }}</div>
                  </div>
                </div>
              </div>
            </details>

            <div v-if="selectedChildMemberDraft?.onboarding && (portraitWorkspaceMode === 'summary' || portraitWorkspaceMode === 'state')" class="mt-4 rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-4 text-sm text-emerald-950">
              <div class="font-medium">画像与培训接管记录</div>
              <div class="mt-2 text-xs text-emerald-800">所属空间 {{ autonomyStatus?.tenant_id || tenantId || 'default' }}</div>
              <div v-if="selectedChildLifecycleSummary" class="mt-2 rounded-lg border border-emerald-100 bg-white/80 px-3 py-3 text-xs text-emerald-900">
                <div class="font-medium">生命周期</div>
                <div class="mt-2">{{ selectedChildLifecycleSummary.label }}</div>
                <div class="mt-1 leading-5 text-emerald-800">{{ selectedChildLifecycleSummary.description }}</div>
              </div>
              <div class="mt-2 text-xs text-emerald-800">建档来源 {{ selectedChildMemberDraft.onboarding.created_by_member_id || '--' }}</div>
              <div class="mt-1 text-xs text-emerald-800">当前带教人 {{ selectedChildMemberDraft.onboarding.training_owner_member_id || '--' }}</div>
              <div class="mt-1 text-xs text-emerald-800">状态 {{ formatLifecycleStage(selectedChildMemberDraft.onboarding.status) }}</div>
              <div class="mt-1 text-xs text-emerald-800">建档时间 {{ formatDate(selectedChildMemberDraft.onboarding.created_at) }}</div>
              <div v-if="selectedChildMemberDraft?.current_jobs?.[0]" class="mt-2 rounded-lg border border-emerald-100 bg-white/80 px-3 py-3 text-xs text-emerald-900">
                <div class="font-medium">岗位绑定上下文</div>
                <div class="mt-2">岗位任务 {{ selectedChildMemberDraft.current_jobs[0].job_id || '--' }}</div>
                <div class="mt-1">account {{ selectedChildMemberDraft.current_jobs[0].account_id || '--' }}</div>
                <div class="mt-1">状态 {{ formatJobStatus(selectedChildMemberDraft.current_jobs[0].status) }}</div>
                <div v-if="selectedChildMemberDraft.current_jobs[0].notes" class="mt-1 break-all">{{ selectedChildMemberDraft.current_jobs[0].notes }}</div>
              </div>
              <div class="mt-2 text-xs text-emerald-800">{{ selectedChildMemberDraft.onboarding.notes || '无' }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { resolveMemberWorkTypeId } from '../utils/formalTaskRecommendation'

type GenericRecord = Record<string, any>

const props = defineProps<{
  tenantId: string
  parentDisplayName: string
  parentRoleLabel: string
  parentDescription: string
  newChildPortraitName: string
  newChildPortraitWorkTypeId: string
  companyWorkTypes: GenericRecord[]
  companyWorkTypesLoading: boolean
  childMembersDraft: GenericRecord[]
  selectedChildMemberId: string
  selectedChildMemberDraft: GenericRecord | null
  activeChildMembersDraft: GenericRecord[]
  childGrowthDigestCards: GenericRecord[]
  childGrowthNarrative: GenericRecord | null
  childGrowthPriorityQueue: GenericRecord[]
  childMemberId: string
  childName: string
  childPrimaryRole: string
  childRoleLabel: string
  childSelfDescription: string
  childLongTermGoal: string
  childSpeakingStyle: string
  childInteractionStyle: string
  childStrengthsText: string
  childShortcomingsText: string
  childPreferredDomainsText: string
  childCurrentFocus: string
  childNextGoal: string
  childLearningStrategy: string
  childDerivedState: GenericRecord | null
  childAutonomousPlan: GenericRecord | null
  autonomyStatus: GenericRecord | null
  selectedChildLifecycleSummary: GenericRecord | null
  formatDate: (value?: string | null) => string
  selectChildMember: (memberId?: string) => void
  goToDispatchForMember?: (memberId?: string) => void
  archiveSelectedChildMember: () => void
  deleteSelectedChildMember: () => void
  growthDigestStatusBadgeClass: (status?: string | null) => string
  workspaceMode?: 'summary' | 'members' | 'identity' | 'state'
}>()

const portraitWorkspaceMode = ref<'summary' | 'members' | 'identity' | 'state'>('summary')

const canGoToDispatchForSelectedChild = computed(() => {
  const workTypeId = resolveMemberWorkTypeId(props.selectedChildMemberDraft)
  return Boolean(workTypeId && props.selectedChildMemberId)
})

const goToDispatchForSelectedChild = () => {
  if (!canGoToDispatchForSelectedChild.value) return
  props.goToDispatchForMember?.(props.selectedChildMemberId)
}

const isPortraitWorkspaceMode = (value: unknown): value is 'summary' | 'members' | 'identity' | 'state' => (
  value === 'summary' || value === 'members' || value === 'identity' || value === 'state'
)

const setPortraitWorkspaceMode = (value: 'summary' | 'members' | 'identity' | 'state') => {
  if (portraitWorkspaceMode.value === value) return
  portraitWorkspaceMode.value = value
}

const portraitWorkspaceMeta = computed(() => {
  if (portraitWorkspaceMode.value === 'members') {
    return {
      title: '成员与优先级视图',
      description: '这里专门看当前有哪些子女、谁最值得优先介入、每个子女最近的成长摘要和阻塞点。',
    }
  }
  if (portraitWorkspaceMode.value === 'identity') {
    return {
      title: '画像编辑视图',
      description: '这里专门编辑当前选中子女的身份、人格、长期目标、能力和成长方向。',
    }
  }
  if (portraitWorkspaceMode.value === 'state') {
    return {
      title: '状态与接管记录视图',
      description: '这里专门看当前状态、自主计划、生命周期和画像接管记录，不和成员列表混看。',
    }
  }
  return {
    title: '画像总览视图',
    description: '这里把父节点、建立画像、成员摘要和当前子女编辑聚合在一起，适合快速总览当前建档情况。',
  }
})

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

const formatDerivedStatus = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return '--'
  if (normalized === 'idle') return '待启动'
  if (normalized === 'needs_learning') return '待学习'
  if (normalized === 'awaiting_assignment') return '待分配'
  if (normalized === 'training_children') return '带教中'
  if (normalized === 'active_training') return '训练中'
  if (normalized === 'validating') return '验证中'
  if (normalized === 'stable') return '稳定'
  if (normalized === 'delivering') return '交付中'
  if (normalized === 'blocked') return '已阻塞'
  if (normalized === 'failed') return '失败'
  return normalized
}

const formatJobStatus = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return '--'
  if (normalized === 'planned') return '已规划'
  if (normalized === 'waiting_login') return '待登录'
  if (normalized === 'executor_missing') return '缺少执行器'
  if (normalized === 'bootstrapping') return '初始化中'
  if (normalized === 'running') return '运行中'
  if (normalized === 'completed') return '已完成'
  if (normalized === 'failed') return '失败'
  return normalized
}

watch(() => props.selectedChildMemberId, (value) => {
  if (value && portraitWorkspaceMode.value === 'members') {
    setPortraitWorkspaceMode('identity')
  }
})

watch(() => props.workspaceMode, (value) => {
  if (!isPortraitWorkspaceMode(value) || value === portraitWorkspaceMode.value) return
  portraitWorkspaceMode.value = value
}, { immediate: true })

watch(portraitWorkspaceMode, (value) => {
  if (value === props.workspaceMode) return
  emit('update:workspaceMode', value)
})

const emit = defineEmits<{
  'update:parentDisplayName': [value: string]
  'update:parentRoleLabel': [value: string]
  'update:parentDescription': [value: string]
  'update:newChildPortraitName': [value: string]
  'update:newChildPortraitWorkTypeId': [value: string]
  'update:childMemberId': [value: string]
  'update:childName': [value: string]
  'update:childPrimaryRole': [value: string]
  'update:childRoleLabel': [value: string]
  'update:childSelfDescription': [value: string]
  'update:childLongTermGoal': [value: string]
  'update:childSpeakingStyle': [value: string]
  'update:childInteractionStyle': [value: string]
  'update:childStrengthsText': [value: string]
  'update:childShortcomingsText': [value: string]
  'update:childPreferredDomainsText': [value: string]
  'update:childCurrentFocus': [value: string]
  'update:childNextGoal': [value: string]
  'update:childLearningStrategy': [value: string]
  'update:workspaceMode': [value: 'summary' | 'members' | 'identity' | 'state']
  'apply-work-type': [workTypeId: string]
}>()

const onNewPortraitWorkTypeChange = (event: Event) => {
  const value = String((event.target as HTMLSelectElement).value || '').trim()
  emit('update:newChildPortraitWorkTypeId', value)
  if (value) emit('apply-work-type', value)
}

const onEditPortraitWorkTypeChange = (event: Event) => {
  const value = String((event.target as HTMLSelectElement).value || '').trim()
  emit('update:childPrimaryRole', value)
  if (value) emit('apply-work-type', value)
}
</script>
