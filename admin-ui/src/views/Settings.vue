<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      v-if="showTrainerLanding"
      eyebrow="育成师空间"
      title="先选员工，再推进带教"
      description="对内带教（建档/训练/复盘），对外接单对接（能力路由与分派）。商业任务请从接单台进入。"
      :show-refresh="false"
      :back-to="{ path: '/dashboard' }"
    >
      <template #actions>
        <button
          type="button"
          class="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
          @click="setTrainerMainlineMode('portrait', { replace: false })"
        >
          进入工作台
        </button>
        <router-link
          to="/organization/intake"
          class="rounded-lg border border-slate-800 bg-slate-900/90 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
        >
          接单对接台
        </router-link>
        <router-link
          to="/organization/trainer/talent_development_officer/tools"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          支撑工具
        </router-link>
        <router-link
          to="/organization/child"
          class="rounded-lg border border-emerald-300 px-3 py-1.5 text-xs font-medium text-emerald-800 hover:bg-emerald-50"
        >
          员工工作台
        </router-link>
      </template>
    </WorkspacePageHeader>

    <WorkspacePageHeader
      v-else
      eyebrow="育成师 · 工作台"
      :title="trainerMainlineModeMeta.title"
      :description="trainerMainlineModeMeta.description"
      :show-refresh="false"
      :back-to="trainerLandingRoute"
      back-label="返回育成主页"
    >
      <template #actions>
        <router-link
          to="/organization/intake"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
        >
          接单对接
        </router-link>
        <router-link
          v-if="selectedChildWorkspaceRoute"
          :to="selectedChildWorkspaceRoute"
          class="rounded-lg border border-emerald-300 px-3 py-1.5 text-xs font-medium text-emerald-800 hover:bg-emerald-50"
        >
          员工工作台
        </router-link>
        <router-link
          v-if="trainerWorkNodeLink"
          :to="trainerWorkNodeLink"
          class="rounded-lg border border-teal-200 bg-teal-50 px-3 py-1.5 text-xs font-medium text-teal-800 hover:bg-teal-100"
        >
          节点流水
        </router-link>
      </template>
    </WorkspacePageHeader>

    <WorkspaceSubNav
      v-if="!showTrainerLanding"
      orientation="horizontal"
      class="w-full"
      :items="trainerSubNavItems"
      @select="onTrainerSubNavSelect"
    />

    <section v-if="showTrainerLanding" class="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
      <article class="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div class="text-xs uppercase tracking-[0.16em] text-slate-400">当前育成官</div>
            <div class="mt-2 text-2xl font-semibold text-slate-900">{{ trainerMemberDraft?.name || '育成官' }}</div>
            <div class="mt-2 text-sm text-slate-500">{{ trainerMemberDraft?.persona?.role_label || trainerMemberDraft?.primary_role || 'talent_development' }}</div>
          </div>
          <div class="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
            <div class="text-slate-400">当前工作位</div>
            <div class="mt-2 font-medium text-slate-900">{{ trainerMainlineModeMeta.title }}</div>
          </div>
        </div>
        <div class="mt-5 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
          <div class="text-sm font-semibold text-slate-900">当前关注</div>
          <div class="mt-2 text-sm leading-6 text-slate-700">
            {{ trainerMemberDraft?.growth_state?.current_focus || trainerMemberDraft?.self_development?.current_objective || '先确认正在带谁，再推进哪一轮带教。' }}
          </div>
        </div>
      </article>

      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-1">
        <article class="rounded-2xl border border-amber-200 bg-amber-50/80 px-5 py-4 shadow-sm">
          <div class="text-xs uppercase tracking-[0.16em] text-amber-700">当前对象</div>
          <div class="mt-2 text-xl font-semibold text-slate-900">{{ trainerSelectedChildName }}</div>
          <div class="mt-2 text-sm text-amber-900">{{ trainerSelectedChildMeta }}</div>
        </article>
        <article class="rounded-2xl border border-emerald-200 bg-emerald-50/70 px-5 py-4 shadow-sm">
          <div class="text-xs uppercase tracking-[0.16em] text-emerald-700">当前闭环</div>
          <div class="mt-2 text-xl font-semibold text-slate-900">{{ trainerFormalTaskStageLabel }}</div>
          <div class="mt-2 text-sm text-emerald-900">{{ activeFormalTaskRecommendation?.title || '围绕当前员工继续推进这轮带教闭环' }}</div>
        </article>
      </div>
    </section>

    <details v-if="showTrainerLanding" class="rounded-2xl border border-slate-200 bg-white/80">
      <summary class="cursor-pointer list-none px-5 py-4">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div class="text-sm font-semibold text-slate-900">次要支撑工具</div>
            <div class="mt-1 text-sm text-slate-500">这些内容保留在这里备用，只有需要时再展开，不压在主工作流前面。</div>
          </div>
          <div class="rounded-full bg-slate-100 px-3 py-1 text-[11px] text-slate-600">
            辅助
          </div>
        </div>
      </summary>

      <div class="border-t border-slate-200 px-5 py-5 space-y-6">
        <div class="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-4 text-sm text-sky-900">
          支撑工具仍然可看，但公司级修改统一收回公司空间。育成官这里主要读运行状态、判断是否需要介入，并把员工送回自己的岗位空间闭环。
        </div>

        <div class="grid gap-6 lg:grid-cols-2">
          <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div class="mb-3 inline-flex rounded-full bg-teal-100 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-teal-800">
              公司维护
            </div>
            <div class="flex items-start justify-between gap-4">
              <div>
                <h2 class="text-lg font-semibold text-slate-900">Gitee 入库状态</h2>
                <p class="mt-1 text-sm text-slate-500">令牌绑定与知识仓接入由公司维护，育成官这里只看当前是否具备入库条件。</p>
              </div>
              <router-link to="/organization/parent/workspace" class="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                去公司维护
              </router-link>
            </div>
            <div class="mt-4 grid gap-3 md:grid-cols-2">
              <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                <div class="text-slate-400">令牌</div>
                <div class="mt-2 font-medium text-slate-900">{{ selfMediaJobRuntime?.tenant_state?.git_export?.token_available ? '已就绪' : '缺失' }}</div>
              </div>
              <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                <div class="text-slate-400">仓库键</div>
                <div class="mt-2 font-medium text-slate-900">{{ selfMediaJobRuntime?.tenant_state?.git_export?.repo_key || '--' }}</div>
              </div>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div class="mb-3 inline-flex rounded-full bg-slate-100 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-slate-700">
              公司维护
            </div>
            <div class="flex items-start justify-between gap-4">
              <div>
                <h2 class="text-lg font-semibold text-slate-900">插件与工种边界</h2>
                <p class="mt-1 text-sm text-slate-500">育成官只需要知道当前有哪些能力可用，不应该在这里改公司级白名单、黑名单或工种开关。</p>
              </div>
              <router-link to="/organization/parent/workspace" class="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                去公司维护
              </router-link>
            </div>
            <div class="mt-4 grid gap-3 md:grid-cols-2">
              <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                <div class="text-slate-400">插件</div>
                <div class="mt-2 font-medium text-slate-900">{{ plugins.length }} 个已加载</div>
                <div class="mt-1 text-xs text-slate-500">允许 {{ enabledSet.size }} / 禁用 {{ disabledSet.size }}</div>
              </div>
              <div class="rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
                <div class="text-slate-400">工种</div>
                <div class="mt-2 font-medium text-slate-900">{{ enabledWorkerCount }}/{{ workerManifestList.length }} 已启用</div>
                <div class="mt-1 text-xs text-slate-500">外部 {{ externalWorkerCount }} / 运行时 {{ runtimeWorkerCount }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
          <div class="mb-3 inline-flex rounded-full bg-slate-100 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-slate-700">
            运行摘要
          </div>
          <div class="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold text-slate-900">工种与执行器运行摘要</h2>
              <p class="mt-1 text-sm text-slate-500">这里只保留运行态观察，真正的工种开关、插件边界和制度修改都回到公司空间。</p>
            </div>
            <button
              @click="loadWorkerRegistry"
              :disabled="workerRegistryLoading"
              class="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              {{ workerRegistryLoading ? '刷新中...' : '刷新摘要' }}
            </button>
          </div>

          <p v-if="workerRegistryMessage" class="mb-4 text-sm" :class="workerRegistrySuccess ? 'text-green-600' : 'text-red-600'">
            {{ workerRegistryMessage }}
          </p>

          <div class="grid gap-3 md:grid-cols-4 mb-4">
        <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
          <div class="text-xs uppercase tracking-[0.16em] text-slate-400">工种总数</div>
          <div class="mt-2 font-medium text-slate-900">{{ workerManifestList.length }}</div>
        </div>
        <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
          <div class="text-xs uppercase tracking-[0.16em] text-slate-400">已启用</div>
          <div class="mt-2 font-medium text-slate-900">{{ enabledWorkerCount }}</div>
        </div>
        <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
          <div class="text-xs uppercase tracking-[0.16em] text-slate-400">项目外挂</div>
          <div class="mt-2 font-medium text-slate-900">{{ externalWorkerCount }}</div>
        </div>
        <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
          <div class="text-xs uppercase tracking-[0.16em] text-slate-400">运行中</div>
          <div class="mt-2 font-medium text-slate-900">{{ runtimeWorkerCount }}</div>
          <div class="mt-1 text-xs text-slate-400">{{ formatDate(workerRegistry?.config?.updated_at || workerRegistry?.runtime?.updated_at) }}</div>
        </div>
      </div>

      <div
        v-if="workerRegistry?.self_media?.executor_registry"
        class="mb-4 rounded-xl border border-teal-200 bg-teal-50/70 px-4 py-4"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-sm font-medium text-teal-950">头条执行器</div>
            <div class="mt-1 text-xs text-teal-700">
              当前偏好 {{ workerRegistry.self_media.executor_registry.preferred_mode || '自动' }}
            </div>
          </div>
          <div class="text-right text-xs text-teal-700">
            <div>当前选中 {{ workerRegistry.self_media.executor_registry.selected?.label || '--' }}</div>
            <div v-if="workerRegistry.self_media.executor_registry.selected?.adapter" class="mt-1">
              {{ workerRegistry.self_media.executor_registry.selected?.adapter }}
            </div>
          </div>
        </div>
        <div class="mt-3 grid gap-3 md:grid-cols-3">
          <div
            v-for="item in workerRegistry.self_media.executor_registry.executors || []"
            :key="item.key"
            class="rounded-lg border px-3 py-3 text-sm"
            :class="item.available ? 'border-teal-200 bg-white text-slate-700' : 'border-slate-200 bg-slate-50 text-slate-400'"
          >
            <div class="font-medium">{{ item.label || item.key }}</div>
            <div class="mt-1 text-xs">{{ item.adapter || '--' }} / {{ item.source || '--' }}</div>
            <div class="mt-1 text-xs">{{ item.available ? '可用' : '缺失' }}</div>
            <div v-if="item.root_dir" class="mt-2 break-all text-[11px]">{{ item.root_dir }}</div>
          </div>
        </div>
        <div class="mt-4 grid gap-3 md:grid-cols-[0.8fr_1fr_1fr_auto]">
          <div>
            <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-teal-700">默认模式</label>
            <select
              v-model="selfMediaExecutorModeDraft"
              class="w-full rounded-lg border border-teal-200 bg-white px-3 py-2 text-sm text-slate-700"
            >
              <option value="evo">Evo 本地执行器</option>
              <option value="auto">自动 / Evo 优先</option>
            </select>
          </div>
          <div>
            <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-teal-700">执行器目录（可选）</label>
            <input
              v-model="selfMediaExecutorDirDraft"
              type="text"
              class="w-full rounded-lg border border-teal-200 bg-white px-3 py-2 text-sm text-slate-700"
              placeholder="/absolute/path/to/executor"
            >
          </div>
          <div>
            <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-teal-700">登录目标地址</label>
            <input
              v-model="selfMediaExecutorLoginTargetUrlDraft"
              type="text"
              class="w-full rounded-lg border border-teal-200 bg-white px-3 py-2 text-sm text-slate-700"
              placeholder="https://..."
            >
          </div>
          <div class="self-end">
            <button
              @click="saveSelfMediaExecutorConfig"
              :disabled="selfMediaExecutorSaving || workerRegistryLoading"
              class="rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-700 disabled:opacity-60"
            >
              {{ selfMediaExecutorSaving ? '保存中...' : '保存默认路由' }}
            </button>
          </div>
        </div>
      </div>

      <div class="mb-4 rounded-xl border border-sky-200 bg-sky-50/70 px-4 py-4">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-sm font-medium text-sky-950">头条账号运行态</div>
            <div class="mt-1 text-xs text-sky-700">先用本地占位登录态把系统流程跑通，后面再替换成真实 WebView / 浏览器 / 设备接管。</div>
          </div>
          <button
            @click="loadToutiaoAccounts"
            :disabled="toutiaoAccountLoading"
            class="rounded-lg border border-sky-200 bg-white px-4 py-2 text-sm text-sky-700 hover:bg-sky-50 disabled:opacity-60"
          >
            {{ toutiaoAccountLoading ? '刷新中...' : '刷新账号状态' }}
          </button>
        </div>

        <p v-if="toutiaoAccountMessage" class="mt-3 text-sm" :class="toutiaoAccountSuccess ? 'text-green-600' : 'text-red-600'">
          {{ toutiaoAccountMessage }}
        </p>

        <div class="mt-4 grid gap-3 md:grid-cols-[0.7fr_1fr_1fr]">
          <div>
            <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-sky-700">账号编号</label>
            <input
              v-model="toutiaoAccountId"
              type="text"
              class="w-full rounded-lg border border-sky-200 bg-white px-3 py-2 text-sm text-slate-700"
              placeholder="default"
            >
          </div>
          <div>
            <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-sky-700">显示名称</label>
            <input
              v-model="toutiaoAccountDisplayName"
              type="text"
              class="w-full rounded-lg border border-sky-200 bg-white px-3 py-2 text-sm text-slate-700"
              placeholder="Evo Toutiao"
            >
          </div>
          <div>
            <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-sky-700">主页链接</label>
            <input
              v-model="toutiaoAccountProfileUrl"
              type="text"
              class="w-full rounded-lg border border-sky-200 bg-white px-3 py-2 text-sm text-slate-700"
              placeholder="https://..."
            >
          </div>
        </div>

        <div class="mt-3">
          <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-sky-700">备注</label>
          <textarea
            v-model="toutiaoAccountNotes"
            rows="2"
            class="w-full rounded-lg border border-sky-200 bg-white px-3 py-2 text-sm text-slate-700"
            placeholder="记录当前账号接入状态、登录方式或后续替换计划"
          ></textarea>
        </div>
        <div class="mt-3">
          <label class="mb-2 block text-xs uppercase tracking-[0.16em] text-sky-700">登录目标地址</label>
          <input
            v-model="toutiaoLoginTargetUrl"
            type="text"
            class="w-full rounded-lg border border-sky-200 bg-white px-3 py-2 text-sm text-slate-700"
            placeholder="https://..."
          >
        </div>

        <div class="mt-4 flex flex-wrap gap-3">
          <button
            @click="beginToutiaoAccountLoginFlow"
            :disabled="toutiaoAccountSaving || toutiaoAccountLoading"
            class="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-60"
          >
            创建登录占位会话
          </button>
          <button
            @click="openToutiaoHandoffPage"
            :disabled="toutiaoAccountSaving || toutiaoAccountLoading"
            class="rounded-lg border border-emerald-200 bg-white px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-60"
          >
            打开登录接管页
          </button>
          <button
            @click="launchToutiaoLoginTarget"
            :disabled="toutiaoAccountSaving || toutiaoAccountLoading"
            class="rounded-lg border border-cyan-200 bg-white px-4 py-2 text-sm font-medium text-cyan-700 hover:bg-cyan-50 disabled:opacity-60"
          >
            发起登录目标
          </button>
          <button
            @click="confirmToutiaoAccountLoginFlow"
            :disabled="toutiaoAccountSaving || toutiaoAccountLoading"
            class="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
          >
            确认已登录
          </button>
          <button
            @click="saveToutiaoAccountDraft"
            :disabled="toutiaoAccountSaving || toutiaoAccountLoading"
            class="rounded-lg border border-sky-200 bg-white px-4 py-2 text-sm font-medium text-sky-700 hover:bg-sky-50 disabled:opacity-60"
          >
            保存账号资料
          </button>
          <button
            @click="logoutToutiaoAccountFlow"
            :disabled="toutiaoAccountSaving || toutiaoAccountLoading"
            class="rounded-lg border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-60"
          >
            标记登出
          </button>
        </div>

        <div class="mt-4 grid gap-3 md:grid-cols-2">
          <div class="rounded-lg border border-sky-100 bg-white px-4 py-3 text-sm text-slate-700">
            <div class="font-medium text-slate-900">当前账号状态</div>
            <div class="mt-2 text-xs text-slate-500">账号 {{ toutiaoAccounts?.current?.account_id || toutiaoAccountId }}</div>
            <div class="mt-1 text-xs text-slate-500">昵称 {{ toutiaoAccounts?.current?.display_name || '--' }}</div>
            <div class="mt-1 text-xs text-slate-500">登录 {{ toutiaoAccounts?.current?.logged_in ? '已登录' : '未登录' }}</div>
            <div class="mt-1 text-xs text-slate-500">会话 {{ (toutiaoAccounts?.current?.profile as any)?.login_session_id || '--' }}</div>
            <div class="mt-1 break-all text-xs text-slate-500">目标 {{ (toutiaoAccounts?.current?.profile as any)?.login_target_url || '--' }}</div>
            <div class="mt-1 text-xs text-slate-500">执行器 {{ toutiaoAccounts?.current?.executor?.adapter || '--' }}</div>
          </div>
          <div class="rounded-lg border border-sky-100 bg-white px-4 py-3 text-sm text-slate-700">
            <div class="font-medium text-slate-900">已发现账号</div>
            <div v-if="!(toutiaoAccounts?.items || []).length" class="mt-2 text-xs text-slate-500">当前还没有账号状态文件</div>
            <div
              v-for="item in (toutiaoAccounts?.items || []).slice(0, 6)"
              :key="String(item.account_id || item.display_name || JSON.stringify(item))"
              class="mt-2 rounded bg-slate-50 px-3 py-2 text-xs text-slate-600"
            >
              {{ item.account_id || '--' }} / {{ item.display_name || '--' }} / {{ item.logged_in ? 'logged_in' : 'logged_out' }}
            </div>
          </div>
        </div>

        <div v-if="selfMediaJobRuntime?.tenant_state?.git_export" class="mt-4 rounded-lg border border-sky-100 bg-white px-4 py-3 text-sm text-slate-700">
          <div class="font-medium text-slate-900">Gitee 入库运行态</div>
          <div class="mt-2 grid gap-3 md:grid-cols-2">
            <div>
              <div class="text-xs text-slate-500">令牌</div>
              <div class="mt-1 font-medium text-slate-900">{{ selfMediaJobRuntime.tenant_state.git_export.token_available ? '已就绪' : '缺失' }}</div>
            </div>
            <div>
              <div class="text-xs text-slate-500">状态</div>
              <div class="mt-1 font-medium text-slate-900">{{ formatGitExportStatus(selfMediaJobRuntime.tenant_state.git_export.status) }}</div>
            </div>
            <div>
              <div class="text-xs text-slate-500">仓库键</div>
              <div class="mt-1 font-medium text-slate-900">{{ selfMediaJobRuntime.tenant_state.git_export.repo_key || '--' }}</div>
            </div>
            <div>
              <div class="text-xs text-slate-500">分支</div>
              <div class="mt-1 font-medium text-slate-900">{{ selfMediaJobRuntime.tenant_state.git_export.branch || '--' }}</div>
            </div>
          </div>
          <div class="mt-3 text-xs text-slate-500">仓库 {{ selfMediaJobRuntime.tenant_state.git_export.target_repo || '--' }}</div>
          <div class="mt-1 break-all text-xs text-slate-500">链接 {{ selfMediaJobRuntime.tenant_state.git_export.target_url || '--' }}</div>
          <div class="mt-1 text-xs text-slate-500">原因 {{ selfMediaJobRuntime.tenant_state.git_export.reason || '无' }}</div>
          <div class="mt-1 text-xs text-slate-500">下一步 {{ selfMediaJobRuntime.tenant_state.git_export.next_action || '--' }}</div>
          <div v-if="selfMediaJobRuntime.tenant_state.git_export.last_export" class="mt-4 rounded-lg bg-sky-50 px-3 py-3 text-xs text-slate-600">
            <div class="font-medium text-slate-900">最近导出</div>
            <div class="mt-2">任务 {{ selfMediaJobRuntime.tenant_state.git_export.last_export.task_type || '--' }} / {{ selfMediaJobRuntime.tenant_state.git_export.last_export.task_id || '--' }}</div>
            <div class="mt-1">状态 {{ formatGitExportStatus(selfMediaJobRuntime.tenant_state.git_export.last_export.status) }}</div>
            <div class="mt-1">时间 {{ formatDate(selfMediaJobRuntime.tenant_state.git_export.last_export.completed_at) }}</div>
            <div class="mt-1">仓库 {{ selfMediaJobRuntime.tenant_state.git_export.last_export.repo_full_name || '--' }}</div>
            <div class="mt-1 break-all">链接 {{ selfMediaJobRuntime.tenant_state.git_export.last_export.repo_url || '--' }}</div>
            <div class="mt-1">原因 {{ selfMediaJobRuntime.tenant_state.git_export.last_export.reason || '无' }}</div>
            <div v-if="selfMediaJobRuntime.tenant_state.git_export.last_export.files?.length" class="mt-2">
              <div class="text-slate-500">文件</div>
              <div
                v-for="file in selfMediaJobRuntime.tenant_state.git_export.last_export.files.slice(0, 4)"
                :key="file"
                class="mt-1 break-all rounded bg-white px-2 py-1"
              >
                {{ file }}
              </div>
            </div>
          </div>
        </div>

        <div v-if="selfMediaKnowledgeEntries.length" class="mt-4 rounded-lg border border-sky-100 bg-white px-4 py-3 text-sm text-slate-700">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="font-medium text-slate-900">最近知识条目</div>
              <div class="mt-1 text-xs text-slate-500">最近写入 `evo/index.json` 的自媒体沉淀记录。</div>
            </div>
            <div class="text-xs text-slate-500">{{ selfMediaGitRepoKey || 'toutiao' }}</div>
          </div>
          <div class="mt-3 space-y-2">
            <div
              v-for="entry in selfMediaKnowledgeEntries"
              :key="entry.id || `${entry.path}-${entry.title}`"
              class="rounded-lg bg-sky-50 px-3 py-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="font-medium text-slate-900">{{ entry.title || '--' }}</div>
                <div class="rounded-full bg-white px-2 py-1 text-[11px] text-slate-600">{{ entry.type || '--' }}</div>
              </div>
              <div v-if="entry.summary" class="mt-2 text-xs text-slate-600">{{ entry.summary }}</div>
              <div v-if="entry.keywords?.length" class="mt-2 flex flex-wrap gap-2">
                <span
                  v-for="keyword in entry.keywords.slice(0, 5)"
                  :key="`${entry.id}-${keyword}`"
                  class="rounded-full bg-white px-2 py-1 text-[11px] text-slate-600"
                >
                  {{ keyword }}
                </span>
              </div>
              <div class="mt-2 break-all text-[11px] text-slate-500">{{ entry.path || '--' }}</div>
            </div>
          </div>
        </div>

        <div class="mt-4 rounded-lg border border-sky-100 bg-white px-4 py-3 text-sm text-slate-700">
          <div class="font-medium text-slate-900">最近登录会话</div>
          <div v-if="!toutiaoSessions.length" class="mt-2 text-xs text-slate-500">当前还没有登录接管会话</div>
          <div
            v-for="item in toutiaoSessions.slice(0, 5)"
            :key="item.session_id || item.updated_at"
            class="mt-2 rounded bg-slate-50 px-3 py-2 text-xs text-slate-600"
          >
            <div>{{ item.session_id || '--' }} / {{ item.status || '--' }}</div>
            <div class="mt-1 text-slate-500">{{ item.display_name || '--' }} / {{ item.updated_at || '--' }}</div>
          </div>
        </div>
      </div>

          <div v-if="!workerManifestList.length" class="rounded-xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
            当前还没有发现可注册工种。
          </div>
          <div v-else class="space-y-3">
        <div
          v-for="item in workerManifestList"
          :key="item.worker_id"
          class="rounded-xl border border-slate-200 bg-white px-4 py-4"
        >
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <div class="text-sm font-medium text-slate-900">{{ item.title }}</div>
                <span
                  class="rounded-full px-2.5 py-1 text-[11px]"
                  :class="item.source === 'external' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'"
                >
                  {{ item.source === 'external' ? '项目外挂' : '系统内置' }}
                </span>
              </div>
              <div class="mt-1 text-xs text-slate-500">{{ item.worker_id }} / {{ item.capability_type }}</div>
              <div v-if="item.definition_path" class="mt-1 break-all text-[11px] text-slate-400">
                {{ item.definition_path }}
              </div>
            </div>
            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600">
              {{ (workerEnabledDraft[item.worker_id] ?? item.default_enabled) ? '已启用' : '已停用' }}
            </span>
          </div>

          <div class="mt-3 grid gap-3 md:grid-cols-3">
            <div class="rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-600">
              <div class="font-medium text-slate-800">工种范围</div>
              <div class="mt-2 flex flex-wrap gap-2">
                <span
                  v-for="workTypeId in item.work_type_ids"
                  :key="`${item.worker_id}-${workTypeId}`"
                  class="rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-600"
                >
                  {{ workTypeId }}
                </span>
              </div>
            </div>
            <div class="rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-600">
              <div class="font-medium text-slate-800">任务类型</div>
              <div class="mt-2 flex flex-wrap gap-2">
                <span
                  v-for="taskType in item.task_types"
                  :key="`${item.worker_id}-${taskType}`"
                  class="rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-600"
                >
                  {{ taskType }}
                </span>
              </div>
            </div>
            <div class="rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-600">
              <div class="font-medium text-slate-800">运行态</div>
              <div class="mt-2">处理器 {{ workerRegistry?.runtime?.workers?.[item.worker_id]?.handler_count ?? 0 }}</div>
              <div class="mt-1">已注册 {{ workerRegistry?.runtime?.workers?.[item.worker_id] ? '是' : '否' }}</div>
              <div class="mt-1">来源 {{ item.source === 'external' ? '项目外挂' : '系统内置' }}</div>
              <div class="mt-1">模块 {{ item.owned_modules.join(', ') || '--' }}</div>
            </div>
          </div>
        </div>
      </div>
        </div>

        <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div class="mb-3 inline-flex rounded-full bg-violet-100 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-violet-800">
            公司维护
          </div>
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold text-slate-900">公司制度摘要</h2>
              <p class="mt-1 text-sm text-slate-500">共享制度和外部学习边界会直接影响所有孩子，所以不再允许在育成官页双写。</p>
            </div>
            <router-link to="/organization/parent/workspace" class="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
              去公司维护
            </router-link>
          </div>
          <div class="mt-4 grid gap-4 md:grid-cols-2">
            <div class="rounded-xl border border-violet-200 bg-violet-50/60 px-4 py-4 text-sm text-violet-950">
              <div class="font-medium">共享制度</div>
              <div class="mt-2">模式 {{ knowledgePolicy.share_mode || 'private_only' }}</div>
              <div class="mt-1">平台晋升 {{ knowledgePolicy.allow_platform_promotion ? '允许' : '关闭' }}</div>
              <div class="mt-1">审核 {{ knowledgePolicy.review_required ? '必需' : '可跳过' }}</div>
            </div>
            <div class="rounded-xl border border-sky-200 bg-sky-50/60 px-4 py-4 text-sm text-sky-950">
              <div class="font-medium">外部学习边界</div>
              <div class="mt-2">AI {{ externalLearningPolicy.allow_ai_assist ? '允许' : '关闭' }}</div>
              <div class="mt-1">网页 {{ externalLearningPolicy.allow_web_research ? '允许' : '关闭' }}</div>
              <div class="mt-1">企业源 {{ externalLearningPolicy.allow_enterprise_sources ? '允许' : '关闭' }}</div>
              <div class="mt-1">验证 {{ externalLearningPolicy.validation_required ? '必需' : '非必需' }}</div>
            </div>
          </div>
          <div class="mt-4 rounded-xl bg-slate-50 px-4 py-4 text-sm text-slate-700">
            <div class="text-slate-400">来源优先级</div>
            <div class="mt-2 leading-6">{{ externalLearningPolicy.source_priority.join(' -> ') || '--' }}</div>
          </div>
        </div>
      </div>
    </details>

    <TrainerMainlineShell
      :compact="!showTrainerLanding"
      :hide-mode-switcher="!showTrainerLanding"
      :autonomy-identity-message="autonomyIdentityMessage"
      :autonomy-identity-success="autonomyIdentitySuccess"
      :autonomy-loading="autonomyLoading"
      :autonomy-identity-saving="autonomyIdentitySaving"
      :managed-child-members-draft="managedChildMembersDraft"
      :selected-child-member-id="selectedChildMemberId"
      :trainer-member-draft="trainerMemberDraft"
      :trainer-mainline-mode-meta="trainerMainlineModeMeta"
      :trainer-selected-child-name="trainerSelectedChildName"
      :trainer-selected-child-meta="trainerSelectedChildMeta"
      :trainer-formal-task-stage-label="trainerFormalTaskStageLabel"
      :trainer-formal-task-guidance="trainerFormalTaskGuidance"
      :trainer-formal-task-steps="trainerFormalTaskSteps"
      :trainer-mainline-cards="trainerMainlineCards"
      :active-formal-task="activeFormalTask"
      :current-child-workspace-route="selectedChildWorkspaceRoute"
      :format-lifecycle-stage="formatLifecycleStage"
      :select-child-member="selectChildMember"
      :create-child-portrait="createChildPortrait"
      :load-autonomy-status="loadAutonomyStatus"
      :save-autonomy-identity="saveAutonomyIdentity"
      :set-trainer-mainline-mode="setTrainerMainlineMode"
    >
      <TrainerPortraitPanel
        v-show="trainerMainlineMode === 'portrait'"
        :workspace-mode="portraitWorkspaceMode"
        :tenant-id="tenantId"
        :parent-display-name="parentDisplayName"
        :parent-role-label="parentRoleLabel"
        :parent-description="parentDescription"
        :new-child-portrait-name="newChildPortraitName"
        :new-child-portrait-work-type-id="newChildPortraitWorkTypeId"
        :company-work-types="companyWorkTypes"
        :company-work-types-loading="companyWorkTypesLoading"
        :child-members-draft="childMembersDraft"
        :selected-child-member-id="selectedChildMemberId"
        :selected-child-member-draft="selectedChildMemberDraft"
        :active-child-members-draft="activeChildMembersDraft"
        :child-growth-digest-cards="childGrowthDigestCards"
        :child-growth-narrative="childGrowthNarrative"
        :child-growth-priority-queue="childGrowthPriorityQueue"
        :child-member-id="childMemberId"
        :child-name="childName"
        :child-primary-role="childPrimaryRole"
        :child-role-label="childRoleLabel"
        :child-self-description="childSelfDescription"
        :child-long-term-goal="childLongTermGoal"
        :child-speaking-style="childSpeakingStyle"
        :child-interaction-style="childInteractionStyle"
        :child-strengths-text="childStrengthsText"
        :child-shortcomings-text="childShortcomingsText"
        :child-preferred-domains-text="childPreferredDomainsText"
        :child-current-focus="childCurrentFocus"
        :child-next-goal="childNextGoal"
        :child-learning-strategy="childLearningStrategy"
        :child-derived-state="childDerivedState"
        :child-autonomous-plan="childAutonomousPlan"
        :autonomy-status="autonomyStatus"
        :selected-child-lifecycle-summary="selectedChildLifecycleSummary"
        :format-date="formatDate"
        :select-child-member="selectChildMember"
        :go-to-dispatch-for-member="goToTrainerDispatchForMember"
        :archive-selected-child-member="archiveSelectedChildMember"
        :delete-selected-child-member="deleteSelectedChildMember"
        :growth-digest-status-badge-class="growthDigestStatusBadgeClass"
        @update:parent-display-name="parentDisplayName = $event"
        @update:parent-role-label="parentRoleLabel = $event"
        @update:parent-description="parentDescription = $event"
        @update:new-child-portrait-name="newChildPortraitName = $event"
        @update:new-child-portrait-work-type-id="newChildPortraitWorkTypeId = $event"
        @update:child-primary-role="childPrimaryRole = $event"
        @apply-work-type="applyWorkTypeToPortraitDraft"
        @update:child-member-id="childMemberId = $event"
        @update:child-name="childName = $event"
        @update:child-role-label="childRoleLabel = $event"
        @update:child-self-description="childSelfDescription = $event"
        @update:child-long-term-goal="childLongTermGoal = $event"
        @update:child-speaking-style="childSpeakingStyle = $event"
        @update:child-interaction-style="childInteractionStyle = $event"
        @update:child-strengths-text="childStrengthsText = $event"
        @update:child-shortcomings-text="childShortcomingsText = $event"
        @update:child-preferred-domains-text="childPreferredDomainsText = $event"
        @update:child-current-focus="childCurrentFocus = $event"
        @update:child-next-goal="childNextGoal = $event"
        @update:child-learning-strategy="childLearningStrategy = $event"
        @update:workspace-mode="syncTrainerRouteQuery({ mode: 'portrait', portraitTab: $event })"
      />

      <TrainerDispatchPanel
        v-show="trainerMainlineMode === 'dispatch'"
        :workspace-mode="dispatchWorkspaceMode"
        :selected-child-member-id="selectedChildMemberId"
        :selected-child-member-draft="selectedChildMemberDraft"
        :member-knowledge-learning-task="selectedChildKnowledgeLearningTask"
        :validating-knowledge-learning-task-id="validatingLearningTaskId"
        :selected-child-formal-tasks="selectedChildFormalTasks"
        :trainer-formal-task-stage-label="trainerFormalTaskStageLabel"
        :trainer-formal-task-steps="trainerFormalTaskSteps"
        :trainer-formal-task-guidance="trainerFormalTaskGuidance"
        :formal-task-message="formalTaskMessage"
        :formal-task-success="formalTaskSuccess"
        :formal-task-assign-title-draft="formalTaskAssignTitleDraft"
        :formal-task-assign-objective-draft="formalTaskAssignObjectiveDraft"
        :formal-task-assign-deliverables-draft="formalTaskAssignDeliverablesDraft"
        :formal-task-recommendation-hint="formalTaskRecommendationHint"
        :formal-task-assign-work-type-id="formalTaskAssignWorkTypeId"
        :formal-task-assign-mission-kind="formalTaskAssignMissionKind"
        :formal-task-approve-note-draft="formalTaskApproveNoteDraft"
        :formal-task-action-running="formalTaskActionRunning"
        :active-formal-task="activeFormalTask"
        :active-formal-task-recommendation="activeFormalTaskRecommendation"
        :formal-task-git-export-runtime="formalTaskGitExportRuntime"
        :formal-task-git-export-status-class="formalTaskGitExportStatusClass"
        :formal-task-git-export-status-label="formalTaskGitExportStatusLabel"
        :formal-task-git-export-matches-active-task="formalTaskGitExportMatchesActiveTask"
        :formal-task-experience-exporting="formalTaskExperienceExporting"
        :format-date="formatDate"
        :apply-recommended-formal-task-draft="applyRecommendedFormalTaskDraft"
        :assign-formal-task-to-selected-child="assignFormalTaskToSelectedChild"
        :go-to-child-workspace-for-member="goToChildWorkspaceForMember"
        :approve-selected-formal-task="approveSelectedFormalTask"
        :adopt-recommended-formal-task="adoptRecommendedFormalTask"
        :adopt-and-assign-recommended-formal-task="adoptAndAssignRecommendedFormalTask"
        :export-current-tenant-experiences-to-git="exportCurrentTenantExperiencesToGit"
        :validate-member-knowledge-learning="validateSelectedChildKnowledgeLearning"
        :tenant-id="tenantId"
        :child-members-for-collaboration="childMembersDraft"
        :company-work-types="companyWorkTypes"
        :go-to-trainer-dispatch-for-member="goToTrainerDispatchForMember"
        @work-type-saved="onTrainerWorkTypeSaved"
        @update:formal-task-assign-title-draft="formalTaskAssignTitleDraft = $event"
        @update:formal-task-assign-objective-draft="formalTaskAssignObjectiveDraft = $event"
        @update:formal-task-assign-deliverables-draft="formalTaskAssignDeliverablesDraft = $event"
        @update:formal-task-approve-note-draft="formalTaskApproveNoteDraft = $event"
        @update:workspace-mode="syncTrainerRouteQuery({ mode: 'dispatch', dispatchTab: $event })"
        @autonomy-updated="onCollaborationAutonomyUpdated"
      />

      <TrainerReviewPanel
        v-show="trainerMainlineMode === 'review'"
        :workspace-mode="reviewWorkspaceMode"
        :selected-child-member-id="selectedChildMemberId"
        :selected-child-member-draft="selectedChildMemberDraft"
        :selected-child-member-runtime="selectedChildMemberRuntime"
        :selected-child-conversation="selectedChildConversation"
        :child-reply-draft="childReplyDraft"
        :child-reply-sending="childReplySending"
        :learning-task="selectedChildKnowledgeLearningTask"
        :tenant-id="tenantId"
        :validating-knowledge-learning="Boolean(validatingLearningTaskId)"
        :can-validate-knowledge-learning="canValidateSelectedChildKnowledgeLearning"
        :format-date="formatDate"
        :send-child-reply="sendChildReply"
        :relationship-message-card-class="relationshipMessageCardClass"
        :relationship-sender-label="relationshipSenderLabel"
        :relationship-message-badge-class="relationshipMessageBadgeClass"
        :relationship-message-type-label="relationshipMessageTypeLabel"
        @update:child-reply-draft="childReplyDraft = $event"
        @update:workspace-mode="syncTrainerRouteQuery({ mode: 'review', reviewTab: $event })"
        @validate-knowledge="validateSelectedChildKnowledgeLearning"
        @go-dispatch="goToDispatchAfterKnowledge"
        @knowledge-refreshed="onKnowledgePanelRefreshed"
      />

      <TrainerExclusivePanel
        v-show="trainerMainlineMode === 'exclusive'"
        :workspace-mode="exclusiveWorkspaceMode"
        :selected-child-member-draft="selectedChildMemberDraft"
        :selected-child-member-runtime="selectedChildMemberRuntime"
        :autonomy-status="autonomyStatus"
        :training-review-running="trainingReviewRunning"
        :training-review-message="trainingReviewMessage"
        :training-review-success="trainingReviewSuccess"
        :trainer-intent-summary="trainerIntentSummary"
        :trainer-directive-queue="trainerDirectiveQueue"
        :trainer-auto-assist-enabled="trainerAutoAssistEnabled"
        :trainer-batch-running="trainerBatchRunning"
        :trainer-low-risk-suggestion-queue="trainerLowRiskSuggestionQueue"
        :trainer-auto-assist-allowed-take-over="trainerAutoAssistAllowedTakeOver"
        :trainer-auto-assist-allowed-reflection="trainerAutoAssistAllowedReflection"
        :trainer-auto-assist-allowed-stages="trainerAutoAssistAllowedStages"
        :trainer-action-running-id="trainerActionRunningId"
        :talent-development-assignments="talentDevelopmentAssignments"
        :format-date="formatDate"
        :run-training-review="runTrainingReview"
        :run-trainer-low-risk-suggestion-batch="runTrainerLowRiskSuggestionBatch"
        :select-child-member="selectChildMember"
        :handle-trainer-suggested-action="handleTrainerSuggestedAction"
        :handle-trainer-directive-action="handleTrainerDirectiveAction"
        :handle-trainer-directive-review="handleTrainerDirectiveReview"
        :trainer-queue-status-badge-class="trainerQueueStatusBadgeClass"
        @update:trainer-auto-assist-enabled="trainerAutoAssistEnabled = $event"
        @update:trainer-auto-assist-allowed-take-over="trainerAutoAssistAllowedTakeOver = $event"
        @update:trainer-auto-assist-allowed-reflection="trainerAutoAssistAllowedReflection = $event"
        @update:trainer-auto-assist-allowed-stages="trainerAutoAssistAllowedStages = $event"
        @update:workspace-mode="syncTrainerRouteQuery({ mode: 'exclusive', exclusiveTab: $event })"
      />
    </TrainerMainlineShell>

    <details class="rounded-2xl border border-slate-200 bg-slate-50/70">
      <summary class="cursor-pointer list-none px-5 py-4">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div class="text-sm font-semibold text-slate-900">辅助观察</div>
            <div class="mt-1 text-sm text-slate-500">这里放当前岗位运行态和父节点沟通，帮助育成判断，但不压在主工作区前面。</div>
            <div class="mt-3 flex flex-wrap gap-2 text-[11px]">
              <span class="rounded-full bg-white px-2.5 py-1 text-slate-600">岗位运行 {{ childCurrentJobs.length }}</span>
              <span class="rounded-full bg-white px-2.5 py-1 text-slate-600">父节点消息 {{ parentInboxMessages.length }}</span>
              <span class="rounded-full bg-white px-2.5 py-1 text-slate-600">当前对象 {{ selectedChildMemberId || '未选中' }}</span>
            </div>
          </div>
          <div class="rounded-full bg-white px-3 py-1 text-[11px] text-slate-600">
            辅助
          </div>
        </div>
      </summary>

      <div class="space-y-6 border-t border-slate-200 px-5 py-5">
        <div v-if="childCurrentJobs.length" class="grid gap-3 md:grid-cols-2">
          <div
            v-for="job in childCurrentJobs"
            :key="job.job_id || job.title"
            class="rounded-xl border border-slate-200 bg-white px-4 py-4 text-sm text-slate-700"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="font-medium text-slate-900">{{ job.title || job.job_id }}</div>
                <div class="mt-1 text-xs text-slate-500">{{ job.job_id || '--' }} / {{ job.priority || '--' }}</div>
              </div>
              <div class="text-xs text-slate-500">{{ formatJobStatus(job.runtime_state?.status || job.status) }}</div>
            </div>
            <div class="mt-3 text-sm text-slate-600">目标：{{ job.target_outcome || '--' }}</div>
            <div class="mt-2 text-xs text-slate-500">下一步：{{ job.runtime_state?.next_action || '--' }}</div>
            <div v-if="job.runtime_state?.blocked_reason" class="mt-1 text-xs text-rose-600">阻塞：{{ job.runtime_state.blocked_reason }}</div>
            <div v-if="job.runtime_state?.signals?.length" class="mt-2 flex flex-wrap gap-2">
              <span
                v-for="signal in job.runtime_state.signals"
                :key="`${job.job_id}-${signal}`"
                class="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600"
              >
                {{ signal }}
              </span>
            </div>
            <div v-if="job.runtime_state?.tenant_state" class="mt-3 grid gap-3 md:grid-cols-2">
              <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-600">
                <div class="font-medium text-slate-900">运行进度</div>
                <div class="mt-2">阶段 {{ formatLifecycleStage(job.runtime_state.tenant_state.stage) }}</div>
                <div class="mt-1">登录 {{ job.runtime_state.tenant_state.login_status || '--' }}</div>
                <div class="mt-1">内容 {{ job.runtime_state.tenant_state.last_article_title || '--' }}</div>
                <div class="mt-1">分析 {{ (job.runtime_state.tenant_state.analytics_completed_types || []).join(', ') || '--' }}</div>
                <div class="mt-1">检查时间 {{ formatDate(job.runtime_state.tenant_state.last_checked_at) }}</div>
              </div>
              <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-600">
                <div class="font-medium text-slate-900">经验入库</div>
                <div class="mt-2">状态 {{ formatGitExportStatus(job.runtime_state.tenant_state.git_export?.status) }}</div>
                <div class="mt-1">令牌 {{ job.runtime_state.tenant_state.git_export?.token_available ? '已就绪' : '缺失' }}</div>
                <div class="mt-1">仓库键 {{ job.runtime_state.tenant_state.git_export?.repo_key || '--' }}</div>
                <div class="mt-1">目标仓库 {{ job.runtime_state.tenant_state.git_export?.target_repo || '--' }}</div>
                <div class="mt-1">分支 {{ job.runtime_state.tenant_state.git_export?.branch || '--' }}</div>
                <div class="mt-1 break-all">链接 {{ job.runtime_state.tenant_state.git_export?.target_url || '--' }}</div>
                <div class="mt-1 text-amber-700">下一步 {{ job.runtime_state.tenant_state.git_export?.next_action || '--' }}</div>
                <div v-if="job.runtime_state.tenant_state.git_export?.last_export" class="mt-2 rounded bg-white px-2 py-2">
                  <div>最近导出 {{ job.runtime_state.tenant_state.git_export.last_export.task_type || '--' }}</div>
                  <div class="mt-1">结果 {{ job.runtime_state.tenant_state.git_export.last_export.status || '--' }}</div>
                  <div class="mt-1">时间 {{ formatDate(job.runtime_state.tenant_state.git_export.last_export.completed_at) }}</div>
                  <div class="mt-1 break-all">仓库 {{ job.runtime_state.tenant_state.git_export.last_export.repo_full_name || '--' }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <ParentInboxPanel
          :parent-directive-type="parentDirectiveType"
          :parent-directive-templates="parentDirectiveTemplates"
          :trainer-member-draft="trainerMemberDraft"
          :selected-child-member-draft="selectedChildMemberDraft"
          :selected-child-member-id="selectedChildMemberId"
          :parent-message-draft="parentMessageDraft"
          :parent-directive-preview="parentDirectivePreview"
          :parent-message-sending="parentMessageSending"
          :parent-inbox-messages="parentInboxMessages"
          :selected-parent-directive-receipt="selectedParentDirectiveReceipt"
          :format-date="formatDate"
          :send-parent-message="sendParentMessage"
          :directive-receipt-verdict-badge-class="directiveReceiptVerdictBadgeClass"
          :parent-inbox-message-card-class="parentInboxMessageCardClass"
          :parent-inbox-message-badge-class="parentInboxMessageBadgeClass"
          :parent-inbox-message-type-label="parentInboxMessageTypeLabel"
          @update:parent-directive-type="parentDirectiveType = $event"
          @update:parent-message-draft="parentMessageDraft = $event"
        />
      </div>
    </details>

    <details class="rounded-2xl border border-slate-200 bg-slate-50/70">
      <summary class="cursor-pointer list-none px-5 py-4">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div class="text-sm font-semibold text-slate-900">成长档案与研究</div>
            <div class="mt-1 text-sm text-slate-500">这里看自治状态、学习任务和长期档案，用来支持下一轮带教判断。</div>
            <div class="mt-3 flex flex-wrap gap-2 text-[11px]">
              <span class="rounded-full bg-white px-2.5 py-1 text-slate-600">学习任务 {{ learningTasks.length }}</span>
              <span class="rounded-full bg-white px-2.5 py-1 text-slate-600">成长时间线 {{ growthTimeline.length }}</span>
              <span class="rounded-full bg-white px-2.5 py-1 text-slate-600">待复核 {{ reviewQueueTop.length }}</span>
            </div>
          </div>
          <div class="rounded-full bg-white px-3 py-1 text-[11px] text-slate-600">
            辅助
          </div>
        </div>
      </summary>

      <div class="space-y-6 border-t border-slate-200 px-5 py-5">
        <AutonomyStatusPanel
          :autonomy-loading="autonomyLoading"
          :autonomy-status="autonomyStatus"
          :autonomy-entries="autonomyEntries"
          :format-score="formatScore"
          :format-signed="formatSigned"
          :load-autonomy-status="loadAutonomyStatus"
        />

        <LearningTasksPanel
          :learning-tasks-loading="learningTasksLoading"
          :learning-tasks="learningTasks"
          :validating-learning-task-id="validatingLearningTaskId"
          :learning-task-message="learningTaskMessage"
          :format-date="formatDate"
          :format-score="formatScore"
          :format-delta="formatDelta"
          :comparison-badge-class="comparisonBadgeClass"
          :load-learning-tasks="loadLearningTasks"
          :trigger-learning-task-validation="triggerLearningTaskValidation"
        />

        <EvolutionArchivePanel
          :evolution-loading="evolutionLoading"
          :evolution-overview="evolutionOverview"
          :growth-timeline="growthTimeline"
          :review-queue-top="reviewQueueTop"
          :format-date="formatDate"
          :format-score="formatScore"
          :format-delta="formatDelta"
          :load-evolution-overview="loadEvolutionOverview"
        />
      </div>
    </details>

    <details class="rounded-2xl border border-slate-200 bg-slate-50/70">
      <summary class="cursor-pointer list-none px-5 py-4">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div class="text-sm font-semibold text-slate-900">平台基础设施</div>
            <div class="mt-1 text-sm text-slate-500">冷启动种子、平台共享经验和 Git 知识仓属于基础设施，按需展开即可。</div>
            <div class="mt-3 flex flex-wrap gap-2 text-[11px]">
              <span class="rounded-full bg-white px-2.5 py-1 text-slate-600">冷启动建议 {{ seedRecommendations?.items?.length || 0 }}</span>
              <span class="rounded-full bg-white px-2.5 py-1 text-slate-600">知识仓条目 {{ selfMediaKnowledgeEntries.length }}</span>
              <span class="rounded-full bg-white px-2.5 py-1 text-slate-600">Git 仓库 {{ Object.keys(gitStatus?.git_knowledge?.repos || {}).length }}</span>
            </div>
          </div>
          <div class="rounded-full bg-white px-3 py-1 text-[11px] text-slate-600">
            辅助
          </div>
        </div>
      </summary>

      <div class="space-y-6 border-t border-slate-200 px-5 py-5">
        <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
          <div class="flex items-start justify-between gap-4 mb-4">
            <div>
              <h2 class="text-lg font-semibold">平台冷启动种子</h2>
              <p class="text-slate-500 text-sm mt-1">把平台共享层里已经验证过的策略，作为当前租户的起步经验注入，但仍保留租户私有成长空间。</p>
            </div>
            <div class="text-right text-sm text-slate-500">
              <div>租户 {{ tenantId || 'default' }}</div>
              <div class="mt-1">冷启动: {{ seedRecommendations?.is_cold_start ? '是' : '否' }}</div>
            </div>
          </div>

          <div class="flex gap-3 mb-4">
            <button
              @click="loadPlatformSeeds"
              :disabled="seedLoading"
              class="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              {{ seedLoading ? '加载中...' : '刷新平台种子' }}
            </button>
            <button
              @click="applyRecommendedSeeds"
              :disabled="seedApplying || !seedRecommendations?.items?.length"
              class="px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-60"
            >
              {{ seedApplying ? '应用中...' : '一键应用推荐种子' }}
            </button>
          </div>

          <p v-if="seedMessage" class="mb-4 text-sm" :class="seedSuccess ? 'text-green-600' : 'text-red-600'">
            {{ seedMessage }}
          </p>

          <div v-if="!seedRecommendations?.items?.length" class="rounded-xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
            当前没有可用于当前租户的共享冷启动种子。
          </div>
          <div v-else class="space-y-3">
            <div
              v-for="item in seedRecommendations.items"
              :key="item.strategy_id"
              class="rounded-xl border border-indigo-100 bg-indigo-50/40 px-4 py-4"
            >
              <div class="flex items-start justify-between gap-4">
                <div>
                  <div class="text-sm font-medium text-slate-900">{{ item.title }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ item.strategy_id }}</div>
                </div>
                <div class="text-right text-xs text-slate-500">
                  <div>推荐分 {{ item.score.toFixed(2) }}</div>
                  <div class="mt-1">{{ item.promoted_at?.replace('T', ' ').slice(0, 19) || '--' }}</div>
                </div>
              </div>
              <div class="mt-3 text-sm text-slate-600">{{ item.summary }}</div>
              <div class="mt-3 flex flex-wrap gap-2">
                <span class="rounded-full bg-white px-2.5 py-1 text-xs text-slate-500">
                  来源租户 {{ item.source_tenant_id || '--' }}
                </span>
                <span class="rounded-full bg-white px-2.5 py-1 text-xs text-slate-500">
                  decision {{ item.decision || '--' }}
                </span>
                <span class="rounded-full bg-white px-2.5 py-1 text-xs text-slate-500">
                  weight {{ item.recommended_override.weight_delta }}
                </span>
                <span class="rounded-full bg-white px-2.5 py-1 text-xs text-slate-500">
                  preferred {{ item.recommended_override.preferred ? 'yes' : 'no' }}
                </span>
              </div>
              <ul class="mt-3 space-y-1 text-sm text-slate-600">
                <li v-for="reason in item.reasons" :key="reason">• {{ reason }}</li>
              </ul>
            </div>
          </div>
        </div>

        <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
          <div class="flex items-start justify-between gap-4 mb-4">
            <div>
              <h2 class="text-lg font-semibold">Git Knowledge Layer</h2>
              <p class="text-slate-500 text-sm mt-1">为当前租户初始化独立的 skills / experiences / strategies / reports / config 仓库。</p>
            </div>
            <div class="min-w-52">
              <label class="block text-xs uppercase tracking-[0.18em] text-slate-400 mb-2">Repo Base</label>
              <input
                v-model="repoBaseName"
                type="text"
                class="w-full px-3 py-2 border rounded-lg"
                :placeholder="`evo-${tenantId}`"
              >
            </div>
          </div>

          <div class="grid gap-3 md:grid-cols-2 mb-4">
            <div>
              <label class="block text-xs uppercase tracking-[0.18em] text-slate-400 mb-2">Git Provider</label>
              <select v-model="gitProvider" class="w-full px-3 py-2 border rounded-lg bg-white">
                <option value="gitee">gitee</option>
                <option value="gitlab">gitlab</option>
              </select>
            </div>
            <div>
              <label class="block text-xs uppercase tracking-[0.18em] text-slate-400 mb-2">Namespace</label>
              <input
                v-model="gitNamespace"
                type="text"
                class="w-full px-3 py-2 border rounded-lg"
                placeholder="企业组/用户名，可留空"
              >
            </div>
            <div>
              <label class="block text-xs uppercase tracking-[0.18em] text-slate-400 mb-2">API Base</label>
              <input
                v-model="gitApiBase"
                type="text"
                class="w-full px-3 py-2 border rounded-lg"
                :placeholder="gitProvider === 'gitlab' ? 'https://gitlab.example.com/api/v4' : 'https://gitee.com/api/v5'"
              >
            </div>
            <div>
              <label class="block text-xs uppercase tracking-[0.18em] text-slate-400 mb-2">Base URL</label>
              <input
                v-model="gitBaseUrl"
                type="text"
                class="w-full px-3 py-2 border rounded-lg"
                :placeholder="gitProvider === 'gitlab' ? 'https://gitlab.example.com' : 'https://gitee.com'"
              >
            </div>
          </div>

          <div class="flex gap-3 mb-4">
            <button
              @click="loadGitStatus"
              :disabled="gitLoading"
              class="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              {{ gitLoading ? '加载中...' : '刷新 Git 状态' }}
            </button>
            <button
              @click="bootstrapGitKnowledge"
              :disabled="gitBootstrapping"
              class="px-4 py-2 rounded-lg bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-60"
            >
              {{ gitBootstrapping ? '初始化中...' : '初始化知识仓库' }}
            </button>
            <button
              @click="loadGitIndexTemplate"
              :disabled="gitTemplateLoading"
              class="px-4 py-2 rounded-lg border border-amber-300 text-amber-800 hover:bg-amber-50 disabled:opacity-60"
            >
              {{ gitTemplateLoading ? '生成中...' : '生成索引模板' }}
            </button>
            <button
              @click="scanGitKnowledge"
              :disabled="gitScanning"
              class="px-4 py-2 rounded-lg bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {{ gitScanning ? '扫描中...' : '扫描企业仓索引' }}
            </button>
            <button
              @click="exportGitIndexTemplate"
              :disabled="gitTemplateExporting"
              class="px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-60"
            >
              {{ gitTemplateExporting ? '写入中...' : '一键写入索引模板' }}
            </button>
          </div>

          <p v-if="gitMessage" class="mb-4 text-sm" :class="gitSuccess ? 'text-green-600' : 'text-red-600'">
            {{ gitMessage }}
          </p>

          <div class="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
            <div>Provider: {{ gitStatus?.provider || '--' }}</div>
            <div class="mt-1">用户 Token: {{ gitStatus?.has_user_token ? '已绑定' : '未绑定' }}</div>
            <div class="mt-1">Tenant: {{ tenantId || 'default' }}</div>
            <div class="mt-1">Namespace: {{ gitStatus?.git_knowledge?.namespace || '--' }}</div>
            <div class="mt-1">索引仓数: {{ gitStatus?.repo_index_summary?.indexed_repo_count || 0 }} / {{ gitStatus?.repo_index_summary?.repo_count || 0 }}</div>
            <div class="mt-1">索引条目: {{ gitStatus?.repo_index_summary?.total_entries || 0 }}</div>
          </div>

          <div v-if="gitStatus?.git_knowledge?.repos" class="mt-4 grid gap-3 md:grid-cols-2">
            <div
              v-for="(repo, key) in gitStatus.git_knowledge.repos"
              :key="key"
              class="rounded-xl border border-slate-200 bg-white px-4 py-3"
            >
              <div class="text-sm font-medium text-slate-900">{{ key }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ repo.full_name }}</div>
              <a :href="repo.url" target="_blank" class="mt-2 inline-block text-xs text-teal-600 hover:text-teal-800">
                打开仓库
              </a>
            </div>
          </div>

          <div class="mt-4 grid gap-4 lg:grid-cols-[1.1fr_1fr]">
            <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-sm font-medium text-slate-900">企业索引状态</div>
                  <div class="mt-1 text-xs text-slate-500">区分“仓库已配置”和“索引已命中”，避免后台以为有企业知识，实际却读不到。</div>
                </div>
                <div class="text-right text-xs text-slate-500">
                  <div>更新 {{ formatDate(gitStatus?.repo_index_summary?.updated_at) }}</div>
                </div>
              </div>

              <div v-if="!(gitStatus?.repo_index_summary?.repos || []).length" class="mt-4 rounded-lg bg-white px-4 py-6 text-sm text-slate-500">
                还没有扫描结果。先生成模板，写入 `evo/index.json`，再执行扫描。
              </div>
              <div v-else class="mt-4 space-y-3">
                <div
                  v-for="repo in gitStatus?.repo_index_summary?.repos || []"
                  :key="repo.repo_key"
                  class="rounded-lg bg-white px-4 py-3 text-sm text-slate-600"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div class="font-medium text-slate-900">{{ repo.repo_key }}</div>
                    <div
                      class="rounded-full px-2.5 py-1 text-[11px] font-medium"
                      :class="repo.entry_count > 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'"
                    >
                      {{ repo.entry_count > 0 ? '已索引' : '仅配置未命中' }}
                    </div>
                  </div>
                  <div class="mt-2 text-xs text-slate-500">index: {{ repo.index_path || '--' }}</div>
                  <div class="mt-1 text-xs text-slate-500">entries: {{ repo.entry_count }} / scanned {{ formatDate(repo.scanned_at) }}</div>
                </div>
              </div>

              <div v-if="gitScanErrors.length" class="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                <div class="font-medium">扫描异常</div>
                <ul class="mt-2 space-y-1 text-xs">
                  <li v-for="item in gitScanErrors" :key="`${item.repo_key}-${item.error}`">• {{ item.repo_key }} / {{ item.error }}</li>
                </ul>
              </div>

              <div v-if="selfMediaKnowledgeEntries.length" class="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-4">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <div class="text-sm font-medium text-slate-900">自媒体最新入库</div>
                    <div class="mt-1 text-xs text-slate-500">从 `{{ selfMediaGitRepoKey || 'toutiao' }}` 仓索引里提取最近记录。</div>
                  </div>
                  <div class="text-xs text-slate-500">{{ selfMediaKnowledgeEntries.length }} shown</div>
                </div>
                <div class="mt-3 space-y-2">
                  <div
                    v-for="entry in selfMediaKnowledgeEntries"
                    :key="`git-entry-${entry.id || entry.path || entry.title}`"
                    class="rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-600"
                  >
                    <div class="flex items-start justify-between gap-3">
                      <div class="font-medium text-slate-900">{{ entry.title || '--' }}</div>
                      <div class="text-[11px] text-slate-500">{{ entry.type || '--' }}</div>
                    </div>
                    <div v-if="entry.summary" class="mt-2 text-xs text-slate-600">{{ entry.summary }}</div>
                    <div class="mt-2 break-all text-[11px] text-slate-500">{{ entry.path || '--' }}</div>
                  </div>
                </div>
              </div>
            </div>

            <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-sm font-medium text-slate-900">`evo/index.json` 模板</div>
                  <div class="mt-1 text-xs text-slate-500">自动从当前租户的本地技能、成长轨迹、策略复盘和学习任务中抽出一批高价值摘要。</div>
                </div>
                <div class="text-right text-xs text-slate-500">
                  <div>{{ gitIndexTemplate?.template?.entries?.length || 0 }} entries</div>
                </div>
              </div>

              <div class="mt-4 grid gap-3 md:grid-cols-2">
                <div>
                  <label class="block text-xs uppercase tracking-[0.18em] text-slate-400 mb-2">目标 Repo</label>
                  <select v-model="gitIndexRepoKey" class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
                    <option
                      v-for="(repo, key) in gitStatus?.git_knowledge?.repos || {}"
                      :key="key"
                      :value="key"
                    >
                      {{ key }} / {{ repo.full_name }}
                    </option>
                  </select>
                </div>
                <div class="rounded-lg bg-white px-4 py-3 text-xs text-slate-500">
                  默认写入 `evo/index.json`
                </div>
              </div>

              <div v-if="gitIndexTemplate?.template" class="mt-4">
                <div class="rounded-lg bg-white px-4 py-3 text-xs text-slate-500">
                  可以直接点“一键写入索引模板”，系统会把模板提交到目标仓库的 `evo/index.json`，并尝试刷新本地索引状态。
                </div>
                <pre class="mt-3 max-h-[24rem] overflow-auto rounded-lg bg-slate-950 p-4 text-xs leading-6 text-slate-100">{{ gitIndexTemplateText }}</pre>
              </div>
              <div v-else class="mt-4 rounded-lg bg-white px-4 py-6 text-sm text-slate-500">
                点击“生成索引模板”后，这里会显示可直接落仓的示例内容。
              </div>
            </div>
          </div>
        </div>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import WorkspaceSubNav from '../components/shell/WorkspaceSubNav.vue'
