<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      v-if="companySection === 'overview'"
      eyebrow="公司空间"
      title="公司治理与结构设置"
      description="公司层身份、工种目录与制度边界；员工日常执行在各自工作台完成。"
      :loading="loading"
      refresh-label="刷新公司状态"
      :back-to="{ path: '/dashboard' }"
      @refresh="refresh"
    >
      <template #actions>
        <router-link
          to="/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary"
          class="rounded-lg bg-teal-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-teal-800"
        >
          打开育成师
        </router-link>
      </template>
    </WorkspacePageHeader>

    <WorkspacePageHeader
      v-else
      eyebrow="公司空间"
      :title="companySectionMeta.title"
      :description="companySectionMeta.description"
      :loading="loading"
      refresh-label="刷新"
      :back-to="companyOverviewRoute"
      back-label="返回公司总览"
      @refresh="refreshSection"
    />

    <WorkspaceSubNav
      orientation="horizontal"
      :items="companySubNavItems"
      @select="onCompanySectionSelect"
    />

    <div v-show="companySection === 'overview'" class="grid gap-4 md:grid-cols-3">
      <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">父节点</div>
        <div class="mt-2 text-lg font-semibold text-slate-900">{{ profileName }}</div>
        <div class="mt-1 text-sm text-slate-500">{{ userLabel || '负责公司治理与方向边界' }}</div>
      </div>
      <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">活跃员工</div>
        <div class="mt-2 text-lg font-semibold text-slate-900">{{ activeChildren.length }}</div>
        <div class="mt-1 text-sm text-slate-500">每个孩子一个独立岗位空间</div>
      </div>
      <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">公司结构</div>
        <div class="mt-2 text-lg font-semibold text-slate-900">{{ trainerCount }} 位育成官 / {{ supportNodeCount }} 个职能节点</div>
        <div class="mt-1 text-sm text-slate-500">负责带教、支持和治理的公司层成员</div>
      </div>
    </div>

    <div v-show="companySection === 'overview'" class="rounded-2xl border border-emerald-200 bg-[linear-gradient(135deg,#f0fdf4_0%,#ffffff_55%,#ecfeff_100%)] p-6 shadow-sm">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="inline-flex rounded-full bg-white px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-emerald-700">
            主入口
          </div>
          <h2 class="mt-3 text-2xl font-semibold text-slate-900">新增员工从这里开始</h2>
          <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            如果你现在要新增一个孩子，不需要猜去哪个页面。父节点只负责发起新增，具体建档和画像交给育成官空间完成。
          </p>
        </div>
        <router-link
          to="/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary"
          class="rounded-2xl bg-emerald-600 px-5 py-3 text-sm font-medium text-white shadow-sm hover:bg-emerald-700"
        >
          新增员工
        </router-link>
      </div>
      <div class="mt-5 grid gap-3 md:grid-cols-3">
        <div class="rounded-xl border border-emerald-200 bg-white px-4 py-4 text-sm text-slate-700">
          <div class="font-medium text-slate-900">1. 公司发起</div>
          <div class="mt-2 leading-6">点击“新增员工”，直接进入育成官的建档主线。</div>
        </div>
        <div class="rounded-xl border border-emerald-200 bg-white px-4 py-4 text-sm text-slate-700">
          <div class="font-medium text-slate-900">2. 育成官建档</div>
          <div class="mt-2 leading-6">确认岗位、画像、长期目标和第一轮训练任务。</div>
        </div>
        <div class="rounded-xl border border-emerald-200 bg-white px-4 py-4 text-sm text-slate-700">
          <div class="font-medium text-slate-900">3. 员工开始工作</div>
          <div class="mt-2 leading-6">建档完成后，员工进入自己的岗位空间执行和提交结果。</div>
        </div>
      </div>
    </div>

    <div v-show="companySection === 'structure'" class="grid gap-6 xl:grid-cols-[1.18fr_0.82fr]">
      <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-lg font-semibold text-slate-900">公司结构</div>
            <div class="mt-1 text-sm text-slate-500">这里只放组织入口和当前成员编制，具体工作进入对应节点空间。</div>
          </div>
          <div class="rounded-full bg-slate-100 px-3 py-1 text-[11px] text-slate-600">
            租户 {{ tenantId }}
          </div>
        </div>

        <div class="mt-4 grid gap-4 md:grid-cols-3">
          <router-link to="/organization/parent/workspace" class="rounded-2xl border border-amber-200 bg-amber-50 p-4 hover:bg-amber-100/70">
            <div class="text-sm font-semibold text-amber-950">公司空间</div>
            <div class="mt-2 text-sm leading-6 text-amber-900">查看公司制度、共享策略、能力池和接入边界。</div>
          </router-link>
          <router-link to="/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary" class="rounded-2xl border border-sky-200 bg-sky-50 p-4 hover:bg-sky-100/70">
            <div class="text-sm font-semibold text-sky-950">育成官空间</div>
            <div class="mt-2 text-sm leading-6 text-sky-900">负责画像建立、训练分发、成长观察和任务带教。</div>
          </router-link>
          <router-link to="/organization/child" class="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 hover:bg-emerald-100/70">
            <div class="text-sm font-semibold text-emerald-950">员工工作台</div>
            <div class="mt-2 text-sm leading-6 text-emerald-900">进入每位员工自己的任务、成长、复盘和经验入库空间。</div>
          </router-link>
        </div>

        <div class="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div class="flex items-center justify-between gap-3">
            <div class="text-sm font-semibold text-slate-900">当前员工编制</div>
            <div class="text-xs text-slate-500">{{ activeChildren.length }} 位活跃员工</div>
          </div>
          <div v-if="activeChildren.length" class="mt-4 grid gap-3">
            <router-link
              v-for="member in activeChildren"
              :key="member.id"
              :to="member.link || '/organization/child'"
              class="rounded-xl border border-slate-200 bg-white px-4 py-4 hover:border-emerald-300 hover:bg-emerald-50/40"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="font-medium text-slate-900">{{ member.label }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ member.role || '--' }}</div>
                </div>
                <div class="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600">
                  {{ member.stage || '--' }}
                </div>
              </div>
            <div class="mt-3 text-sm text-slate-600">{{ member.nextAction || member.focus || '等待进入工作台' }}</div>
          </router-link>
          </div>
          <div v-else class="mt-4 rounded-xl border border-dashed border-slate-200 bg-white px-4 py-4 text-sm text-slate-500">
            当前还没有活跃员工。先去画像与育成入口建立第一位员工。
          </div>
        </div>
      </section>

      <section class="space-y-6">
        <div class="rounded-2xl border border-slate-200 bg-[linear-gradient(180deg,#ffffff_0%,#f8fafc_100%)] p-5 shadow-sm">
          <div class="text-sm font-semibold text-slate-900">公司只做三件事</div>
          <div class="mt-4 space-y-3">
            <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4 text-sm leading-6 text-slate-700">定义方向和边界，不代替员工执行具体工作。</div>
            <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4 text-sm leading-6 text-slate-700">统一发起新增入口，再交给育成官完成建档和带教。</div>
            <div class="rounded-2xl border border-slate-200 bg-white px-4 py-4 text-sm leading-6 text-slate-700">先把第一位员工培养成型，再复制到更多岗位。</div>
          </div>
        </div>

        <div class="rounded-2xl border border-amber-200 bg-amber-50/70 p-5 shadow-sm">
          <div class="text-sm font-semibold text-amber-950">阅读顺序</div>
          <div class="mt-2 text-sm leading-6 text-amber-900">
            先看新增入口和公司结构，再往下看制度、能力池和接入边界。这里改成顺序阅读，不再依赖页内跳转。
          </div>
        </div>
      </section>
    </div>

    <div v-show="companySection === 'policies'" class="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
      <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-2">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-lg font-semibold text-slate-900">公司制度层</div>
            <div class="mt-1 text-sm text-slate-500">共享制度和外部学习边界属于父节点，不应该长期挂在育成官主屏。</div>
          </div>
          <button
            @click="loadPolicies"
            :disabled="policyLoading"
            class="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            {{ policyLoading ? '刷新中...' : '刷新制度' }}
          </button>
        </div>

        <div class="mt-5 rounded-2xl border border-violet-200 bg-violet-50/60 p-4">
          <div class="text-sm font-semibold text-violet-950">共享制度</div>
          <div class="mt-1 text-sm text-violet-900">决定经验、技能和策略是只留私有，还是允许审核后共享到平台层。</div>
          <div class="mt-4 grid gap-3 md:grid-cols-3">
            <label class="rounded-xl border border-violet-200 bg-white px-4 py-4">
              <div class="flex items-center gap-2">
                <input v-model="knowledgePolicy.share_mode" type="radio" value="private_only">
                <span class="font-medium text-slate-900">完全私有</span>
              </div>
              <div class="mt-2 text-sm text-slate-500">只留当前 tenant。</div>
            </label>
            <label class="rounded-xl border border-violet-200 bg-white px-4 py-4">
              <div class="flex items-center gap-2">
                <input v-model="knowledgePolicy.share_mode" type="radio" value="reviewed_share">
                <span class="font-medium text-slate-900">审核共享</span>
              </div>
              <div class="mt-2 text-sm text-slate-500">审核后可晋升到共享层。</div>
            </label>
            <label class="rounded-xl border border-violet-200 bg-white px-4 py-4">
              <div class="flex items-center gap-2">
                <input v-model="knowledgePolicy.share_mode" type="radio" value="platform_share">
                <span class="font-medium text-slate-900">平台共享</span>
              </div>
              <div class="mt-2 text-sm text-slate-500">允许更积极地复用通用成果。</div>
            </label>
          </div>
          <div class="mt-4 grid gap-3 md:grid-cols-2">
            <label class="inline-flex items-center gap-2 text-sm text-slate-700">
              <input v-model="knowledgePolicy.allow_platform_promotion" type="checkbox">
              <span>允许平台晋升</span>
            </label>
            <label class="inline-flex items-center gap-2 text-sm text-slate-700">
              <input v-model="knowledgePolicy.review_required" type="checkbox">
              <span>共享前必须审核</span>
            </label>
          </div>
          <div class="mt-4 flex gap-3">
            <button
              @click="saveKnowledgePolicyLocal"
              :disabled="knowledgePolicySaving"
              class="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-60"
            >
              {{ knowledgePolicySaving ? '保存中...' : '保存共享制度' }}
            </button>
          </div>
          <p v-if="knowledgePolicyMessage" class="mt-3 text-sm" :class="knowledgePolicySuccess ? 'text-green-600' : 'text-red-600'">
            {{ knowledgePolicyMessage }}
          </p>
        </div>

        <div class="mt-5 rounded-2xl border border-sky-200 bg-sky-50/60 p-4">
          <div class="text-sm font-semibold text-sky-950">外部学习边界</div>
          <div class="mt-1 text-sm text-sky-900">决定孩子和育成官在遇到缺口时，是否允许 AI、网页研究、企业私有知识参与。</div>
          <div class="mt-4 grid gap-3 md:grid-cols-2">
            <label class="inline-flex items-center gap-2 text-sm text-slate-700">
              <input v-model="externalLearningPolicy.allow_ai_assist" type="checkbox">
              <span>允许 AI 辅助分析</span>
            </label>
            <label class="inline-flex items-center gap-2 text-sm text-slate-700">
              <input v-model="externalLearningPolicy.allow_web_research" type="checkbox">
              <span>允许网页研究</span>
            </label>
            <label class="inline-flex items-center gap-2 text-sm text-slate-700">
              <input v-model="externalLearningPolicy.allow_enterprise_sources" type="checkbox">
              <span>允许企业私有知识源</span>
            </label>
            <label class="inline-flex items-center gap-2 text-sm text-slate-700">
              <input v-model="externalLearningPolicy.validation_required" type="checkbox">
              <span>外部学习后必须验证</span>
            </label>
          </div>
          <div class="mt-4">
            <label class="mb-2 block text-xs uppercase tracking-[0.18em] text-slate-400">Source Priority</label>
            <input
              :value="externalLearningPolicy.source_priority.join(', ')"
              @change="externalLearningPolicy.source_priority = String(($event.target as HTMLInputElement).value || '').split(',').map((item) => item.trim()).filter(Boolean)"
              type="text"
              class="w-full rounded-lg border border-sky-200 bg-white px-3 py-2 text-sm text-slate-700"
            >
          </div>
          <div class="mt-5 rounded-xl border border-sky-100 bg-white p-4">
            <div class="text-sm font-semibold text-slate-900">自主学习模型（OpenAI 兼容）</div>
            <p class="mt-1 text-xs text-slate-500">
              填 DeepSeek / 通义 / 本地网关等：base_url + api_key + model。用于员工补知识与 AI 辅助学习。
            </p>
            <label class="mt-3 inline-flex items-center gap-2 text-sm text-slate-700">
              <input
                :checked="modelProvider.enabled"
                type="checkbox"
                @change="patchModelProvider({ enabled: ($event.target as HTMLInputElement).checked })"
              >
              <span>启用模型学习</span>
            </label>
            <div class="mt-4 rounded-xl border border-slate-100 bg-slate-50/80 p-4">
              <div class="text-sm font-semibold text-slate-800">连接</div>
              <div class="mt-3 grid gap-3 md:grid-cols-2">
                <div class="md:col-span-2">
                  <label class="mb-1 block text-xs text-slate-400">
                    API Key
                    <span v-if="modelProvider.api_key_configured" class="ml-2 text-emerald-600">已配置</span>
                  </label>
                  <input
                    :value="modelProvider.api_key.includes('*') ? '' : modelProvider.api_key"
                    type="password"
                    placeholder="留空则保留原密钥"
                    class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                    autocomplete="off"
                    @input="patchModelProvider({ api_key: ($event.target as HTMLInputElement).value })"
                  >
                </div>
                <div>
                  <label class="mb-1 block text-xs text-slate-400">Base URL</label>
                  <input
                    :value="modelProvider.base_url"
                    type="text"
                    placeholder="https://api.deepseek.com"
                    class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                    @input="patchModelProvider({ base_url: ($event.target as HTMLInputElement).value })"
                  >
                </div>
                <div>
                  <label class="mb-1 block text-xs text-slate-400">端点格式</label>
                  <input
                    value="/v1/chat/completions"
                    type="text"
                    readonly
                    class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600"
                  >
                </div>
                <div class="md:col-span-2">
                  <label class="mb-1 block text-xs text-slate-400">Model</label>
                  <input
                    :value="modelProvider.model"
                    type="text"
                    placeholder="deepseek-chat"
                    class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                    @input="patchModelProvider({ model: ($event.target as HTMLInputElement).value })"
                  >
                </div>
              </div>
            </div>
          </div>
          <div class="mt-4 flex gap-3">
            <button
              @click="saveExternalLearningPolicyLocal"
              :disabled="externalLearningPolicySaving"
              class="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-60"
            >
              {{ externalLearningPolicySaving ? '保存中...' : '保存学习边界' }}
            </button>
          </div>
          <p v-if="externalLearningPolicyMessage" class="mt-3 text-sm" :class="externalLearningPolicySuccess ? 'text-green-600' : 'text-red-600'">
            {{ externalLearningPolicyMessage }}
          </p>
        </div>
      </section>
    </div>

    <div v-show="companySection === 'worktypes'" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div class="text-lg font-semibold text-slate-900">能力池与工种</div>
          <div class="mt-4 grid gap-3 md:grid-cols-3">
            <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
              <div class="text-slate-400">岗位工种</div>
              <div class="mt-2 font-medium text-slate-900">{{ workTypeCount }} 个</div>
              <div class="mt-1 text-xs text-slate-500">已写入 work_types.json</div>
            </div>
            <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
              <div class="text-slate-400">执行器</div>
              <div class="mt-2 font-medium text-slate-900">{{ enabledWorkers }}/{{ totalWorkers }}</div>
              <div class="mt-1 text-xs text-slate-500">已启用的 openSpec 插件</div>
            </div>
            <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
              <div class="text-slate-400">共享模式</div>
              <div class="mt-2 font-medium text-slate-900">{{ knowledgePolicyLabel }}</div>
              <div class="mt-1 text-xs text-slate-500">当前公司经验制度</div>
            </div>
          </div>
          <CompanyWorkTypesPanel
            ref="workTypesPanelRef"
            class="mt-5"
            :worker-registry="workerRegistry"
            :worker-enabled-draft="workerEnabledDraft"
            @work-types-updated="onWorkTypesUpdated"
            @request-enable-worker="onRequestEnableWorker"
          />

          <div class="mt-5 rounded-2xl border border-amber-200 bg-amber-50/60 p-4">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-sm font-semibold text-amber-950">执行器开关</div>
                <div class="mt-1 text-sm text-amber-900">启用 openSpec 执行器插件后需重启 Admin；岗位工种须先在上方「添加工种」写入。</div>
              </div>
              <button
                @click="loadWorkerRegistryLocal"
                :disabled="workerRegistryLoading"
                class="rounded-full border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-60"
              >
                {{ workerRegistryLoading ? '刷新中...' : '刷新执行器' }}
              </button>
            </div>
            <div v-if="workerManifestList.length" class="mt-4 space-y-2">
              <label
                v-for="item in workerManifestList"
                :key="item.worker_id"
                class="flex cursor-pointer items-center gap-4 rounded-xl border border-amber-200 bg-white px-4 py-3 transition hover:border-amber-300"
              >
                <div class="min-w-0 flex-1">
                  <div class="font-medium text-slate-900">{{ item.title || item.worker_id }}</div>
                  <div class="mt-0.5 text-xs text-slate-500">{{ item.capability_type || '--' }}</div>
                  <div class="mt-1 text-[11px] text-slate-500">{{ item.owned_modules.join(', ') || '--' }}</div>
                </div>
                <input
                  type="checkbox"
                  class="h-4 w-4 shrink-0 rounded border-amber-300 text-amber-600"
                  :checked="workerEnabledDraft[item.worker_id] ?? item.default_enabled"
                  @change="toggleWorkerEnabledLocal(item.worker_id, ($event.target as HTMLInputElement).checked)"
                >
              </label>
            </div>
            <div v-else class="mt-4 rounded-xl border border-dashed border-amber-200 bg-white px-4 py-4 text-sm text-slate-500">
              当前还没有发现可注册执行器。
            </div>
            <div class="mt-4 flex gap-3">
              <button
                @click="saveWorkerRegistryLocal"
                :disabled="workerRegistrySaving || workerRegistryLoading"
                class="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-60"
              >
                {{ workerRegistrySaving ? '保存中...' : '保存执行器开关' }}
              </button>
            </div>
            <p v-if="workerRegistryMessage" class="mt-3 rounded-lg border px-3 py-2 text-sm" :class="workerRegistrySuccess ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-rose-200 bg-rose-50 text-rose-700'">
              {{ workerRegistryMessage }}
            </p>
          </div>
          <div class="mt-4 grid gap-3">
            <router-link to="/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary" class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-700 hover:bg-slate-100">
              回到育成官主线
            </router-link>
            <router-link to="/organization/child" class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-700 hover:bg-slate-100">
              查看员工工作台
            </router-link>
          </div>
    </div>

    <div v-show="companySection === 'integrations'" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div class="text-lg font-semibold text-slate-900">公司接入与插件</div>
          <div class="mt-4 rounded-2xl border border-teal-200 bg-teal-50/60 p-4">
            <div class="text-sm font-semibold text-teal-950">Gitee 绑定</div>
            <div class="mt-1 text-sm text-teal-900">把经验、技能、成长文档稳定沉淀到外部仓库，这属于父节点的公司级接入。</div>
            <input
              v-model="token"
              type="password"
              placeholder="Gitee Token"
              class="mt-4 w-full rounded-lg border border-teal-200 bg-white px-3 py-2 text-sm text-slate-700"
            >
            <div class="mt-4 flex gap-3">
              <button
                @click="saveToken"
                :disabled="tokenSaving"
                class="rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-700 disabled:opacity-60"
              >
                {{ tokenSaving ? '保存中...' : '保存 Gitee Token' }}
              </button>
            </div>
            <p v-if="tokenMessage" class="mt-3 text-sm" :class="tokenSuccess ? 'text-green-600' : 'text-red-600'">
              {{ tokenMessage }}
            </p>
          </div>

          <div class="mt-5 rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-sm font-semibold text-slate-900">插件策略</div>
                <div class="mt-1 text-sm text-slate-500">决定哪些插件能参与当前公司的自主决策，不把能力边界写死在系统里。</div>
              </div>
              <button
                @click="loadPluginPolicyLocal"
                :disabled="pluginLoading"
                class="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                {{ pluginLoading ? '刷新中...' : '刷新插件' }}
              </button>
            </div>
            <div v-if="plugins.length" class="mt-4 grid gap-3">
              <label
                v-for="plugin in plugins"
                :key="plugin.name"
                class="rounded-xl border border-slate-200 bg-white px-4 py-4"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <div class="font-medium text-slate-900">{{ plugin.name }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ plugin.manifest.description || plugin.module_path }}</div>
                  </div>
                </div>
                <div class="mt-2 text-[11px] text-slate-500">
                  {{ plugin.capability_types?.join(', ') || 'no capability type' }}
                </div>
                <div class="mt-3 grid gap-3 md:grid-cols-2">
                  <label class="inline-flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      :checked="enabledSet.has(plugin.name)"
                      @change="togglePluginEnabled(plugin.name, ($event.target as HTMLInputElement).checked)"
                    >
                    <span>启用白名单</span>
                  </label>
                  <label class="inline-flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      :checked="disabledSet.has(plugin.name)"
                      @change="togglePluginDisabled(plugin.name, ($event.target as HTMLInputElement).checked)"
                    >
                    <span>禁用黑名单</span>
                  </label>
                </div>
              </label>
            </div>
            <div v-else class="mt-4 rounded-xl border border-dashed border-slate-200 bg-white px-4 py-4 text-sm text-slate-500">
              当前还没有已加载插件。
            </div>
            <div class="mt-4 flex gap-3">
              <button
                @click="savePluginPolicyLocal"
                :disabled="pluginSaving || pluginLoading"
                class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
              >
                {{ pluginSaving ? '保存中...' : '保存插件策略' }}
              </button>
            </div>
            <p v-if="pluginMessage" class="mt-3 text-sm" :class="pluginSuccess ? 'text-green-600' : 'text-red-600'">
              {{ pluginMessage }}
            </p>
          </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import WorkspaceSubNav from '../components/shell/WorkspaceSubNav.vue'
