import type { ChildMemberRuntimeProfile } from '../api/plugins'
import type { WorkTypeItem } from '../api/workTypes'
import { resolveMemberWorkTypeId } from './formalTaskRecommendation'
import { formatTaskStatusLabel } from './workTypeDashboard'
import type { WorkNode } from './workNodes'

export type CompanyTreeKind = 'overview' | 'department' | 'work_type' | 'member' | 'function' | 'link' | 'hint'

export type CompanyTreeNode = {
  id: string
  kind: CompanyTreeKind
  label: string
  subtitle?: string
  badge?: string
  department_id?: string
  work_type_id?: string
  member_id?: string
  href?: string
  children?: CompanyTreeNode[]
}

const DEPARTMENT_ORDER = ['operations', 'rnd', 'quality', 'unassigned'] as const
const DEPARTMENT_LABELS: Record<string, string> = {
  operations: '运营',
  rnd: '研发',
  quality: '质量',
  unassigned: '未分组',
}

const TRAINER_PORTRAIT_PATH = '/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary'
const TRAINER_DISPATCH_PATH = '/organization/trainer/talent_development_officer/workspace?mode=dispatch&dispatchTab=assign'

const activeMembers = (members: ChildMemberRuntimeProfile[]) => (
  members.filter((item) => (
    String(item.status || 'active') !== 'archived'
    && String(item.primary_role || '') !== 'talent_development'
  ))
)

export function isMemberWorkTypeBound(member: ChildMemberRuntimeProfile, workTypes: WorkTypeItem[]): boolean {
  const workTypeId = resolveMemberWorkTypeId(member)
  if (!workTypeId || workTypeId === 'pending_role') return false
  const boundIds = new Set(workTypes.map((item) => String(item.work_type_id || '').trim()))
  return boundIds.has(workTypeId)
}

export function listUnboundMembers(
  members: ChildMemberRuntimeProfile[],
  workTypes: WorkTypeItem[],
): ChildMemberRuntimeProfile[] {
  const roster = activeMembers(members)
  return roster.filter((member) => !isMemberWorkTypeBound(member, workTypes))
}

const memberBadge = (
  member: ChildMemberRuntimeProfile,
  tasks: { member_id?: string | null; status?: string }[],
  workNodes: WorkNode[] = [],
) => {
  const memberId = String(member.member_id || '').trim()
  const node = workNodes.find((item) => (
    item.member_id === memberId
    && ['running', 'submitted'].includes(item.status)
  ))
  if (node) return node.status === 'submitted' ? '待确认' : node.status_label
  const open = tasks.find((item) => (
    String(item.member_id || '').trim() === memberId
    && !['approved', 'archived'].includes(String(item.status || '').trim())
  ))
  if (!open) return undefined
  return formatTaskStatusLabel(open.status)
}

const workTypeNodeBadge = (workTypeId: string, workNodes: WorkNode[], memberCount: number) => {
  const nodes = workNodes.filter((item) => item.work_type_id === workTypeId)
  const submitted = nodes.filter((item) => item.status === 'submitted').length
  const running = nodes.filter((item) => item.status === 'running').length
  if (submitted) return `${submitted} 待确认`
  if (running) return `${running} 进行中`
  if (memberCount) return `${memberCount} 人`
  return undefined
}