import type { WorkspaceSubNavItem } from '../components/shell/WorkspaceSubNav.vue'
import { companyConsoleKey } from '../composables/companyConsole'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import AutonomyStatusPanel from '../components/AutonomyStatusPanel.vue'
import EvolutionArchivePanel from '../components/EvolutionArchivePanel.vue'
import LearningTasksPanel from '../components/LearningTasksPanel.vue'
import ParentInboxPanel from '../components/ParentInboxPanel.vue'
import TrainerDispatchPanel from '../components/TrainerDispatchPanel.vue'
import TrainerExclusivePanel from '../components/TrainerExclusivePanel.vue'
import TrainerMainlineShell from '../components/TrainerMainlineShell.vue'
import TrainerPortraitPanel from '../components/TrainerPortraitPanel.vue'
import TrainerReviewPanel from '../components/TrainerReviewPanel.vue'
import {
  beginToutiaoLogin,
  confirmToutiaoLogin,
  getToutiaoAccounts,
  getToutiaoHandoffInfo,
  getToutiaoSessions,
  launchToutiaoLogin,
  logoutToutiaoLogin,
  updateToutiaoAccount,
  type ToutiaoAccountsPayload,
  type ToutiaoLoginSession,
} from '../api/selfMedia'
import {
  bootstrapTenantGitKnowledge,
  exportGitKnowledgeIndexTemplate,
  getGitKnowledgeIndexTemplate,
  getGitProviderStatus,
  scanTenantGitKnowledge,
  type GitKnowledgeConfig,
  type GitKnowledgeRepoIndex,
  type GitKnowledgeRepoIndexSummary,
  type RepoIndexEntry,
} from '../api/git'
import { exportTenantExperiences } from '../api/knowledge'
import { listMissionTemplates, type MissionTemplate } from '../api/missions'
import { getWorkTypes, type WorkTypeItem } from '../api/workTypes'
import {
  buildFormalTaskRecommendation,
  formatFormalTaskRecommendationHint,
  resolveMemberWorkTypeId,
  type FormalTaskRecommendation,
} from '../utils/formalTaskRecommendation'
import { findMemberKnowledgeLearningTask } from '../utils/memberEvolutionView'
import {
  approveAutonomyTask,
  assignAutonomyTask,
  applyPlatformSharedSeeds,
  createAutonomyMember,
  getAutonomyLearningTasks,
  getAutonomyStatus,
  getEvolutionOverview,
  getWorkerRegistry,
  getPlatformSharedSeeds,
  postChildRelationshipReply,
  postParentRelationshipMessage,
  postTrainerRelationshipAction,
  runAutonomyTrainingReview,
  getTenantExternalLearningPolicy,
  getTenantKnowledgePolicy,
  getTenantPluginPolicy,
  type AutonomyFormalTask,
  type AutonomyFormalTaskRecommendation,
  type EvolutionOverview,
  type LearningTask,
  listPlugins,
  type AutonomyStatus,
  type ChildMemberRuntimeProfile,
  type PlatformSharedSeedItem,
  type TenantExternalLearningPolicy,
  type TenantKnowledgePolicy,
  type WorkerRegistryPayload,
  updateAutonomyIdentity,
  updateSelfMediaExecutorConfig,
  validateLearningTask,
  type PluginItem,
} from '../api/plugins'