import type { WorkspaceSubNavItem } from '../components/shell/WorkspaceSubNav.vue'
import CompanyWorkTypesPanel from '../components/CompanyWorkTypesPanel.vue'
import { bindGiteeToken, getUser, type UserProfile } from '../api/auth'
import { getWorkTypes } from '../api/workTypes'
import {
  getAutonomyStatus,
  getTenantExternalLearningPolicy,
  getTenantKnowledgePolicy,
  getTenantPluginPolicy,
  getWorkerRegistry,
  listPlugins,
  type PluginItem,
  type AutonomyStatus,
  type TenantExternalLearningPolicy,
  type TenantKnowledgePolicy,
  type WorkerManifest,
  type WorkerRegistryPayload,
  updateTenantExternalLearningPolicy,
  updateTenantKnowledgePolicy,
  updateTenantPluginPolicy,
  updateWorkerRegistry,
} from '../api/plugins'
import { buildOrganizationModel } from '../utils/organization'

type CompanySection = 'overview' | 'structure' | 'policies' | 'worktypes' | 'integrations'

const route = useRoute()
const router = useRouter()

const normalizeCompanySection = (value: unknown): CompanySection => {
  const section = String(value || '').trim()
  if (section === 'structure' || section === 'policies' || section === 'worktypes' || section === 'integrations') {
    return section
  }
  return 'overview'
}

