<template>
  <AppShell v-if="!isLoginPage">
    <router-view />
  </AppShell>
  <router-view v-else />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from './components/shell/AppShell.vue'

const route = useRoute()
const isLoginPage = computed(() => route.path === '/login' || route.path === '/register')
</script>