const route = useRoute()
const router = useRouter()
const consoleCtx = inject(companyConsoleKey)

const showTrainerLanding = computed(() => {
  const mode = String(route.query.mode || '').trim()
  return !['portrait', 'dispatch', 'review', 'exclusive'].includes(mode)
})

const trainerLandingRoute = computed(() => {
  const member = String(route.query.member || '').trim()
  return {
    path: '/organization/trainer/talent_development_officer/workspace',
    query: member ? { member } : {},
  }
})

const tenantId = ref(localStorage.getItem('tenant_id') || 'default')
const plugins = ref<PluginItem[]>([])
const enabledPlugins = ref<string[]>([])
const disabledPlugins = ref<string[]>([])
const pluginsLoading = ref(false)
const policyMessage = ref('')
const policySuccess = ref(false)
const gitLoading = ref(false)
const gitBootstrapping = ref(false)
const gitScanning = ref(false)
const gitTemplateLoading = ref(false)
const gitTemplateExporting = ref(false)
const gitMessage = ref('')
const gitSuccess = ref(false)
const gitStatus = ref<{
  provider: string
  has_user_token: boolean
  git_knowledge: GitKnowledgeConfig
  repo_index: GitKnowledgeRepoIndex
  repo_index_summary: GitKnowledgeRepoIndexSummary
} | null>(null)
const gitIndexTemplate = ref<{
  tenant_id: string
  template: {
    schema_version: string
    tenant_id: string
    generated_at: string
    description?: string
    entries: RepoIndexEntry[]
  }
  repo_index: GitKnowledgeRepoIndex
  repo_index_summary: GitKnowledgeRepoIndexSummary
} | null>(null)
const gitScanErrors = ref<Array<{ repo_key: string; error: string }>>([])
const repoBaseName = ref('')
const gitIndexRepoKey = ref('config')
const gitProvider = ref('gitee')
const gitApiBase = ref('')
const gitBaseUrl = ref('')
const gitNamespace = ref('')
const knowledgePolicyLoading = ref(false)
const knowledgePolicyMessage = ref('')
const knowledgePolicySuccess = ref(false)
const knowledgePolicy = ref<TenantKnowledgePolicy>({
  share_mode: 'private_only',
  allow_platform_promotion: false,
  review_required: true,
})
const externalLearningPolicyLoading = ref(false)
const externalLearningPolicyMessage = ref('')
const externalLearningPolicySuccess = ref(false)
const externalLearningPolicy = ref<TenantExternalLearningPolicy>({
  allow_ai_assist: true,
  allow_web_research: true,
  allow_enterprise_sources: true,
  source_priority: ['local_memory', 'platform_shared', 'enterprise_repo', 'official_docs', 'web_search', 'ai_assist'],
  validation_required: true,
})
const seedLoading = ref(false)
const seedApplying = ref(false)
const seedMessage = ref('')
const seedSuccess = ref(false)
const seedRecommendations = ref<{
  tenant_id: string
  is_cold_start: boolean
  current_override_count: number
  items: PlatformSharedSeedItem[]
} | null>(null)
const autonomyLoading = ref(false)
const autonomyStatus = ref<AutonomyStatus | null>(null)
const autonomyIdentitySaving = ref(false)
const autonomyIdentityMessage = ref('')
const autonomyIdentitySuccess = ref(false)
const trainingReviewRunning = ref(false)
const trainingReviewMessage = ref('')
const trainingReviewSuccess = ref(false)
const trainerActionRunningId = ref('')
const trainerAutoAssistEnabled = ref(localStorage.getItem('trainer_auto_assist_enabled') === '1')
const trainerBatchRunning = ref(false)
const trainerAutoAssistLastSignature = ref('')
const trainerAutoAssistAllowedTakeOver = ref(localStorage.getItem('trainer_auto_assist_allowed_take_over') !== '0')
const trainerAutoAssistAllowedReflection = ref(localStorage.getItem('trainer_auto_assist_allowed_reflection') !== '0')
const trainerAutoAssistAllowedStages = ref<string[]>(
  (localStorage.getItem('trainer_auto_assist_allowed_stages') || 'profile_initialized,active_training')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean),
)
const parentMessageDraft = ref('')
const parentDirectiveType = ref('stabilize_current_path')
const parentMessageSending = ref(false)
const childReplyDraft = ref('')
const childReplySending = ref(false)
const formalTaskAssignTitleDraft = ref('')
const formalTaskAssignObjectiveDraft = ref('')
const formalTaskAssignDeliverablesDraft = ref('完成第一篇可发布内容\n提交执行结果与复盘\n沉淀下一轮优化点')
const formalTaskAssignMissionKind = ref('')
const formalTaskAssignWorkTypeId = ref('')
const formalTaskRecommendationHint = ref('')
const missionTemplates = ref<MissionTemplate[]>([])
const formalTaskApproveNoteDraft = ref('')
const formalTaskActionRunning = ref<'assign' | 'submit' | 'approve' | ''>('')
const formalTaskMessage = ref('')
const formalTaskSuccess = ref(false)
const formalTaskExperienceExporting = ref(false)
const parentDisplayName = ref('')
const parentRoleLabel = ref('父节点')
const parentDescription = ref('')
const selectedChildMemberId = ref('')
const childMembersDraft = ref<ChildMemberRuntimeProfile[]>([])
const newChildPortraitName = ref('')
const newChildPortraitWorkTypeId = ref('')
const companyWorkTypes = ref<WorkTypeItem[]>([])
const companyWorkTypesLoading = ref(false)
const childMemberId = ref('')
const childName = ref('')
const childPrimaryRole = ref('')
const childRoleLabel = ref('')
const childSelfDescription = ref('')
const childLongTermGoal = ref('')
const childSpeakingStyle = ref('')
const childInteractionStyle = ref('')
const childStrengthsText = ref('')
type TrainerMainlineMode = 'portrait' | 'dispatch' | 'review' | 'exclusive'
type PortraitWorkspaceMode = 'summary' | 'members' | 'identity' | 'state'
type DispatchWorkspaceMode = 'summary' | 'assign' | 'confirm' | 'collaboration'
type ReviewWorkspaceMode = 'conversation' | 'professional' | 'diagnosis' | 'knowledge'
type ExclusiveWorkspaceMode = 'overview' | 'queue' | 'automation' | 'growth'

const trainerMainlineMode = ref<TrainerMainlineMode>('portrait')
const portraitWorkspaceMode = ref<PortraitWorkspaceMode>('summary')
const dispatchWorkspaceMode = ref<DispatchWorkspaceMode>('summary')
const reviewWorkspaceMode = ref<ReviewWorkspaceMode>('conversation')
const exclusiveWorkspaceMode = ref<ExclusiveWorkspaceMode>('overview')
const childShortcomingsText = ref('')
const childPreferredDomainsText = ref('')
const childCurrentFocus = ref('')
const childNextGoal = ref('')
const childLearningStrategy = ref('')
const workerRegistryLoading = ref(false)
const workerRegistryMessage = ref('')
const workerRegistrySuccess = ref(false)
const workerRegistry = ref<WorkerRegistryPayload | null>(null)
const workerEnabledDraft = ref<Record<string, boolean>>({})
const selfMediaExecutorSaving = ref(false)
const selfMediaExecutorModeDraft = ref('auto')
const selfMediaExecutorDirDraft = ref('')
const selfMediaExecutorLoginTargetUrlDraft = ref('')
const toutiaoAccountLoading = ref(false)
const toutiaoAccountSaving = ref(false)
const toutiaoAccountMessage = ref('')
const toutiaoAccountSuccess = ref(false)
const toutiaoAccountId = ref('default')
const toutiaoAccountDisplayName = ref('')
const toutiaoAccountProfileUrl = ref('')
const toutiaoAccountNotes = ref('')
const toutiaoLoginTargetUrl = ref('')
const toutiaoAccounts = ref<ToutiaoAccountsPayload | null>(null)
const toutiaoSessions = ref<ToutiaoLoginSession[]>([])
const learningTasksLoading = ref(false)
const learningTasks = ref<LearningTask[]>([])
const evolutionLoading = ref(false)
const evolutionOverview = ref<EvolutionOverview | null>(null)
const validatingLearningTaskId = ref('')
const learningTaskMessage = ref('')