const companySection = ref<CompanySection>('overview')

const companyOverviewRoute = { path: '/organization/parent/workspace' }

const companySectionMeta = computed(() => {
  const meta: Record<CompanySection, { title: string; description: string }> = {
    overview: {
      title: '公司治理与结构设置',
      description: '公司层身份、工种目录与制度边界。',
    },
    structure: {
      title: '公司结构与编制',
      description: '组织入口、当前员工编制与职能分工。',
    },
    policies: {
      title: '共享制度与学习边界',
      description: '经验共享模式、外部学习来源与审核策略。',
    },
    worktypes: {
      title: '工种与执行器',
      description: '添加工种、启用 openSpec 执行器插件（需重启 Admin）。',
    },
    integrations: {
      title: '接入与插件策略',
      description: 'Gitee Token 绑定与公司级插件白名单。',
    },
  }
  return meta[companySection.value]
})

const companySubNavItems = computed<WorkspaceSubNavItem[]>(() => ([
  { key: 'overview', title: '总览', badge: '入口', active: companySection.value === 'overview' },
  { key: 'structure', title: '结构', badge: `${activeChildren.value.length} 人`, active: companySection.value === 'structure' },
  { key: 'policies', title: '制度', badge: knowledgePolicyLabel.value, active: companySection.value === 'policies' },
  { key: 'worktypes', title: '工种', badge: `${workTypeCount.value} 个`, active: companySection.value === 'worktypes' },
  { key: 'integrations', title: '接入', badge: plugins.value.length ? `${plugins.value.length} 插件` : 'Gitee', active: companySection.value === 'integrations' },
]))

