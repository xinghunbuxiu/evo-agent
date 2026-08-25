import { get, put } from './request'
import type { WorkerManifest } from './plugins'

export type WorkTypeRuntimeRoute = {
  work_type_id?: string
  capability_type?: string | null
  mission_kind?: string | null
  workers?: Array<{
    worker_id?: string
    title?: string
    enabled?: boolean
    capability_type?: string | null
    task_types?: string[]
  }>
  project_packages?: Array<{
    package_id?: string
    adapter?: string
    capability_type?: string
    enabled?: boolean
  }>
}

export type WorkTypeItem = {
  work_type_id: string
  title?: string
  status?: string
  department_id?: string
  department_label?: string
  capability_type?: string
  mission_kind?: string
  worker_id?: string
  finance_project_id?: string
  enabled?: boolean
  goal_schema?: {
    default_goal?: string
    deliverables?: string[]
  }
  input_schema?: {
    required?: string[]
    optional?: string[]
  }
  closure_loop?: {
    label?: string
    channel?: string
    steps?: string[]
  }
  enabled_packages?: string[]
  runtime_route?: WorkTypeRuntimeRoute
}

export type WorkTypesPayload = {
  version?: number
  items: WorkTypeItem[]
  runtime_index?: Record<string, unknown>
}

export const RESERVED_WORK_TYPE_IDS = new Set([
  'talent_development',
  'talent_development_officer',
  'finance',
])

const DEPARTMENT_LABELS: Record<string, string> = {
  operations: '运营',
  rnd: '研发',
  quality: '质量',
  unassigned: '未分组',
}

export function getWorkTypes() {
  return get<WorkTypesPayload>('/api/work-types')
}

export function saveWorkTypes(payload: WorkTypesPayload) {
  return put<WorkTypesPayload>('/api/work-types', payload)
}

export function resolveDepartmentLabel(departmentId?: string | null): string | undefined {
  const normalized = String(departmentId || '').trim()
  if (!normalized) return undefined
  return DEPARTMENT_LABELS[normalized] || normalized
}

export function buildWorkTypeFromWorker(manifest: WorkerManifest, overrides: Partial<WorkTypeItem> = {}): WorkTypeItem {
  const workerId = String(manifest.worker_id || '').trim()
  const suggestedId = String(manifest.work_type_ids?.[0] || workerId).trim() || workerId
  const capabilityType = String(manifest.capability_type || '').trim()
  const missionKind = capabilityType === 'javascript_reverse'
    ? 'javascript_reverse'
    : capabilityType === 'automation'
      ? 'automation_operation'
      : ''
  return {
    work_type_id: suggestedId,
    title: String(manifest.title || suggestedId),
    status: 'active',
    capability_type: capabilityType,
    mission_kind: missionKind,
    worker_id: workerId,
    finance_project_id: suggestedId,
    enabled: true,
    goal_schema: {
      default_goal: '',
      deliverables: [],
    },
    input_schema: {
      required: [],
      optional: [],
    },
    enabled_packages: [],
    ...overrides,
  }
}

export function buildAuxiliaryWorkType(input: {
  work_type_id: string
  title: string
  department_id?: string
  default_goal?: string
  deliverables?: string[]
}): WorkTypeItem {
  const departmentId = String(input.department_id || 'quality').trim() || 'quality'
  return {
    work_type_id: input.work_type_id,
    title: input.title,
    status: 'active',
    department_id: departmentId,
    department_label: resolveDepartmentLabel(departmentId),
    capability_type: 'coordination',
    mission_kind: '',
    finance_project_id: input.work_type_id,
    enabled: true,
    goal_schema: {
      default_goal: input.default_goal || `围绕「${input.title}」岗位目标完成协作、审核或验证。`,
      deliverables: input.deliverables || [],
    },
    input_schema: {
      required: [],
      optional: ['related_task_id', 'review_scope'],
    },
    enabled_packages: [],
  }
}

export type WorkTypePreset = Partial<WorkTypeItem> & {
  preset_key: string
  preset_label: string
  requires_worker?: boolean
}

/** 示例工种模板（按执行器 worker_id 匹配，非业务硬编码） */
export const WORK_TYPE_EXAMPLE_PRESETS: WorkTypePreset[] = [
  {
    preset_key: 'toutiao_ops_example',
    preset_label: '头条运营示例',
    worker_id: 'self_media_operations',
    work_type_id: 'self_media_operations',
    title: '头条运营',
    department_id: 'operations',
    department_label: '运营',
    finance_project_id: 'self_media_operations',
    goal_schema: {
      default_goal: '以头条号为核心渠道，稳定产出内容、回收阅读与收益数据，并形成可复用的运营经验。',
      deliverables: [
        '账号登录与环境验证通过',
        '阅读/互动/收益数据落盘财务',
        '至少一条可发布草稿',
        '育成师复盘确认',
      ],
    },
    requires_worker: true,
  },
]

/** 辅助工种：无需自动化执行器，由育成师按需创建 */
export const AUXILIARY_WORK_TYPE_PRESETS: WorkTypePreset[] = [
  {
    preset_key: 'quality_reviewer',
    preset_label: '审核员',
    work_type_id: 'quality_reviewer',
    title: '审核员',
    department_id: 'quality',
    goal_schema: {
      default_goal: '在育成师忙碌时承接任务审核、质量把关与反馈汇总。',
      deliverables: ['完成指定任务的审核结论', '输出可执行的修改建议'],
    },
    requires_worker: false,
  },
  {
    preset_key: 'qa_tester',
    preset_label: '测试员',
    work_type_id: 'qa_tester',
    title: '测试员',
    department_id: 'quality',
    goal_schema: {
      default_goal: '验证任务交付是否达到验收标准，并记录缺陷与回归建议。',
      deliverables: ['测试用例或检查清单', '缺陷与回归结论'],
    },
    requires_worker: false,
  },
]

export function findWorkTypeExamplePreset(workerId: string): WorkTypePreset | null {
  const normalized = String(workerId || '').trim()
  if (!normalized) return null
  return WORK_TYPE_EXAMPLE_PRESETS.find((item) => String(item.worker_id || '').trim() === normalized) || null
}