const enabledSet = computed(() => new Set(enabledPlugins.value))
const disabledSet = computed(() => new Set(disabledPlugins.value))
const workerManifestList = computed(() => (
  Object.values(workerRegistry.value?.manifests || {})
    .sort((a, b) => {
      const sourceOrder = (value?: string) => value === 'external' ? 1 : 0
      const sourceDiff = sourceOrder(a.source) - sourceOrder(b.source)
      if (sourceDiff !== 0) return sourceDiff
      return a.worker_id.localeCompare(b.worker_id)
    })
))
const enabledWorkerCount = computed(() => Object.values(workerEnabledDraft.value).filter(Boolean).length)
const externalWorkerCount = computed(() => workerManifestList.value.filter((item) => item.source === 'external').length)
const runtimeWorkerCount = computed(() => Object.keys(workerRegistry.value?.runtime?.workers || {}).length)
const autonomyEntries = computed(() => {
  const result: Array<{
    tenantId: string
    sourceDir: string
    diagnosis: NonNullable<AutonomyStatus['samples']>[string][string]['diagnosis']
  }> = []
  const samples = autonomyStatus.value?.samples || {}
  for (const [tenantId, tenantSamples] of Object.entries(samples)) {
    for (const [sourceDir, item] of Object.entries(tenantSamples || {})) {
      result.push({
        tenantId,
        sourceDir,
        diagnosis: item?.diagnosis,
      })
    }
  }
  return result
})
const formatScore = (value?: number | null) => typeof value === 'number' ? value.toFixed(2) : '--'
const formatDelta = (value?: number | null) => {
  if (typeof value !== 'number') return '--'
  return value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2)
}
const formatSigned = (value: unknown) => {
  const number = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(number)) return '--'
  return number > 0 ? `+${number.toFixed(2)}` : number.toFixed(2)
}
const formatDate = (value?: string | null) => value ? value.replace('T', ' ').slice(0, 19) : '--'
const relationshipMessageTypeLabel = (message?: { message_type?: string }) => {
  const type = String(message?.message_type || '').trim()
  if (type === 'parent_guidance') return '父节点指令'
  if (type === 'mission_reflection') return '子女岗位复盘'
  if (type === 'trainer_growth_comment') return '育成官成长点评'
  if (type === 'training_update') return '系统训练更新'
  if (type === 'trainer_reply') return '育成官回复'
  if (type === 'child_reply') return '子女主动反馈'
  return type || '内部消息'
}
const relationshipSenderLabel = (message?: { sender_role?: string; sender_member_id?: string }) => {
  const role = String(message?.sender_role || '').trim()
  if (role === 'talent_development') return '育成官'
  if (role === 'child_domain_expert') return '当前子女'
  return String(message?.sender_member_id || role || '--').trim() || '--'
}
const relationshipMessageBadgeClass = (message?: { message_type?: string }) => {
  const type = String(message?.message_type || '').trim()
  if (type === 'parent_guidance') return 'bg-amber-100 text-amber-700'
  if (type === 'mission_reflection') return 'bg-emerald-100 text-emerald-700'
  if (type === 'trainer_growth_comment') return 'bg-violet-100 text-violet-700'
  if (type === 'training_update') return 'bg-sky-100 text-sky-700'
  if (type === 'trainer_reply') return 'bg-fuchsia-100 text-fuchsia-700'
  if (type === 'child_reply') return 'bg-cyan-100 text-cyan-700'
  return 'bg-slate-100 text-slate-600'
}
const relationshipMessageCardClass = (message?: { message_type?: string; sender_role?: string }) => {
  const type = String(message?.message_type || '').trim()
  if (type === 'parent_guidance') return 'border border-amber-200 bg-amber-50/80 text-slate-700'
  if (type === 'trainer_growth_comment') return 'border border-violet-200 bg-violet-50/80 text-slate-700'
  if (type === 'training_update') return 'border border-sky-200 bg-sky-50/80 text-slate-700'
  if (type === 'mission_reflection') return 'border border-emerald-200 bg-emerald-50/80 text-slate-700'
  if (String(message?.sender_role || '').trim() === 'talent_development') return 'border border-fuchsia-200 bg-fuchsia-50/70 text-slate-700'
  return 'border border-cyan-200 bg-white text-slate-700'
}
const parentInboxMessageTypeLabel = (message?: { message_type?: string }) => {
  const type = String(message?.message_type || '').trim()
  if (type === 'parent_guidance') return '父节点指令'
  if (type === 'training_review_summary') return '训练巡检播报'
  if (type === 'trainer_reply') return '育成官回复'
  if (type === 'child_reply') return '子女反馈'
  return relationshipMessageTypeLabel(message)
}
const parentInboxMessageBadgeClass = (message?: { message_type?: string }) => {
  const type = String(message?.message_type || '').trim()
  if (type === 'parent_guidance') return 'bg-amber-100 text-amber-700'
  if (type === 'training_review_summary') return 'bg-sky-100 text-sky-700'
  if (type === 'trainer_reply') return 'bg-violet-100 text-violet-700'
  if (type === 'child_reply') return 'bg-cyan-100 text-cyan-700'
  return 'bg-slate-100 text-slate-600'
}
const parentInboxMessageCardClass = (message?: { message_type?: string }) => {
  const type = String(message?.message_type || '').trim()
  if (type === 'parent_guidance') return 'border-amber-200 bg-white'
  if (type === 'training_review_summary') return 'border-sky-200 bg-sky-50/60'
  if (type === 'trainer_reply') return 'border-violet-200 bg-violet-50/60'
  if (type === 'child_reply') return 'border-cyan-200 bg-cyan-50/50'
  return 'border-slate-200 bg-white'
}
const directiveReceiptVerdictBadgeClass = (verdict?: string | null) => {
  const normalized = String(verdict || '').trim()
  if (normalized === 'executed') return 'bg-emerald-100 text-emerald-700'
  if (normalized === 'partially_executed') return 'bg-amber-100 text-amber-700'
  if (normalized === 'acknowledged_only') return 'bg-sky-100 text-sky-700'
  return 'bg-slate-100 text-slate-600'
}
const trainerQueueStatusBadgeClass = (status?: string | null) => {
  const normalized = String(status || '').trim()
  if (normalized === 'completed_cycle') return 'bg-emerald-100 text-emerald-700'
  if (normalized === 'in_progress') return 'bg-sky-100 text-sky-700'
  if (normalized === 'accepted') return 'bg-violet-100 text-violet-700'
  return 'bg-slate-100 text-slate-600'
}
const growthDigestStatusBadgeClass = (status?: string | null) => {
  const normalized = String(status || '').trim()
  if (['completed', 'improved', 'stable', 'delivering'].includes(normalized)) return 'bg-emerald-100 text-emerald-700'
  if (['training_children', 'active_training', 'validating', 'bootstrapping'].includes(normalized)) return 'bg-sky-100 text-sky-700'
  if (['blocked', 'failed', 'regressed'].includes(normalized)) return 'bg-rose-100 text-rose-700'
  if (['needs_learning', 'awaiting_assignment', 'profile_initialized'].includes(normalized)) return 'bg-amber-100 text-amber-700'
  return 'bg-slate-100 text-slate-600'
}
const comparisonBadgeClass = (value?: string | null) => {
  if (value === 'improved') return 'bg-emerald-100 text-emerald-700'
  if (value === 'regressed') return 'bg-rose-100 text-rose-700'
  if (value === 'unchanged') return 'bg-slate-200 text-slate-700'
  return 'bg-slate-100 text-slate-500'
}
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
  if (normalized === 'commercial_delivery_done') return '商业交付已结算'
  if (normalized === 'active_training') return '持续训练中'
  if (normalized === 'completed_cycle') return '本轮已闭环'
  if (normalized === 'archived') return '已归档'
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
type RelationshipThreadMessage = {
  message_id?: string
  sender_member_id?: string
  sender_role?: string
  message_type?: string
  content?: string
  created_at?: string
  metadata?: Record<string, unknown>
}
type ChildGrowthDigestCard = {
  member_id: string
  name: string
  primary_role: string
  derived_status: string
  training_stage: string
  current_focus: string
  next_action: string
  blocked_reason: string
  reflection_summary: string
  trainer_comment: string
  next_experiment: string
  mission_status: string
  training_stage_from: string
  training_stage_to: string
  learning_strategy: string
  latest_activity_at: string | null
}
type ChildGrowthPriorityItem = ChildGrowthDigestCard & {
  priority_score: number
  priority_reasons: string[]
  priority_summary: string
}
type ChildGrowthNarrative = {
  summary: string
  highlights: string[]
  updated_label: string
}
type ParentDirectiveTemplate = {
  value: string
  label: string
  title: string
  buildContent: (memberName: string, roleLabel: string, note: string) => string
}
type ChildPortraitBootstrapSummary = {
  member_id: string
  name: string
  role_label: string
  primary_role: string
  next_action: string
}
type ChildLifecycleSummary = {
  status: string
  label: string
  description: string
}
type ParentDirectiveReceipt = {
  title: string
  content: string
  created_at: string | null
  status_label: string
  execution_verdict: string
  execution_summary: string
  child_reply: string
  trainer_reply: string
  training_update: string
  signals: string[]
  stage_change: string
  next_action_change: string
  focus_change: string
  reflection_update: string
}
type TrainerDirectiveQueueItem = {
  message_id: string
  title: string
  content: string
  created_at: string | null
  managed_child_member_id: string
  managed_child_name: string
  managed_child_role: string
  directive_type: string
  training_stage: string
  next_action: string
  current_focus: string
  queue_status: string
  queue_status_label: string
  latest_action_label: string
  management_summary: string
  suggested_action: 'take_over' | 'request_reflection' | 'replan_training' | 'run_review' | 'observe'
  suggested_action_label: string
  timeline: Array<{
    key: string
    label: string
    at: string | null
  }>
}
const latestTimestamp = (...values: Array<string | null | undefined>) => {
  const normalized = values
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .sort()
  return normalized.length ? normalized[normalized.length - 1] : null
}
const relationshipMessagesForMember = (memberId?: string | null): RelationshipThreadMessage[] => {
  const normalizedMemberId = String(memberId || '').trim()
  if (!normalizedMemberId) return []
  const thread = (autonomyStatus.value?.relationship_center?.conversation_threads || []).find((item) => (
    String(item.thread_id || '') === `trainer:${normalizedMemberId}`
  ))
  if (!thread?.messages?.length) return []
  return (thread.messages || [])
    .filter((item): item is RelationshipThreadMessage => !!item && typeof item === 'object')
    .slice()
    .sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')))
}
const latestRelationshipMessageByType = (memberId?: string | null, type?: string) => {
  const normalizedType = String(type || '').trim()
  return relationshipMessagesForMember(memberId).find((item) => (
    !normalizedType || String(item.message_type || '').trim() === normalizedType
  )) || null
}
const growthTimeline = computed(() => (evolutionOverview.value?.growth_timeline || []).slice(0, 6))
const reviewQueueTop = computed(() => (evolutionOverview.value?.strategy_review_queue || []).slice(0, 3))
const gitIndexTemplateText = computed(() => (
  gitIndexTemplate.value?.template
    ? JSON.stringify(gitIndexTemplate.value.template, null, 2)
    : ''
))
const selectedChildMemberRuntime = computed(() => (
  (autonomyStatus.value?.child_members?.items || []).find((item) => String(item.member_id || '') === String(selectedChildMemberId.value || ''))
  || autonomyStatus.value?.child_agent
  || null
))
const selectedChildFormalTasks = computed<AutonomyFormalTask[]>(() => {
  const memberId = String(selectedChildMemberId.value || '').trim()
  if (!memberId) return []
  return (autonomyStatus.value?.task_center?.items || [])
    .filter((item) => String(item?.member_id || '').trim() === memberId)
    .slice()
    .sort((left, right) => String(right.assigned_at || '').localeCompare(String(left.assigned_at || '')))
})
const selectedChildFormalTaskRecommendations = computed<AutonomyFormalTaskRecommendation[]>(() => {
  const memberId = String(selectedChildMemberId.value || '').trim()
  if (!memberId) return []
  return (autonomyStatus.value?.task_center?.recommendations || [])
    .filter((item) => String(item?.member_id || '').trim() === memberId)
    .slice()
    .sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')))
})
const activeFormalTaskRecommendation = computed<AutonomyFormalTaskRecommendation | null>(() => (
  selectedChildFormalTaskRecommendations.value.find((item) => String(item.status || '').trim() === 'suggested')
  || selectedChildFormalTaskRecommendations.value[0]
  || null
))
const activeFormalTask = computed<AutonomyFormalTask | null>(() => (
  selectedChildFormalTasks.value.find((item) => !['approved'].includes(String(item.status || '').trim()))
  || selectedChildFormalTasks.value[0]
  || null
))
const trainerFormalTaskStageLabel = computed(() => {
  const status = String(activeFormalTask.value?.status || '').trim()
  if (status === 'assigned') return '等待子女提交'
  if (status === 'submitted') return '等待育成官确认'
  if (status === 'approved') return '本轮已完成'
  return '等待分配任务'
})
const trainerFormalTaskSteps = computed(() => {
  const task = activeFormalTask.value
  const status = String(task?.status || '').trim()
  const hasTask = Boolean(task)
  const isAssigned = status === 'assigned'
  const isSubmitted = status === 'submitted'
  const isApproved = status === 'approved'
  return [
    {
      key: 'assign',
      title: '1. 分配任务',
      badge: hasTask ? 'done' : 'now',
      badgeClass: hasTask ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700',
      summary: hasTask ? `已分配：${task?.title || '--'}` : '当前还没有正式任务，需要先下达第一轮训练',
      tone: hasTask ? 'border-emerald-200 bg-emerald-50/70' : 'border-amber-200 bg-amber-50/70',
    },
    {
      key: 'submit',
      title: '2. 子女提交',
      badge: isSubmitted || isApproved ? 'done' : (isAssigned ? 'now' : 'waiting'),
      badgeClass: isSubmitted || isApproved ? 'bg-emerald-100 text-emerald-700' : (isAssigned ? 'bg-cyan-100 text-cyan-700' : 'bg-slate-100 text-slate-600'),
      summary: isSubmitted || isApproved ? '这轮结果与复盘已经回传' : (isAssigned ? '当前应推动子女交付结果与复盘' : '先分配任务才会进入这一环'),
      tone: isSubmitted || isApproved ? 'border-emerald-200 bg-emerald-50/70' : (isAssigned ? 'border-cyan-200 bg-cyan-50/70' : 'border-slate-200 bg-slate-50'),
    },
    {
      key: 'approve',
      title: '3. 育成确认',
      badge: isApproved ? 'done' : (isSubmitted ? 'now' : 'waiting'),
      badgeClass: isApproved ? 'bg-emerald-100 text-emerald-700' : (isSubmitted ? 'bg-violet-100 text-violet-700' : 'bg-slate-100 text-slate-600'),
      summary: isApproved ? '本轮已确认完成，可准备下一轮' : (isSubmitted ? '当前应阅读结果并给出确认点评' : '收到提交后才进入确认环节'),
      tone: isApproved ? 'border-emerald-200 bg-emerald-50/70' : (isSubmitted ? 'border-violet-200 bg-violet-50/70' : 'border-slate-200 bg-slate-50'),
    },
  ]
})
const trainerFormalTaskGuidance = computed(() => {
  const task = activeFormalTask.value
  const status = String(task?.status || '').trim()
  const memberName = String(selectedChildMemberDraft.value?.name || selectedChildMemberId.value || '当前子女')
  if (!task) {
    return `先为${memberName}确认第一轮正式训练任务，让它进入可执行、可提交、可复盘的最小闭环。`
  }
  if (status === 'assigned') {
    return `${memberName}已经收到任务，当前重点不是再加新任务，而是推动它完成交付并提交结果与复盘。`
  }
  if (status === 'submitted') {
    return `${memberName}已经提交了这轮结果，当前应该由育成官做确认点评，判断是否进入下一轮。`
  }
  if (status === 'approved') {
    return `${memberName}这一轮已经确认完成，可以采用系统建议或手动整理下一轮训练任务。`
  }
  return `继续围绕${memberName}当前任务推进闭环，不要同时打开过多变量。`
})
const formalTaskDeliverablesDraftList = computed(() => (
  String(formalTaskAssignDeliverablesDraft.value || '')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
))
const parentInboxMessages = computed(() => (
  (autonomyStatus.value?.relationship_center?.parent_inbox || []).slice().reverse().slice(0, 6)
))
const allParentInboxMessages = computed(() => (
  (autonomyStatus.value?.relationship_center?.parent_inbox || []).slice().sort((left, right) => (
    String(left?.created_at || '').localeCompare(String(right?.created_at || ''))
  ))
))
const selectedChildConversation = computed(() => {
  const memberId = String(selectedChildMemberId.value || '').trim()
  if (!memberId) return null
  return (autonomyStatus.value?.relationship_center?.conversation_threads || []).find((item) => (
    String(item.thread_id || '') === `trainer:${memberId}`
  )) || null
})
const selectedChildMemberDraft = computed(() => (
  childMembersDraft.value.find((item) => String(item.member_id || '') === String(selectedChildMemberId.value || '')) || null
))
const selectedChildKnowledgeLearningTask = computed(() => (
  findMemberKnowledgeLearningTask(selectedChildMemberDraft.value, learningTasks.value)
))
const canValidateSelectedChildKnowledgeLearning = computed(() => {
  const status = String(selectedChildKnowledgeLearningTask.value?.status || '').trim()
  return ['needs_learning', 'researching', 'candidate_found', 'ready_for_validation'].includes(status)
})
const validateSelectedChildKnowledgeLearning = async () => {
  const taskId = String(selectedChildKnowledgeLearningTask.value?.task_id || '').trim()
  if (!taskId) return
  await triggerLearningTaskValidation(taskId)
}
const goToDispatchAfterKnowledge = () => {
  setTrainerMainlineMode('dispatch')
  syncTrainerRouteQuery({ mode: 'dispatch', dispatchTab: 'assign' })
}
const onKnowledgePanelRefreshed = async () => {
  await Promise.all([loadLearningTasks(), loadAutonomyStatus()])
}
const trainerMemberDraft = computed(() => (
  childMembersDraft.value.find((item) => String(item.primary_role || '') === 'talent_development') || null
))
const parentDirectiveTemplates: ParentDirectiveTemplate[] = [
  {
    value: 'stabilize_current_path',
    label: '稳住当前主线',
    title: '父节点要求育成官稳住当前主线',
    buildContent: (memberName, roleLabel, note) => (
      `【父节点 -> 育成官】请你接手 ${memberName} 当前的 ${roleLabel} 培养，先稳住主线，不要扩新方向，先把这一轮任务压到可验证、可复盘、可沉淀的最小闭环。${note ? `\n【父节点补充】${note}` : ''}`
    ),
  },
  {
    value: 'force_reflection',
    label: '强制补一轮复盘',
    title: '父节点要求育成官推动岗位复盘',
    buildContent: (memberName, roleLabel, note) => (
      `【父节点 -> 育成官】请你推动 ${memberName} 立即补一轮 ${roleLabel} 岗位复盘，明确这轮做了什么、卡在哪里、下一实验是什么，再决定后续动作。${note ? `\n【父节点补充】${note}` : ''}`
    ),
  },
  {
    value: 'narrow_problem',
    label: '压缩问题范围',
    title: '父节点要求育成官压缩问题范围',
    buildContent: (memberName, roleLabel, note) => (
      `【父节点 -> 育成官】请你协助 ${memberName} 先把当前 ${roleLabel} 问题压缩到一个最小可验证点，不要同时处理太多变量，先拿到一个稳定样本或稳定步骤。${note ? `\n【父节点补充】${note}` : ''}`
    ),
  },
  {
    value: 'trainer_replan',
    label: '让育成官重排训练',
    title: '父节点要求育成官重排训练',
    buildContent: (memberName, roleLabel, note) => (
      `【父节点 -> 育成官】请你重新评估 ${memberName} 当前的 ${roleLabel} 训练计划，判断是否需要调整阶段、案例顺序或下一步目标。${note ? `\n【父节点补充】${note}` : ''}`
    ),
  },
]
const selectedParentDirectiveTemplate = computed(() => (
  parentDirectiveTemplates.find((item) => item.value === parentDirectiveType.value) || parentDirectiveTemplates[0]
))
const parentDirectivePreview = computed(() => {
  const memberName = String(selectedChildMemberDraft.value?.name || selectedChildMemberId.value || '当前子女').trim()
  const roleLabel = String(
    selectedChildMemberDraft.value?.persona?.role_label
    || selectedChildMemberDraft.value?.primary_role
    || '岗位'
  ).trim()
  const note = String(parentMessageDraft.value || '').trim()
  const template = selectedParentDirectiveTemplate.value
  return {
    title: template?.title || '父节点指令',
    directive_type: template?.value || 'custom',
    content: template?.buildContent(memberName, roleLabel, note) || note,
  }
})
const selectedParentDirectiveReceipt = computed<ParentDirectiveReceipt | null>(() => {
  const memberId = String(selectedChildMemberId.value || '').trim()
  if (!memberId) return null
  const trainerId = String(trainerMemberDraft.value?.member_id || 'talent_development_officer').trim()
  const messages = allParentInboxMessages.value
  const latestDirective = messages
    .filter((item) => (
      String(item?.message_type || '').trim() === 'parent_guidance'
      && String(item?.metadata?.target_member_id || '') === trainerId
      && String(item?.metadata?.managed_child_member_id || '') === memberId
    ))
    .slice(-1)[0]
  if (!latestDirective) return null
  const directiveTime = String(latestDirective.created_at || '')
  const followUps = messages.filter((item) => {
    const createdAt = String(item?.created_at || '')
    if (!createdAt || createdAt < directiveTime) return false
    const relatedMemberId = String(item?.metadata?.member_id || item?.metadata?.target_member_id || '')
    return relatedMemberId === memberId
  })
  const childReply = followUps.find((item) => String(item?.message_type || '') === 'child_reply')
  const trainerReply = followUps.find((item) => String(item?.message_type || '') === 'trainer_reply')
  const trainingUpdate = followUps.find((item) => (
    String(item?.message_type || '') === 'training_review_summary'
    || String(item?.message_type || '') === 'training_update'
  ))
  const snapshot = latestDirective.metadata?.directive_snapshot as Record<string, unknown> | undefined
  const runtimeMember = selectedChildMemberRuntime.value
  const runtimeOnboarding = (
    runtimeMember && 'onboarding' in runtimeMember && runtimeMember.onboarding && typeof runtimeMember.onboarding === 'object'
      ? runtimeMember.onboarding as Record<string, unknown>
      : null
  )
  const runtimeOnboardingStatus = (
    runtimeOnboarding
      ? String(runtimeOnboarding.status || '')
      : ''
  )
  const currentStage = String(runtimeMember?.training_plan?.stage || runtimeOnboardingStatus || '')
  const currentNextAction = String(runtimeMember?.derived_state?.next_action || runtimeMember?.training_plan?.next_action || '')
  const currentFocus = String(runtimeMember?.growth_state?.current_focus || '')
  const beforeStage = String(snapshot?.training_stage || '')
  const beforeNextAction = String(snapshot?.next_action || '')
  const beforeFocus = String(snapshot?.current_focus || '')
  const latestReflectionAt = String(runtimeMember?.experience_journal?.last_compiled_at || runtimeMember?.growth_state?.last_reflection_at || '')
  const signals: string[] = []
  if (childReply) signals.push('child_replied')
  if (trainerReply) signals.push('trainer_responded')
  if (trainingUpdate) signals.push('training_broadcast_updated')
  if (beforeStage && currentStage && beforeStage !== currentStage) signals.push('training_stage_changed')
  if (beforeNextAction && currentNextAction && beforeNextAction !== currentNextAction) signals.push('next_action_changed')
  if (beforeFocus && currentFocus && beforeFocus !== currentFocus) signals.push('focus_changed')
  if (latestReflectionAt && String(latestDirective.created_at || '') && latestReflectionAt >= String(latestDirective.created_at || '')) {
    signals.push('reflection_compiled_after_directive')
  }
  const hasStateChange = signals.some((item) => (
    item === 'training_stage_changed'
    || item === 'next_action_changed'
    || item === 'focus_changed'
    || item === 'reflection_compiled_after_directive'
  ))
  const hasConversationFollowup = !!childReply || !!trainerReply
  let executionVerdict = 'waiting_response'
  let executionSummary = '这条父节点指令发出后，系统还没有观察到明显响应。'
  if (hasStateChange) {
    executionVerdict = 'executed'
    executionSummary = '这条指令已经带来了真实状态变化或新的复盘沉淀，说明开始落地执行了。'
  } else if (hasConversationFollowup && trainingUpdate) {
    executionVerdict = 'partially_executed'
    executionSummary = '已经出现沟通和训练播报，但还没有看到足够明确的状态跃迁，属于部分执行。'
  } else if (hasConversationFollowup) {
    executionVerdict = 'acknowledged_only'
    executionSummary = '已经收到回复，但暂时还停留在确认或沟通层，尚未形成明确落地变化。'
  }
  const statusLabel = signals.length
    ? `已产生 ${signals.length} 条后续动作`
    : '等待后续动作'
  return {
    title: String(latestDirective.title || '父节点指令'),
    content: String(latestDirective.content || ''),
    created_at: latestDirective.created_at || null,
    status_label: statusLabel,
    execution_verdict: executionVerdict,
    execution_summary: executionSummary,
    child_reply: String(childReply?.content || ''),
    trainer_reply: String(trainerReply?.content || ''),
    training_update: String(trainingUpdate?.content || ''),
    signals,
    stage_change: (
      beforeStage && currentStage
        ? (beforeStage === currentStage ? `${beforeStage} -> ${currentStage}（未变化）` : `${beforeStage} -> ${currentStage}`)
        : ''
    ),
    next_action_change: (
      beforeNextAction && currentNextAction
        ? (beforeNextAction === currentNextAction ? `仍为：${currentNextAction}` : `${beforeNextAction} -> ${currentNextAction}`)
        : ''
    ),
    focus_change: (
      beforeFocus && currentFocus
        ? (beforeFocus === currentFocus ? `仍为：${currentFocus}` : `${beforeFocus} -> ${currentFocus}`)
        : ''
    ),
    reflection_update: (
      latestReflectionAt && String(latestDirective.created_at || '') && latestReflectionAt >= String(latestDirective.created_at || '')
        ? `已在 ${formatDate(latestReflectionAt)} 之后产生新的复盘沉淀`
        : ''
    ),
  }
})
const childGrowthDigestCards = computed<ChildGrowthDigestCard[]>(() => {
  const runtimeMembers = autonomyStatus.value?.child_members?.items || []
  const runtimeMemberMap = new Map(
    runtimeMembers
      .filter((item) => item && typeof item === 'object')
      .map((item) => [String(item.member_id || ''), item]),
  )
  return activeChildMembersDraft.value
    .filter((member) => String(member.primary_role || '') !== 'talent_development')
    .map((member) => {
      const memberId = String(member.member_id || '').trim()
      const runtimeMember = runtimeMemberMap.get(memberId) || member
      const reflectionMessage = latestRelationshipMessageByType(memberId, 'mission_reflection')
      const trainerMessage = latestRelationshipMessageByType(memberId, 'trainer_growth_comment')
      const journalCards = Array.isArray(runtimeMember.experience_journal?.cards) ? runtimeMember.experience_journal?.cards.slice() : []
      const latestCard = journalCards
        .sort((left, right) => String(right.updated_at || right.created_at || '').localeCompare(String(left.updated_at || left.created_at || '')))[0]
      return {
        member_id: memberId,
        name: String(runtimeMember.name || member.name || memberId),
        primary_role: String(runtimeMember.primary_role || member.primary_role || ''),
        derived_status: String(runtimeMember.derived_state?.status || runtimeMember.growth_state?.phase || runtimeMember.onboarding?.status || 'idle'),
        training_stage: String(runtimeMember.training_plan?.stage || runtimeMember.onboarding?.status || 'profile_initialized'),
        current_focus: String(runtimeMember.growth_state?.current_focus || member.growth_state?.current_focus || ''),
        next_action: String(runtimeMember.derived_state?.next_action || runtimeMember.training_plan?.next_action || member.training_plan?.next_action || ''),
        blocked_reason: String(runtimeMember.derived_state?.blocked_reason || runtimeMember.growth_state?.blocked_reason || ''),
        reflection_summary: String(
          runtimeMember.professional_view?.reflection_summary
          || latestCard?.summary
          || reflectionMessage?.content
          || runtimeMember.professional_view?.summary
          || ''
        ),
        trainer_comment: String(trainerMessage?.content || ''),
        next_experiment: String(runtimeMember.professional_view?.next_experiment || latestCard?.next_experiment || ''),
        mission_status: String((trainerMessage?.metadata?.mission_status as string) || (latestCard?.status || '')),
        training_stage_from: String((trainerMessage?.metadata?.training_stage_from as string) || ''),
        training_stage_to: String((trainerMessage?.metadata?.training_stage_to as string) || ''),
        learning_strategy: String(runtimeMember.operating_contract?.learning_strategy || member.operating_contract?.learning_strategy || ''),
        latest_activity_at: latestTimestamp(
          trainerMessage?.created_at,
          reflectionMessage?.created_at,
          latestCard?.updated_at,
          latestCard?.created_at,
          runtimeMember.experience_journal?.last_compiled_at,
          runtimeMember.growth_state?.last_reflection_at,
        ),
      }
    })
    .sort((left, right) => {
      if (left.member_id === selectedChildMemberId.value) return -1
      if (right.member_id === selectedChildMemberId.value) return 1
      return String(right.latest_activity_at || '').localeCompare(String(left.latest_activity_at || ''))
    })
})
const childGrowthPriorityQueue = computed<ChildGrowthPriorityItem[]>(() => (
  childGrowthDigestCards.value
    .map((card) => {
      const reasons: string[] = []
      let score = 0
      if (card.blocked_reason) {
        score += 5
        reasons.push('存在阻塞')
      }
      if (!card.trainer_comment) {
        score += 2
        reasons.push('缺少育成官点评')
      }
      if (!card.reflection_summary) {
        score += 2
        reasons.push('缺少岗位复盘')
      }
      if (['profile_initialized', 'awaiting_assignment', 'needs_learning'].includes(card.training_stage)) {
        score += 2
        reasons.push('仍处于早期培养阶段')
      }
      if (['failed', 'blocked', 'regressed'].includes(card.derived_status)) {
        score += 3
        reasons.push('近期状态不稳定')
      }
      if (['bootstrapping', 'validating'].includes(card.derived_status)) {
        score += 1
        reasons.push('还在过渡验证阶段')
      }
      return {
        ...card,
        priority_score: score,
        priority_reasons: reasons,
        priority_summary: reasons.length
          ? `优先处理 ${reasons.slice(0, 2).join('、')}`
          : '当前成长比较稳定，可继续观察',
      }
    })
    .filter((item) => item.priority_score > 0)
    .sort((left, right) => {
      if (right.priority_score !== left.priority_score) return right.priority_score - left.priority_score
      return String(right.latest_activity_at || '').localeCompare(String(left.latest_activity_at || ''))
    })
    .slice(0, 3)
))
const childGrowthNarrative = computed<ChildGrowthNarrative | null>(() => {
  const cards = childGrowthDigestCards.value
  if (!cards.length) return null
  const blocked = cards.filter((item) => !!item.blocked_reason)
  const stable = cards.filter((item) => ['completed', 'improved', 'stable', 'delivering'].includes(item.derived_status))
  const early = cards.filter((item) => ['profile_initialized', 'awaiting_assignment', 'needs_learning'].includes(item.training_stage))
  const missingReflection = cards.filter((item) => !item.reflection_summary)
  const topPriority = childGrowthPriorityQueue.value[0] || null
  const newest = cards
    .slice()
    .sort((left, right) => String(right.latest_activity_at || '').localeCompare(String(left.latest_activity_at || '')))[0]
  const summaryParts = [
    `当前共有 ${cards.length} 名在成长中的子女。`,
    stable.length ? `${stable.length} 名状态相对稳定，正在持续推进。` : '目前还没有进入稳定交付阶段的子女。',
    blocked.length ? `${blocked.length} 名存在阻塞，需要优先看护。` : '目前没有检测到明显阻塞。',
    early.length ? `${early.length} 名还处于早期培养阶段，需要继续喂案例和陪跑。` : '大多数子女已经离开初始建档阶段。',
  ]
  if (topPriority) {
    summaryParts.push(`此刻最值得先关注的是 ${topPriority.name || topPriority.member_id}，重点是 ${topPriority.next_action || topPriority.current_focus || '继续观察当前进展'}。`)
  }
  const highlights: string[] = []
  if (topPriority) {
    highlights.push(`优先对象：${topPriority.name || topPriority.member_id}，因为 ${topPriority.priority_reasons.join('、') || '近期波动较大'}。`)
  }
  if (missingReflection.length) {
    highlights.push(`复盘缺口：${missingReflection.map((item) => item.name || item.member_id).slice(0, 3).join('、')} 还没有形成清晰的岗位复盘。`)
  }
  if (newest?.latest_activity_at) {
    highlights.push(`最近一次成长动作来自 ${newest.name || newest.member_id}，时间 ${formatDate(newest.latest_activity_at)}。`)
  }
  if (blocked.length) {
    highlights.push(`阻塞观察：${blocked.slice(0, 2).map((item) => `${item.name || item.member_id}(${item.blocked_reason})`).join('、')}。`)
  }
  return {
    summary: summaryParts.join(' '),
    highlights,
    updated_label: newest?.latest_activity_at ? `updated ${formatDate(newest.latest_activity_at)}` : 'updated --',
  }
})
const trainerDirectiveQueue = computed<TrainerDirectiveQueueItem[]>(() => {
  const trainerId = String(trainerMemberDraft.value?.member_id || 'talent_development_officer').trim()
  const memberMap = new Map(
    childMembersDraft.value
      .filter((item) => item && typeof item === 'object')
      .map((item) => [String(item.member_id || ''), item]),
  )
  return allParentInboxMessages.value
    .filter((item) => (
      String(item?.message_type || '').trim() === 'parent_guidance'
      && String(item?.metadata?.target_member_id || '') === trainerId
    ))
    .slice()
    .sort((left, right) => String(right?.created_at || '').localeCompare(String(left?.created_at || '')))
    .map((item) => {
      const managedChildMemberId = String(item?.metadata?.managed_child_member_id || '').trim()
      const managedChild = memberMap.get(managedChildMemberId)
      const snapshot = item?.metadata?.directive_snapshot as Record<string, unknown> | undefined
      const followUps = allParentInboxMessages.value.filter((followUp) => {
        const createdAt = String(followUp?.created_at || '')
        return !!createdAt
          && createdAt >= String(item?.created_at || '')
          && (
            String(followUp?.metadata?.source_directive_message_id || '') === String(item?.message_id || '')
            || String(followUp?.metadata?.member_id || '') === managedChildMemberId
          )
      })
      const latestTrainerAction = followUps
        .filter((followUp) => (
          String(followUp?.message_type || '') === 'training_update'
          && String(followUp?.metadata?.source_directive_message_id || '') === String(item?.message_id || '')
        ))
        .slice(-1)[0]
      const takeOverAction = followUps.find((followUp) => (
        String(followUp?.message_type || '') === 'training_update'
        && String(followUp?.metadata?.source_directive_message_id || '') === String(item?.message_id || '')
        && String(followUp?.metadata?.action_type || '') === 'take_over'
      ))
      const reflectionAction = followUps.find((followUp) => (
        String(followUp?.message_type || '') === 'training_update'
        && String(followUp?.metadata?.source_directive_message_id || '') === String(item?.message_id || '')
        && String(followUp?.metadata?.action_type || '') === 'request_reflection'
      ))
      const replanAction = followUps.find((followUp) => (
        String(followUp?.message_type || '') === 'training_update'
        && String(followUp?.metadata?.source_directive_message_id || '') === String(item?.message_id || '')
        && String(followUp?.metadata?.action_type || '') === 'replan_training'
      ))
      const childReply = followUps.find((followUp) => String(followUp?.message_type || '') === 'child_reply')
      const trainerReply = followUps.find((followUp) => String(followUp?.message_type || '') === 'trainer_reply')
      const trainingBroadcast = followUps.find((followUp) => (
        String(followUp?.message_type || '') === 'training_review_summary'
      ))
      const childRuntime = (autonomyStatus.value?.child_members?.items || []).find((runtimeItem) => (
        String(runtimeItem.member_id || '') === managedChildMemberId
      ))
      const reflectionChanged = (
        String(childRuntime?.experience_journal?.last_compiled_at || childRuntime?.growth_state?.last_reflection_at || '') >= String(item?.created_at || '')
      )
      const stageChanged = String(snapshot?.training_stage || '') && String(childRuntime?.training_plan?.stage || '') && String(snapshot?.training_stage || '') !== String(childRuntime?.training_plan?.stage || '')
      let queueStatus = 'pending'
      let queueStatusLabel = '未接手'
      let latestActionLabel = '等待育成官处理'
      if (latestTrainerAction) {
        const actionType = String(latestTrainerAction?.metadata?.action_type || '')
        if (actionType === 'take_over') {
          queueStatus = 'accepted'
          queueStatusLabel = '已接手'
          latestActionLabel = '育成官已确认接手'
        } else if (actionType === 'request_reflection' || actionType === 'replan_training') {
          queueStatus = 'in_progress'
          queueStatusLabel = '已推进'
          latestActionLabel = String(latestTrainerAction?.title || '育成官已采取处理动作')
        }
      }
      if (reflectionChanged || stageChanged) {
        queueStatus = 'completed_cycle'
        queueStatusLabel = '已完成一轮'
        latestActionLabel = reflectionChanged
          ? '已形成新复盘沉淀'
          : '训练阶段已发生变化'
      }
      let managementSummary = '这条交办还在等待育成官正式接手。'
      let suggestedAction: TrainerDirectiveQueueItem['suggested_action'] = 'take_over'
      let suggestedActionLabel = '建议先接手'
      if (queueStatus === 'accepted') {
        managementSummary = '育成官已经接手，但还需要继续推动子女给出反馈或触发训练动作。'
        suggestedAction = reflectionAction ? 'run_review' : 'request_reflection'
        suggestedActionLabel = reflectionAction ? '建议立即巡检' : '建议要求补复盘'
      } else if (queueStatus === 'in_progress') {
        managementSummary = reflectionAction
          ? '育成官已经要求子女补复盘，下一步要盯住是否真的产出新的经验沉淀。'
          : '育成官已经开始调整训练，下一步要观察训练阶段和下一步是否发生变化。'
        suggestedAction = reflectionAction ? 'run_review' : 'replan_training'
        suggestedActionLabel = reflectionAction ? '建议立即巡检' : '建议继续重排训练'
      } else if (queueStatus === 'completed_cycle') {
        managementSummary = reflectionChanged
          ? '这条交办已经完成一轮闭环，并且形成了新的复盘沉淀。'
          : '这条交办已经推动训练阶段发生变化，可以准备进入下一轮管理。'
        suggestedAction = 'observe'
        suggestedActionLabel = '建议进入观察'
      }
      if (queueStatus !== 'completed_cycle' && ['profile_initialized', 'needs_learning'].includes(String(managedChild?.training_plan?.stage || ''))) {
        suggestedAction = 'replan_training'
        suggestedActionLabel = '建议先重排训练'
      }
      const timeline = [
        {
          key: 'directive',
          label: '父节点交办',
          at: item?.created_at || null,
        },
        takeOverAction ? {
          key: 'take_over',
          label: '育成官已接手',
          at: takeOverAction.created_at || null,
        } : null,
        reflectionAction ? {
          key: 'request_reflection',
          label: '要求子女补复盘',
          at: reflectionAction.created_at || null,
        } : null,
        replanAction ? {
          key: 'replan_training',
          label: '已重排训练',
          at: replanAction.created_at || null,
        } : null,
        childReply ? {
          key: 'child_reply',
          label: '子女给出反馈',
          at: childReply.created_at || null,
        } : null,
        trainerReply ? {
          key: 'trainer_reply',
          label: '育成官作出回应',
          at: trainerReply.created_at || null,
        } : null,
        trainingBroadcast ? {
          key: 'training_review_summary',
          label: '训练巡检播报',
          at: trainingBroadcast.created_at || null,
        } : null,
        reflectionChanged ? {
          key: 'reflection_compiled',
          label: '形成新复盘沉淀',
          at: String(childRuntime?.experience_journal?.last_compiled_at || childRuntime?.growth_state?.last_reflection_at || '') || null,
        } : null,
      ].filter((entry): entry is { key: string; label: string; at: string | null } => !!entry)
      return {
        message_id: String(item?.message_id || ''),
        title: String(item?.title || '父节点交办任务'),
        content: String(item?.content || ''),
        created_at: item?.created_at || null,
        managed_child_member_id: managedChildMemberId,
        managed_child_name: String(
          snapshot?.member_name
          || managedChild?.name
          || managedChildMemberId
          || '--'
        ),
        managed_child_role: String(
          snapshot?.primary_role
          || managedChild?.primary_role
          || '--'
        ),
        directive_type: String(item?.metadata?.directive_type || ''),
        training_stage: String(snapshot?.training_stage || managedChild?.training_plan?.stage || managedChild?.onboarding?.status || '--'),
        next_action: String(snapshot?.next_action || managedChild?.training_plan?.next_action || '--'),
        current_focus: String(snapshot?.current_focus || managedChild?.growth_state?.current_focus || '--'),
        queue_status: queueStatus,
        queue_status_label: queueStatusLabel,
        latest_action_label: latestActionLabel,
        management_summary: managementSummary,
        suggested_action: suggestedAction,
        suggested_action_label: suggestedActionLabel,
        timeline,
      }
    })
    .slice(0, 6)
})
const trainerLowRiskSuggestionQueue = computed(() => (
  trainerDirectiveQueue.value.filter((item) => {
    const stageAllowed = trainerAutoAssistAllowedStages.value.includes(String(item.training_stage || '').trim())
    if (!stageAllowed) return false
    if (item.suggested_action === 'take_over') return trainerAutoAssistAllowedTakeOver.value
    if (item.suggested_action === 'request_reflection') return trainerAutoAssistAllowedReflection.value
    return false
  })
))
const trainerLowRiskSuggestionSignature = computed(() => (
  trainerLowRiskSuggestionQueue.value
    .map((item) => `${item.message_id}:${item.suggested_action}:${item.queue_status}`)
    .join('|')
))
const talentDevelopmentAssignments = computed(() => (
  childMembersDraft.value
    .filter((item) => String(item.primary_role || '') !== 'talent_development')
    .filter((item) => String(item.onboarding?.training_owner_member_id || '') === 'talent_development_officer')
    .slice(0, 8)
))
const childDerivedState = computed(() => selectedChildMemberRuntime.value?.derived_state || autonomyStatus.value?.child_agent?.derived_state || null)
const childCurrentJobs = computed(() => selectedChildMemberRuntime.value?.current_jobs || autonomyStatus.value?.child_agent?.current_jobs || [])
const childAutonomousPlan = computed(() => {
  const runtime = selectedChildMemberRuntime.value
  const draft = selectedChildMemberDraft.value
  if (!runtime && !draft) return null
  const objective = String(
    runtime?.derived_state?.next_action
    || runtime?.training_plan?.next_action
    || draft?.training_plan?.next_action
    || runtime?.growth_state?.next_goal
    || draft?.growth_state?.next_goal
    || '继续推进当前岗位主线'
  ).trim()
  const whyNow = String(
    runtime?.growth_state?.current_focus
    || draft?.growth_state?.current_focus
    || runtime?.professional_view?.current_judgement
    || '当前专业判断还需要更多证据'
  ).trim()
  const steps = [
    runtime?.professional_view?.next_professional_focus,
    runtime?.professional_view?.next_experiment,
    runtime?.training_plan?.goals?.[0],
    runtime?.training_plan?.curriculum?.[0],
  ]
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .slice(0, 4)
  const evidence = String(
    runtime?.professional_view?.evidence?.join(' / ')
    || runtime?.experience_journal?.cards?.[0]?.summary
    || '等待新的执行证据、结果样本或岗位反馈'
  ).trim()
  const replanTrigger = String(
    runtime?.growth_state?.blocked_reason
    || runtime?.professional_view?.professional_risk
    || '如果连续一轮没有拿到新证据、结果回退或风险升高，就触发重排'
  ).trim()
  return {
    objective,
    why_now: whyNow,
    steps,
    evidence,
    replan_trigger: replanTrigger,
  }
})
const trainerIntentSummary = computed(() => {
  const memberId = String(selectedChildMemberId.value || '').trim()
  if (!memberId) return null
  const queueItem = trainerDirectiveQueue.value.find((item) => String(item.managed_child_member_id || '') === memberId) || null
  const runtime = selectedChildMemberRuntime.value
  const intent = String(
    queueItem?.suggested_action_label
    || runtime?.training_plan?.next_action
    || '继续观察当前培养进展'
  ).trim()
  const reason = String(
    queueItem?.management_summary
    || runtime?.growth_state?.current_focus
    || '当前还没有足够信号，需要继续收集状态'
  ).trim()
  const risk = String(
    runtime?.growth_state?.blocked_reason
    || runtime?.professional_view?.professional_risk
    || '避免子女在没有形成证据前盲目前进'
  ).trim()
  const nextMoves = [
    queueItem?.latest_action_label,
    queueItem?.current_focus ? `盯住当前焦点：${queueItem.current_focus}` : '',
    queueItem?.next_action ? `推动下一步：${queueItem.next_action}` : '',
    runtime?.professional_view?.next_experiment ? `观察实验结果：${runtime.professional_view.next_experiment}` : '',
  ]
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .slice(0, 4)
  return {
    intent,
    reason,
    risk,
    next_moves: nextMoves,
  }
})
const selfMediaJobRuntime = computed(() => {
  const jobs = childCurrentJobs.value
  const withTenantState = jobs.find((job) => job?.runtime_state?.tenant_state)
  if (withTenantState?.runtime_state) return withTenantState.runtime_state
  return jobs.find((job) => job?.runtime_state)?.runtime_state || null
})
const formalTaskGitExportRuntime = computed(() => (
  childCurrentJobs.value.find((job) => job?.runtime_state?.tenant_state?.git_export)?.runtime_state?.tenant_state?.git_export
  || selfMediaJobRuntime.value?.tenant_state?.git_export
  || null
))
const formalTaskGitExportMatchesActiveTask = computed(() => {
  const activeTaskId = String(activeFormalTask.value?.task_id || '').trim()
  const exportTaskId = String(formalTaskGitExportRuntime.value?.last_export?.task_id || '').trim()
  if (!activeTaskId || !exportTaskId) return false
  return activeTaskId === exportTaskId
})
const formalTaskGitExportStatusLabel = computed(() => {
  const status = String(formalTaskGitExportRuntime.value?.status || '').trim()
  if (status === 'exported') return '已自动入库'
  if (status === 'failed') return '自动入库失败'
  if (status === 'blocked') return '自动入库受阻'
  if (status === 'ready') return '等待自动入库'
  if (status === 'skipped') return '当前岗位未自动入库'
  return '暂无入库状态'
})
const formalTaskGitExportStatusClass = computed(() => {
  const status = String(formalTaskGitExportRuntime.value?.status || '').trim()
  if (status === 'exported') return 'border-emerald-200 bg-emerald-50 text-emerald-900'
  if (status === 'failed') return 'border-rose-200 bg-rose-50 text-rose-900'
  if (status === 'blocked') return 'border-amber-200 bg-amber-50 text-amber-900'
  if (status === 'ready') return 'border-sky-200 bg-sky-50 text-sky-900'
  return 'border-slate-200 bg-slate-50 text-slate-700'
})
const selfMediaGitRepoKey = computed(() => {
  const lastExportRepoKey = String(selfMediaJobRuntime.value?.tenant_state?.git_export?.last_export?.repo_key || '').trim()
  if (lastExportRepoKey) return lastExportRepoKey
  const runtimeRepoKey = String(selfMediaJobRuntime.value?.tenant_state?.git_export?.repo_key || '').trim()
  if (runtimeRepoKey) return runtimeRepoKey
  return 'toutiao'
})