const onCompanySectionSelect = (key: string) => {
  const section = normalizeCompanySection(key)
  companySection.value = section
  router.replace({
    path: route.path,
    query: section === 'overview' ? {} : { section },
  })
}

const refreshSection = async () => {
  if (companySection.value === 'policies') {
    await loadPolicies()
    return
  }
  if (companySection.value === 'worktypes') {
    await Promise.all([loadWorkerRegistryLocal(), loadWorkTypeCount()])
    return
  }
  if (companySection.value === 'integrations') {
    await loadPluginPolicyLocal()
    return
  }
  await refresh()
}

watch(() => route.query.section, (value) => {
  companySection.value = normalizeCompanySection(value)
}, { immediate: true })

const tenantId = ref(localStorage.getItem('tenant_id') || 'default')
const loading = ref(false)
const policyLoading = ref(false)
const pluginLoading = ref(false)
const user = ref<UserProfile | null>(null)
const autonomyStatus = ref<AutonomyStatus | null>(null)
const workerRegistry = ref<WorkerRegistryPayload | null>(null)
const workTypesPanelRef = ref<InstanceType<typeof CompanyWorkTypesPanel> | null>(null)
const workTypeCount = ref(0)
const token = ref('')
const tokenSaving = ref(false)
const tokenMessage = ref('')
const tokenSuccess = ref(false)
const workerRegistryLoading = ref(false)
const workerRegistrySaving = ref(false)
const workerRegistryMessage = ref('')
const workerRegistrySuccess = ref(false)
const workerEnabledDraft = ref<Record<string, boolean>>({})
const plugins = ref<PluginItem[]>([])
const enabledPlugins = ref<string[]>([])
const disabledPlugins = ref<string[]>([])
const pluginSaving = ref(false)
const pluginMessage = ref('')
const pluginSuccess = ref(false)
const knowledgePolicySaving = ref(false)
const knowledgePolicyMessage = ref('')
const knowledgePolicySuccess = ref(false)
const knowledgePolicy = ref<TenantKnowledgePolicy>({
  share_mode: 'private_only',
  allow_platform_promotion: false,
  review_required: true,
})
const externalLearningPolicySaving = ref(false)
const externalLearningPolicyMessage = ref('')
const externalLearningPolicySuccess = ref(false)
const externalLearningPolicy = ref<TenantExternalLearningPolicy>({
  allow_ai_assist: true,
  allow_web_research: true,
  allow_enterprise_sources: true,
  source_priority: ['local_memory', 'platform_shared', 'enterprise_repo', 'official_docs', 'web_search', 'ai_assist'],
  validation_required: true,
  model_provider: {
    enabled: false,
    label: 'openai_compatible',
    base_url: '',
    api_key: '',
    model: '',
  },
})

