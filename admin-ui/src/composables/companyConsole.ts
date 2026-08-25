import type { InjectionKey, Ref } from 'vue'
import type { AutonomyStatus } from '../api/plugins'
import type { FinanceOverview } from '../api/finance'
import type { WorkTypeItem } from '../api/workTypes'
import type { CompanyTreeNode } from '../utils/companyTree'
import type { WorkNode } from '../utils/workNodes'

export type CompanyConsoleContext = {
  loading: Ref<boolean>
  overviewError: Ref<string>
  tenantId: Ref<string>
  autonomyStatus: Ref<AutonomyStatus | null>
  workTypes: Ref<WorkTypeItem[]>
  companyTree: Ref<CompanyTreeNode[]>
  workNodes: Ref<WorkNode[]>
  financeOverview: Ref<FinanceOverview | null>
  selectionId: Ref<string>
  refreshOverview: () => Promise<void>
  selectTreeNode: (node: CompanyTreeNode) => void
}

export const companyConsoleKey: InjectionKey<CompanyConsoleContext> = Symbol('companyConsole')
