<script setup lang="ts">
import { onMounted, ref } from 'vue'
import OceanBackground from './components/OceanBackground.vue'
import LoginView from './views/LoginView.vue'
import ChatView from './views/ChatView.vue'

const isLogin = ref(false)
const username = ref('')

onMounted(() => {
  const saved = localStorage.getItem('user')
  if (saved) {
    username.value = saved
    isLogin.value = true
  }
})

const handleLogin = (name:string) => {
  username.value = name
  isLogin.value = true
  localStorage.setItem('user', name)
}

const handleLogout = () => {
  localStorage.removeItem('user')
  username.value = ''
  isLogin.value = false
}
</script>

<template>

  <OceanBackground src="/4611886.mp4" :brightness="0.78" />
  <LoginView v-if="!isLogin" @login="handleLogin" />
  <ChatView v-else :username="username" @logout="handleLogout" />

</template>

<style scoped></style>