const modelProvider = computed(() => {
  const current = externalLearningPolicy.value.model_provider || {}
  return {
    enabled: Boolean(current.enabled),
    label: String(current.label || 'openai_compatible'),
    base_url: String(current.base_url || ''),
    api_key: String(current.api_key || ''),
    api_key_configured: Boolean(current.api_key_configured),
    model: String(current.model || ''),
  }
})

const patchModelProvider = (patch: Record<string, unknown>) => {
  externalLearningPolicy.value = {
    ...externalLearningPolicy.value,
    model_provider: {
      ...(externalLearningPolicy.value.model_provider || {}),
      ...patch,
    },
  }
}

const organizationModel = computed(() => buildOrganizationModel(autonomyStatus.value, null))
const activeChildren = computed(() => organizationModel.value.childNodes)
const trainerCount = computed(() => organizationModel.value.trainerNodes.length)
const supportNodeCount = computed(() => organizationModel.value.supportNodes.length)

const totalWorkers = computed(() => Object.keys(workerRegistry.value?.manifests || {}).length)
const enabledWorkers = computed(() => (
  Object.values(workerRegistry.value?.config?.workers || {}).filter((item) => Boolean(item?.enabled)).length
))
const enabledSet = computed(() => new Set(enabledPlugins.value))
const disabledSet = computed(() => new Set(disabledPlugins.value))
const workerManifestList = computed<WorkerManifest[]>(() => (
  Object.values(workerRegistry.value?.manifests || {})
    .sort((a, b) => a.worker_id.localeCompare(b.worker_id))
))