const trainerMainlineModeMeta = computed(() => {
  if (trainerMainlineMode.value === 'dispatch') {
    return {
      title: '任务分发模式',
      description: '这里专门处理正式任务草案、任务下发、结果确认和下一轮建议，不和其他育成动作混看。',
    }
  }
  if (trainerMainlineMode.value === 'review') {
    return {
      title: '审核与沟通模式',
      description: '这里专门处理育成官和子女之间的反馈、关系层沟通、专业视角和成长诊断。',
    }
  }
  if (trainerMainlineMode.value === 'exclusive') {
    return {
      title: '巡检与带教策略模式',
      description: '这里专门处理育成官的自检、低风险自动介入、训练策略和带教判断。',
    }
  }
  return {
    title: '画像与建档模式',
    description: '这里专门处理父节点画像、新子女建立、岗位身份确认和成长起点设定。',
  }
})

const trainerSelectedChildName = computed(() => (
  selectedChildMemberDraft.value && selectedChildMemberDraft.value.primary_role !== 'talent_development'
    ? (selectedChildMemberDraft.value.name || selectedChildMemberDraft.value.member_id || '--')
    : '请先从左侧选中一个孩子'
))

const trainerSelectedChildMeta = computed(() => (
  selectedChildMemberDraft.value && selectedChildMemberDraft.value.primary_role !== 'talent_development'
    ? `${selectedChildMemberDraft.value.primary_role || '--'} / ${selectedChildMemberDraft.value.training_plan?.stage || selectedChildMemberDraft.value.onboarding?.status || '--'}`
    : '育成师的主工作永远应该绑定到具体对象，而不是空转看配置。'
))

const selectedChildWorkspaceRoute = computed(() => (
  selectedChildMemberDraft.value && selectedChildMemberDraft.value.primary_role !== 'talent_development'
    ? `/organization/child/${encodeURIComponent(String(selectedChildMemberId.value || ''))}/workspace`
    : ''
))

