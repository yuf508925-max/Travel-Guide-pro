<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import OceanBackground from './components/OceanBackground.vue'
import LoginView from './views/LoginView.vue'
import ChatView from './views/ChatView.vue'
import AdminView from './views/AdminView.vue'
import { useAuth } from './composables/useAuth'

// user / role 是模块级共享状态：LoginView 登录成功后这里会自动变成用户名
const { user, role, fetchMe, logout } = useAuth()

const isLogin = computed(() => user.value !== null)
const username = computed(() => user.value ?? '')

// 管理员进的是纯后台（没有聊天界面），普通用户才是聊天页
const isAdmin = computed(() => role.value === 'admin')

// 页面访问打点：每次打开/刷新记一次（后台统计用，失败无所谓）
function reportVisit() {
  fetch('/api/visit', { method: 'POST', credentials: 'include' }).catch(() => {})
}

// 刷新页面时问后端：Session Cookie 还有效就自动恢复登录
onMounted(() => {
  fetchMe()
  reportVisit()
})

// 管理员登录后也补一次访问记录（登录前那次是匿名的）
watch(role, (value) => {
  if (value === 'admin') reportVisit()
})
</script>

<template>

  <OceanBackground src="/4611886.mp4" :brightness="0.78" />
  <LoginView v-if="!isLogin" />
  <AdminView v-else-if="isAdmin" :username="username" @logout="logout" />
  <ChatView v-else :username="username" @logout="logout" />

</template>

<style scoped></style>