const profileName = computed(() => {
  const parentName = String(autonomyStatus.value?.parent_profile?.display_name || '').trim()
  return parentName || user.value?.name || user.value?.login || 'Parent Node'
})

const userLabel = computed(() => {
  const login = user.value?.login || 'unknown'
  const tenant = tenantId.value || 'default'
  return `${login} / ${tenant}`
})

const knowledgePolicyLabel = computed(() => {
  if (knowledgePolicy.value.share_mode === 'platform_share') return '平台共享'
  if (knowledgePolicy.value.share_mode === 'reviewed_share') return '审核共享'
  return '完全私有'
})

const loadPolicies = async () => {
  policyLoading.value = true
  try {
    const [knowledgeResult, externalResult] = await Promise.all([
      getTenantKnowledgePolicy(tenantId.value || 'default').catch(() => null),
      getTenantExternalLearningPolicy(tenantId.value || 'default').catch(() => null),
    ])
    knowledgePolicy.value = knowledgeResult?.data?.policy || knowledgePolicy.value
    externalLearningPolicy.value = externalResult?.data?.policy || externalLearningPolicy.value
  } finally {
    policyLoading.value = false
  }
}

const loadPluginPolicyLocal = async () => {
  pluginLoading.value = true
  pluginMessage.value = ''
  try {
    const [pluginResult, policyResult] = await Promise.all([
      listPlugins().catch(() => null),
      getTenantPluginPolicy(tenantId.value || 'default').catch(() => null),
    ])
    plugins.value = pluginResult?.data?.plugins || []
    enabledPlugins.value = policyResult?.data?.policy?.enabled || []
    disabledPlugins.value = policyResult?.data?.policy?.disabled || []
  } catch {
    pluginSuccess.value = false
    pluginMessage.value = '插件策略加载失败'
  } finally {
    pluginLoading.value = false
  }
}

