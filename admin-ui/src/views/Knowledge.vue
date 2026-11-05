<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      eyebrow="知识库"
      :title="sectionMeta.title"
      :description="sectionMeta.description"
      :loading="loading"
      refresh-label="刷新"
      :back-to="{ path: '/dashboard' }"
      back-label="返回公司总览"
      @refresh="refreshSection"
    >
      <template #actions>
        <a
          v-if="knowledgeRepo"
          :href="knowledgeRepo"
          target="_blank"
          rel="noopener noreferrer"
          class="rounded-lg border border-teal-200 bg-teal-50 px-3 py-1.5 text-xs font-medium text-teal-800 hover:bg-teal-100"
        >
          打开 Git 仓库
        </a>
        <router-link
          to="/organization/parent/workspace?section=policies"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          共享制度设置
        </router-link>
      </template>
    </WorkspacePageHeader>

    <WorkspaceSubNav
      orientation="horizontal"
      :items="subNavItems"
      @select="onSectionSelect"
    />

    <div v-show="activeSection === 'overview'">
      <KnowledgeOverviewPanel
        :tenant-id="tenantId || 'default'"
        :private-container-count="privateContainerCount"
        :project-container-count="projectContainerCount"
        :shared-container-count="sharedContainerCount"
        :share-mode-label="shareModeLabel"
        :platform-promotion-label="platformPromotionLabel"
        :indexed-repo-count="repoIndexSummary?.indexed_repo_count ?? 0"
        :knowledge-layer-advice="knowledgeLayerAdvice"
        :stats="stats"
        :git-ready="gitReady"
      />
    </div>

    <div v-show="activeSection === 'index'" class="space-y-5">
      <KnowledgeIndexPanel :tenant-id="tenantId || 'default'" :summary="repoIndexSummary" :refresh="loadSkills" @update:summary="repoIndexSummary = $event" />

      <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 class="text-lg font-semibold text-slate-900">当前租户知识状态</h2>
      <div class="mt-3 grid gap-3 text-sm text-slate-600 md:grid-cols-3">
        <div class="rounded-xl bg-slate-50 px-4 py-3">
          <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Tenant</div>
          <div class="mt-1 font-medium text-slate-900">{{ tenantId || 'default' }}</div>
        </div>
        <div class="rounded-xl bg-slate-50 px-4 py-3">
          <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Repo</div>
          <div class="mt-1 break-all font-medium text-slate-900">{{ repoFullName || '-' }}</div>
        </div>
        <div class="rounded-xl bg-slate-50 px-4 py-3">
          <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Bootstrap</div>
          <div class="mt-1 font-medium text-slate-900">{{ bootstrappedAt || '未初始化' }}</div>
        </div>
      </div>
      <div class="mt-4">
        <div class="mb-2 text-sm font-medium text-slate-900">知识容器</div>
        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <div
            v-for="container in knowledgeContainers"
            :key="container.id"
            class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="font-medium text-slate-900">{{ container.name }}</div>
                <div class="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">
                  {{ container.purpose }} / {{ container.backend }}
                </div>
              </div>
              <span
                class="rounded-full px-2 py-1 text-xs"
                :class="container.status === 'ready'
                  ? 'bg-emerald-100 text-emerald-700'
                  : container.status === 'standby'
                    ? 'bg-amber-100 text-amber-700'
                    : 'bg-slate-200 text-slate-600'"
              >
                {{ container.status }}
              </span>
            </div>
            <div class="mt-2 text-xs text-slate-500">scope: {{ container.scope }} | {{ container.writable ? 'writable' : 'readonly' }}</div>
            <div class="mt-2 break-all text-xs text-slate-600">{{ container.repo_full_name || container.location }}</div>
          </div>
          <div v-if="knowledgeContainers.length === 0" class="rounded-xl border border-dashed border-slate-200 px-4 py-6 text-sm text-slate-500">
            当前还没有发现可用知识容器
          </div>
        </div>
      </div>
      <div v-if="repoIndexSummary?.repos?.length" class="mt-4">
        <div class="mb-2 text-sm font-medium text-slate-900">索引覆盖</div>
        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div
            v-for="repo in repoIndexSummary.repos"
            :key="repo.repo_key"
            class="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm"
          >
            <div class="font-medium text-slate-900">{{ repo.repo_key }}</div>
            <div class="mt-1 text-xs text-slate-500">{{ repo.entry_count }} entries</div>
            <div class="mt-1 text-xs text-slate-400">{{ repo.scanned_at || '未扫描' }}</div>
          </div>
        </div>
      </div>
      <p v-if="pageMessage" class="mt-4 text-sm" :class="pageSuccess ? 'text-green-600' : 'text-rose-600'">
        {{ pageMessage }}
      </p>
      </div>
    </div>

    <div v-show="activeSection === 'shards'" class="space-y-5">
      <KnowledgeShardsPanel :inventory="shardInventory" />
    </div>

    <div v-show="activeSection === 'skills'" class="space-y-5">
      <AutonomySkillsPanel :summary="autonomySkillSummary" :recent-skills="recentAutonomySkills" />

      <KnowledgeSkillsCatalog :tenant-id="tenantId || 'default'" :skills="skills" :loading="loading" />
    </div>

    <div v-show="activeSection === 'export'" class="space-y-5">
      <KnowledgeExportPanel :tenant-id="tenantId || 'default'" :refresh="loadSkills" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AutonomySkillsPanel from '../components/AutonomySkillsPanel.vue'
