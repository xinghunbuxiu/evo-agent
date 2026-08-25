<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      eyebrow="育成师 · 支撑工具"
      :title="sectionMeta.title"
      :description="sectionMeta.description"
      :loading="loading"
      refresh-label="刷新"
      :back-to="trainerWorkspaceRoute"
      back-label="返回育成工作台"
      @refresh="refreshSection"
    >
      <template #actions>
        <router-link
          to="/organization/parent/workspace?section=integrations"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          公司接入设置
        </router-link>
      </template>
    </WorkspacePageHeader>

    <WorkspaceSubNav
      orientation="horizontal"
      :items="subNavItems"
      @select="onSectionSelect"
    />

    <div v-show="activeSection === 'overview'" class="grid gap-4 md:grid-cols-2">
      <article class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="text-sm font-semibold text-slate-900">Gitee 入库就绪</div>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm">
            <div class="text-slate-400">用户 Token</div>
            <div class="mt-1 font-medium">{{ gitStatus?.has_user_token ? '已绑定' : '未绑定' }}</div>
          </div>
          <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm">
            <div class="text-slate-400">索引条目</div>
            <div class="mt-1 font-medium">{{ gitStatus?.repo_index_summary?.total_entries || 0 }}</div>
          </div>
        </div>
        <router-link
          to="/organization/parent/workspace?section=integrations"
          class="mt-4 inline-flex text-xs font-medium text-teal-700 hover:underline"
        >
          去公司空间配置 Gitee →
        </router-link>
      </article>
      <article class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="text-sm font-semibold text-slate-900">能力边界摘要</div>
        <div class="mt-3 space-y-2 text-sm text-slate-700">
          <div>插件 {{ plugins.length }} 个 · 启用白名单 {{ enabledPlugins.length }}</div>
          <div>工种 {{ workerManifestList.length }} · 已启用 {{ enabledWorkerCount }}</div>
          <div>共享制度 {{ knowledgePolicyLabel }}</div>
        </div>
        <router-link
          to="/organization/parent/workspace?section=worktypes"
          class="mt-4 inline-flex text-xs font-medium text-teal-700 hover:underline"
        >
          去公司空间管理工种 →
        </router-link>
      </article>
    </div>

    <div v-show="activeSection === 'workers'" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="text-sm font-semibold text-slate-900">工种与执行器（只读）</div>
        <span class="text-xs text-slate-500">修改请前往公司设置</span>
      </div>
      <div class="mt-4 grid gap-3 md:grid-cols-4">
        <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm">
          <div class="text-slate-400">工种总数</div>
          <div class="mt-1 text-lg font-semibold">{{ workerManifestList.length }}</div>
        </div>
        <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm">
          <div class="text-slate-400">已启用</div>
          <div class="mt-1 text-lg font-semibold">{{ enabledWorkerCount }}</div>
        </div>
        <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm">
          <div class="text-slate-400">项目外挂</div>
          <div class="mt-1 text-lg font-semibold">{{ externalWorkerCount }}</div>
        </div>
        <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm">
          <div class="text-slate-400">运行中</div>
          <div class="mt-1 text-lg font-semibold">{{ runtimeWorkerCount }}</div>
        </div>
      </div>
      <div v-if="workerManifestList.length" class="mt-4 space-y-3">
        <article
          v-for="item in workerManifestList"
          :key="item.worker_id"
          class="rounded-xl border border-slate-200 px-4 py-4"
        >
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div>
              <div class="font-medium text-slate-900">{{ item.title || item.worker_id }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ item.capability_type }} · {{ item.source === 'external' ? '外挂' : '内置' }}</div>
            </div>
            <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px]">
              {{ workerEnabled(item.worker_id) ? '已启用' : '已停用' }}
            </span>
          </div>
          <div class="mt-2 text-[11px] text-slate-500">
            处理器 {{ workerRegistry?.runtime?.workers?.[item.worker_id]?.handler_count ?? 0 }}
            · 模块 {{ item.owned_modules.join(', ') || '--' }}
          </div>
        </article>
      </div>
      <div v-else class="mt-4 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
        暂无执行器注册信息。
      </div>
    </div>

    <div v-show="activeSection === 'git'" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="text-sm font-semibold text-slate-900">Git 知识仓状态</div>
      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm">
          <div class="text-slate-400">Provider</div>
          <div class="mt-1 font-medium">{{ gitStatus?.provider || '--' }}</div>
        </div>
        <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm">
          <div class="text-slate-400">Namespace</div>
          <div class="mt-1 font-medium">{{ gitStatus?.git_knowledge?.namespace || '--' }}</div>
        </div>
      </div>
      <div v-if="gitRepos.length" class="mt-4 divide-y divide-slate-100 rounded-xl border border-slate-200">
        <div
          v-for="repo in gitRepos"
          :key="repo.key"
          class="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm"
        >
          <div>
            <div class="font-medium text-slate-900">{{ repo.key }}</div>
            <div class="text-xs text-slate-500">{{ repo.full_name || repo.url || '--' }}</div>
          </div>
          <span class="text-xs text-slate-500">{{ repo.branch || 'master' }}</span>
        </div>
      </div>
      <p v-else class="mt-4 text-sm text-slate-500">尚未配置 Git 仓库，请在公司设置中绑定。</p>
    </div>

    <div v-show="activeSection === 'policies'" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="text-sm font-semibold text-slate-900">公司制度摘要（只读）</div>
      <div class="mt-4 grid gap-4 md:grid-cols-2">
        <div class="rounded-xl border border-violet-200 bg-violet-50/60 px-4 py-4 text-sm">
          <div class="font-medium text-violet-950">共享制度</div>
          <div class="mt-2">模式 {{ knowledgePolicy.share_mode || 'private_only' }}</div>
          <div class="mt-1">平台晋升 {{ knowledgePolicy.allow_platform_promotion ? '允许' : '关闭' }}</div>
          <div class="mt-1">审核 {{ knowledgePolicy.review_required ? '必需' : '可跳过' }}</div>
        </div>
        <div class="rounded-xl border border-sky-200 bg-sky-50/60 px-4 py-4 text-sm">
          <div class="font-medium text-sky-950">外部学习边界</div>
          <div class="mt-2">AI {{ externalLearningPolicy.allow_ai_assist ? '允许' : '关闭' }}</div>
          <div class="mt-1">网页 {{ externalLearningPolicy.allow_web_research ? '允许' : '关闭' }}</div>
          <div class="mt-1">企业源 {{ externalLearningPolicy.allow_enterprise_sources ? '允许' : '关闭' }}</div>
        </div>
      </div>
      <router-link
        to="/organization/parent/workspace?section=policies"
        class="mt-4 inline-flex text-xs font-medium text-teal-700 hover:underline"
      >
        去公司空间修改制度 →
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import WorkspaceSubNav from '../components/shell/WorkspaceSubNav.vue'
import type { WorkspaceSubNavItem } from '../components/shell/WorkspaceSubNav.vue'
import {
  getTenantExternalLearningPolicy,
  getTenantKnowledgePolicy,
  getTenantPluginPolicy,
  getWorkerRegistry,
  listPlugins,
  type PluginItem,
  type TenantExternalLearningPolicy,
  type TenantKnowledgePolicy,
  type WorkerManifest,
  type WorkerRegistryPayload,
} from '../api/plugins'
import { getGitProviderStatus } from '../api/git'