const loadWorkerRegistryLocal = async () => {
  workerRegistryLoading.value = true
  workerRegistryMessage.value = ''
  try {
    const result = await getWorkerRegistry()
    workerRegistry.value = result.data || null
    const nextDraft: Record<string, boolean> = {}
    for (const [workerId, item] of Object.entries(result.data?.config?.workers || {})) {
      nextDraft[workerId] = Boolean(item.enabled)
    }
    workerEnabledDraft.value = nextDraft
  } catch {
    workerRegistrySuccess.value = false
    workerRegistryMessage.value = '工种目录加载失败'
  } finally {
    workerRegistryLoading.value = false
  }
}

const toggleWorkerEnabledLocal = (workerId: string, enabled: boolean) => {
  workerEnabledDraft.value = {
    ...workerEnabledDraft.value,
    [workerId]: enabled,
  }
}

const loadWorkTypeCount = async () => {
  try {
    const result = await getWorkTypes()
    workTypeCount.value = result.data?.items?.length || 0
  } catch {
    workTypeCount.value = 0
  }
}

const onWorkTypesUpdated = async () => {
  await loadWorkTypeCount()
}

const onRequestEnableWorker = (workerId: string, enabled: boolean) => {
  workerEnabledDraft.value = {
    ...workerEnabledDraft.value,
    [workerId]: enabled,
  }
}