const trainerMainlineCards = computed(() => ([
  {
    key: 'portrait',
    title: '1. 画像建档',
    description: '先把身份、岗位和成长起点建稳。',
    badge: trainerMainlineMode.value === 'portrait' ? '当前' : '建档',
    badgeClass: trainerMainlineMode.value === 'portrait' ? 'bg-emerald-600 text-white' : 'bg-emerald-100 text-emerald-700',
    active: trainerMainlineMode.value === 'portrait',
    activeClass: 'border-emerald-300 bg-emerald-50 shadow-sm',
    idleClass: 'border-emerald-200 bg-white hover:bg-emerald-50/60',
  },
  {
    key: 'intake',
    title: '2. 接单对接',
    description: '商业任务入口：智脑按能力推荐，育成确认分派与结算。',
    badge: '消费环',
    badgeClass: 'bg-slate-900 text-white',
    active: false,
    activeClass: 'border-slate-400 bg-slate-50 shadow-sm',
    idleClass: 'border-slate-200 bg-white hover:bg-slate-50',
  },
  {
    key: 'dispatch',
    title: '3. 任务编排',
    description: activeFormalTask.value ? '当前轮任务已经存在，重点是推动闭环。' : '对内训练任务或接单后的正式任务跟踪。',
    badge: trainerMainlineMode.value === 'dispatch' ? '当前' : (activeFormalTask.value ? '进行中' : '待进入'),
    badgeClass: trainerMainlineMode.value === 'dispatch' ? 'bg-amber-600 text-white' : (activeFormalTask.value ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'),
    active: trainerMainlineMode.value === 'dispatch',
    activeClass: 'border-amber-300 bg-amber-50 shadow-sm',
    idleClass: 'border-amber-200 bg-white hover:bg-amber-50/60',
  },
  {
    key: 'review',
    title: '4. 复盘沟通',
    description: activeFormalTask.value?.status === 'submitted' ? '孩子已经提交结果，适合现在确认和点评。' : '集中处理结果、反馈和专业判断。',
    badge: trainerMainlineMode.value === 'review' ? '当前' : (activeFormalTask.value?.status === 'submitted' ? '待确认' : '观察'),
    badgeClass: trainerMainlineMode.value === 'review' ? 'bg-violet-600 text-white' : (activeFormalTask.value?.status === 'submitted' ? 'bg-violet-100 text-violet-700' : 'bg-slate-100 text-slate-600'),
    active: trainerMainlineMode.value === 'review',
    activeClass: 'border-violet-300 bg-violet-50 shadow-sm',
    idleClass: 'border-violet-200 bg-white hover:bg-violet-50/60',
  },
  {
    key: 'exclusive',
    title: '5. 巡检策略',
    description: '看风险、低风险代办和带教策略是否要调整。',
    badge: trainerMainlineMode.value === 'exclusive' ? '当前' : '策略',
    badgeClass: trainerMainlineMode.value === 'exclusive' ? 'bg-sky-600 text-white' : 'bg-sky-100 text-sky-700',
    active: trainerMainlineMode.value === 'exclusive',
    activeClass: 'border-sky-300 bg-sky-50 shadow-sm',
    idleClass: 'border-sky-200 bg-white hover:bg-sky-50/60',
  },
]) as Array<{
  key: TrainerMainlineMode | 'intake'
  title: string
  description: string
  badge: string
  badgeClass: string
  active: boolean
  activeClass: string
  idleClass: string
}>)

const trainerWorkNodeLink = computed(() => {
  const taskId = String(activeFormalTask.value?.task_id || '').trim()
  const memberId = String(selectedChildMemberId.value || '').trim()
  if (!taskId || !memberId) return null
  const wt = String(
    formalTaskAssignWorkTypeId.value
    || selectedChildMemberDraft.value?.current_jobs?.[0]?.job_id
    || '',
  ).trim()
  return {
    path: '/dashboard',
    query: {
      scope: 'node',
      node: `node:${taskId}`,
      member: memberId,
      wt: wt || undefined,
    },
  }
})

const trainerSubNavItems = computed<WorkspaceSubNavItem[]>(() => (
  trainerMainlineCards.value.map((item) => ({
    key: item.key,
    title: item.title.replace(/^\d+\.\s*/, ''),
    badge: item.badge,
    badgeClass: item.badgeClass,
    active: item.active,
  }))
))

const onTrainerSubNavSelect = (key: string) => {
  if (key === 'intake') {
    router.push('/organization/intake')
    return
  }
  if (key === 'portrait' || key === 'dispatch' || key === 'review' || key === 'exclusive') {
    setTrainerMainlineMode(key, { replace: false })
  }
}

const normalizeTrainerMainlineMode = (value: unknown): TrainerMainlineMode | null => {
  const normalized = String(value || '').trim()
  if (normalized === 'portrait' || normalized === 'dispatch' || normalized === 'review' || normalized === 'exclusive') {
    return normalized
  }
  return null
}

const normalizeTrainerSelectedMember = (value: unknown): string => String(value || '').trim()

const normalizePortraitWorkspaceMode = (value: unknown): PortraitWorkspaceMode | null => {
  const normalized = String(value || '').trim()
  if (normalized === 'summary' || normalized === 'members' || normalized === 'identity' || normalized === 'state') {
    return normalized
  }
  return null
}

const normalizeDispatchWorkspaceMode = (value: unknown): DispatchWorkspaceMode | null => {
  const normalized = String(value || '').trim()
  if (normalized === 'summary' || normalized === 'assign' || normalized === 'confirm' || normalized === 'collaboration') {
    return normalized
  }
  return null
}

const normalizeReviewWorkspaceMode = (value: unknown): ReviewWorkspaceMode | null => {
  const normalized = String(value || '').trim()
  if (normalized === 'conversation' || normalized === 'professional' || normalized === 'diagnosis' || normalized === 'knowledge') {
    return normalized
  }
  return null
}

const normalizeExclusiveWorkspaceMode = (value: unknown): ExclusiveWorkspaceMode | null => {
  const normalized = String(value || '').trim()
  if (normalized === 'overview' || normalized === 'queue' || normalized === 'automation' || normalized === 'growth') {
    return normalized
  }
  return null
}

const resolveTrainerTabQuery = (mode: TrainerMainlineMode, query: Record<string, unknown>) => {
  if (mode === 'portrait') {
    return { portraitTab: normalizePortraitWorkspaceMode(query.portraitTab) || portraitWorkspaceMode.value }
  }
  if (mode === 'dispatch') {
    return { dispatchTab: normalizeDispatchWorkspaceMode(query.dispatchTab) || dispatchWorkspaceMode.value }
  }
  if (mode === 'review') {
    return { reviewTab: normalizeReviewWorkspaceMode(query.reviewTab) || reviewWorkspaceMode.value }
  }
  return { exclusiveTab: normalizeExclusiveWorkspaceMode(query.exclusiveTab) || exclusiveWorkspaceMode.value }
}

const setTrainerMainlineMode = (mode: TrainerMainlineMode | 'intake' | string, options?: { replace?: boolean }) => {
  if (mode === 'intake') {
    router.push('/organization/intake')
    return
  }
  const nextMode = mode as TrainerMainlineMode
  trainerMainlineMode.value = nextMode
  const currentMode = normalizeTrainerMainlineMode(route.query.mode)
  if (currentMode === nextMode) {
    syncTrainerRouteQuery({ mode: nextMode }, options)
    return
  }
  syncTrainerRouteQuery({ mode: nextMode }, options)
}

const syncTrainerRouteQuery = (
  updates: {
    mode?: TrainerMainlineMode
    member?: string
    portraitTab?: PortraitWorkspaceMode | null
    dispatchTab?: DispatchWorkspaceMode | null
    reviewTab?: ReviewWorkspaceMode | null
    exclusiveTab?: ExclusiveWorkspaceMode | null
  },
  options?: { replace?: boolean },
) => {
  const nextMode = updates.mode ?? normalizeTrainerMainlineMode(route.query.mode)
  const nextMember = updates.member !== undefined ? normalizeTrainerSelectedMember(updates.member) : normalizeTrainerSelectedMember(route.query.member)
  const currentMode = normalizeTrainerMainlineMode(route.query.mode)
  const currentMember = normalizeTrainerSelectedMember(route.query.member)
  const currentPortraitTab = normalizePortraitWorkspaceMode(route.query.portraitTab)
  const currentDispatchTab = normalizeDispatchWorkspaceMode(route.query.dispatchTab)
  const currentReviewTab = normalizeReviewWorkspaceMode(route.query.reviewTab)
  const currentExclusiveTab = normalizeExclusiveWorkspaceMode(route.query.exclusiveTab)
  const nextTabs = resolveTrainerTabQuery(nextMode || 'portrait', {
    ...route.query,
    ...updates,
  })

  if (
    currentMode === nextMode
    && currentMember === nextMember
    && currentPortraitTab === (nextTabs as { portraitTab?: PortraitWorkspaceMode }).portraitTab
    && currentDispatchTab === (nextTabs as { dispatchTab?: DispatchWorkspaceMode }).dispatchTab
    && currentReviewTab === (nextTabs as { reviewTab?: ReviewWorkspaceMode }).reviewTab
    && currentExclusiveTab === (nextTabs as { exclusiveTab?: ExclusiveWorkspaceMode }).exclusiveTab
  ) return

  const nextQuery: LocationQueryRaw = {
    ...route.query,
  }
  if (nextMode) nextQuery.mode = nextMode
  else delete nextQuery.mode
  if (nextMember) nextQuery.member = nextMember
  else delete nextQuery.member
  delete nextQuery.portraitTab
  delete nextQuery.dispatchTab
  delete nextQuery.reviewTab
  delete nextQuery.exclusiveTab
  if ('portraitTab' in nextTabs && nextTabs.portraitTab) nextQuery.portraitTab = nextTabs.portraitTab
  if ('dispatchTab' in nextTabs && nextTabs.dispatchTab) nextQuery.dispatchTab = nextTabs.dispatchTab
  if ('reviewTab' in nextTabs && nextTabs.reviewTab) nextQuery.reviewTab = nextTabs.reviewTab
  if ('exclusiveTab' in nextTabs && nextTabs.exclusiveTab) nextQuery.exclusiveTab = nextTabs.exclusiveTab

  const navigation = {
    path: route.path,
    query: nextQuery,
  }
  const action = options?.replace === false ? router.push(navigation) : router.replace(navigation)
  action.catch(() => {})
}

const inferTrainerMainlineMode = (
  member: ChildMemberRuntimeProfile | null | undefined,
  activeTask?: AutonomyFormalTask | null,
): 'portrait' | 'dispatch' | 'review' | 'exclusive' => {
  const primaryRole = String(member?.primary_role || '').trim()
  if (primaryRole === 'talent_development') return 'exclusive'

  const onboardingStatus = String(member?.onboarding?.status || '').trim()
  const trainingStage = String(member?.training_plan?.stage || '').trim()
  const taskStatus = String(activeTask?.status || '').trim()

  if (!primaryRole || ['portrait_created', 'trainer_taken_over'].includes(onboardingStatus) || ['profile_initialized', 'foundation'].includes(trainingStage)) {
    return 'portrait'
  }
  if (taskStatus === 'submitted') return 'review'
  if (taskStatus === 'assigned' || taskStatus === 'approved') return 'dispatch'
  return 'dispatch'
}

const syncTrainerMainlineMode = (options?: { force?: boolean }) => {
  if (!options?.force && trainerMainlineMode.value === 'exclusive' && String(selectedChildMemberDraft.value?.primary_role || '') !== 'talent_development') {
    setTrainerMainlineMode('dispatch')
    return
  }
  if (!options?.force && ['dispatch', 'review'].includes(trainerMainlineMode.value) && !selectedChildMemberId.value) {
    setTrainerMainlineMode('portrait')
    return
  }
  setTrainerMainlineMode(inferTrainerMainlineMode(selectedChildMemberDraft.value, activeFormalTask.value))
}
const selfMediaKnowledgeEntries = computed(() => {
  const repoKey = selfMediaGitRepoKey.value
  const repoEntries = gitStatus.value?.repo_index?.repos?.[repoKey]?.entries
  if (!Array.isArray(repoEntries)) return []
  return repoEntries
    .filter((entry) => {
      if (!entry || typeof entry !== 'object') return false
      const source = String(entry.source || '').trim()
      return !source || source === 'self_media_autonomy'
    })
    .slice(0, 6)
})

const buildEmployeeSeedFromWorkType = (employeeName: string, workType: WorkTypeItem) => {
  const normalizedName = String(employeeName || '').trim() || '新员工'
  const workTypeId = String(workType.work_type_id || '').trim()
  const title = String(workType.title || workTypeId).trim() || workTypeId
  const defaultGoal = String(workType.goal_schema?.default_goal || '').trim()
  return {
    roleLabel: title,
    primaryRole: workTypeId,
    selfDescription: `${normalizedName} 是「${title}」岗位成员，等待育成师确认画像、边界和首轮训练方向。`,
    longTermGoal: defaultGoal || '先完成岗位定义与第一轮真实任务闭环，再逐步形成稳定经验。',
  }
}

const findCompanyWorkType = (workTypeId?: string | null) => {
  const normalized = String(workTypeId || '').trim()
  if (!normalized) return null
  return companyWorkTypes.value.find((item) => item.work_type_id === normalized) || null
}

const applyWorkTypeToPortraitDraft = (workTypeId: string) => {
  const workType = findCompanyWorkType(workTypeId)
  if (!workType) return
  childPrimaryRole.value = workType.work_type_id
  childRoleLabel.value = String(workType.title || workType.work_type_id)
  if (workType.goal_schema?.default_goal) {
    childLongTermGoal.value = String(workType.goal_schema.default_goal)
  }
  childCurrentFocus.value = workType.work_type_id
  childPreferredDomainsText.value = workType.work_type_id
}

const loadMissionTemplates = async () => {
  try {
    const result = await listMissionTemplates()
    missionTemplates.value = result.data?.items || []
  } catch {
    missionTemplates.value = []
  }
}

const loadCompanyWorkTypes = async () => {
  companyWorkTypesLoading.value = true
  try {
    const result = await getWorkTypes()
    companyWorkTypes.value = (result.data?.items || []).filter((item) => item.work_type_id)
  } catch {
    companyWorkTypes.value = []
  } finally {
    companyWorkTypesLoading.value = false
  }
}

const onTrainerWorkTypeSaved = async (workTypeId: string) => {
  await loadCompanyWorkTypes()
  newChildPortraitWorkTypeId.value = workTypeId
  formalTaskAssignWorkTypeId.value = workTypeId
}

const applyRouteWorkTypePrefill = () => {
  const workTypeId = String(route.query.work_type_id || '').trim()
  if (!workTypeId) return
  newChildPortraitWorkTypeId.value = workTypeId
  applyWorkTypeToPortraitDraft(workTypeId)
  trainerMainlineMode.value = 'portrait'
  portraitWorkspaceMode.value = 'summary'
}

const normalizeTextList = (value: string) => (
  value.split(',').map((item) => item.trim()).filter(Boolean)
)

const buildTrainingPlanDraft = (member: ChildMemberRuntimeProfile) => {
  const primaryRole = String(member.primary_role || member.role_memory?.primary_identity || 'autonomous_child_agent')
  const roleLabel = String(member.persona?.role_label || member.name || primaryRole)
  const trainingOwner = String(member.onboarding?.training_owner_member_id || 'talent_development_officer')
  const existing = member.training_plan || {}

  const defaults: Record<string, { goals: string[]; curriculum: string[]; milestones: string[]; nextAction: string; stage: string }> = {
    talent_development: {
      stage: 'active_training',
      goals: ['稳定建立新子女岗位画像', '为每个子女生成可执行的成长路径', '持续复盘培养质量并纠偏'],
      curriculum: ['岗位画像建模', '训练计划设计', '培养结果复盘'],
      milestones: ['完成系统默认育成官初始化', '成功接管至少一个新子女培养过程', '沉淀可复用的培养经验'],
      nextAction: '继续观察新子女画像需求并优化培养方法',
    },
  }
  const fallback = defaults[primaryRole] || {
    stage: 'profile_initialized',
    goals: [`理解 ${roleLabel} 的核心职责与目标`, '找到该岗位第一轮可执行案例', '沉淀稳定可复用的经验闭环'],
    curriculum: ['岗位认知建立', '真实案例实践', '复盘与经验入库'],
    milestones: ['完成岗位画像初始化', '完成首个真实案例', '形成首轮经验卡片'],
    nextAction: `由育成官继续细化 ${roleLabel} 的实践训练路径`,
  }

  return {
    stage: String(existing.stage || fallback.stage),
    owner_member_id: String(existing.owner_member_id || trainingOwner),
    goals: Array.isArray(existing.goals) && existing.goals.length ? existing.goals : fallback.goals,
    curriculum: Array.isArray(existing.curriculum) && existing.curriculum.length ? existing.curriculum : fallback.curriculum,
    milestones: Array.isArray(existing.milestones) && existing.milestones.length ? existing.milestones : fallback.milestones,
    next_action: String(existing.next_action || fallback.nextAction),
    review_after: existing.review_after || null,
  }
}

const buildChildPortraitBootstrapSummary = (member: ChildMemberRuntimeProfile): ChildPortraitBootstrapSummary => {
  const roleLabel = String(member.persona?.role_label || member.name || member.primary_role || '员工成员').trim()
  return {
    member_id: String(member.member_id || '').trim(),
    name: String(member.name || member.identity?.name || member.member_id || '新子女').trim(),
    role_label: roleLabel,
    primary_role: String(member.primary_role || member.role_memory?.primary_identity || '').trim(),
    next_action: String(
      member.training_plan?.next_action
      || member.growth_state?.next_goal
      || `继续完成 ${roleLabel} 的第一轮岗位实践`
    ).trim(),
  }
}

const persistAutonomyIdentityDraftSilently = async () => {
  persistSelectedChildDraft()
  const result = await updateAutonomyIdentity({
    tenant_id: tenantId.value || 'default',
    parent_profile: {
      display_name: parentDisplayName.value || undefined,
      role_label: parentRoleLabel.value || undefined,
      description: parentDescription.value || undefined,
    },
    primary_child_member_id: selectedChildMemberId.value || undefined,
    child_members: {
      selected_member_id: selectedChildMemberId.value || undefined,
      items: childMembersDraft.value,
    },
  })
  autonomyStatus.value = result.data || autonomyStatus.value
  if (result.data) {
    hydrateAutonomyIdentityDraft(result.data)
  }
}

const syncChildLifecycleFromRuntime = (payload: AutonomyStatus | null) => {
  const runtimeMembers = payload?.child_members?.items || []
  let changed = false
  for (const runtimeMember of runtimeMembers) {
    const memberId = String(runtimeMember?.member_id || '').trim()
    if (!memberId) continue
    const target = childMembersDraft.value.find((item) => String(item.member_id || '') === memberId)
    if (!target) continue
    const currentStatus = String(target.onboarding?.status || '').trim()
    const jobRuntimeStatus = String(runtimeMember?.current_jobs?.[0]?.runtime_state?.status || '').trim()
    const tenantState = runtimeMember?.current_jobs?.[0]?.runtime_state?.tenant_state
    const hasReflection = !!runtimeMember?.experience_journal?.last_compiled_at
    const hasRuntimeProgress = !!(
      jobRuntimeStatus
      && !['waiting_login', 'executor_missing', 'bootstrapping', 'planned', 'idle'].includes(jobRuntimeStatus)
    )
    const hasDeliverableSignal = !!(
      tenantState?.last_article_title
      || tenantState?.last_task_id
      || tenantState?.last_draft_task_id
      || tenantState?.last_submitted_at
    )
    if (hasReflection && currentStatus !== 'first_reflection_done') {
      advanceChildLifecycleForMember(memberId, 'reflection_compiled')
      changed = true
      continue
    }
    if ((hasRuntimeProgress || hasDeliverableSignal) && ['trainer_taken_over', 'profile_initialized', 'portrait_created'].includes(currentStatus)) {
      advanceChildLifecycleForMember(memberId, 'first_case_started')
      changed = true
      continue
    }
  }
  return changed
}

const advanceChildLifecycleForMember = (
  memberId: string,
  event:
    | 'trainer_take_over'
    | 'first_case_started'
    | 'reflection_requested'
    | 'reflection_compiled'
) => {
  const target = childMembersDraft.value.find((item) => String(item.member_id || '') === String(memberId || ''))
  if (!target) return
  const currentOnboarding = target.onboarding || {}
  const currentTrainingPlan = target.training_plan || buildTrainingPlanDraft(target)
  const firstJob = Array.isArray(target.current_jobs) && target.current_jobs[0]
    ? target.current_jobs[0]
    : null

  if (event === 'trainer_take_over') {
    target.onboarding = {
      ...currentOnboarding,
      status: 'trainer_taken_over',
      notes: `${String(currentOnboarding.notes || '').trim()} 育成官已正式接手，准备安排第一轮真实案例。`.trim(),
    }
    target.training_plan = {
      ...currentTrainingPlan,
      stage: 'profile_initialized',
    }
    if (firstJob) {
      target.current_jobs = [{
        ...firstJob,
        status: 'ready_for_first_case',
      }]
    }
    return
  }

  if (event === 'first_case_started') {
    target.onboarding = {
      ...currentOnboarding,
      status: 'first_case_running',
      notes: `${String(currentOnboarding.notes || '').trim()} 子女已经开始第一轮真实案例实践。`.trim(),
    }
    target.training_plan = {
      ...currentTrainingPlan,
      stage: 'active_training',
    }
    if (firstJob) {
      target.current_jobs = [{
        ...firstJob,
        status: 'running_first_case',
      }]
    }
    return
  }

  if (event === 'reflection_requested') {
    target.onboarding = {
      ...currentOnboarding,
      status: 'reflection_pending',
      notes: `${String(currentOnboarding.notes || '').trim()} 育成官已要求补一轮复盘，等待形成首轮经验沉淀。`.trim(),
    }
    if (firstJob) {
      target.current_jobs = [{
        ...firstJob,
        status: 'awaiting_reflection',
      }]
    }
    return
  }

  target.onboarding = {
    ...currentOnboarding,
    status: 'first_reflection_done',
    notes: `${String(currentOnboarding.notes || '').trim()} 已完成首轮复盘沉淀，可以进入下一轮成长。`.trim(),
  }
  if (firstJob) {
    target.current_jobs = [{
      ...firstJob,
      status: 'first_case_reflected',
    }]
  }
}

const selectedChildLifecycleSummary = computed<ChildLifecycleSummary | null>(() => {
  const status = String(selectedChildMemberDraft.value?.onboarding?.status || '').trim()
  if (!status) return null
  if (status === 'portrait_created') {
    return {
      status,
      label: '已建立画像',
      description: '这个子女刚刚完成岗位画像，还没有进入真实案例训练。',
    }
  }
  if (status === 'trainer_taken_over') {
    return {
      status,
      label: '育成官已接手',
      description: '育成官已经正式接手，下一步应该尽快安排第一轮真实案例。',
    }
  }
  if (status === 'first_case_running') {
    return {
      status,
      label: '首轮案例进行中',
      description: '子女已经开始第一轮真实实践，当前重点是拿到结果与证据。',
    }
  }
  if (status === 'reflection_pending') {
    return {
      status,
      label: '等待首轮复盘',
      description: '案例已经推进过一轮，当前重点是把经验沉淀成可复用认知。',
    }
  }
  if (status === 'first_reflection_done') {
    return {
      status,
      label: '首轮复盘完成',
      description: '已经形成第一批经验沉淀，后面可以进入下一轮任务和迭代。',
    }
  }
  return {
    status,
    label: status,
    description: '当前处于自定义生命周期状态。',
  }
})

const currentTenantAccountId = computed(() => (
  String(toutiaoAccounts.value?.current?.account_id || toutiaoAccountId.value || tenantId.value || 'default').trim() || 'default'
))

const persistSelectedChildDraft = () => {
  const targetId = String(selectedChildMemberId.value || '').trim()
  if (!targetId) return
  const target = childMembersDraft.value.find((item) => String(item.member_id || '') === targetId)
  if (!target) return
  const lockedPrimaryRole = String(target.primary_role || target.role_memory?.primary_identity || childPrimaryRole.value || '').trim()
  target.member_id = childMemberId.value || targetId
  target.name = childName.value || target.name
  target.primary_role = lockedPrimaryRole || target.primary_role
  target.persona = {
    ...(target.persona || {}),
    role_label: childRoleLabel.value || target.persona?.role_label,
    speaking_style: childSpeakingStyle.value || target.persona?.speaking_style,
    interaction_style: childInteractionStyle.value || target.persona?.interaction_style,
    self_description: childSelfDescription.value || target.persona?.self_description,
    tone: target.persona?.tone || target.identity?.tone || 'curious_steady',
  }
  target.identity = {
    ...(target.identity || {}),
    agent_id: childMemberId.value || target.identity?.agent_id || targetId,
    name: childName.value || target.identity?.name,
    self_description: childSelfDescription.value || target.identity?.self_description,
    tone: target.identity?.tone || target.persona?.tone || 'curious_steady',
  }
  target.role_memory = {
    ...(target.role_memory || {}),
    primary_identity: lockedPrimaryRole || target.role_memory?.primary_identity,
    long_term_goal: childLongTermGoal.value || target.role_memory?.long_term_goal,
    strengths: normalizeTextList(childStrengthsText.value),
    shortcomings: normalizeTextList(childShortcomingsText.value),
    preferred_domains: normalizeTextList(childPreferredDomainsText.value),
  }
  target.growth_state = {
    ...(target.growth_state || {}),
    current_focus: childCurrentFocus.value || target.growth_state?.current_focus,
    next_goal: childNextGoal.value || target.growth_state?.next_goal,
  }
  target.operating_contract = {
    ...(target.operating_contract || {}),
    learning_strategy: childLearningStrategy.value || target.operating_contract?.learning_strategy,
    autonomy_mode: target.operating_contract?.autonomy_mode || 'observe_plan_act_reflect',
    allow_external_learning: target.operating_contract?.allow_external_learning ?? true,
      allow_shared_knowledge: target.operating_contract?.allow_shared_knowledge ?? false,
      must_record_experience: target.operating_contract?.must_record_experience ?? true,
  }
  target.training_plan = buildTrainingPlanDraft(target)
  target.onboarding = {
    ...(target.onboarding || {}),
    created_by_member_id: target.onboarding?.created_by_member_id || 'talent_development_officer',
    training_owner_member_id: target.onboarding?.training_owner_member_id || 'talent_development_officer',
    status: target.onboarding?.status || 'profile_initialized',
    created_at: target.onboarding?.created_at || new Date().toISOString(),
      notes: target.onboarding?.notes || '已建立初始画像，等待育成官继续培训与跟进。',
  }
  const selectedWorkType = findCompanyWorkType(lockedPrimaryRole)
  if (selectedWorkType) {
    const existingJob = Array.isArray(target.current_jobs) && target.current_jobs[0]
      ? target.current_jobs[0]
      : {}
    target.current_jobs = [{
      ...existingJob,
      job_id: selectedWorkType.work_type_id,
      title: selectedWorkType.title || existingJob.title || selectedWorkType.work_type_id,
      status: existingJob.status || 'profile_initialized',
      account_id: existingJob.account_id || 'default',
    }]
  }
}

const activeChildMembersDraft = computed(() => childMembersDraft.value.filter((item) => String(item.status || 'active') !== 'archived'))
const managedChildMembersDraft = computed(() => (
  activeChildMembersDraft.value.filter((item) => String(item.primary_role || '') !== 'talent_development')
))

const buildRecommendedFormalTaskDraft = (member: ChildMemberRuntimeProfile): FormalTaskRecommendation => (
  buildFormalTaskRecommendation({
    member,
    workTypes: companyWorkTypes.value,
    missionTemplates: missionTemplates.value,
    accountId: String(member.current_jobs?.[0]?.account_id || currentTenantAccountId.value || tenantId.value || 'default').trim(),
  })
)

const applyRecommendedFormalTaskDraft = (member: ChildMemberRuntimeProfile, options: { force?: boolean } = {}) => {
  const { force = false } = options
  if (!force && activeFormalTask.value) return
  const recommended = buildRecommendedFormalTaskDraft(member)
  if (force || !String(formalTaskAssignTitleDraft.value || '').trim()) {
    formalTaskAssignTitleDraft.value = recommended.title
  }
  if (force || !String(formalTaskAssignObjectiveDraft.value || '').trim()) {
    formalTaskAssignObjectiveDraft.value = recommended.objective
  }
  if (force || !formalTaskDeliverablesDraftList.value.length) {
    formalTaskAssignDeliverablesDraft.value = recommended.deliverables.join('\n')
  }
  formalTaskAssignMissionKind.value = String(recommended.mission_kind || '').trim()
  formalTaskAssignWorkTypeId.value = String(recommended.work_type_id || '').trim()
  formalTaskRecommendationHint.value = formatFormalTaskRecommendationHint(recommended)
}

const resetFormalTaskDrafts = () => {
  formalTaskAssignTitleDraft.value = ''
  formalTaskAssignObjectiveDraft.value = ''
  formalTaskAssignDeliverablesDraft.value = '完成第一篇可发布内容\n提交执行结果与复盘\n沉淀下一轮优化点'
  formalTaskApproveNoteDraft.value = ''
  formalTaskMessage.value = ''
  formalTaskAssignMissionKind.value = ''
  formalTaskAssignWorkTypeId.value = ''
  formalTaskRecommendationHint.value = ''
}

const goToChildWorkspaceForMember = (memberId?: string) => {
  const targetId = String(memberId || selectedChildMemberId.value || '').trim()
  if (!targetId) return
  router.push(`/organization/child/${encodeURIComponent(targetId)}/workspace`).catch(() => {})
}

const goToTrainerDispatchForMember = (memberId?: string, dispatchTab: DispatchWorkspaceMode = 'assign') => {
  const targetId = String(memberId || selectedChildMemberId.value || '').trim()
  if (!targetId) return
  dispatchWorkspaceMode.value = dispatchTab
  trainerMainlineMode.value = 'dispatch'
  hydrateSelectedChildDraft(targetId, { skipModeSync: true })
  syncTrainerRouteQuery({
    mode: 'dispatch',
    member: targetId,
    dispatchTab,
  })
}

const hydrateSelectedChildDraft = (memberId?: string, options?: { skipModeSync?: boolean }) => {
  const targetId = String(memberId || selectedChildMemberId.value || '').trim()
  const member = childMembersDraft.value.find((item) => String(item.member_id || '') === targetId)
  if (!member) return
  selectedChildMemberId.value = String(member.member_id || targetId)
  syncTrainerRouteQuery({ member: selectedChildMemberId.value })
  childMemberId.value = String(member.member_id || '')
  childName.value = String(member.name || member.identity?.name || '')
  childPrimaryRole.value = String(member.primary_role || member.role_memory?.primary_identity || '')
  childRoleLabel.value = String(member.persona?.role_label || '')
  childSelfDescription.value = String(member.persona?.self_description || member.identity?.self_description || '')
  childLongTermGoal.value = String(member.role_memory?.long_term_goal || '')
  childSpeakingStyle.value = String(member.persona?.speaking_style || '')
  childInteractionStyle.value = String(member.persona?.interaction_style || '')
  childStrengthsText.value = Array.isArray(member.role_memory?.strengths) ? member.role_memory?.strengths.join(', ') : ''
  childShortcomingsText.value = Array.isArray(member.role_memory?.shortcomings) ? member.role_memory?.shortcomings.join(', ') : ''
  childPreferredDomainsText.value = Array.isArray(member.role_memory?.preferred_domains) ? member.role_memory?.preferred_domains.join(', ') : ''
  childCurrentFocus.value = String(member.growth_state?.current_focus || '')
  childNextGoal.value = String(member.growth_state?.next_goal || '')
  childLearningStrategy.value = String(member.operating_contract?.learning_strategy || '')
  member.training_plan = buildTrainingPlanDraft(member)
  resetFormalTaskDrafts()
  applyRecommendedFormalTaskDraft(member, { force: true })
  if (!options?.skipModeSync) {
    syncTrainerMainlineMode({ force: true })
  }
}

const selectChildMember = (memberId?: string) => {
  persistSelectedChildDraft()
  hydrateSelectedChildDraft(memberId)
}

const archiveSelectedChildMember = () => {
  persistSelectedChildDraft()
  const target = childMembersDraft.value.find((item) => String(item.member_id || '') === String(selectedChildMemberId.value || ''))
  if (!target) return
  target.status = 'archived'
  target.archived_at = new Date().toISOString()
  const next = activeChildMembersDraft.value.find((item) => String(item.member_id || '') !== String(target.member_id || ''))
    || childMembersDraft.value.find((item) => String(item.member_id || '') !== String(target.member_id || ''))
  if (next?.member_id) {
    hydrateSelectedChildDraft(String(next.member_id))
  }
}

const deleteSelectedChildMember = () => {
  persistSelectedChildDraft()
  if (childMembersDraft.value.length <= 1) return
  const currentId = String(selectedChildMemberId.value || '')
  childMembersDraft.value = childMembersDraft.value.filter((item) => String(item.member_id || '') !== currentId)
  const next = activeChildMembersDraft.value[0] || childMembersDraft.value[0]
  if (next?.member_id) {
    hydrateSelectedChildDraft(String(next.member_id))
  }
}

const createChildPortrait = async () => {
  persistSelectedChildDraft()
  try {
    const workTypeId = String(newChildPortraitWorkTypeId.value || '').trim()
    if (!workTypeId) {
      autonomyIdentitySuccess.value = false
      autonomyIdentityMessage.value = '创建员工前必须先选择岗位工种。可在公司设置添加，或在派任务页快速创建审核员/测试员。'
      return
    }
    const workType = findCompanyWorkType(workTypeId)
    if (!workType) {
      autonomyIdentitySuccess.value = false
      autonomyIdentityMessage.value = `工种 ${workTypeId} 不存在，请先在公司设置登记。`
      return
    }
    const portraitName = String(newChildPortraitName.value || '').trim() || `Employee ${childMembersDraft.value.length + 1}`
    const blankSeed = buildEmployeeSeedFromWorkType(portraitName, workType)
    const result = await createAutonomyMember({
      tenant_id: tenantId.value || 'default',
      name: portraitName,
      role_label: blankSeed.roleLabel,
      role_key: blankSeed.primaryRole,
      primary_role: blankSeed.primaryRole,
      work_type_id: workType?.work_type_id,
      self_description: blankSeed.selfDescription,
      long_term_goal: blankSeed.longTermGoal,
      trainer_member_id: 'talent_development_officer',
      created_by_member_id: 'talent_development_officer',
    })
    const createdMember = result.data?.member || result.data?.employee || null
    const createdMemberId = String(createdMember?.member_id || '').trim()
    await loadAutonomyStatus()
    if (createdMemberId) {
      selectedChildMemberId.value = createdMemberId
      hydrateSelectedChildDraft(createdMemberId)
    }
    newChildPortraitName.value = ''
    newChildPortraitWorkTypeId.value = ''
    autonomyIdentitySuccess.value = true
    autonomyIdentityMessage.value = `已创建「${workType.title}」岗位员工 ${portraitName}，下一步确认画像并派首个正式任务`

    const selectedMember = childMembersDraft.value.find((item) => String(item.member_id || '') === createdMemberId)
    const bootstrap = buildChildPortraitBootstrapSummary(selectedMember || createdMember || {})
    const trainerId = String(trainerMemberDraft.value?.member_id || 'talent_development_officer').trim() || 'talent_development_officer'
    await postParentRelationshipMessage({
      tenant_id: tenantId.value || 'default',
      target_member_id: trainerId,
      title: `父节点创建新子女 ${bootstrap.name}`,
      content: `【父节点 -> 育成官】我刚刚创建了新的员工实例 ${bootstrap.name}。先不要套任何固定模板，请你接手这个新成员，确认岗位画像、主线目标、运行边界和第一轮实践。`,
      metadata: {
        directive_type: 'new_child_bootstrap',
        source: 'portrait_bootstrap',
        managed_child_member_id: bootstrap.member_id,
      },
    })
    await postTrainerRelationshipAction({
      tenant_id: tenantId.value || 'default',
      member_id: bootstrap.member_id,
      title: `育成官接手 ${bootstrap.name} 入职培养`,
      content: `育成官已接手 ${bootstrap.name} 的入职培养。当前先完成岗位确认、画像收口和首轮行动闭环设计，下一步是：${bootstrap.next_action}。`,
      action_type: 'take_over',
      metadata: {
        source: 'portrait_bootstrap',
        bootstrap: true,
        training_stage_from: 'portrait_created',
        training_stage_to: 'profile_initialized',
      },
    })
    await loadAutonomyStatus()
    autonomyIdentitySuccess.value = true
    const boundWorkTypeId = resolveMemberWorkTypeId(
      (childMembersDraft.value.find((item) => String(item.member_id || '') === createdMemberId) || createdMember) as ChildMemberRuntimeProfile,
    )
    if (createdMemberId && boundWorkTypeId) {
      goToTrainerDispatchForMember(createdMemberId, 'assign')
      autonomyIdentityMessage.value = `${bootstrap.name} 已创建完成，已跳转派任务页并生成 Mission 草案`
    } else {
      autonomyIdentityMessage.value = `${bootstrap.name} 已创建完成，并已进入育成师接手阶段`
    }
  } catch (error) {
    console.error('Failed to create employee instance:', error)
    autonomyIdentitySuccess.value = false
    autonomyIdentityMessage.value = '创建员工实例失败'
  }
}

const hydrateAutonomyIdentityDraft = (payload: AutonomyStatus | null) => {
  const parent = payload?.parent_profile || {}
  parentDisplayName.value = String(parent.display_name || '')
  parentRoleLabel.value = String(parent.role_label || '父节点')
  parentDescription.value = String(parent.description || '')
  const members = payload?.child_members?.items || []
  childMembersDraft.value = members.map((item) => {
    const cloned = JSON.parse(JSON.stringify(item))
    cloned.training_plan = buildTrainingPlanDraft(cloned)
    return cloned
  })
  const routeMemberId = normalizeTrainerSelectedMember(route.query.member)
  selectedChildMemberId.value = routeMemberId || String(payload?.child_members?.selected_member_id || members[0]?.member_id || '')
  if (!childMembersDraft.value.length && payload?.child_agent) {
    childMembersDraft.value = [{
      member_id: String(payload.child_agent.identity?.agent_id || 'legacy_child_agent'),
      name: String(payload.child_agent.identity?.name || 'Legacy Child Agent'),
      identity_type: 'child_agent',
      primary_role: String(payload.child_agent.role_memory?.primary_identity || 'autonomous_child_agent'),
      persona: {
        role_label: '岗位成员',
        speaking_style: 'clear_supportive',
        self_description: String(payload.child_agent.identity?.self_description || ''),
        tone: String(payload.child_agent.identity?.tone || 'curious_steady'),
      },
      identity: payload.child_agent.identity,
      role_memory: payload.child_agent.role_memory,
      growth_state: payload.child_agent.growth_state,
      training_plan: payload.child_agent.training_plan,
      current_jobs: payload.child_agent.current_jobs,
      world_observation: payload.child_agent.world_observation,
      derived_state: payload.child_agent.derived_state,
    }]
    selectedChildMemberId.value = String(childMembersDraft.value[0]?.member_id || '')
  }
  const activeFirst = childMembersDraft.value.find((item) => String(item.status || 'active') !== 'archived')
  if (!childMembersDraft.value.find((item) => String(item.member_id || '') === selectedChildMemberId.value) || String(childMembersDraft.value.find((item) => String(item.member_id || '') === selectedChildMemberId.value)?.status || 'active') === 'archived') {
    selectedChildMemberId.value = String(activeFirst?.member_id || childMembersDraft.value[0]?.member_id || '')
  }
  hydrateSelectedChildDraft(selectedChildMemberId.value)
}

const loadPluginSettings = async () => {
  pluginsLoading.value = true
  policyMessage.value = ''
  localStorage.setItem('tenant_id', tenantId.value || 'default')

  try {
    const [pluginRes, policyRes] = await Promise.all([
      listPlugins(),
      getTenantPluginPolicy(tenantId.value || 'default'),
    ])

    plugins.value = pluginRes.data?.plugins || []
    enabledPlugins.value = policyRes.data?.policy?.enabled || []
    disabledPlugins.value = policyRes.data?.policy?.disabled || []
  } catch (error) {
    console.error('Failed to load plugin settings:', error)
    policySuccess.value = false
    policyMessage.value = '插件设置加载失败，请检查后台服务是否已启动'
  } finally {
    pluginsLoading.value = false
  }
}

const loadGitStatus = async () => {
  gitLoading.value = true
  gitMessage.value = ''
  try {
    const result = await getGitProviderStatus(tenantId.value || 'default')
    gitStatus.value = result.data || null
    gitProvider.value = gitStatus.value?.git_knowledge?.provider || gitStatus.value?.provider || 'gitee'
    gitApiBase.value = gitStatus.value?.git_knowledge?.api_base || result.data?.api_base || ''
    gitBaseUrl.value = gitStatus.value?.git_knowledge?.base_url || ''
    gitNamespace.value = gitStatus.value?.git_knowledge?.namespace || ''
    if (gitStatus.value?.git_knowledge?.repos && !gitStatus.value.git_knowledge.repos[gitIndexRepoKey.value]) {
      const firstRepoKey = Object.keys(gitStatus.value.git_knowledge.repos)[0]
      gitIndexRepoKey.value = firstRepoKey || 'config'
    }
    if (!repoBaseName.value) {
      repoBaseName.value = gitStatus.value?.git_knowledge?.base_name || `evo-${tenantId.value || 'default'}`
    }
    gitScanErrors.value = []
  } catch (error) {
    console.error('Failed to load git provider status:', error)
    gitSuccess.value = false
    gitMessage.value = 'Git 状态加载失败'
  } finally {
    gitLoading.value = false
  }
}

const loadKnowledgePolicy = async () => {
  knowledgePolicyLoading.value = true
  knowledgePolicyMessage.value = ''
  try {
    const result = await getTenantKnowledgePolicy(tenantId.value || 'default')
    knowledgePolicy.value = result.data?.policy || {
      share_mode: 'private_only',
      allow_platform_promotion: false,
      review_required: true,
    }
  } catch (error) {
    console.error('Failed to load knowledge policy:', error)
    knowledgePolicySuccess.value = false
    knowledgePolicyMessage.value = '共享策略加载失败'
  } finally {
    knowledgePolicyLoading.value = false
  }
}

const loadExternalLearningPolicy = async () => {
  externalLearningPolicyLoading.value = true
  externalLearningPolicyMessage.value = ''
  try {
    const result = await getTenantExternalLearningPolicy(tenantId.value || 'default')
    externalLearningPolicy.value = result.data?.policy || externalLearningPolicy.value
  } catch (error) {
    console.error('Failed to load external learning policy:', error)
    externalLearningPolicySuccess.value = false
    externalLearningPolicyMessage.value = '外部学习策略加载失败'
  } finally {
    externalLearningPolicyLoading.value = false
  }
}

const bootstrapGitKnowledge = async () => {
  gitBootstrapping.value = true
  gitMessage.value = ''
  try {
    const result = await bootstrapTenantGitKnowledge(tenantId.value || 'default', {
      base_name: repoBaseName.value || `evo-${tenantId.value || 'default'}`,
      private: true,
      provider: gitProvider.value,
      api_base: gitApiBase.value || undefined,
      base_url: gitBaseUrl.value || undefined,
      namespace: gitNamespace.value || undefined,
    })
    gitSuccess.value = true
    gitMessage.value = result.message || '知识仓库初始化完成'
    await loadGitStatus()
  } catch (error) {
    console.error('Failed to bootstrap git knowledge:', error)
    gitSuccess.value = false
    gitMessage.value = '知识仓库初始化失败，请先绑定 Gitee Token'
  } finally {
    gitBootstrapping.value = false
  }
}

const loadGitIndexTemplate = async () => {
  gitTemplateLoading.value = true
  gitMessage.value = ''
  try {
    const result = await getGitKnowledgeIndexTemplate(tenantId.value || 'default')
    gitIndexTemplate.value = result.data || null
    if (gitStatus.value && result.data?.repo_index && result.data?.repo_index_summary) {
      gitStatus.value = {
        ...gitStatus.value,
        repo_index: result.data.repo_index,
        repo_index_summary: result.data.repo_index_summary,
      }
    }
    gitSuccess.value = true
    gitMessage.value = result.message || '索引模板已生成'
  } catch (error) {
    console.error('Failed to build git knowledge index template:', error)
    gitSuccess.value = false
    gitMessage.value = '索引模板生成失败'
  } finally {
    gitTemplateLoading.value = false
  }
}

const scanGitKnowledge = async () => {
  gitScanning.value = true
  gitMessage.value = ''
  try {
    const result = await scanTenantGitKnowledge(tenantId.value || 'default')
    gitScanErrors.value = result.data?.errors || []
    if (gitStatus.value && result.data?.repo_index && result.data?.repo_index_summary) {
      gitStatus.value = {
        ...gitStatus.value,
        repo_index: result.data.repo_index,
        repo_index_summary: result.data.repo_index_summary,
      }
    }
    gitSuccess.value = true
    gitMessage.value = result.message || '企业仓索引扫描完成'
  } catch (error) {
    console.error('Failed to scan git knowledge:', error)
    gitSuccess.value = false
    gitMessage.value = '企业仓索引扫描失败，请确认 Token 和仓库可访问'
  } finally {
    gitScanning.value = false
  }
}

const exportGitIndexTemplate = async () => {
  gitTemplateExporting.value = true
  gitMessage.value = ''
  try {
    const result = await exportGitKnowledgeIndexTemplate(tenantId.value || 'default', {
      repo_key: gitIndexRepoKey.value || 'config',
      file_path: 'evo/index.json',
      scan_after_write: true,
    })
    gitScanErrors.value = []
    if (gitStatus.value && result.data?.repo_index && result.data?.repo_index_summary) {
      gitStatus.value = {
        ...gitStatus.value,
        repo_index: result.data.repo_index,
        repo_index_summary: result.data.repo_index_summary,
      }
    }
    gitSuccess.value = true
    gitMessage.value = result.message || '索引模板已写入仓库'
    await loadGitIndexTemplate()
  } catch (error) {
    console.error('Failed to export git knowledge index template:', error)
    gitSuccess.value = false
    gitMessage.value = '索引模板写入失败，请确认 Token、命名空间和仓库权限'
  } finally {
    gitTemplateExporting.value = false
  }
}

const loadPlatformSeeds = async () => {
  seedLoading.value = true
  seedMessage.value = ''
  localStorage.setItem('tenant_id', tenantId.value || 'default')
  try {
    const result = await getPlatformSharedSeeds(tenantId.value || 'default')
    seedRecommendations.value = result.data || null
  } catch (error) {
    console.error('Failed to load platform shared seeds:', error)
    seedSuccess.value = false
    seedMessage.value = '平台冷启动种子加载失败'
  } finally {
    seedLoading.value = false
  }
}

const applyRecommendedSeeds = async () => {
  const strategyIds = (seedRecommendations.value?.items || []).map((item) => item.strategy_id)
  if (!strategyIds.length) return

  seedApplying.value = true
  seedMessage.value = ''
  try {
    const result = await applyPlatformSharedSeeds(tenantId.value || 'default', strategyIds)
    seedSuccess.value = true
    seedMessage.value = result.message || '平台冷启动种子已应用'
    await loadPlatformSeeds()
    await loadPluginSettings()
  } catch (error) {
    console.error('Failed to apply platform shared seeds:', error)
    seedSuccess.value = false
    seedMessage.value = '平台冷启动种子应用失败'
  } finally {
    seedApplying.value = false
  }
}

const loadAutonomyStatus = async () => {
  autonomyLoading.value = true
  try {
    const result = await getAutonomyStatus(tenantId.value || 'default')
    autonomyStatus.value = result.data || null
    hydrateAutonomyIdentityDraft(result.data || null)
    if (syncChildLifecycleFromRuntime(result.data || null)) {
      await persistAutonomyIdentityDraftSilently()
      await loadAutonomyStatus()
      return
    }
  } catch (error) {
    console.error('Failed to load autonomy status:', error)
  } finally {
    autonomyLoading.value = false
  }
}

const onCollaborationAutonomyUpdated = (status: AutonomyStatus | null) => {
  if (!status) return
  autonomyStatus.value = status
  hydrateAutonomyIdentityDraft(status)
}

const runTrainingReview = async () => {
  trainingReviewRunning.value = true
  trainingReviewMessage.value = ''
  try {
    const result = await runAutonomyTrainingReview(tenantId.value || 'default')
    autonomyStatus.value = result.data?.autonomy || autonomyStatus.value
    if (result.data?.autonomy) {
      hydrateAutonomyIdentityDraft(result.data.autonomy)
      const runtimeMembers = result.data.autonomy.child_members?.items || []
      for (const item of runtimeMembers) {
        if (item?.experience_journal?.last_compiled_at) {
          advanceChildLifecycleForMember(String(item.member_id || ''), 'reflection_compiled')
        }
      }
      await persistAutonomyIdentityDraftSilently()
    }
    const changedCount = Number(result.data?.review_summary?.changed_count || 0)
    trainingReviewSuccess.value = true
    trainingReviewMessage.value = result.message || (
      changedCount
        ? `育成官已更新 ${changedCount} 个子女的训练计划`
        : '育成官巡检完成，当前没有需要调整的训练计划'
    )
  } catch (error) {
    console.error('Failed to run autonomy training review:', error)
    trainingReviewSuccess.value = false
    trainingReviewMessage.value = '育成官巡检失败'
  } finally {
    trainingReviewRunning.value = false
  }
}

const applyAutonomyTaskSnapshot = (payload?: AutonomyStatus | null) => {
  if (!payload) return
  autonomyStatus.value = payload
  hydrateAutonomyIdentityDraft(payload)
}

const assignFormalTaskToSelectedChild = async () => {
  const memberId = String(selectedChildMemberId.value || '').trim()
  const title = String(formalTaskAssignTitleDraft.value || '').trim()
  const objective = String(formalTaskAssignObjectiveDraft.value || '').trim()
  const deliverables = formalTaskDeliverablesDraftList.value
  if (!memberId || !title || !objective) return
  formalTaskActionRunning.value = 'assign'
  formalTaskMessage.value = ''
  try {
    const result = await assignAutonomyTask({
      tenant_id: tenantId.value || 'default',
      member_id: memberId,
      title,
      objective,
      deliverables,
      metadata: {
        source: 'settings_formal_task_panel',
        work_type_id: String(formalTaskAssignWorkTypeId.value || childCurrentJobs.value[0]?.job_id || selectedChildMemberDraft.value?.primary_role || '').trim() || undefined,
        mission_kind: String(formalTaskAssignMissionKind.value || '').trim() || undefined,
        role_scope: String(
          childCurrentJobs.value[0]?.job_id
          || selectedChildMemberDraft.value?.primary_role
          || '',
        ).trim() || undefined,
      },
    })
    applyAutonomyTaskSnapshot(result.data?.autonomy || null)
    formalTaskSuccess.value = true
    formalTaskMessage.value = `${result.message || '正式任务已分配'} · 正在打开员工工作台`
    formalTaskApproveNoteDraft.value = ''
    goToChildWorkspaceForMember(memberId)
  } catch (error) {
    console.error('Failed to assign formal task:', error)
    formalTaskSuccess.value = false
    formalTaskMessage.value = '正式任务分配失败'
  } finally {
    formalTaskActionRunning.value = ''
  }
}

const approveSelectedFormalTask = async () => {
  const taskId = String(activeFormalTask.value?.task_id || '').trim()
  if (!taskId) return
  formalTaskActionRunning.value = 'approve'
  formalTaskMessage.value = ''
  try {
    const result = await approveAutonomyTask({
      tenant_id: tenantId.value || 'default',
      task_id: taskId,
      review_note: String(formalTaskApproveNoteDraft.value || '').trim() || undefined,
    })
    applyAutonomyTaskSnapshot(result.data?.autonomy || null)
    formalTaskSuccess.value = true
    formalTaskMessage.value = result.message || '本轮任务已确认完成'
    await loadLearningTasks()
    const evolution = result.data?.evolution_summary
    if (evolution?.next_task_title) {
      dispatchWorkspaceMode.value = 'assign'
      syncTrainerRouteQuery({ mode: 'dispatch', dispatchTab: 'assign' })
    }
    await consoleCtx?.refreshOverview?.()
  } catch (error) {
    console.error('Failed to approve formal task:', error)
    formalTaskSuccess.value = false
    formalTaskMessage.value = '任务确认失败'
  } finally {
    formalTaskActionRunning.value = ''
  }
}

const exportCurrentTenantExperiencesToGit = async () => {
  formalTaskExperienceExporting.value = true
  formalTaskMessage.value = ''
  try {
    const result = await exportTenantExperiences(tenantId.value || 'default')
    formalTaskSuccess.value = true
    formalTaskMessage.value = result.success
      ? `${result.message || '经验已导出'}：${result.data?.file_path || ''}`
      : (result.message || '经验导出失败')
    await loadAutonomyStatus()
  } catch (error) {
    console.error('Failed to export experiences to git knowledge:', error)
    formalTaskSuccess.value = false
    formalTaskMessage.value = '经验导出失败'
  } finally {
    formalTaskExperienceExporting.value = false
  }
}

const adoptRecommendedFormalTask = () => {
  const recommendation = activeFormalTaskRecommendation.value
  if (!recommendation) return
  formalTaskAssignTitleDraft.value = String(recommendation.title || '').trim()
  formalTaskAssignObjectiveDraft.value = String(recommendation.objective || '').trim()
  formalTaskAssignDeliverablesDraft.value = Array.isArray(recommendation.deliverables)
    ? recommendation.deliverables.join('\n')
    : ''
  formalTaskSuccess.value = true
  formalTaskMessage.value = '已采用系统生成的下一轮任务建议，你可以直接分配或再微调。'
}

const adoptAndAssignRecommendedFormalTask = async () => {
  const recommendation = activeFormalTaskRecommendation.value
  const memberId = String(selectedChildMemberId.value || '').trim()
  if (!recommendation || !memberId) return
  formalTaskActionRunning.value = 'assign'
  formalTaskMessage.value = ''
  try {
    const result = await assignAutonomyTask({
      tenant_id: tenantId.value || 'default',
      member_id: memberId,
      recommendation_id: String(recommendation.recommendation_id || '').trim() || undefined,
      title: String(recommendation.title || '').trim(),
      objective: String(recommendation.objective || '').trim(),
      deliverables: Array.isArray(recommendation.deliverables) ? recommendation.deliverables : [],
      metadata: {
        source: 'auto_recommendation_one_click_assign',
        adopted_from_recommendation: true,
      },
    })
    applyAutonomyTaskSnapshot(result.data?.autonomy || null)
    formalTaskSuccess.value = true
    formalTaskMessage.value = `${result.message || '已根据系统建议直接进入下一轮任务'} · 正在打开员工工作台`
    goToChildWorkspaceForMember(memberId)
  } catch (error) {
    console.error('Failed to adopt and assign recommended task:', error)
    formalTaskSuccess.value = false
    formalTaskMessage.value = '一键进入下一轮任务失败'
  } finally {
    formalTaskActionRunning.value = ''
  }
}

const handleTrainerDirectiveAction = async (
  item: TrainerDirectiveQueueItem,
  actionType: 'take_over' | 'request_reflection' | 'replan_training',
) => {
  const memberId = String(item.managed_child_member_id || '').trim()
  if (!memberId) return
  const actionKey = `${item.message_id}:${actionType}`
  trainerActionRunningId.value = actionKey
  try {
    let content = ''
    let title = ''
    if (actionType === 'take_over') {
      title = `育成官已接手 ${item.managed_child_name}`
      content = `育成官已正式接手 ${item.managed_child_name} 当前交办任务，接下来会围绕 ${item.managed_child_role} 主线推进：${item.next_action || item.current_focus || '继续当前训练主线'}。`
    } else if (actionType === 'request_reflection') {
      title = `育成官要求 ${item.managed_child_name} 补复盘`
      content = `育成官已要求 ${item.managed_child_name} 先补一轮岗位复盘，再继续推进当前 ${item.managed_child_role} 训练，重点关注：${item.current_focus || item.next_action || '当前专业主线'}。`
    } else {
      title = `育成官重排 ${item.managed_child_name} 训练`
      content = `育成官已开始重排 ${item.managed_child_name} 的训练计划，会重新评估当前阶段 ${item.training_stage || '--'} 与下一步 ${item.next_action || '--'} 是否需要调整。`
    }
    const result = await postTrainerRelationshipAction({
      tenant_id: tenantId.value || 'default',
      member_id: memberId,
      title,
      content,
      action_type: actionType,
      metadata: {
        source_directive_message_id: item.message_id,
        directive_type: item.directive_type,
      },
    })
    autonomyStatus.value = result.data || autonomyStatus.value
    if (result.data) {
      hydrateAutonomyIdentityDraft(result.data)
    }
    if (actionType === 'take_over') {
      advanceChildLifecycleForMember(memberId, 'trainer_take_over')
      await persistAutonomyIdentityDraftSilently()
    } else if (actionType === 'request_reflection') {
      advanceChildLifecycleForMember(memberId, 'reflection_requested')
      await persistAutonomyIdentityDraftSilently()
    }
    trainingReviewSuccess.value = true
    trainingReviewMessage.value = result.message || '育成官处理动作已记录'
  } catch (error) {
    console.error('Failed to post trainer action:', error)
    trainingReviewSuccess.value = false
    trainingReviewMessage.value = '育成官处理动作写入失败'
  } finally {
    trainerActionRunningId.value = ''
  }
}

const handleTrainerDirectiveReview = async (item: TrainerDirectiveQueueItem) => {
  if (item.managed_child_member_id) {
    selectChildMember(item.managed_child_member_id)
  }
  await runTrainingReview()
}

const handleTrainerSuggestedAction = async (item: TrainerDirectiveQueueItem) => {
  const actionKey = `${item.message_id}:suggested`
  trainerActionRunningId.value = actionKey
  try {
    if (item.suggested_action === 'take_over' || item.suggested_action === 'request_reflection' || item.suggested_action === 'replan_training') {
      await handleTrainerDirectiveAction(item, item.suggested_action)
      return
    }
    if (item.suggested_action === 'run_review') {
      await handleTrainerDirectiveReview(item)
      return
    }
    trainingReviewSuccess.value = true
    trainingReviewMessage.value = `${item.managed_child_name || '当前子女'} 当前建议进入观察阶段，暂不自动执行额外动作`
  } finally {
    if (trainerActionRunningId.value === actionKey) {
      trainerActionRunningId.value = ''
    }
  }
}

const runTrainerLowRiskSuggestionBatch = async () => {
  if (!trainerAutoAssistEnabled.value) return
  const queue = trainerLowRiskSuggestionQueue.value.slice(0, 6)
  if (!queue.length) return
  trainerBatchRunning.value = true
  try {
    for (const item of queue) {
      if (item.suggested_action === 'take_over' || item.suggested_action === 'request_reflection') {
        await handleTrainerDirectiveAction(item, item.suggested_action)
      }
    }
    trainingReviewSuccess.value = true
    trainingReviewMessage.value = `育成官已批量执行 ${queue.length} 条低风险建议`
  } catch (error) {
    console.error('Failed to run low risk suggestion batch:', error)
    trainingReviewSuccess.value = false
    trainingReviewMessage.value = '低风险建议批处理失败'
  } finally {
    trainerBatchRunning.value = false
  }
}

const maybeRunTrainerAutoAssist = async () => {
  if (!trainerAutoAssistEnabled.value || trainerBatchRunning.value) return
  const signature = trainerLowRiskSuggestionSignature.value
  if (!signature || signature === trainerAutoAssistLastSignature.value) return
  trainerAutoAssistLastSignature.value = signature
  await runTrainerLowRiskSuggestionBatch()
}

const sendParentMessage = async () => {
  const targetMemberId = String(trainerMemberDraft.value?.member_id || '').trim()
  const managedChildMemberId = String(selectedChildMemberId.value || '').trim()
  const content = String(parentDirectivePreview.value.content || '').trim()
  if (!targetMemberId || !managedChildMemberId || !content) return
  parentMessageSending.value = true
  try {
    const result = await postParentRelationshipMessage({
      tenant_id: tenantId.value || 'default',
      target_member_id: targetMemberId,
      content,
      title: parentDirectivePreview.value.title,
      metadata: {
        directive_type: parentDirectivePreview.value.directive_type,
        source: 'parent_directive_console',
        managed_child_member_id: managedChildMemberId,
      },
    })
    autonomyStatus.value = result.data || autonomyStatus.value
    if (result.data) {
      hydrateAutonomyIdentityDraft(result.data)
    }
    parentMessageDraft.value = ''
    autonomyIdentitySuccess.value = true
    autonomyIdentityMessage.value = result.message || '父节点留言已送达'
  } catch (error) {
    console.error('Failed to send parent message:', error)
    autonomyIdentitySuccess.value = false
    autonomyIdentityMessage.value = '父节点留言发送失败'
  } finally {
    parentMessageSending.value = false
  }
}

const sendChildReply = async () => {
  const memberId = String(selectedChildMemberId.value || '').trim()
  const content = String(childReplyDraft.value || '').trim()
  if (!memberId || !content) return
  childReplySending.value = true
  try {
    const result = await postChildRelationshipReply({
      tenant_id: tenantId.value || 'default',
      member_id: memberId,
      content,
    })
    autonomyStatus.value = result.data || autonomyStatus.value
    if (result.data) {
      hydrateAutonomyIdentityDraft(result.data)
    }
    advanceChildLifecycleForMember(memberId, 'first_case_started')
    await persistAutonomyIdentityDraftSilently()
    childReplyDraft.value = ''
    autonomyIdentitySuccess.value = true
    autonomyIdentityMessage.value = result.message || '子女反馈已提交'
  } catch (error) {
    console.error('Failed to send child reply:', error)
    autonomyIdentitySuccess.value = false
    autonomyIdentityMessage.value = '子女反馈提交失败'
  } finally {
    childReplySending.value = false
  }
}

const saveAutonomyIdentity = async () => {
  autonomyIdentitySaving.value = true
  autonomyIdentityMessage.value = ''
  try {
    persistSelectedChildDraft()
    const result = await updateAutonomyIdentity({
      tenant_id: tenantId.value || 'default',
      parent_profile: {
        display_name: parentDisplayName.value || undefined,
        role_label: parentRoleLabel.value || undefined,
        description: parentDescription.value || undefined,
      },
      primary_child_member_id: selectedChildMemberId.value || undefined,
      child_members: {
        selected_member_id: selectedChildMemberId.value || undefined,
        items: childMembersDraft.value,
      },
    })
    autonomyStatus.value = result.data || null
    hydrateAutonomyIdentityDraft(result.data || null)
    autonomyIdentitySuccess.value = true
    autonomyIdentityMessage.value = result.message || '公司与员工身份已更新'
  } catch (error) {
    console.error('Failed to save autonomy identity:', error)
    autonomyIdentitySuccess.value = false
    autonomyIdentityMessage.value = '员工身份保存失败'
  } finally {
    autonomyIdentitySaving.value = false
  }
}

const loadWorkerRegistry = async () => {
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
    selfMediaExecutorModeDraft.value = result.data?.self_media?.executor_registry?.configured_runtime?.preferred_mode || 'auto'
    selfMediaExecutorDirDraft.value = result.data?.self_media?.executor_registry?.configured_runtime?.executor_dir || ''
    selfMediaExecutorLoginTargetUrlDraft.value = result.data?.self_media?.executor_registry?.configured_runtime?.login_target_url || ''
  } catch (error) {
    console.error('Failed to load worker registry:', error)
    workerRegistrySuccess.value = false
    workerRegistryMessage.value = '工种目录加载失败'
  } finally {
    workerRegistryLoading.value = false
  }
}

