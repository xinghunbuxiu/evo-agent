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
      <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 class="text-lg font-semibold text-slate-900">知识索引状态</h2>
        <div class="mt-4 grid gap-3 sm:grid-cols-3">
          <div class="rounded-xl bg-slate-50 px-4 py-3 text-center">
            <div class="text-2xl font-bold text-slate-900">{{ repoIndexSummary?.repo_count ?? 0 }}</div>
            <div class="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">Repos</div>
          </div>
          <div class="rounded-xl bg-slate-50 px-4 py-3 text-center">
            <div class="text-2xl font-bold text-slate-900">{{ repoIndexSummary?.indexed_repo_count ?? 0 }}</div>
            <div class="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">Indexed</div>
          </div>
          <div class="rounded-xl bg-slate-50 px-4 py-3 text-center">
            <div class="text-2xl font-bold text-slate-900">{{ repoIndexSummary?.total_entries ?? 0 }}</div>
            <div class="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">Entries</div>
          </div>
        </div>
        <div class="mt-4 flex flex-wrap gap-3">
          <button
            class="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            :disabled="scanning"
            @click="scanKnowledgeIndex"
          >
            {{ scanning ? '扫描中...' : '扫描知识索引' }}
          </button>
          <button
            class="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            :disabled="exportingIndex"
            @click="exportIndexTemplate"
          >
            {{ exportingIndex ? '导出中...' : '导出索引模板' }}
          </button>
        </div>
        <p v-if="indexResult" class="mt-3 text-sm" :class="indexSuccess ? 'text-green-600' : 'text-rose-600'">
          {{ indexResult }}
        </p>
      </div>

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

    <div v-show="activeSection === 'skills'" class="space-y-5">
      <div class="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
      <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 class="text-lg font-semibold text-slate-900">自治技能产出</h2>
        <div class="mt-4 grid gap-3 sm:grid-cols-3">
          <div class="rounded-xl bg-slate-50 px-4 py-3 text-center">
            <div class="text-2xl font-bold text-slate-900">{{ autonomySkillSummary?.auto_generated_total ?? 0 }}</div>
            <div class="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">Generated</div>
          </div>
          <div class="rounded-xl bg-amber-50 px-4 py-3 text-center">
            <div class="text-2xl font-bold text-amber-700">{{ autonomySkillSummary?.auto_draft_count ?? 0 }}</div>
            <div class="mt-1 text-xs uppercase tracking-[0.16em] text-amber-500">Draft</div>
          </div>
          <div class="rounded-xl bg-emerald-50 px-4 py-3 text-center">
            <div class="text-2xl font-bold text-emerald-700">{{ autonomySkillSummary?.auto_verified_count ?? 0 }}</div>
            <div class="mt-1 text-xs uppercase tracking-[0.16em] text-emerald-500">Verified</div>
          </div>
        </div>
        <p class="mt-4 text-sm text-slate-500">系统从经验里长出来的技能，不包含纯手工导入。</p>
      </div>
      <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="flex items-center justify-between gap-3">
          <h2 class="text-lg font-semibold text-slate-900">最近自治技能</h2>
          <span class="text-xs text-slate-400">{{ recentAutonomySkills.length }} 条</span>
        </div>
        <div v-if="!recentAutonomySkills.length" class="py-10 text-center text-sm text-slate-500">
          还没有检测到最近的自治技能产出。
        </div>
        <div v-else class="mt-4 space-y-3">
          <div
            v-for="skill in recentAutonomySkills"
            :key="skill.id || `${skill.domain}-${skill.name}`"
            class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="text-sm font-medium text-slate-900">{{ skill.name }}</div>
              <StatusBadge :status="skill.trust_level || 'draft'" />
            </div>
            <div class="mt-2 text-xs text-slate-500">
              {{ skill.domain || 'unknown' }} | {{ skill.source || 'local' }}
            </div>
          </div>
        </div>
      </div>
    </div>

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

    <div v-show="activeSection === 'export'" class="grid gap-4 md:grid-cols-3">
        <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 class="font-semibold text-slate-900">同步本地技能</h3>
          <p class="mt-2 text-sm text-slate-500">把当前租户 `skills/draft` 下的技能推送到 Git knowledge 仓库。</p>
          <button
            @click="syncSkills"
            class="mt-4 rounded-lg bg-teal-500 px-4 py-2 text-white transition-colors hover:bg-teal-600"
            :disabled="syncing"
          >
            {{ syncing ? '同步中...' : '同步本地技能到 Git' }}
          </button>
          <p v-if="syncResult" class="mt-3 text-sm" :class="syncSuccess ? 'text-green-600' : 'text-rose-600'">
            {{ syncResult }}
          </p>
        </div>

        <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 class="font-semibold text-slate-900">导出租户经验</h3>
          <p class="mt-2 text-sm text-slate-500">把成长事件、重放校验记录和子女岗位经验卡片一起导出到 experiences 仓库，形成真正可沉淀的经验层。</p>
          <button
            @click="exportExperiencesToGit"
            class="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-white hover:bg-slate-800"
            :disabled="exportingExperiences"
          >
            {{ exportingExperiences ? '导出中...' : '导出经验摘要' }}
          </button>
          <p v-if="experienceResult" class="mt-3 text-sm" :class="experienceSuccess ? 'text-green-600' : 'text-rose-600'">
            {{ experienceResult }}
          </p>
        </div>

        <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 class="font-semibold text-slate-900">导出成长报告</h3>
          <p class="mt-2 text-sm text-slate-500">把当前自主进化总览快照导出到 reports 仓库，便于后续回看和企业定制沉淀。</p>
          <button
            @click="exportReportToGit"
            class="mt-4 rounded-lg border border-slate-300 px-4 py-2 text-slate-700 hover:bg-slate-50"
            :disabled="exportingReport"
          >
            {{ exportingReport ? '导出中...' : '导出成长总览' }}
          </button>
          <p v-if="reportResult" class="mt-3 text-sm" :class="reportSuccess ? 'text-green-600' : 'text-rose-600'">
            {{ reportResult }}
          </p>
        </div>
    </div>

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
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import WorkspaceSubNav, { type WorkspaceSubNavItem } from '../components/shell/WorkspaceSubNav.vue'
import {
  exportGitKnowledgeIndexTemplate,
  getGitProviderStatus,
  scanTenantGitKnowledge,
  type GitKnowledgeRepoIndexSummary,
  type KnowledgeContainer,
} from '../api/git'
import { getTenantKnowledgePolicy, type TenantKnowledgePolicy } from '../api/plugins'
import {
  exportTenantExperiences,
  exportTenantReport,
  getKnowledgeSkillDetail,
  getKnowledgeSkills,
  syncLocalSkills,
  type KnowledgeSkill,
  type KnowledgeSkillsPayload,
} from '../api/knowledge'

