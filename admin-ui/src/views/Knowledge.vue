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

    <div v-show="activeSection === 'overview'" class="space-y-5">
      <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold text-slate-900">三层知识架构</h2>
            <p class="mt-1 text-sm text-slate-500">服务端做分析与建议，项目做上下文，Git 做长期容器，平台共享只接收经过复盘验证的经验。</p>
          </div>
          <div class="text-xs text-slate-400">tenant {{ tenantId || 'default' }}</div>
        </div>
        <div class="mt-4 grid gap-3 md:grid-cols-3">
          <article class="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
            <div class="text-xs uppercase tracking-[0.16em] text-emerald-700">Private Brain</div>
            <div class="mt-2 text-2xl font-bold text-slate-900">{{ privateContainerCount }}</div>
            <div class="mt-2 text-sm text-slate-600">租户私有知识、经验、报告只在自己的空间里生长。</div>
            <div class="mt-3 text-xs text-slate-500">share mode: {{ shareModeLabel }}</div>
          </article>
          <article class="rounded-2xl border border-sky-200 bg-sky-50 p-4">
            <div class="text-xs uppercase tracking-[0.16em] text-sky-700">Project Containers</div>
            <div class="mt-2 text-2xl font-bold text-slate-900">{{ projectContainerCount }}</div>
            <div class="mt-2 text-sm text-slate-600">按工种、项目、经验仓拆分容器，避免所有知识互相污染。</div>
            <div class="mt-3 text-xs text-slate-500">indexed repos: {{ repoIndexSummary?.indexed_repo_count ?? 0 }}</div>
          </article>
          <article class="rounded-2xl border border-fuchsia-200 bg-fuchsia-50 p-4">
            <div class="text-xs uppercase tracking-[0.16em] text-fuchsia-700">Platform Shared</div>
            <div class="mt-2 text-2xl font-bold text-slate-900">{{ sharedContainerCount }}</div>
            <div class="mt-2 text-sm text-slate-600">经过 review 和验证后，才进入平台共享层给后续租户复用。</div>
            <div class="mt-3 text-xs text-slate-500">{{ platformPromotionLabel }}</div>
          </article>
        </div>
        <div v-if="knowledgeLayerAdvice" class="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="text-sm font-semibold text-slate-900">系统自动分层建议</div>
              <div class="mt-1 text-sm text-slate-600">{{ knowledgeLayerAdvice.headline }}</div>
            </div>
            <span class="rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-700">
              next {{ knowledgeLayerAdvice.recommended_next_layer }}
            </span>
          </div>
          <div class="mt-3 text-sm text-slate-500">{{ knowledgeLayerAdvice.recommendation_reason }}</div>
          <div class="mt-4 grid gap-3 md:grid-cols-3">
            <div
              v-for="layer in knowledgeLayerAdvice.layers"
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
          <ul v-if="knowledgeLayerAdvice.next_actions?.length" class="mt-4 space-y-1 text-sm text-slate-600">
            <li v-for="item in knowledgeLayerAdvice.next_actions" :key="item">• {{ item }}</li>
          </ul>
        </div>
      </div>

      <div class="grid gap-4 md:grid-cols-4">
      <div class="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
        <div class="text-2xl font-bold text-teal-600">{{ stats.total }}</div>
        <div class="text-sm text-slate-500">本地技能</div>
      </div>
      <div class="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
        <div class="text-2xl font-bold text-yellow-600">{{ stats.draft }}</div>
        <div class="text-sm text-slate-500">草稿</div>
      </div>
      <div class="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
        <div class="text-2xl font-bold text-green-600">{{ stats.verified }}</div>
        <div class="text-sm text-slate-500">已验证</div>
      </div>
      <div class="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
        <div class="text-2xl font-bold" :class="gitReady ? 'text-emerald-600' : 'text-slate-400'">
          {{ gitReady ? 'Ready' : 'Pending' }}
        </div>
        <div class="text-sm text-slate-500">Git 知识层</div>
      </div>
      </div>
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

    <KnowledgeShardsPanel :inventory="shardInventory" />

    <div v-show="activeSection === 'skills'" class="space-y-5">
      <AutonomySkillsPanel :summary="autonomySkillSummary" :recent-skills="recentAutonomySkills" />

      <div class="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table class="w-full">
        <thead class="border-b bg-slate-50">
          <tr class="text-left text-sm text-slate-500">
            <th class="px-4 py-3 font-medium">技能名称</th>
            <th class="px-4 py-3 font-medium">领域</th>
            <th class="px-4 py-3 font-medium">信任级别</th>
            <th class="px-4 py-3 font-medium">来源</th>
            <th class="px-4 py-3 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="skill in skills" :key="`${skill.domain}-${skill.name}`" class="border-b last:border-0 hover:bg-slate-50">
            <td class="px-4 py-3 font-mono text-sm">{{ skill.name }}</td>
            <td class="px-4 py-3">{{ skill.domain || '-' }}</td>
            <td class="px-4 py-3">
              <StatusBadge :status="skill.trust_level || 'draft'" />
            </td>
            <td class="px-4 py-3">{{ skill.source || 'local' }}</td>
            <td class="px-4 py-3">
              <button
                @click="viewSkill(skill)"
                class="text-sm text-teal-600 hover:text-teal-800"
              >
                查看
              </button>
            </td>
          </tr>
          <tr v-if="skills.length === 0">
            <td colspan="5" class="px-4 py-8 text-center text-gray-500">
              <div v-if="loading" class="loading">加载中...</div>
              <div v-else>当前租户暂无本地技能</div>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>

    <KnowledgeExportPanel :tenant-id="tenantId || 'default'" :refresh="loadSkills" />

    <div v-if="selectedSkill" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 w-full max-w-lg max-h-[80vh] overflow-auto">
        <h2 class="text-xl font-bold mb-4">技能详情</h2>
        <pre class="bg-gray-50 p-4 rounded-lg text-sm overflow-auto">{{ JSON.stringify(selectedSkill, null, 2) }}</pre>
        <div class="flex justify-end mt-4">
          <button
            @click="selectedSkill = null"
            class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StatusBadge from '../components/StatusBadge.vue'
import AutonomySkillsPanel from '../components/AutonomySkillsPanel.vue'
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
  getKnowledgeSkillDetail,
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
const selectedSkill = ref<KnowledgeSkill | null>(null)
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
  localStorage.setItem('tenant_id', tenantId.value || 'default')
  try {
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
  }
  loading.value = false
}

const viewSkill = async (skill: KnowledgeSkill) => {
  try {
    const res = await getKnowledgeSkillDetail(tenantId.value || 'default', skill.domain || 'unknown', skill.name)
    if (res.success && res.data) {
      selectedSkill.value = res.data
    } else {
      selectedSkill.value = skill
    }
  } catch {
    selectedSkill.value = skill
  }
}

onMounted(loadSkills)
</script>