const saveSelfMediaExecutorConfig = async () => {
  selfMediaExecutorSaving.value = true
  workerRegistryMessage.value = ''
  try {
    const result = await updateSelfMediaExecutorConfig({
      preferred_mode: selfMediaExecutorModeDraft.value || 'auto',
      executor_dir: selfMediaExecutorDirDraft.value.trim() || null,
      login_target_url: selfMediaExecutorLoginTargetUrlDraft.value.trim() || null,
    })
    workerRegistrySuccess.value = true
    workerRegistryMessage.value = result.message || '自媒体执行器默认路由已更新'
    await loadWorkerRegistry()
  } catch (error) {
    console.error('Failed to save self media executor config:', error)
    workerRegistrySuccess.value = false
    workerRegistryMessage.value = '自媒体执行器默认路由保存失败'
  } finally {
    selfMediaExecutorSaving.value = false
  }
}

const hydrateToutiaoAccountDraft = (payload: ToutiaoAccountsPayload | null) => {
  const current = payload?.current
  toutiaoAccountDisplayName.value = String(current?.display_name || '')
  const profile = current?.profile && typeof current.profile === 'object' ? current.profile : {}
  toutiaoAccountProfileUrl.value = String((profile as Record<string, unknown>).profile_url || '')
  toutiaoAccountNotes.value = String((profile as Record<string, unknown>).notes || '')
  toutiaoLoginTargetUrl.value = String((profile as Record<string, unknown>).login_target_url || selfMediaExecutorLoginTargetUrlDraft.value || '')
}

