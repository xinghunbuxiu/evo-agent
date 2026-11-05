<template>
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

    <div v-if="selectedSkill" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div class="max-h-[80vh] w-full max-w-lg overflow-auto rounded-lg bg-white p-6">
        <h2 class="mb-4 text-xl font-bold">技能详情</h2>
        <pre class="overflow-auto rounded-lg bg-gray-50 p-4 text-sm">{{ JSON.stringify(selectedSkill, null, 2) }}</pre>
        <div class="mt-4 flex justify-end">
          <button
            @click="selectedSkill = null"
            class="rounded-lg bg-gray-200 px-4 py-2 text-gray-700 hover:bg-gray-300"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import StatusBadge from './StatusBadge.vue'
import { getKnowledgeSkillDetail, type KnowledgeSkill } from '../api/knowledge'

const props = defineProps<{
  tenantId: string
  skills: KnowledgeSkill[]
  loading: boolean
}>()

const selectedSkill = ref<KnowledgeSkill | null>(null)

const viewSkill = async (skill: KnowledgeSkill) => {
  try {
    const response = await getKnowledgeSkillDetail(
      props.tenantId || 'default',
      skill.domain || 'unknown',
      skill.name
    )
    selectedSkill.value = response.success && response.data ? response.data : skill
  } catch {
    selectedSkill.value = skill
  }
}
</script>