type ToolsSection = 'overview' | 'workers' | 'git' | 'policies'

const route = useRoute()
const router = useRouter()
const tenantId = ref(localStorage.getItem('tenant_id') || 'default')
const loading = ref(false)
const activeSection = ref<ToolsSection>('overview')

const gitStatus = ref<Record<string, any> | null>(null)
const workerRegistry = ref<WorkerRegistryPayload | null>(null)
const plugins = ref<PluginItem[]>([])
const enabledPlugins = ref<string[]>([])
const knowledgePolicy = ref<TenantKnowledgePolicy>({
  share_mode: 'private_only',
  allow_platform_promotion: false,
  review_required: true,
})
const externalLearningPolicy = ref<TenantExternalLearningPolicy>({
  allow_ai_assist: true,
  allow_web_research: true,
  allow_enterprise_sources: true,
  source_priority: [],
  validation_required: true,
})

const trainerWorkspaceRoute = computed(() => ({
  path: '/organization/trainer/talent_development_officer/workspace',
  query: route.query.member ? { member: route.query.member } : {},
}))

const sectionMeta = computed(() => {
  const map: Record<ToolsSection, { title: string; description: string }> = {
    overview: { title: '运行摘要', description: '只读观察 Gitee、插件与工种边界；修改请去公司设置。' },
    workers: { title: '工种与执行器', description: '查看 openSpec 执行器注册与启用状态。' },
    git: { title: 'Git 知识仓', description: '查看经验仓接入与索引概况。' },
    policies: { title: '制度摘要', description: '共享制度与外部学习边界（只读）。' },
  }
  return map[activeSection.value]
})