type KnowledgeSection = 'overview' | 'index' | 'skills' | 'export'

const route = useRoute()
const router = useRouter()
const activeSection = ref<KnowledgeSection>('overview')

const tenantId = ref(localStorage.getItem('tenant_id') || 'default')
const skills = ref<KnowledgeSkill[]>([])
const stats = ref({ total: 0, draft: 0, verified: 0 })
const loading = ref(false)
const syncing = ref(false)
const exportingExperiences = ref(false)
const exportingReport = ref(false)
const syncResult = ref('')
const syncSuccess = ref(false)
const experienceResult = ref('')
const experienceSuccess = ref(false)
const reportResult = ref('')
const reportSuccess = ref(false)
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
const scanning = ref(false)
const exportingIndex = ref(false)
const indexResult = ref('')
const indexSuccess = ref(false)
const repoIndexSummary = ref<GitKnowledgeRepoIndexSummary | null>(null)

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
    skills: { title: '技能目录', description: '本地技能、自治产出与信任级别；可查看单条技能详情。' },
    export: { title: '同步与导出', description: '推送技能到 Git、导出经验摘要与成长报告。' },
  }
  return map[activeSection.value]
})

const subNavItems = computed<WorkspaceSubNavItem[]>(() => ([
  { key: 'overview', title: '总览', badge: String(stats.value.total), active: activeSection.value === 'overview' },
  { key: 'index', title: '索引', badge: String(repoIndexSummary.value?.total_entries ?? 0), active: activeSection.value === 'index' },
  { key: 'skills', title: '技能', badge: String(stats.value.verified), active: activeSection.value === 'skills' },
  { key: 'export', title: '导出', active: activeSection.value === 'export' },
]))

