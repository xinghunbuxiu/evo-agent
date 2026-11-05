import { computed, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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

type KnowledgeSection = 'overview' | 'index' | 'shards' | 'skills' | 'export'

export function useKnowledgePage() {
const {
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
exportReportToGit
} = useKnowledgePage()

  return {

  }
}