const loadToutiaoAccounts = async () => {
  toutiaoAccountLoading.value = true
  toutiaoAccountMessage.value = ''
  try {
    const result = await getToutiaoAccounts(toutiaoAccountId.value || 'default')
    toutiaoAccounts.value = result.data || null
    hydrateToutiaoAccountDraft(result.data || null)
    const sessionsResult = await getToutiaoSessions(toutiaoAccountId.value || 'default')
    toutiaoSessions.value = sessionsResult.data?.items || []
    toutiaoAccountSuccess.value = true
  } catch (error) {
    console.error('Failed to load toutiao accounts:', error)
    toutiaoAccountSuccess.value = false
    toutiaoAccountMessage.value = '头条账号状态加载失败'
  } finally {
    toutiaoAccountLoading.value = false
  }
}

const beginToutiaoAccountLoginFlow = async () => {
  toutiaoAccountSaving.value = true
  toutiaoAccountMessage.value = ''
  try {
    const result = await beginToutiaoLogin({
      account_id: toutiaoAccountId.value || 'default',
      display_name: toutiaoAccountDisplayName.value || undefined,
      login_target_url: toutiaoLoginTargetUrl.value || undefined,
    })
    toutiaoAccountSuccess.value = true
    toutiaoAccountMessage.value = result.message || '已创建登录占位会话'
    await loadToutiaoAccounts()
  } catch (error) {
    console.error('Failed to begin toutiao login:', error)
    toutiaoAccountSuccess.value = false
    toutiaoAccountMessage.value = '登录占位会话创建失败'
  } finally {
    toutiaoAccountSaving.value = false
  }
}

const launchToutiaoLoginTarget = async () => {
  toutiaoAccountSaving.value = true
  toutiaoAccountMessage.value = ''
  try {
    const sessionId = String((toutiaoAccounts.value?.current?.profile as Record<string, unknown> | undefined)?.login_session_id || '')
    const result = await launchToutiaoLogin(toutiaoAccountId.value || 'default', {
      session_id: sessionId || undefined,
      login_target_url: toutiaoLoginTargetUrl.value || undefined,
    })
    const target = (result.data as any)?.result?.login_target_url as string | undefined
    if (target) {
      window.open(target, '_blank', 'noopener,noreferrer')
    }
    toutiaoAccountSuccess.value = true
    toutiaoAccountMessage.value = result.message || '已发起登录目标'
    await loadToutiaoAccounts()
  } catch (error) {
    console.error('Failed to launch toutiao login target:', error)
    toutiaoAccountSuccess.value = false
    toutiaoAccountMessage.value = '登录目标发起失败'
  } finally {
    toutiaoAccountSaving.value = false
  }
}

const openToutiaoHandoffPage = async () => {
  toutiaoAccountMessage.value = ''
  try {
    const result = await getToutiaoHandoffInfo(toutiaoAccountId.value || 'default')
    const handoffUrl = result.data?.handoff_url
    if (!handoffUrl) {
      throw new Error('missing handoff url')
    }
    window.open(handoffUrl, '_blank', 'noopener,noreferrer')
    toutiaoAccountSuccess.value = true
    toutiaoAccountMessage.value = result.message || '登录接管页已打开'
  } catch (error) {
    console.error('Failed to open toutiao handoff page:', error)
    toutiaoAccountSuccess.value = false
    toutiaoAccountMessage.value = '登录接管页打开失败'
  }
}

const confirmToutiaoAccountLoginFlow = async () => {
  toutiaoAccountSaving.value = true
  toutiaoAccountMessage.value = ''
  try {
    const result = await confirmToutiaoLogin(toutiaoAccountId.value || 'default', {
      display_name: toutiaoAccountDisplayName.value || undefined,
      profile_url: toutiaoAccountProfileUrl.value || undefined,
    })
    toutiaoAccountSuccess.value = true
    toutiaoAccountMessage.value = result.message || '账号已标记为登录就绪'
    await loadToutiaoAccounts()
  } catch (error) {
    console.error('Failed to confirm toutiao login:', error)
    toutiaoAccountSuccess.value = false
    toutiaoAccountMessage.value = '登录确认失败'
  } finally {
    toutiaoAccountSaving.value = false
  }
}

const saveToutiaoAccountDraft = async () => {
  toutiaoAccountSaving.value = true
  toutiaoAccountMessage.value = ''
  try {
    const result = await updateToutiaoAccount(toutiaoAccountId.value || 'default', {
      display_name: toutiaoAccountDisplayName.value || undefined,
      profile_url: toutiaoAccountProfileUrl.value || undefined,
      login_target_url: toutiaoLoginTargetUrl.value || undefined,
      notes: toutiaoAccountNotes.value || undefined,
    })
    toutiaoAccountSuccess.value = true
    toutiaoAccountMessage.value = result.message || '账号信息已更新'
    await loadToutiaoAccounts()
  } catch (error) {
    console.error('Failed to save toutiao account:', error)
    toutiaoAccountSuccess.value = false
    toutiaoAccountMessage.value = '账号信息保存失败'
  } finally {
    toutiaoAccountSaving.value = false
  }
}

const logoutToutiaoAccountFlow = async () => {
  toutiaoAccountSaving.value = true
  toutiaoAccountMessage.value = ''
  try {
    const result = await logoutToutiaoLogin(toutiaoAccountId.value || 'default')
    toutiaoAccountSuccess.value = true
    toutiaoAccountMessage.value = result.message || '账号已登出'
    await loadToutiaoAccounts()
  } catch (error) {
    console.error('Failed to logout toutiao account:', error)
    toutiaoAccountSuccess.value = false
    toutiaoAccountMessage.value = '账号登出失败'
  } finally {
    toutiaoAccountSaving.value = false
  }
}

const loadLearningTasks = async () => {
  learningTasksLoading.value = true
  try {
    const result = await getAutonomyLearningTasks(tenantId.value || 'default')
    learningTasks.value = result.data?.items || []
  } catch (error) {
    console.error('Failed to load learning tasks:', error)
  } finally {
    learningTasksLoading.value = false
  }
}

const triggerLearningTaskValidation = async (taskId: string) => {
  validatingLearningTaskId.value = taskId
  learningTaskMessage.value = ''
  try {
    const result = await validateLearningTask(taskId, tenantId.value || 'default')
    learningTaskMessage.value = result.message || result.data?.message || '学习任务验证已启动'
    await loadLearningTasks()
    await loadAutonomyStatus()
  } catch (error) {
    console.error('Failed to validate learning task:', error)
    learningTaskMessage.value = '学习任务验证启动失败'
  } finally {
    validatingLearningTaskId.value = ''
  }
}

const loadEvolutionOverview = async () => {
  evolutionLoading.value = true
  try {
    const result = await getEvolutionOverview(tenantId.value || 'default')
    evolutionOverview.value = result.data || null
  } catch (error) {
    console.error('Failed to load evolution overview:', error)
  } finally {
    evolutionLoading.value = false
  }
}

onMounted(async () => {
  await loadCompanyWorkTypes()
  await loadMissionTemplates()
  applyRouteWorkTypePrefill()
  await loadAutonomyStatus()
  await loadWorkerRegistry()
  await loadToutiaoAccounts()
  await loadLearningTasks()
  await loadEvolutionOverview()
  await loadPluginSettings()
  await loadKnowledgePolicy()
  await loadExternalLearningPolicy()
  await loadPlatformSeeds()
  await loadGitStatus()
  await loadGitIndexTemplate()
  await maybeRunTrainerAutoAssist()
})

watch(tenantId, async (value, oldValue) => {
  if (!value || value === oldValue) return
  localStorage.setItem('tenant_id', value || 'default')
  await loadCompanyWorkTypes()
  await loadMissionTemplates()
  await loadAutonomyStatus()
  await loadWorkerRegistry()
  await loadLearningTasks()
  await loadEvolutionOverview()
  await loadPluginSettings()
  await loadKnowledgePolicy()
  await loadExternalLearningPolicy()
  await loadPlatformSeeds()
  await loadGitStatus()
  await loadGitIndexTemplate()
  trainerAutoAssistLastSignature.value = ''
  await maybeRunTrainerAutoAssist()
})

watch(toutiaoAccountId, async (value, oldValue) => {
  if (!value || value === oldValue) return
  await loadToutiaoAccounts()
})

watch(trainerAutoAssistEnabled, async (value) => {
  localStorage.setItem('trainer_auto_assist_enabled', value ? '1' : '0')
  if (!value) return
  trainerAutoAssistLastSignature.value = ''
  await maybeRunTrainerAutoAssist()
})

watch(() => route.query.mode, (value) => {
  const normalized = normalizeTrainerMainlineMode(value)
  if (normalized && normalized !== trainerMainlineMode.value) {
    trainerMainlineMode.value = normalized
  }
}, { immediate: true })

watch(() => route.query.portraitTab, (value) => {
  const normalized = normalizePortraitWorkspaceMode(value)
  if (normalized && normalized !== portraitWorkspaceMode.value) {
    portraitWorkspaceMode.value = normalized
  }
}, { immediate: true })

watch(() => route.query.dispatchTab, (value) => {
  const normalized = normalizeDispatchWorkspaceMode(value)
  if (normalized && normalized !== dispatchWorkspaceMode.value) {
    dispatchWorkspaceMode.value = normalized
  }
}, { immediate: true })

watch(() => [selectedChildMemberId.value, trainerMainlineMode.value] as const, ([memberId, mode]) => {
  if (mode === 'dispatch' && memberId) {
    void loadLearningTasks()
  }
})

watch(() => route.query.reviewTab, (value) => {
  const normalized = normalizeReviewWorkspaceMode(value)
  if (normalized && normalized !== reviewWorkspaceMode.value) {
    reviewWorkspaceMode.value = normalized
  }
}, { immediate: true })

watch(() => route.query.exclusiveTab, (value) => {
  const normalized = normalizeExclusiveWorkspaceMode(value)
  if (normalized && normalized !== exclusiveWorkspaceMode.value) {
    exclusiveWorkspaceMode.value = normalized
  }
}, { immediate: true })

watch([companyWorkTypes, missionTemplates], () => {
  const member = selectedChildMemberDraft.value
  if (!member || activeFormalTask.value) return
  applyRecommendedFormalTaskDraft(member, { force: true })
})

watch(() => route.query.work_type_id, async () => {
  if (!companyWorkTypes.value.length) {
    await loadCompanyWorkTypes()
  }
  applyRouteWorkTypePrefill()
})

watch(() => route.query.member, (value) => {
  const normalized = normalizeTrainerSelectedMember(value)
  if (!normalized || normalized === selectedChildMemberId.value) return
  const exists = childMembersDraft.value.find((item) => String(item.member_id || '') === normalized)
  if (exists) {
    persistSelectedChildDraft()
    hydrateSelectedChildDraft(normalized)
  }
}, { immediate: true })

watch(activeFormalTask, () => {
  syncTrainerMainlineMode({ force: true })
})

watch(trainerAutoAssistAllowedTakeOver, (value) => {
  localStorage.setItem('trainer_auto_assist_allowed_take_over', value ? '1' : '0')
})

watch(trainerAutoAssistAllowedReflection, (value) => {
  localStorage.setItem('trainer_auto_assist_allowed_reflection', value ? '1' : '0')
})

watch(trainerAutoAssistAllowedStages, (value) => {
  localStorage.setItem('trainer_auto_assist_allowed_stages', value.join(','))
}, { deep: true })

watch(trainerLowRiskSuggestionSignature, async () => {
  await maybeRunTrainerAutoAssist()
})
</script>