import KnowledgeOverviewPanel from '../components/KnowledgeOverviewPanel.vue'
import KnowledgeSkillsCatalog from '../components/KnowledgeSkillsCatalog.vue'
import KnowledgeExportPanel from '../components/KnowledgeExportPanel.vue'
import KnowledgeIndexPanel from '../components/KnowledgeIndexPanel.vue'
import KnowledgeShardsPanel from '../components/KnowledgeShardsPanel.vue'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import WorkspaceSubNav, { type WorkspaceSubNavItem } from '../components/shell/WorkspaceSubNav.vue'
import {
  getGitProviderStatus,
  type GitKnowledgeRepoIndexSummary,
  type KnowledgeContainer,
} from '../api/git'
import { getTenantKnowledgePolicy, type TenantKnowledgePolicy } from '../api/plugins'
import {
  getKnowledgeSkills,
  getKnowledgeShards,
  type KnowledgeSkill,
  type KnowledgeSkillsPayload,
  type KnowledgeShardInventory,
} from '../api/knowledge'

type KnowledgeSection = 'overview' | 'index' | 'shards' | 'skills' | 'export'

const route = useRoute()
const router = useRouter()
const activeSection = ref<KnowledgeSection>('overview')

const tenantId = ref(localStorage.getItem('tenant_id') || 'default')
const skills = ref<KnowledgeSkill[]>([])
const stats = ref({ total: 0, draft: 0, verified: 0 })
const loading = ref(false)
const pageMessage = ref('')
const pageSuccess = ref(false)
const knowledgeRepo = ref('')
const repoFullName = ref('')
const bootstrappedAt = ref('')
const gitReady = ref(false)
const knowledgeContainers = ref<KnowledgeContainer[]>([])
const knowledgePolicy = ref<TenantKnowledgePolicy | null>(null)
const knowledgeLayerAdvice = ref<KnowledgeSkillsPayload['knowledge_layer_advice'] | null>(null)
const autonomySkillSummary = ref<KnowledgeSkillsPayload['autonomy_skill_summary'] | null>(null)
const recentAutonomySkills = ref<NonNullable<KnowledgeSkillsPayload['recent_autonomy_skills']>>([])
const repoIndexSummary = ref<GitKnowledgeRepoIndexSummary | null>(null)
const shardInventory = ref<KnowledgeShardInventory | null>(null)