const saveWorkerRegistryLocal = async () => {
  workerRegistrySaving.value = true
  workerRegistryMessage.value = ''
  try {
    const workers = Object.fromEntries(
      Object.entries(workerEnabledDraft.value).map(([workerId, enabled]) => [workerId, { enabled }])
    )
    await updateWorkerRegistry(workers)
    workerRegistrySuccess.value = true
    workerRegistryMessage.value = '执行器开关已保存。请重启 Admin 后新启用的插件才会注册到任务队列。'
    await loadWorkerRegistryLocal()
  } catch {
    workerRegistrySuccess.value = false
    workerRegistryMessage.value = '工种注册配置保存失败'
  } finally {
    workerRegistrySaving.value = false
  }
}

const togglePluginEnabled = (name: string, checked: boolean) => {
  const enabled = new Set(enabledPlugins.value)
  const disabled = new Set(disabledPlugins.value)
  if (checked) {
    enabled.add(name)
    disabled.delete(name)
  } else {
    enabled.delete(name)
  }
  enabledPlugins.value = Array.from(enabled)
  disabledPlugins.value = Array.from(disabled)
}

const togglePluginDisabled = (name: string, checked: boolean) => {
  const enabled = new Set(enabledPlugins.value)
  const disabled = new Set(disabledPlugins.value)
  if (checked) {
    disabled.add(name)
    enabled.delete(name)
  } else {
    disabled.delete(name)
  }
  enabledPlugins.value = Array.from(enabled)
  disabledPlugins.value = Array.from(disabled)
}

const savePluginPolicyLocal = async () => {
  pluginSaving.value = true
  pluginMessage.value = ''
  try {
    const result = await updateTenantPluginPolicy(tenantId.value || 'default', {
      enabled: enabledPlugins.value,
      disabled: disabledPlugins.value,
    })
    enabledPlugins.value = result.data?.policy?.enabled || enabledPlugins.value
    disabledPlugins.value = result.data?.policy?.disabled || disabledPlugins.value
    pluginSuccess.value = true
    pluginMessage.value = result.message || '插件策略已更新'
  } catch {
    pluginSuccess.value = false
    pluginMessage.value = '插件策略保存失败'
  } finally {
    pluginSaving.value = false
  }
}

const saveToken = async () => {
  tokenSaving.value = true
  tokenMessage.value = ''
  try {
    const result = await bindGiteeToken(token.value)
    tokenSuccess.value = result.code === 0
    tokenMessage.value = result.message || (result.code === 0 ? 'Gitee Token 已更新' : 'Gitee Token 保存失败')
    if (result.code === 0) token.value = ''
  } catch {
    tokenSuccess.value = false
    tokenMessage.value = 'Gitee Token 保存失败'
  } finally {
    tokenSaving.value = false
  }
}

const saveKnowledgePolicyLocal = async () => {
  knowledgePolicySaving.value = true
  knowledgePolicyMessage.value = ''
  try {
    const result = await updateTenantKnowledgePolicy(tenantId.value || 'default', knowledgePolicy.value)
    knowledgePolicy.value = result.data?.policy || knowledgePolicy.value
    knowledgePolicySuccess.value = true
    knowledgePolicyMessage.value = result.message || '共享制度已更新'
  } catch {
    knowledgePolicySuccess.value = false
    knowledgePolicyMessage.value = '共享制度保存失败'
  } finally {
    knowledgePolicySaving.value = false
  }
}

const saveExternalLearningPolicyLocal = async () => {
  externalLearningPolicySaving.value = true
  externalLearningPolicyMessage.value = ''
  try {
    const result = await updateTenantExternalLearningPolicy(tenantId.value || 'default', externalLearningPolicy.value)
    externalLearningPolicy.value = result.data?.policy || externalLearningPolicy.value
    externalLearningPolicySuccess.value = true
    externalLearningPolicyMessage.value = result.message || '学习边界已更新'
  } catch {
    externalLearningPolicySuccess.value = false
    externalLearningPolicyMessage.value = '学习边界保存失败'
  } finally {
    externalLearningPolicySaving.value = false
  }
}

const refresh = async () => {
  loading.value = true
  try {
    const [userResult, autonomyResult, workerResult] = await Promise.all([
      getUser().catch(() => null),
      getAutonomyStatus(tenantId.value || 'default').catch(() => null),
      getWorkerRegistry().catch(() => null),
    ])
    if (userResult?.code === 0 && userResult.data) {
      user.value = userResult.data
    }
    autonomyStatus.value = autonomyResult?.data || null
    workerRegistry.value = workerResult?.data || null
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await refresh()
  await loadPolicies()
  await loadPluginPolicyLocal()
  await loadWorkerRegistryLocal()
  await loadWorkTypeCount()
  await workTypesPanelRef.value?.loadWorkTypesLocal()
})
</script>