const normalizeSection = (value: unknown): KnowledgeSection => {
  const section = String(value || '').trim()
  if (section === 'index' || section === 'skills' || section === 'export') return section
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
    const [response, providerStatus, policyResponse] = await Promise.all([
      getKnowledgeSkills(currentTenantId),
      getGitProviderStatus(currentTenantId),
      getTenantKnowledgePolicy(currentTenantId),
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

const scanKnowledgeIndex = async () => {
  scanning.value = true
  indexResult.value = ''
  try {
    const res = await scanTenantGitKnowledge(tenantId.value || 'default')
    repoIndexSummary.value = res.data?.repo_index_summary || null
    indexResult.value = res.success
      ? `${res.message || '扫描完成'}，已索引 ${res.data?.repo_index_summary?.indexed_repo_count || 0} 个仓库`
      : res.message || '扫描失败'
    indexSuccess.value = res.success
    await loadSkills()
  } catch (error) {
    console.error('Failed to scan knowledge index:', error)
    indexResult.value = '知识索引扫描失败'
    indexSuccess.value = false
  }
  scanning.value = false
}

const exportIndexTemplate = async () => {
  exportingIndex.value = true
  indexResult.value = ''
  try {
    const res = await exportGitKnowledgeIndexTemplate(tenantId.value || 'default', {
      scan_after_write: true,
    })
    repoIndexSummary.value = res.data?.repo_index_summary || null
    indexResult.value = res.success
      ? `${res.message || '导出完成'}：${res.data?.file_path || ''}`
      : res.message || '导出失败'
    indexSuccess.value = res.success
  } catch (error) {
    console.error('Failed to export knowledge index template:', error)
    indexResult.value = '索引模板导出失败'
    indexSuccess.value = false
  }
  exportingIndex.value = false
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

const syncSkills = async () => {
  syncing.value = true
  syncResult.value = ''
  try {
    const res = await syncLocalSkills(tenantId.value || 'default')
    syncResult.value = res.success
      ? `${res.message}，成功同步 ${res.data?.count || 0} 个技能`
      : res.message || '同步失败'
    syncSuccess.value = res.success
    await loadSkills()
  } catch {
    syncResult.value = '❌ 同步失败'
    syncSuccess.value = false
  }
  syncing.value = false
}

const exportExperiencesToGit = async () => {
  exportingExperiences.value = true
  experienceResult.value = ''
  try {
    const res = await exportTenantExperiences(tenantId.value || 'default')
    experienceResult.value = res.success
      ? `${res.message}：${res.data?.file_path || ''} / 子女 ${res.data?.journal_summary?.member_count || 0} / 卡片 ${res.data?.journal_summary?.card_total || 0}`
      : res.message || '经验导出失败'
    experienceSuccess.value = res.success
  } catch {
    experienceResult.value = '经验导出失败'
    experienceSuccess.value = false
  }
  exportingExperiences.value = false
}

const exportReportToGit = async () => {
  exportingReport.value = true
  reportResult.value = ''
  try {
    const res = await exportTenantReport(tenantId.value || 'default')
    reportResult.value = res.success
      ? `${res.message}：${res.data?.file_path || ''}`
      : res.message || '成长总览导出失败'
    reportSuccess.value = res.success
  } catch {
    reportResult.value = '成长总览导出失败'
    reportSuccess.value = false
  }
  exportingReport.value = false
}

onMounted(loadSkills)
</script>
