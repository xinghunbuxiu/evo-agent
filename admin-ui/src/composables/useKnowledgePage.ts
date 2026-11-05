import { computed, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
  getKnowledgeShards,
  syncLocalSkills,
  type KnowledgeSkill,
  type KnowledgeSkillsPayload,
  type KnowledgeShardInventory,
} from '../api/knowledge'

import {
  exportGitKnowledgeIndexTemplate,
  getGitProviderStatus,
  scanTenantGitKnowledge,
  type GitKnowledgeRepoIndexSummary,
  type KnowledgeContainer,
} from '../api/git'
import {
  exportTenantExperiences,
  exportTenantReport,
  getKnowledgeSkillDetail,
  getKnowledgeSkills,
  getKnowledgeShards,
  syncLocalSkills,
  type KnowledgeSkill,
  type KnowledgeSkillsPayload,
  type KnowledgeShardInventory,
} from '../api/knowledge'


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
const shardInventory = ref<KnowledgeShardInventory | null>(null)
const shardActiveCount = computed(() => Object.values(shardInventory.value?.domains || {}).reduce((sum, item) => sum + item.active, 0))
const shardSealedCount = computed(() => Object.values(shardInventory.value?.domains || {}).reduce((sum, item) => sum + item.sealed, 0))
const shardProvisioningCount = computed(() => Object.values(shardInventory.value?.domains || {}).reduce((sum, item) => sum + item.provisioning, 0))

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

export function useKnowledgePage() {
  return {
    activeSection,
    tenantId,
    skills,
    stats,
    loading,
    syncing,
    exportingExperiences,
    exportingReport,
    syncResult,
    syncSuccess,
    experienceResult,
    experienceSuccess,
    reportResult,
    reportSuccess,
    pageMessage,
    pageSuccess,
    selectedSkill,
    knowledgeRepo,
    repoFullName,
    bootstrappedAt,
    gitReady,
    knowledgeContainers,
    knowledgePolicy,
    knowledgeLayerAdvice,
    autonomySkillSummary,
    recentAutonomySkills,
    scanning,
    exportingIndex,
    indexResult,
    indexSuccess,
    repoIndexSummary,
    shardInventory,
    shardActiveCount,
    shardSealedCount,
    shardProvisioningCount,
    privateContainerCount,
    projectContainerCount,
    sharedContainerCount,
    shareModeLabel,
    platformPromotionLabel,
    sectionMeta,
    subNavItems,
    normalizeSection,
    onSectionSelect,
    refreshSection,
    loadSkills,
    scanKnowledgeIndex,
    exportIndexTemplate,
    viewSkill,
    syncSkills,
    exportExperiencesToGit,
    exportReportToGit,
  }
}