export function buildCompanyTree(input: {
  workTypes: WorkTypeItem[]
  members: ChildMemberRuntimeProfile[]
  tasks?: { member_id?: string | null; status?: string; title?: string | null }[]
  workNodes?: WorkNode[]
  parentLabel?: string
}): CompanyTreeNode[] {
  const { workTypes, members, tasks = [], workNodes = [], parentLabel = '公司' } = input
  const roster = activeMembers(members)
  const unboundCount = listUnboundMembers(members, workTypes).length

  const workTypeNodes: CompanyTreeNode[] = workTypes.map((workType) => {
    const workTypeId = String(workType.work_type_id || '').trim()
    const deptId = String(workType.department_id || 'unassigned').trim() || 'unassigned'
    const matched = roster.filter((member) => resolveMemberWorkTypeId(member) === workTypeId)

    return {
      id: `work_type:${workTypeId}`,
      kind: 'work_type',
      label: String(workType.title || workTypeId),
      subtitle: workType.worker_id ? `执行器 ${workType.worker_id}` : '人工协作岗',
      badge: workTypeNodeBadge(workTypeId, workNodes, matched.length) || (matched.length ? `${matched.length} 人` : undefined),
      department_id: deptId,
      work_type_id: workTypeId,
      children: matched.map((member) => {
        const memberId = String(member.member_id || '').trim()
        return {
          id: `member:${memberId}`,
          kind: 'member',
          label: String(member.name || member.identity?.name || memberId),
          subtitle: String(member.content_profile?.content_direction || workType.title || '').trim() || undefined,
          badge: memberBadge(member, tasks, workNodes),
          department_id: deptId,
          work_type_id: workTypeId,
          member_id: memberId,
        } satisfies CompanyTreeNode
      }),
    }
  })

  const grouped = new Map<string, CompanyTreeNode[]>()
  for (const node of workTypeNodes) {
    const deptId = node.department_id || 'unassigned'
    if (!grouped.has(deptId)) grouped.set(deptId, [])
    grouped.get(deptId)?.push(node)
  }

  const departmentNodes: CompanyTreeNode[] = DEPARTMENT_ORDER
    .filter((deptId) => grouped.has(deptId))
    .map((deptId) => ({
      id: `department:${deptId}`,
      kind: 'department',
      label: DEPARTMENT_LABELS[deptId] || deptId,
      department_id: deptId,
      children: grouped.get(deptId) || [],
    }))

  const businessDepartmentChildren: CompanyTreeNode[] = workTypes.length
    ? departmentNodes
    : [{
        id: 'hint:no-work-types',
        kind: 'hint',
        label: '尚未配置工种',
        subtitle: '先去公司设置添加工种',
        href: '/organization/parent/workspace?section=worktypes',
      }]

  const trainerChildren: CompanyTreeNode[] = [
    {
      id: 'function:trainer-portrait',
      kind: 'link',
      label: '建档与画像',
      subtitle: '新建员工、确认岗位',
      href: TRAINER_PORTRAIT_PATH,
    },
    {
      id: 'function:trainer-dispatch',
      kind: 'link',
      label: '派任务与复盘',
      subtitle: '分配正式任务、确认提交',
      href: TRAINER_DISPATCH_PATH,
    },
    {
      id: 'function:trainer-tools',
      kind: 'link',
      label: '支撑工具',
      href: '/organization/trainer/talent_development_officer/tools',
    },
  ]

  return [
    {
      id: 'overview',
      kind: 'overview',
      label: '公司总览',
      subtitle: parentLabel,
    },
    {
      id: 'departments',
      kind: 'department',
      label: '业务部门',
      subtitle: '按工种组织的岗位员工',
      children: businessDepartmentChildren,
    },
    {
      id: 'functions',
      kind: 'function',
      label: '职能',
      subtitle: '带教、财务与公司工具',
      badge: unboundCount ? `${unboundCount} 待绑岗` : undefined,
      children: [
        {
          id: 'function:trainer',
          kind: 'link',
          label: '育成师',
          subtitle: '供给环 · 建档带教复盘',
          badge: unboundCount ? `${unboundCount}` : undefined,
          href: TRAINER_PORTRAIT_PATH,
          children: trainerChildren,
        },
        {
          id: 'function:intake',
          kind: 'link',
          label: '接单台',
          subtitle: '消费环 · 接入分派结算',
          href: '/organization/intake',
        },
        {
          id: 'function:finance',
          kind: 'link',
          label: '财务',
          subtitle: '收支与经营决策',
          href: '/organization/finance',
        },
      ],
    },
    {
      id: 'intelligence',
      kind: 'function',
      label: '成长与知识',
      subtitle: '供给沉淀 · 复盘知识队列',
      children: [
        {
          id: 'function:knowledge',
          kind: 'link',
          label: '知识库',
          href: '/organization/knowledge',
        },
        {
          id: 'function:evolution',
          kind: 'link',
          label: '成长控制台',
          href: '/organization/evolution',
        },
        {
          id: 'function:tasks',
          kind: 'link',
          label: '任务队列',
          href: '/organization/tasks',
        },
        {
          id: 'function:missions',
          kind: 'link',
          label: 'Mission 运行',
          href: '/organization/missions',
        },
      ],
    },
    {
      id: 'settings',
      kind: 'link',
      label: '公司设置',
      subtitle: '工种目录与执行器',
      href: '/organization/parent/workspace?section=worktypes',
    },
  ]
}

export function findCompanyTreeNode(nodes: CompanyTreeNode[], id: string): CompanyTreeNode | null {
  for (const node of nodes) {
    if (node.id === id) return node
    if (node.children?.length) {
      const found = findCompanyTreeNode(node.children, id)
      if (found) return found
    }
  }
  return null
}

export function companyTreeBreadcrumb(nodes: CompanyTreeNode[], selectionId: string): CompanyTreeNode[] {
  const trail: CompanyTreeNode[] = []
  const walk = (items: CompanyTreeNode[], stack: CompanyTreeNode[]): boolean => {
    for (const item of items) {
      const next = [...stack, item]
      if (item.id === selectionId) {
        trail.push(...next)
        return true
      }
      if (item.children?.length && walk(item.children, next)) return true
    }
    return false
  }
  walk(nodes, [])
  return trail
}
