<script setup lang="ts">
import { computed, onMounted } from 'vue'
import OceanBackground from './components/OceanBackground.vue'
import LoginView from './views/LoginView.vue'
import ChatView from './views/ChatView.vue'
import { useAuth } from './composables/useAuth'

// user 是模块级共享状态：LoginView 登录成功后这里会自动变成用户名
const { user, fetchMe, logout } = useAuth()

const isLogin = computed(() => user.value !== null)
const username = computed(() => user.value ?? '')

// 刷新页面时问后端：Session Cookie 还有效就自动恢复登录
onMounted(() => {
  fetchMe()
})
</script>

<template>

  <OceanBackground src="/4611886.mp4" :brightness="0.78" />
  <LoginView v-if="!isLogin" />
  <ChatView v-else :username="username" @logout="logout" />

</template>

<style scoped></style>