const privateContainerCount = computed(() =>
  knowledgeContainers.value.filter((item) => item.scope === 'tenant_private').length
)
const projectContainerCount = computed(() =>
  knowledgeContainers.value.filter((item) => item.scope === 'project' || item.scope === 'tenant_project').length
)
const sharedContainerCount = computed(() =>
  knowledgeContainers.value.filter((item) => item.scope === 'platform_shared').length
)
const shareModeLabel = computed(() => {
  return knowledgePolicy.value?.share_mode || 'private_only'
})
const platformPromotionLabel = computed(() => {
  if (knowledgePolicy.value?.allow_platform_promotion) {
    return knowledgePolicy.value.review_required ? '允许上报，且需要 review' : '允许直接进入平台共享'
  }
  if (sharedContainerCount.value > 0) return '已有平台共享容器'
  return '当前仍以私有沉淀为主'
})

const sectionMeta = computed(() => {
  const map: Record<KnowledgeSection, { title: string; description: string }> = {
    overview: { title: '知识分层总览', description: '租户私有层、项目容器与可共享层三层结构；制度修改请去公司设置。' },
    index: { title: '索引与容器', description: 'Git 知识仓索引扫描、容器就绪状态与租户绑定信息。' },
    shards: { title: '分布式知识仓', description: '查看按知识场景分库的 Gitee 编号仓库、容量和分片状态。' },
    skills: { title: '技能目录', description: '本地技能、自治产出与信任级别；可查看单条技能详情。' },
    export: { title: '同步与导出', description: '推送技能到 Git、导出经验摘要与成长报告。' },
  }
  return map[activeSection.value]
})

const subNavItems = computed<WorkspaceSubNavItem[]>(() => ([
  { key: 'overview', title: '总览', badge: String(stats.value.total), active: activeSection.value === 'overview' },
  { key: 'index', title: '索引', badge: String(repoIndexSummary.value?.total_entries ?? 0), active: activeSection.value === 'index' },
  { key: 'shards', title: '分布式仓库', badge: String(shardInventory.value?.total ?? 0), active: activeSection.value === 'shards' },
  { key: 'skills', title: '技能', badge: String(stats.value.verified), active: activeSection.value === 'skills' },
  { key: 'export', title: '导出', active: activeSection.value === 'export' },
]))

const normalizeSection = (value: unknown): KnowledgeSection => {
  const section = String(value || '').trim()
  if (section === 'index' || section === 'shards' || section === 'skills' || section === 'export') return section
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
  await loadSkills()
}

watch(() => route.query.section, (value) => {
  activeSection.value = normalizeSection(value)
}, { immediate: true })

const loadSkills = async () => {
  loading.value = true
  pageMessage.value = ''
  try {
    localStorage.setItem('tenant_id', tenantId.value || 'default')
    const currentTenantId = tenantId.value || 'default'
    const [response, providerStatus, policyResponse, shardResponse] = await Promise.all([
      getKnowledgeSkills(currentTenantId),
      getGitProviderStatus(currentTenantId),
      getTenantKnowledgePolicy(currentTenantId),
      getKnowledgeShards(currentTenantId),
    ])
    skills.value = response.data?.skills || []
    knowledgeRepo.value = response.data?.repo || ''
    repoFullName.value = response.data?.repo_full_name || ''
    bootstrappedAt.value = response.data?.git_knowledge?.bootstrapped_at || ''
    knowledgeContainers.value = response.data?.knowledge_containers || providerStatus.data?.knowledge_containers || []
    gitReady.value = Boolean(response.data?.git_knowledge?.repos)
    knowledgeLayerAdvice.value = response.data?.knowledge_layer_advice || null
    autonomySkillSummary.value = response.data?.autonomy_skill_summary || null
    recentAutonomySkills.value = response.data?.recent_autonomy_skills || []
    repoIndexSummary.value = providerStatus.data?.repo_index_summary || null
    shardInventory.value = shardResponse.data || null
    knowledgePolicy.value = policyResponse.data?.policy || null
    stats.value = {
      total: skills.value.length,
      draft: skills.value.filter(s => s.trust_level === 'draft').length,
      verified: skills.value.filter(s => s.trust_level === 'verified').length,
    }
    pageMessage.value = response.message || '知识状态已刷新'
    pageSuccess.value = response.success
  } catch (e) {
    console.error('Failed to load skills:', e)
    pageMessage.value = '知识状态加载失败'
    pageSuccess.value = false
  } finally {
    loading.value = false
  }
}


onMounted(loadSkills)
</script>