const workerManifestList = computed<WorkerManifest[]>(() => (
  Object.values(workerRegistry.value?.manifests || {}).sort((a, b) => a.worker_id.localeCompare(b.worker_id))
))

const enabledWorkerCount = computed(() => (
  Object.values(workerRegistry.value?.config?.workers || {}).filter((item) => Boolean(item?.enabled)).length
))

const externalWorkerCount = computed(() => workerManifestList.value.filter((item) => item.source === 'external').length)
const runtimeWorkerCount = computed(() => Object.keys(workerRegistry.value?.runtime?.workers || {}).length)

const knowledgePolicyLabel = computed(() => {
  if (knowledgePolicy.value.share_mode === 'platform_share') return '平台共享'
  if (knowledgePolicy.value.share_mode === 'reviewed_share') return '审核共享'
  return '完全私有'
})

const gitRepos = computed(() => {
  const repos = gitStatus.value?.git_knowledge?.repos
  if (!repos || typeof repos !== 'object') return [] as Array<{ key: string; full_name?: string; url?: string; branch?: string }>
  return Object.entries(repos).map(([key, value]) => {
    const meta = (value && typeof value === 'object') ? value as Record<string, string> : {}
    return {
      key,
      full_name: meta.full_name,
      url: meta.url,
      branch: meta.branch,
    }
  })
})

const subNavItems = computed<WorkspaceSubNavItem[]>(() => ([
  { key: 'overview', title: '摘要', active: activeSection.value === 'overview' },
  { key: 'workers', title: '工种', badge: `${enabledWorkerCount.value}/${workerManifestList.value.length}`, active: activeSection.value === 'workers' },
  { key: 'git', title: 'Git', badge: gitStatus.value?.has_user_token ? '已绑定' : '未绑定', active: activeSection.value === 'git' },
  { key: 'policies', title: '制度', badge: knowledgePolicyLabel.value, active: activeSection.value === 'policies' },
]))

const workerEnabled = (workerId: string) => Boolean(workerRegistry.value?.config?.workers?.[workerId]?.enabled)

const normalizeSection = (value: unknown): ToolsSection => {
  const section = String(value || '').trim()
  if (section === 'workers' || section === 'git' || section === 'policies') return section
  return 'overview'
}

const onSectionSelect = (key: string) => {
  const section = normalizeSection(key)
  activeSection.value = section
  router.replace({
    path: route.path,
    query: {
      ...(route.query.member ? { member: route.query.member } : {}),
      ...(section === 'overview' ? {} : { section }),
    },
  })
}

const loadAll = async () => {
  loading.value = true
  try {
    const tid = tenantId.value || 'default'
    const [gitResult, workerResult, pluginResult, policyResult, knowledgeResult, externalResult] = await Promise.all([
      getGitProviderStatus(tid).catch(() => null),
      getWorkerRegistry().catch(() => null),
      listPlugins().catch(() => null),
      getTenantPluginPolicy(tid).catch(() => null),
      getTenantKnowledgePolicy(tid).catch(() => null),
      getTenantExternalLearningPolicy(tid).catch(() => null),
    ])
    gitStatus.value = gitResult?.data || null
    workerRegistry.value = workerResult?.data || null
    plugins.value = pluginResult?.data?.plugins || []
    enabledPlugins.value = policyResult?.data?.policy?.enabled || []
    knowledgePolicy.value = knowledgeResult?.data?.policy || knowledgePolicy.value
    externalLearningPolicy.value = externalResult?.data?.policy || externalLearningPolicy.value
  } finally {
    loading.value = false
  }
}

const refreshSection = async () => {
  await loadAll()
}

watch(() => route.query.section, (value) => {
  activeSection.value = normalizeSection(value)
}, { immediate: true })

onMounted(loadAll)
</script>
